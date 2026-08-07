"""Đo tốc độ đường tiếng QUA ĐÚNG ĐƯỜNG SẢN PHẨM (PhoneCallBridge).

Khác `do_toc_duong_truyen.py`: script kia nối thẳng vào socket nên đo được dung
lượng đệm của máy, nhưng KHÔNG phản ánh hành vi thật - đường thật đi qua
`_write_loop`, nó bám nhịp 20ms/khung và chỉ giữ trước 60ms.

Ở đây dựng đúng PhoneCallBridge, đưa tiếng vào bằng `play()` như pipeline làm,
rồi đo bốn mốc:

    pipeline giao tiếng
      |-- t1: khung ĐẦU rời khỏi server        <- phần code này chịu trách nhiệm
      |-- t2: khung CUỐI rời khỏi server       <- cho biết có bám nhịp không
      |-- t3: micro nghe lại (nếu loa mở)      <- trọn vòng khách cảm nhận
    và: bao nhiêu tiếng còn nằm chờ khi cắt lời

    python scripts/do_toc_that.py
"""

import asyncio
import math
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

RATE, FRAME_MS = 8000, 20
FRAME_SAMPLES = RATE * FRAME_MS // 1000


def tao_wav_bip(ms: int, freq: float = 1000.0, amp: int = 14000) -> bytes:
    """WAV 8kHz chứa tiếng bíp — giả làm đầu ra của TTS để đưa vào play()."""
    import io
    import wave
    n = RATE * ms // 1000
    ph, step = 0.0, 2 * math.pi * freq / RATE
    b = bytearray()
    for _ in range(n):
        b += int(amp * math.sin(ph)).to_bytes(2, "little", signed=True)
        ph += step
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(b))
    return buf.getvalue()


async def main() -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.services.phone_call_service import PhoneCallBridge

    print("Nối cầu tiếng qua PhoneCallBridge (đúng đường sản phẩm) ...")
    bridge = PhoneCallBridge(pipeline=None, session=CallSession(), port=8123)
    await bridge.start()
    print("  đã nối\n")

    # đếm khung rời khỏi server bằng cách bám vào writer
    goc_write = bridge.writer.write
    moc = []

    def dem(b):
        moc.append(time.perf_counter())
        return goc_write(b)

    bridge.writer.write = dem

    try:
        for ms in (300, 1000, 3000):
            moc.clear()
            wav = tao_wav_bip(ms)
            t0 = time.perf_counter()
            await bridge.play(wav)          # pipeline giao tiếng ở đây
            t_xep = (time.perf_counter() - t0) * 1000

            # chờ khung cuối rời server
            can = ms // FRAME_MS
            han = time.perf_counter() + ms / 1000 + 3
            while len(moc) < can and time.perf_counter() < han:
                await asyncio.sleep(0.02)

            if not moc:
                print(f"  {ms:>5}ms tiếng: KHÔNG có khung nào rời server")
                continue
            t1 = (moc[0] - t0) * 1000
            t2 = (moc[-1] - t0) * 1000
            print(f"  {ms:>5}ms tiếng | xếp hàng {t_xep:5.1f}ms"
                  f" | khung đầu ra {t1:6.1f}ms | khung cuối ra {t2:7.1f}ms"
                  f" | {len(moc)}/{can} khung")
            if t2 > ms * 0.8:
                print(f"          -> bám nhịp thời gian thực (tốt: cắt lời sẽ ăn)")
            else:
                print(f"          -> XẢ NHANH: {ms - t2:.0f}ms tiếng nằm sẵn trong máy,"
                      f" cắt lời sẽ không kịp")
            await asyncio.sleep(0.8)

        # Cắt lời: còn bao nhiêu tiếng chưa rời server?
        print("\nCẮT LỜI: bao nhiêu tiếng lấy lại được?")
        moc.clear()
        wav = tao_wav_bip(3000)
        await bridge.play(wav)
        await asyncio.sleep(0.3)            # để nó chạy 300ms
        con = bridge._out.qsize()
        da_ra = len(moc)
        bo = bridge.drop_pending_audio()
        print(f"  sau 300ms: {da_ra} khung đã rời server"
              f" ({da_ra*FRAME_MS}ms), {con} khung còn trong hàng đợi")
        print(f"  cắt lời lấy lại được {bo} khung = {bo*FRAME_MS}ms tiếng")
        print(f"  KHÔNG lấy lại được {da_ra*FRAME_MS}ms đã rời server"
              f" (nằm trong đệm máy, khách vẫn nghe)")
    finally:
        bridge.writer.write = goc_write
        await bridge.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
