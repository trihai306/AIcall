"""Verify general number corrections against the running Windows backend.

Creates labelled TEST sessions; never dials or changes existing call histories.
Includes one previously recorded customer-channel excerpt. ASR output is not
human ground truth, and this is not a phone transport/end-to-ear latency test.
"""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
import sys
import time

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    reports = []
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        async def get(path):
            response = await client.get("http://127.0.0.1:8100" + path)
            response.raise_for_status()
            return response.json()

        async def idle():
            status = await get("/api/devices/voice/status")
            assert "calls" in status and not status["calls"], status

        await idle()
        health = await get("/api/health")
        assert health["system"]["platform"] == "Windows", health
        assert health["system"]["device"] == "cuda", health
        assert health["services"]["stt_engine"] == "gipformer", health
        assert health["services"]["tts"] == "loaded", health

        for amount in (135, 275, 425, 725, None):
            await idle()
            rows = []
            async with websockets.connect(
                f"ws://127.0.0.1:8100/ws/call/facts-test-{time.time_ns()}",
                max_size=16 * 1024 * 1024, open_timeout=15,
            ) as ws:
                await asyncio.wait_for(ws.recv(), 15)
                await ws.send(json.dumps({"type": "set_session",
                    "customer_name": "TEST du kien vay - khong goi dien",
                    "product": "vay tín chấp"}, ensure_ascii=False))
                updated = json.loads(await asyncio.wait_for(ws.recv(), 15))
                assert updated["type"] == "session_updated", updated
                session_id = updated["session"]["session_id"]

                async def turn(text, expected, field=None, value=None, audio=None):
                    await idle()
                    message = {"type": "text_soi", "text": text, "turn_id": len(rows) + 1}
                    if audio is not None:
                        message = {"type": "audio", "turn_id": len(rows) + 1,
                                   "data": base64.b64encode(audio).decode()}
                    await ws.send(json.dumps(message, ensure_ascii=False))
                    errors, audio_events, transcript = [], 0, ""
                    deadline = time.monotonic() + 60
                    while True:
                        event = json.loads(await asyncio.wait_for(ws.recv(),
                            max(0.01, deadline - time.monotonic())))
                        kind = event.get("type")
                        if kind == "transcript":
                            transcript = event.get("text", "")
                        elif kind in ("audio", "audio_chunk"):
                            audio_events += 1
                        elif kind == "error":
                            errors.append(event)
                        elif kind == "turn_complete":
                            metrics = event.get("metrics", {})
                            row = {"input": text, "transcript": transcript,
                                   "response": event.get("full_response", ""),
                                   "metrics": metrics, "audio_events": audio_events,
                                   "errors": errors}
                            rows.append(row)
                            print("TURN", session_id, json.dumps(row, ensure_ascii=False), flush=True)
                            assert not errors and row["response"], row
                            assert metrics.get("tra_tu_quy_tac_tai_chinh") == expected, row
                            if field:
                                fact = metrics["du_kien_vay"][field]
                                assert fact["value"] == value, row
                                if value is None:
                                    assert fact["status"] in ("ambiguous", "missing_unit", "cancelled"), row
                            if audio is not None:
                                assert audio_events > 0, row
                            return row

                await turn("anh vay 850 triệu trong 36 tháng", "vuot_han_muc", "amount", "850000000")
                if amount is None:
                    sample = ROOT / "logs/asr_eval_20260912/samples/d9b57f0b_07.wav"
                    row = await turn(str(sample), "nhu_cau_vay", "amount", "400000000",
                                     audio=sample.read_bytes())
                    assert "bốn trăm triệu" in row["transcript"], row
                    assert "850" not in row["response"], row
                else:
                    row = await turn(f"{amount} trong 24 tháng mỗi tháng đóng bao nhiêu",
                                     "xac_nhan_don_vi_vay", "amount", None)
                    assert "850" not in row["response"], row
                    row = await turn("triệu đồng", "tinh_tra_gop" if amount <= 500 else "vuot_han_muc",
                                     "amount", str(amount * 1000000))
                    assert "850" not in row["response"], row
                    await turn("nhắc lại số tiền và kỳ hạn hiện tại", "nhac_lai_nhu_cau",
                               "amount", str(amount * 1000000))
                    row = await turn("nhắc lại số tiền và kỳ hạn anh nói lúc đầu", "nhac_lai_nhu_cau",
                                     "amount", str(amount * 1000000))
                    assert "850 triệu" in row["response"] and "36 tháng" in row["response"], row
                    await turn("đổi kỳ hạn sang số khác", "xac_nhan_ky_han_vay", "term", None)
                    await turn("mỗi tháng đóng bao nhiêu", "xac_nhan_ky_han_vay", "term", None)

            for _ in range(10):
                saved = (await get(f"/api/sessions/{session_id}"))["session"]
                history = saved["history"]
                if sum(x["role"] == "user" for x in history) == len(rows):
                    break
                await asyncio.sleep(0.2)
            assert sum(x["role"] == "user" for x in history) == len(rows), saved
            assert sum(x["role"] == "assistant" for x in history) == len(rows), saved
            reports.append({"session_id": session_id, "turns": rows, "history_items": len(history)})

        out = ROOT / "logs" / f"loan_facts_ws_{time.time_ns()}.json"
        with out.open("x", encoding="utf-8") as report:
            json.dump({"health": health, "sessions": reports,
                       "scope": "text and recorded-audio WS, not live telephone or human ASR scoring"},
                      report, ensure_ascii=False, indent=2)
        print("PASS", len(reports), "sessions", sum(len(r["turns"]) for r in reports), "turns", out)


if __name__ == "__main__":
    asyncio.run(main())
