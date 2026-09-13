"""Replay three real audio excerpts through the RUNNING STT/LLM/TTS backend.

Creates a clearly named test session, does not dial or delete any history.
This verifies the audio WebSocket path, not the phone transport/VAD itself.
"""
import asyncio
import base64
import json
from pathlib import Path
import sys
import time

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]


async def main():
    sys.stdout.reconfigure(encoding="utf-8")
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        health = (await client.get("http://127.0.0.1:8100/api/health")).json()
        assert health["services"]["stt_engine"] == "gipformer", health
        assert health["services"]["tts"] == "loaded", health
        calls = (await client.get("http://127.0.0.1:8100/api/devices/voice/status")).json()
        assert not calls.get("calls"), "Active phone call; stop replay"
        rows = []
        async with websockets.connect(f"ws://127.0.0.1:8100/ws/call/gip-smoke-{time.time_ns()}",
                max_size=16*1024*1024, open_timeout=15) as ws:
            connected = json.loads(await asyncio.wait_for(ws.recv(), 15))
            print("CONNECTED", json.dumps(connected, ensure_ascii=False), flush=True)
            await ws.send(json.dumps({"type": "set_session", "customer_name": "TEST Gipformer audio - khong goi",
                                      "product": "vay tín chấp"}))
            updated = json.loads(await asyncio.wait_for(ws.recv(), 15))
            assert updated["type"] == "session_updated", updated
            session_id = updated["session"]["session_id"]
            for index, (sample_id, keyword) in enumerate([
                ("d9b57f0b_03", "khoản vay"), ("d9b57f0b_07", "bốn trăm triệu"),
                ("d9b57f0b_08", "thủ tục")], 1):
                data = (ROOT / "logs/asr_eval_20260912/samples" / f"{sample_id}.wav").read_bytes()
                await ws.send(json.dumps({"type": "audio", "turn_id": index,
                                          "data": base64.b64encode(data).decode()}))
                transcript, audio_events, event_types, errors = "", 0, [], []
                while True:
                    event = json.loads(await asyncio.wait_for(ws.recv(), 45))
                    kind = event.get("type")
                    event_types.append(kind)
                    if kind == "transcript":
                        transcript = event.get("text", "")
                    if kind in ("audio", "audio_chunk"):
                        audio_events += 1
                    if kind == "error":
                        errors.append(event)
                    if kind == "turn_complete":
                        row = {"sample_id": sample_id, "transcript": transcript,
                               "response": event.get("full_response", ""), "audio_events": audio_events,
                               "event_types": event_types, "metrics": event.get("metrics"), "errors": errors}
                        rows.append(row)
                        print("TURN", json.dumps(row, ensure_ascii=False), flush=True)
                        assert not errors and keyword in transcript
                        assert row["response"] and audio_events > 0, "Missing spoken response"
                        if keyword == "thủ tục":
                            assert row["metrics"].get("tra_tu_quy_tac_tai_chinh") == "ho_so_can_thiet", \
                                "Procedure question answered as loan amount instead"
                        break
        saved = (await client.get(f"http://127.0.0.1:8100/api/sessions/{session_id}")).json()
        history = saved["session"]["history"]
        assert sum(x["role"] == "user" for x in history) == 3
        out = ROOT / "logs/asr_eval_20260912/results" / f"gipformer_ws_{session_id}.json"
        out.write_text(json.dumps({"session_id": session_id, "health": health, "turns": rows,
            "history_items": len(history), "scope": "audio WS, not real phone transport"},
            ensure_ascii=False, indent=2), "utf-8")
        print("PASS running backend audio WS / transcript / spoken audio / history", session_id, out)


if __name__ == "__main__":
    asyncio.run(main())
