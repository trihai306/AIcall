"""AudioTrack trên máy thiếu tiếng bao nhiêu - lúc rảnh và lúc đang phát?

Phép so ba cách xử lý đọc được 49368 lần thiếu tiếng trong một lần phát, nhưng
số nền lúc chưa phát đã là 24200. Một AudioTrack kiểu STREAM đang chạy mà không
có dữ liệu thì cũng đếm thiếu tiếng, nên con số thô không nói lên gì: phải so
NHỊP lúc rảnh với NHỊP lúc phát.

  nhịp lúc phát ~ nhịp lúc rảnh  -> đó chỉ là bộ đếm chạy không, tiếng dè do khác
  nhịp lúc phát >> lúc rảnh      -> nhịp gửi từ PC không kịp, đó là tiếng dè thật

Không cần cuộc gọi: cầu tiếng chạy được ở chế độ micro.

    python scripts/do_thieu_tieng.py
"""

import asyncio
import math
import struct
import subprocess
import sys
import time
import wave
from io import BytesIO
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
SERIAL = "21f10e44220c7ece"


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def thieu_tieng() -> int:
    d = sh("dumpsys media.audio_flinger")
    tong = 0
    for dong in d.splitlines():
        c = dong.split()
        if len(c) >= 16 and c[1] in ("yes", "no") and c[2].isdigit():
            try:
                tong += int(c[-4])
            except (ValueError, IndexError):
                pass
    return tong


def tone(giay: float, rate: int) -> bytes:
    n = int(giay * rate)
    mau = b"".join(struct.pack("<h", int(11000 * math.sin(2 * math.pi * 440 * i / rate)))
                   for i in range(n))
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(mau)
    return buf.getvalue()


async def do_nhip(nhan: str, giay: float, viec=None) -> float:
    a = thieu_tieng()
    t0 = time.perf_counter()
    if viec is not None:
        await viec
    con = giay - (time.perf_counter() - t0)
    if con > 0:
        await asyncio.sleep(con)
    that = time.perf_counter() - t0
    b = thieu_tieng()
    nhip = (b - a) / max(that, 1e-6)
    print(f"    {nhan:<24}{b - a:>8} lần / {that:.1f}s  =  {nhip:>8.0f} lần/giây")
    return nhip


async def chay() -> int:
    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge

    rate = settings.phone_rate_xuong
    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=1)
    print(f"[1] {msg}")
    if not ok:
        return 1
    bridge = PhoneCallBridge(None, CallSession(customer_name="Khách"), port=8123)
    bridge.tam_dung_nghe = True
    await bridge.start()

    try:
        print(f"\n[2] Đo nhịp thiếu tiếng (rate xuống {rate}Hz)")
        await asyncio.sleep(1.0)
        nhan = await do_nhip("lúc rảnh", 6.0)
        khi_phat = await do_nhip("lúc đang phát 6s tiếng", 6.0,
                                 viec=bridge.play(tone(6.0, 24000)))
        await asyncio.sleep(1.5)
        sau = await do_nhip("sau khi phát xong", 6.0)

        print("\n" + "=" * 60)
        if khi_phat > nhan * 2 and khi_phat > 100:
            print("NHỊP GỬI KHÔNG KỊP: thiếu tiếng tăng vọt đúng lúc phát.")
            print("Phải tăng đệm/độ trễ dẫn trước ở _write_loop hoặc nới đệm")
            print("AudioTrack trong app cầu nối.")
        elif nhan > 100:
            print("BỘ ĐẾM CHẠY KHÔNG: thiếu tiếng cao cả lúc rảnh.")
            print(f"lúc rảnh {nhan:.0f}/s so với lúc phát {khi_phat:.0f}/s - không")
            print("chênh mấy, nên tiếng dè KHÔNG do nhịp gửi. Xem lại khâu xử lý.")
        else:
            print("Nhịp thiếu tiếng thấp ở cả hai vế - đường phát sạch.")
        print("=" * 60)
    finally:
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(chay()))
