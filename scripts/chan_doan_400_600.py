"""Read-only call diagnosis: recorded audio replay + stale-principal reproduction.

No dial, service restart, config change, or history rewrite. Model outputs are
not a human-verified transcript. Offline excerpts are not production VAD replay.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
from pathlib import Path
import sys
import time

import httpx
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from do_asr_call_that import customer_channel, excerpts, sha256
from backend.pipeline.tra_loi_khoan_vay import (
    _so_tien_nhu_cau, _so_thang_gan_nhat, _tien_gan_nhat, tra_loi,
)
from backend.services.stt_service import STTService


def save(path: Path, data: object) -> None:
    with path.open("x", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def wav_bytes(audio: np.ndarray, sr: int) -> bytes:
    out = io.BytesIO()
    sf.write(out, audio, sr, format="WAV", subtype="PCM_16")
    return out.getvalue()


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", default="4e277738")
    ap.add_argument("--expect-legacy-bug", action="store_true",
                    help="Assert the old failure only when checking a pre-fix checkout")
    args = ap.parse_args()
    out = ROOT / "logs" / f"diagnose_{args.session}_{time.time_ns()}"
    service = STTService()
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        async def idle() -> None:
            response = await client.get("http://127.0.0.1:8100/api/devices/voice/status")
            response.raise_for_status()
            state = response.json()
            if "calls" not in state or state["calls"]:
                raise RuntimeError("Active or unknown call state; do not compete with live calls")

        async def get(url: str) -> dict:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

        await idle()
        session = (await get(f"http://127.0.0.1:8100/api/sessions/{args.session}"))["session"]
        if session.get("status") != "ended":
            raise RuntimeError("Only completed calls can be diagnosed")
        source = Path(session["recording_path"])
        before_hash = sha256(source)
        stereo, sr = sf.read(source, dtype="float32", always_2d=True)
        customer = customer_channel(stereo)
        spans, segmentation = excerpts(customer, sr)
        out.mkdir(parents=True, exist_ok=False)
        save(out / "session.json", session)
        save(out / "backend_log.json", await get(
            "http://127.0.0.1:8100/api/logs?ten=backend&so_dong=2000"))
        sf.write(out / "customer_full.wav", customer, sr, subtype="PCM_16")
        doc_path = ROOT / "knowledge/products/vay_tin_chap.md"
        doc = doc_path.read_text(encoding="utf-8")
        history = session["history"]
        prior: list[dict] = []
        parsing = []
        for index, entry in enumerate(history):
            prior.append(entry)
            if entry["role"] != "user":
                continue
            text = entry["content"]
            answer = tra_loi(text, doc, history=prior)
            actual = history[index + 1]["content"] if index + 1 < len(history) else None
            row = {"turn": len(parsing) + 1, "stt_text": text,
                   "current_principal": _so_tien_nhu_cau(text),
                   "selected_principal": _tien_gan_nhat(text, prior),
                   "selected_term": _so_thang_gan_nhat(text, prior),
                   "reproduced_rule": answer, "recorded_answer": actual,
                   "rule_matches_recorded_answer": bool(answer and answer[1] == actual)}
            parsing.append(row)
            print("PARSE", json.dumps(row, ensure_ascii=False), flush=True)

        # These assertions confirm the existing failure, not a successful fix.
        old_context = history[:5]
        contrasts = []
        for text in (
            "thế thì cho anh vay bốn trăm trong vòng mười hai tháng thì mỗi tháng đóng bao nhiêu",
            "thế thì cho anh vay bốn trăm trong mười hai tháng thì mỗi tháng đóng bao nhiêu",
            "anh anh muốn vay bốn trăm",
            "anh anh muốn vay bốn trăm triệu",
        ):
            row = {"text": text, "current_principal": _so_tien_nhu_cau(text),
                   "selected_principal": _tien_gan_nhat(text, old_context)}
            contrasts.append(row)
            print("CONTRAST", json.dumps(row, ensure_ascii=False), flush=True)
        stale_principal_reproduced = (
            [r["selected_principal"] for r in contrasts] == [600e6, 400e6, 600e6, 400e6]
            and parsing[2]["rule_matches_recorded_answer"]
            and parsing[3]["rule_matches_recorded_answer"])
        print("LEGACY_STALE_PRINCIPAL_REPRODUCED", stale_principal_reproduced, flush=True)
        if args.expect_legacy_bug:
            assert stale_principal_reproduced, "This checkout no longer reproduces the old bug"

        rows = []
        try:
            if service.engine != "gipformer" or not await service.health_check():
                raise RuntimeError("The active configured engine is not healthy Gipformer")
            model_info = await service.model_info()
            pho_info = await get(service.base_url + "/health")
            for index, (a, b) in enumerate(spans, 1):
                await idle()
                audio = customer[a:b]
                wav = wav_bytes(audio, sr)
                clip_name = f"clip_{index:02d}_customer.wav"
                sf.write(out / clip_name, audio, sr, subtype="PCM_16")
                started = time.perf_counter()
                text = await service.transcribe(wav, sample_rate=sr)
                row = {"clip": clip_name, "start_s": round(a / sr, 3),
                       "end_s": round(b / sr, 3), "gipformer": text,
                       "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                       "human_verified": False}
                if "trăm" in text:
                    # Same raw clip through another ASR; no outside audio service.
                    response = await client.post(service.base_url + "/inference",
                        files={"file": (clip_name, wav, "audio/wav")},
                        data={"language": "vi", "response_format": "verbose_json",
                              "temperature": "0", "prompt": ""})
                    response.raise_for_status()
                    row["phowhisper_no_prompt"] = response.json().get("text", "")
                    row["gipformer_repeat"] = await service.transcribe(wav, sample_rate=sr)
                    aa, bb = max(0, a - sr // 2), min(len(customer), b + sr // 2)
                    row["gipformer_extra_context_500ms"] = await service.transcribe(
                        wav_bytes(customer[aa:bb], sr), sample_rate=sr)
                    stereo_name = f"clip_{index:02d}_both_sides.wav"
                    sf.write(out / stereo_name,
                             stereo[a:min(len(stereo), b + 9 * sr)], sr, subtype="PCM_16")
                    row["customer_then_reply_clip"] = stereo_name
                rows.append(row)
                print("AUDIO", json.dumps(row, ensure_ascii=False), flush=True)
            await idle()
            if sha256(source) != before_hash:
                raise RuntimeError("Original recording changed during diagnosis")
            report = {"session_id": args.session, "recording": str(source),
                      "recording_sha256": before_hash, "sample_rate": sr,
                      "duration_s": len(customer) / sr, "model": model_info,
                      "comparison_model": pho_info, "segmentation": segmentation,
                      "reference_status": "No human-verified audio transcript; WER/CER not scored",
                      "source_hashes": {str(p.relative_to(ROOT)): sha256(p) for p in (
                          ROOT / "backend/services/gipformer_stt.py",
                          ROOT / "backend/pipeline/tra_loi_khoan_vay.py", doc_path)},
                      "parsing": parsing, "contrasts": contrasts, "audio": rows,
                      "known_stale_principal_reproduced": stale_principal_reproduced,
                      "production_modified": False}
            save(out / "diagnosis.json", report)
            print("REPORT", out, flush=True)
        finally:
            await service.close()


if __name__ == "__main__":
    asyncio.run(main())
