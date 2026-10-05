"""Probe actual Qwen/RAG and situation filler on the Windows backend."""

import asyncio
import json
import sys

from benchmark_shinhan_fast_ws import run_audio_one, run_one


async def main():
    questions = [
        "Đăng ký thẻ điện tử Shinhan trên SOL cần làm những bước nào và mã SMS dùng ở đâu?",
        "Thẻ điện tử Shinhan có khác thẻ vật lý và có mất phí không?",
    ]
    rows = [await run_one(question) for question in questions]
    voice = [await run_audio_one(questions[0]) for _ in range(3)]
    print(json.dumps({"text_samples": rows, "voice_samples": voice}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
