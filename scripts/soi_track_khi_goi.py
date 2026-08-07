"""Lúc đang có cuộc gọi, tiếng AudioTrack của cầu nối đi đâu?

Phép đo trước dùng nguồn VOICE_UPLINK để xem tiếng có lên sóng không, nhưng
chính nó trả về gần như im lặng ở MỌI hàng - kể cả hàng nền đáng lẽ có tiếng
micro. Thước hỏng thì số đo vô nghĩa, nên không kết luận gì từ đó.

Script này hỏi thẳng AudioFlinger: track của app cầu nối có đang chạy không,
nằm ở luồng ra nào, âm lượng bao nhiêu, có bị tắt tiếng vì đang trong cuộc gọi
không. Đồng thời thu bằng micro để xem loa thoại có thật sự kêu.

    python scripts/soi_track_khi_goi.py 0396130621
"""

import argparse
import asyncio
import math
import re
import struct
import subprocess
import sys
import wave
from io import BytesIO
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

SERIAL = "21f10e44220c7ece"
TAN = 900.0
RATE_LEN = 8000


def sh(cmd: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def tao_tone(giay: float, rate: int = 24000, bien: int = 14000) -> bytes:
    n = int(giay * rate)
    mau = b"".join(struct.pack("<h", int(bien * math.sin(2 * math.pi * TAN * i / rate)))
                   for i in range(n))
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(mau)
    return buf.getvalue()


def cham(khung: list[bytes]) -> tuple[float, float]:
    if not khung:
        return 0.0, 0.0
    x = np.frombuffer(b"".join(khung), dtype=np.int16).astype(np.float32) / 32768.0
    if x.size < 256:
        return 0.0, 0.0
    rms = float(np.sqrt(np.mean(x ** 2))) * 32768.0
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size))) ** 2
    tong = float(spec.sum())
    if tong <= 0:
        return 0.0, rms
    k = int(round(TAN * x.size / RATE_LEN))
    return float(spec[max(0, k - 2):k + 3].sum()) / tong, rms


def in_track(nhan: str):
    """In phần Tracks của mọi luồng ra trong AudioFlinger."""
    d = sh("dumpsys media.audio_flinger")
    print(f"\n--- Tracks trong AudioFlinger ({nhan})")
    giu, dem = False, 0
    for dong in d.splitlines():
        s = dong.rstrip()
        if re.search(r"^\s*(Output thread|Input thread)", s):
            giu = False
            print(f"    {s.strip()[:150]}")
        if "Tracks:" in s or re.search(r"^\s*Name\s+Active", s):
            giu, dem = True, 0
            print(f"    {s.strip()[:150]}")
            continue
        if giu:
            if not s.strip() or dem > 12:
                giu = False
                continue
            dem += 1
            print(f"      {s.strip()[:150]}")


async def chay(a) -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge

    # nguồn 1 = MIC: micro của máy sẽ nghe được loa thoại rò ra nếu AudioTrack
    # thật sự kêu. Đây là bằng chứng độc lập với mọi tuyến trộn.
    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=1)
    print(f"[1] {msg}")
    if not ok:
        return 1

    bridge = PhoneCallBridge(None, CallSession(customer_name="Khách"), port=8123)
    bridge.tam_dung_nghe = True
    thu: list[bytes] = []
    bridge.theo_doi_khung = thu.append
    await bridge.start()

    try:
        print("\n[2] Chưa gọi: phát bíp, micro có nghe thấy không?")
        thu.clear()
        await bridge.play(tao_tone(1.5))
        await asyncio.sleep(2.5)
        ti0, rms0 = cham(list(thu))
        print(f"    ngoài cuộc gọi: 900Hz {ti0*100:.1f}%   RMS {rms0:.0f}")
        in_track("ngoài cuộc gọi")

        print(f"\n[3] Gọi {a.so} ... HÃY BẮT MÁY rồi IM LẶNG")
        sh("input keyevent KEYCODE_WAKEUP")
        sh(f"am start -a android.intent.action.CALL -d tel:{a.so}")
        for i in range(45):
            await asyncio.sleep(1)
            if trang_thai() == 1:
                print(f"    {i}s: ĐÃ NỐI MÁY")
                break
        else:
            print("    không ai bắt máy")
            return 1
        await asyncio.sleep(1.0)

        print("\n[4] Trong cuộc gọi: phát bíp, micro có nghe thấy không?")
        thu.clear()
        await bridge.play(tao_tone(2.0))
        await asyncio.sleep(1.0)
        in_track("đang gọi, đang phát")
        await asyncio.sleep(2.0)
        ti1, rms1 = cham(list(thu))
        print(f"\n    trong cuộc gọi: 900Hz {ti1*100:.1f}%   RMS {rms1:.0f}")

        print("\n[5] Chế độ âm thanh và âm lượng luồng thoại:")
        au = sh("dumpsys audio")
        for dong in au.splitlines():
            s = dong.strip()
            if re.search(r"^- mode|STREAM_VOICE_CALL|Muted|mute", s, re.I) and len(s) < 160:
                print(f"    {s}")

        print("\n" + "=" * 62)
        if rms0 > 200 and rms1 < rms0 * 0.2:
            print("KẾT LUẬN: AudioTrack BỊ TẮT TIẾNG khi vào cuộc gọi.")
            print("Sửa ở phía app cầu nối (kiểu luồng / usage), không phải ở mixer.")
        elif rms1 > 200 and ti1 > 0.2:
            print("KẾT LUẬN: AudioTrack VẪN KÊU trong cuộc gọi.")
            print("Vậy tiếng có ra codec; việc còn lại là nối nó vào đường lên.")
        else:
            print("KẾT LUẬN: chưa rõ - cả hai lần đều yếu, xem lại số ở trên.")
        print("=" * 62)
    finally:
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
