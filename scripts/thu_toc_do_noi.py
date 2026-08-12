"""Dựng lời chào ở nhiều tốc độ để chọn bằng tai.

Giọng mới nói nhanh hơn giọng cũ ~1.44 lần (cùng câu: 191KB so với 275KB).
`f5tts_speed` chia tỉ lệ thời lượng: nhỏ hơn 1 = nói chậm lại.
"""
import asyncio
import io
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

RA = Path("C:/duan/chat-ai/logs/toc_do")
CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
       "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


async def main():
    from backend.config import settings
    from backend.services.tts_service import F5TTSService

    RA.mkdir(parents=True, exist_ok=True)
    for f in RA.glob("*.wav"):
        f.unlink()

    tts = F5TTSService()
    tts.load()
    await tts.synthesize("khởi động một hai ba", use_cache=False)

    print(f"\n  {'speed':>7}{'thời lượng':>13}{'sinh mất':>11}{'so với 1.0':>13}")
    print("  " + "-" * 46)
    goc = None
    for sp in (1.00, 0.90, 0.82, 0.75):
        settings.f5tts_speed = sp
        t0 = time.perf_counter()
        w = await tts.synthesize(CAU, use_cache=False)
        ms = (time.perf_counter() - t0) * 1000
        with wave.open(io.BytesIO(w)) as f:
            giay = f.getnframes() / f.getframerate()
        if goc is None:
            goc = giay
        (RA / f"speed_{sp:.2f}.wav").write_bytes(w)
        print(f"  {sp:>7.2f}{giay:>11.2f}s{ms:>9.0f}ms{giay/goc:>12.2f}x")

    settings.f5tts_speed = 1.0
    print(f"\n  (giọng CŨ đọc câu này dài ~{goc*1.44:.2f}s để so)")
    print(f"  file: {RA}")


asyncio.run(main())
