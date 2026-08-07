"""Quét mức đệm mồi để tìm chỗ AudioTrack hết đói dữ liệu.

Đo được với đệm 60ms: lúc rảnh 0 lần/giây, lúc phát 20913 lần/giây - đói gần như
liên tục, và người nghe báo tiếng "dè". Lịch gửi tự sửa nên tốc độ trung bình
đúng, nhưng đồng hồ Windows bước ~15,6ms nên khung tới theo cụm giật cục và đệm
60ms cạn giữa hai cụm.

Đệm dày thì hết đói NHƯNG cắt lời chậm đi đúng bằng chừng đó: thứ đã rời hàng
đợi của PC thì không thu hồi được. Nên chọn mức NHỎ NHẤT mà đã sạch, không phải
mức lớn nhất.

Không cần cuộc gọi - chạy ở chế độ micro.

    python scripts/quet_dem_mo.py
    python scripts/quet_dem_mo.py --muc 60 150 250 400
"""

import argparse
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


def tone(giay: float, rate: int = 24000) -> bytes:
    n = int(giay * rate)
    mau = b"".join(struct.pack("<h", int(11000 * math.sin(2 * math.pi * 440 * i / rate)))
                   for i in range(n))
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(mau)
    return buf.getvalue()


async def chay(a) -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge

    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=1)
    print(f"[1] {msg}\n")
    if not ok:
        return 1

    print(f"    {'đệm mồi':>10}{'thiếu tiếng':>14}{'nhịp':>12}")
    ket = []
    for ms in a.muc:
        bridge = PhoneCallBridge(None, CallSession(customer_name="K"), port=8123)
        bridge.dem_mo_s = ms / 1000.0
        bridge.tam_dung_nghe = True
        await bridge.start()
        try:
            await asyncio.sleep(1.0)
            truoc = thieu_tieng()
            t0 = time.perf_counter()
            await bridge.play(tone(6.0))
            con = 6.5 - (time.perf_counter() - t0)
            if con > 0:
                await asyncio.sleep(con)
            that = time.perf_counter() - t0
            them = thieu_tieng() - truoc
            nhip = them / max(that, 1e-6)
            ket.append((ms, them, nhip))
            print(f"    {ms:>8}ms{them:>14}{nhip:>10.0f}/s")
        finally:
            await bridge.stop()
        await asyncio.sleep(1.0)

    print("\n" + "=" * 56)
    sach = [(ms, n) for ms, _, n in ket if n < 50]
    if sach:
        ms, n = min(sach, key=lambda x: x[0])
        print(f"NÊN DÙNG {ms}ms - mức nhỏ nhất đã sạch ({n:.0f} lần/giây).")
        print("Nhỏ nhất chứ không phải lớn nhất: đệm dày làm cắt lời chậm đi")
        print("đúng bằng chừng đó, vì tiếng đã rời hàng đợi thì không thu hồi được.")
    else:
        print("KHÔNG MỨC NÀO SẠCH. Nút thắt không nằm ở đệm mồi -")
        print("phải nới đệm AudioTrack trong app cầu nối, hoặc gửi khung to hơn.")
    print("=" * 56)

    await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--muc", type=int, nargs="+", default=[60, 150, 250, 400, 600])
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
