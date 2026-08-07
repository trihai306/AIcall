"""Tiếng AI có THẬT SỰ lên được đường lên của cuộc gọi không?

Đây là phép đo tự kiểm chứng, không cần tai người: thu bằng nguồn VOICE_UPLINK
(2) - tức đúng dòng tiếng đang gửi cho đầu bên kia - rồi phát một tiếng bíp và
xem nó có xuất hiện trong đó không.

Vì sao cần: đường tiêm cũ đặt `AIF1TX1 Input 2 = AIF1RX1` mà đầu bên kia không
nghe gì. Đọc /vendor/etc/mixer_paths.xml thì thấy đường lên đúng là

    IN3L (mic) -> LHPF1 -> ASRC1IN1L -> AIF1TX1 -> UAIF0 -> ABOX NSRC1 -> modem

nên AIF1TX1 là chỗ đúng. Nghi vấn còn lại là AIF1RX1 lúc đang gọi mang gì: nếu
nó chỉ mang tiếng ĐẦU BÊN KIA (đường xuống) chứ không mang tiếng AudioTrack của
ta thì tiêm vào đó chỉ vọng lại tiếng người ta, còn tiếng AI không lên.

Script thử lần lượt vài điểm tiêm, mỗi điểm phát một tiếng bíp rồi chấm điểm
theo tỉ lệ năng lượng đúng tần số. Điểm nào ăn thì dùng điểm đó.

    python scripts/do_duong_len.py 0396130621
"""

import argparse
import asyncio
import math
import re
import struct
import subprocess
import sys
import time
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
MIXCTL = "/data/local/tmp/mixctl"
TAN = 900.0
RATE_LEN = 8000

# Các điểm tiêm để thử, theo thứ tự từ gần đường lên nhất ra xa.
# Tên control lấy từ chính mixer_paths.xml của máy.
UNG_VIEN = [
    ("(không tiêm - nền)", None, None),
    ("AIF1TX1 Input 2", "AIF1TX1 Input 2", "AIF1RX1"),
    ("AIF1TX1 Input 2 <- RX2", "AIF1TX1 Input 2", "AIF1RX2"),
    ("ASRC1IN1L Input 2", "ASRC1IN1L Input 2", "AIF1RX1"),
    ("LHPF1 Input 2", "LHPF1 Input 2", "AIF1RX1"),
    ("AIF1TX1 Input 1 (đè mic)", "AIF1TX1 Input 1", "AIF1RX1"),
]


def sh(cmd: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def dat(ten: str, gt: str) -> str:
    ra = sh(f"""su -c '{MIXCTL} set "{ten}" {gt}'""")
    d = ra.strip().splitlines()
    return d[-1] if d else "(im lặng)"


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def tao_tone(giay: float, rate: int = 24000, bien: int = 12000) -> bytes:
    n = int(giay * rate)
    mau = b"".join(struct.pack("<h", int(bien * math.sin(2 * math.pi * TAN * i / rate)))
                   for i in range(n))
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(mau)
    return buf.getvalue()


def cham(khung: list[bytes]) -> tuple[float, float]:
    """Trả (tỉ lệ năng lượng ở 900Hz, RMS). Ghép hết khung rồi phân tích một lần."""
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
    quanh = float(spec[max(0, k - 2):k + 3].sum())
    return quanh / tong, rms


async def chay(a) -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge

    # nguồn 2 = VOICE_UPLINK: đúng dòng tiếng đang gửi cho đầu bên kia
    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=2)
    print(f"[1] {msg}")
    if not ok:
        return 1

    bridge = PhoneCallBridge(None, CallSession(customer_name="Khách"), port=8123)
    bridge.tam_dung_nghe = True
    thu: list[bytes] = []
    bridge.theo_doi_khung = thu.append
    await bridge.start()

    da_dat: list[str] = []
    try:
        print(f"\n[2] Gọi {a.so} ... HÃY BẮT MÁY rồi IM LẶNG cho tới khi xong")
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

        print(f"\n[3] Thử từng điểm tiêm, mỗi điểm 1.5s bíp {TAN:.0f}Hz")
        print(f"    {'điểm tiêm':<28}{'900Hz':>8}{'RMS':>9}   kết luận")
        ket_qua = []
        for ten, ctl, gt in UNG_VIEN:
            if trang_thai() != 1:
                print("    cuộc gọi rớt giữa chừng")
                break
            if ctl:
                dat(ctl, gt)
                da_dat.append(ctl)
            await asyncio.sleep(0.4)
            thu.clear()
            await bridge.play(tao_tone(1.5))
            await asyncio.sleep(2.6)          # 1.5s tiếng + đệm đường truyền
            ti, rms = cham(list(thu))
            ket_qua.append((ten, ti, rms))
            xet = "CÓ LÊN SÓNG" if ti >= 0.25 and rms > 200 else ""
            print(f"    {ten:<28}{ti*100:>7.1f}%{rms:>9.0f}   {xet}")
            if ctl:
                dat(ctl, "None")
                da_dat.remove(ctl)

        print("\n" + "=" * 62)
        nen = next((t for n, t, _ in ket_qua if n.startswith("(không")), 0.0)
        an = [(n, t) for n, t, r in ket_qua
              if not n.startswith("(không") and t >= 0.25 and t > nen * 2 and r > 200]
        if an:
            print("ĐIỂM TIÊM ĂN:")
            for n, t in sorted(an, key=lambda x: -x[1]):
                print(f"    {n}   ({t*100:.1f}% năng lượng đúng tần số)")
        else:
            print("KHÔNG ĐIỂM NÀO ĐƯA ĐƯỢC TIẾNG LÊN SÓNG.")
            print("Nghĩa là tiếng AudioTrack không tới được AIF1RX1 lúc đang gọi -")
            print("phải tìm cách đưa tiếng vào bộ trộn của ABOX, không phải codec.")
        print("=" * 62)
    finally:
        for c in da_dat:
            dat(c, "None")
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
