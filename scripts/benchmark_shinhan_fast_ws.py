"""Đo thời gian chữ và giọng qua WebSocket thật trên Windows."""

import asyncio
import base64
import io
import json
import statistics
import sys
import time
import wave

import websockets


QUESTIONS = [
    "Thẻ tín dụng Shinhan mới nhận thì kích hoạt như thế nào?",
    "Nếu mất thẻ tín dụng Shinhan, tôi cần khóa thẻ ra sao?",
    "Đăng ký chức năng thẻ điện tử Shinhan trên SOL như thế nào?",
    "Thẻ Shinhan của tôi đã kích hoạt chưa?",
    "Kích hoạt chức năng thẻ điện tử Shinhan sau khi đăng ký thế nào?",
    "Đăng ký và kích hoạt thẻ điện tử Shinhan như thế nào?",
]


async def run_one(question: str) -> dict:
    async with websockets.connect("ws://127.0.0.1:8100/ws/call/new", max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "set_session", "product": "thẻ tín dụng Shinhan"}))
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            if event.get("type") == "session_updated":
                break
        t0 = time.perf_counter()
        await ws.send(json.dumps({"type": "text_soi", "text": question}, ensure_ascii=False))
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            if event.get("type") == "turn_complete":
                return {
                    "question": question,
                    "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "answer": event.get("full_response", ""),
                    "fast_fact": (event.get("metrics") or {}).get("shinhan_fact_nhanh"),
                    "rag_ms": (event.get("metrics") or {}).get("rag_ms"),
                    "rag_sources": (event.get("metrics") or {}).get("rag_nguon"),
                    "llm_ttft_ms": (event.get("metrics") or {}).get("llm_ttft_ms"),
                }


async def run_audio_one(question: str) -> dict:
    async with websockets.connect("ws://127.0.0.1:8100/ws/call/new", max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "set_session", "product": "thẻ tín dụng Shinhan"}))
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            if event.get("type") == "session_updated":
                break
        t0 = time.perf_counter()
        await ws.send(json.dumps({"type": "text", "text": question}, ensure_ascii=False))
        first_audio = None
        first_answer_audio = None
        first_text = None
        last_text = None
        filler_audio_duration_ms = 0.0
        answer_audio_duration_ms = 0.0
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if event.get("type") == "audio" and first_audio is None:
                first_audio = round((time.perf_counter() - t0) * 1000, 1)
            if event.get("type") == "audio":
                with wave.open(io.BytesIO(base64.b64decode(event["data"])), "rb") as wav:
                    duration = wav.getnframes() / wav.getframerate() * 1000
                if event.get("is_filler"):
                    filler_audio_duration_ms += duration
                else:
                    answer_audio_duration_ms += duration
                    if first_answer_audio is None:
                        first_answer_audio = round((time.perf_counter() - t0) * 1000, 1)
            if event.get("type") == "response_chunk":
                now_ms = round((time.perf_counter() - t0) * 1000, 1)
                if first_text is None:
                    first_text = now_ms
                last_text = now_ms
            if event.get("type") == "turn_complete":
                metrics = event.get("metrics") or {}
                return {
                    "question": question,
                    "first_audio_ms": first_audio,
                    "first_text_ms": first_text,
                    "last_text_ms": last_text,
                    "first_answer_audio_ms": first_answer_audio,
                    "turn_complete_ms": round((time.perf_counter() - t0) * 1000, 1),
                    "filler_audio_duration_ms": round(filler_audio_duration_ms),
                    "answer_audio_duration_ms": round(answer_audio_duration_ms),
                    "fast_fact": (event.get("metrics") or {}).get("shinhan_fact_nhanh"),
                    "filler_text": metrics.get("filler_text"),
                    "filler_situation": metrics.get("tinh_huong_id"),
                    "filler_skipped": metrics.get("filler_bo_qua"),
                    "filler_match_score": metrics.get("tinh_huong_diem"),
                    "filler_pick_ms": metrics.get("tinh_huong_chon_ms"),
                    "filler_pick_route": metrics.get("tinh_huong_cach_chon"),
                    "answer_audio_ms": metrics.get("ttfa_ms"),
                    "tts_first_ms": metrics.get("tts_first_ms"),
                    "rag_ms": metrics.get("rag_ms"),
                    "llm_ttft_ms": metrics.get("llm_ttft_ms"),
                    "cached_answer_audio": metrics.get("tieng_san"),
                    "answer": event.get("full_response", ""),
                }


async def main():
    rows = []
    for question in QUESTIONS:
        rows.append(await run_one(question))
    fast_times = [row["wall_ms"] for row in rows if row["fast_fact"]]
    print(json.dumps({
        "samples": rows,
        "fast_median_ms": statistics.median(fast_times),
        "voice_samples": [
            await run_audio_one(question)
            for question in (QUESTIONS[1], QUESTIONS[-1])
            for _ in range(3)
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
