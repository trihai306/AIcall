"""Positive speech controls from local TTS; not a human-voice accuracy score."""
import asyncio
import base64
import io
import json
import time

import httpx
import numpy as np
import soundfile as sf

from kiem_gipformer_tich_hop import ROOT, STTService, wav


async def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    service = STTService()
    rows = []
    out = ROOT / "logs/asr_eval_20260912" / f"short_controls_{time.time_ns()}"
    out.mkdir()
    try:
        assert await service.health_check()
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            for index, phrase in enumerate(["Ừ.", "Vâng.", "Không.", "A lô.",
                                             "Bốn trăm.", "Không vay nữa."]):
                status = await client.get("http://127.0.0.1:8100/api/devices/voice/status")
                status.raise_for_status()
                assert not status.json().get("calls"), "Active call; stop tests"
                response = await client.post("http://127.0.0.1:8100/api/voices/test-tts",
                    data={"text": phrase, "voice_name": "default", "qua_dien_thoai": "true"})
                response.raise_for_status()
                payload = response.json()
                assert "audio" in payload, payload.get("error", "missing audio")
                data = base64.b64decode(payload["audio"])
                (out / f"{index}.wav").write_bytes(data)
                audio, sr = sf.read(io.BytesIO(data), dtype="float32")
                for scale in (1.0, 0.2):
                    text = await service.transcribe(wav(audio * np.float32(scale), sr))
                    row = {"prompt": phrase, "gain": scale, "text": text}
                    rows.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
        (out / "results.json").write_text(json.dumps({"scope": "synthetic local TTS; not human speech",
            "results": rows}, ensure_ascii=False, indent=2), "utf-8")
        assert all(row["text"] for row in rows), "Gate/decoder dropped a positive short-speech control"
        print("PASS 12 positive short-speech controls", out)
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())
