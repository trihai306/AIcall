"""Exercise actual STTService on recorded customer WAVs plus no-speech controls.

Does not dial, alter the DB or change .env. Comparisons with previous model
outputs are consistency checks, NOT WER or human-verified accuracy.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time

import httpx
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["STT_ENGINE"] = "gipformer"
os.environ["GIPFORMER_MODEL_PATH"] = str(ROOT / "models/stt/gipformer1.5-fp32")
from backend.services.stt_service import STTService


def wav(audio, sr=16000):
    output = io.BytesIO()
    sf.write(output, audio, sr, format="WAV", subtype="PCM_16")
    return output.getvalue()


async def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = ROOT / "logs/asr_eval_20260912"
    previous = json.loads((root / "results/gip1.5_fp32_modified_beam_search.json").read_text("utf-8"))
    service = STTService()
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        async def idle():
            response = await client.get("http://127.0.0.1:8100/api/devices/voice/status")
            response.raise_for_status()
            if response.json().get("calls"):
                raise RuntimeError("Active call: stop offline stress tests")
        await idle()
        assert await service.health_check(), "Gipformer did not load"
        rows = []
        try:
            first = root / previous["samples"][0]["path"]
            await service.transcribe(first.read_bytes())
            for sample in previous["samples"]:
                await idle()
                data = (root / sample["path"]).read_bytes()
                assert hashlib.sha256(data).hexdigest() == sample["sha256"]
                t0 = time.perf_counter()
                text = await service.transcribe(data)
                row = {"sample_id": sample["sample_id"], "previous": sample["text"].lower(),
                       "text": text, "elapsed_ms": round((time.perf_counter()-t0)*1000, 2)}
                rows.append(row)
                print("CALL_SAMPLE", json.dumps(row, ensure_ascii=False), flush=True)
            sr = 16000
            rng = np.random.default_rng(20260912)
            controls = {
                "silence1": np.zeros(sr, dtype=np.float32),
                "silence4": np.zeros(sr*4, dtype=np.float32),
                "noise8": (rng.normal(size=sr*3)*8/32768).astype(np.float32),
                "tone450": (np.sin(np.arange(sr*2)*2*np.pi*450/sr)*np.sqrt(2)*1000/32768).astype(np.float32),
            }
            control_results = {}
            for name, audio in controls.items():
                await idle()
                control_results[name] = await service.transcribe(wav(audio))
                print("CONTROL", name, repr(control_results[name]), flush=True)
            # Verify overlapping asynchronous callers cannot mix decoder/VAD state.
            selected = [previous["samples"][2], previous["samples"][6]]
            concurrent = await asyncio.gather(*[
                service.transcribe((root / s["path"]).read_bytes()) for s in selected])
            expected = {r["sample_id"]: r["text"] for r in rows}
            assert concurrent == [expected[s["sample_id"]] for s in selected]
            await idle()
            info = await service.model_info()
            output = root / "results" / f"gipformer_integrated_{time.time_ns()}.json"
            report = {"engine": info, "samples": rows, "controls": control_results,
                      "concurrent_isolation_passed": True,
                      "wer": None, "human_verified_references": 0,
                      "latency_scope": "warm offline STTService incl gate; not phone end-to-end",
                      "empty_samples": [r["sample_id"] for r in rows if not r["text"]],
                      "mean_ms": float(np.mean([r["elapsed_ms"] for r in rows])),
                      "p95_ms": float(np.percentile([r["elapsed_ms"] for r in rows], 95))}
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
            print("REPORT", output, flush=True)
            assert not any(control_results.values()), "No-speech control produced words"
            # Eight key loan questions from the earlier A/B must remain nonempty.
            key_ids = ["d9b57f0b_03", "d9b57f0b_04", "d9b57f0b_05", "d9b57f0b_06",
                       "d9b57f0b_07", "d9b57f0b_08", "bc4d83e7_05", "bc4d83e7_07"]
            assert all(expected[i] for i in key_ids), "Speech gate lost a key loan utterance"
            print("PASS real-model routing, key utterances, silence controls and concurrent isolation")
        finally:
            await service.close()


if __name__ == "__main__":
    asyncio.run(main())
