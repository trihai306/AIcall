"""Tự kiểm chứng: tiếng AI có lên sóng không, không cần tai người.

Trước đây mỗi lần thử một điểm tiêm là tốn một cuộc gọi và phải hỏi người bên
kia có nghe không. Giờ đã biết `ABOX NSRC1` chính là nguồn của đường lên, nên
thu bằng nguồn VOICE_UPLINK (2) là đọc đúng dòng tiếng modem đang gửi đi.

Phép đo chạy hai vế trong cùng một cuộc gọi:
  A. NSRC1 = UAIF0 (mặc định, lấy mic)  -> phát bíp, đo. Đáng lẽ KHÔNG thấy bíp.
  B. NSRC1 = SIFS0 (đường Rx2Tx)        -> phát bíp, đo. Đáng lẽ THẤY rõ bíp.

Có vế A làm nền thì mới phân biệt được "đo thấy vì tiêm ăn" với "đo thấy vì
thước hỏng" - lần đo trước tôi bỏ vế nền nên số 0 ở mọi hàng chẳng nói lên gì.

    python scripts/kiem_len_song.py 0396130621
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
MIXCTL = "/data/local/tmp/mixctl"
TAN = 900.0
RATE_LEN = 8000


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def mix_set(ten: str, gt: str) -> str:
    return sh(f"""su -c '{MIXCTL} set "{ten}" {gt}'""")


def mix_get(ten: str) -> str:
    ra = sh(f"""su -c '{MIXCTL} get "{ten}"'""")
    m = re.search(r"= \d+ \((.*)\)", ra)
    return m.group(1) if m else "?"


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def tao_tone(giay: float, rate: int = 24000) -> bytes:
    n = int(giay * rate)
    mau = b"".join(struct.pack("<h", int(13000 * math.sin(2 * math.pi * TAN * i / rate)))
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
    if x.size < 512:
        return 0.0, 0.0
    rms = float(np.sqrt(np.mean(x ** 2))) * 32768.0
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size))) ** 2
    tong = float(spec.sum())
    if tong <= 0:
        return 0.0, rms
    k = int(round(TAN * x.size / RATE_LEN))
    return float(spec[max(0, k - 2):k + 3].sum()) / tong, rms


async def chay(a) -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge

    # nguồn 2 = VOICE_UPLINK: đúng dòng tiếng modem đang gửi cho đầu bên kia
    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=2)
    print(f"[1] {msg}")
    if not ok:
        return 1
    bridge = PhoneCallBridge(None, CallSession(customer_name="Khách"), port=8123)
    bridge.tam_dung_nghe = True
    thu: list[bytes] = []
    bridge.theo_doi_khung = thu.append
    await bridge.start()

    cu = None
    try:
        print(f"\n[2] Gọi {a.so} ... HÃY BẮT MÁY rồi IM LẶNG")
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
        cu = mix_get("ABOX NSRC1")

        ket = {}
        for nhan, ctl in (("A. mặc định (NSRC1=UAIF0, lấy mic)", "UAIF0"),
                          ("B. Rx2Tx  (NSRC1=SIFS0, lấy tiếng phát)", "SIFS0")):
            if trang_thai() != 1:
                print("    cuộc gọi rớt giữa chừng")
                break
            mix_set("ABOX UAIF0 SPK", "SIFS0")
            mix_set("ABOX NSRC1", ctl)
            mix_set("ABOX SIFM1", "WDMA")
            await asyncio.sleep(0.6)
            thu.clear()
            await bridge.play(tao_tone(2.0))
            await asyncio.sleep(3.2)
            ti, rms = cham(list(thu))
            ket[nhan] = (ti, rms, mix_get("ABOX NSRC1"))
            print(f"\n    {nhan}")
            print(f"       NSRC1 đọc lại = {ket[nhan][2]}")
            print(f"       năng lượng ở {TAN:.0f}Hz: {ti*100:.1f}%    RMS: {rms:.0f}")

        print("\n" + "=" * 64)
        if len(ket) == 2:
            (tiA, rmsA, _), (tiB, rmsB, _) = ket.values()
            if tiB >= 0.25 and rmsB > 200 and tiB > max(tiA * 3, 0.05):
                print("TIẾNG ĐÃ LÊN SÓNG qua đường Rx2Tx.")
                print(f"nền {tiA*100:.1f}% -> tiêm {tiB*100:.1f}%")
            elif rmsA < 50 and rmsB < 50:
                print("THƯỚC HỎNG: VOICE_UPLINK không trả về tiếng ở cả hai vế.")
                print("Không kết luận được gì từ số này - phải nhờ tai người bên kia.")
            else:
                print("TIÊM CHƯA ĂN: đường lên không mang tiếng phát.")
                print(f"nền {tiA*100:.1f}% (RMS {rmsA:.0f}) / tiêm {tiB*100:.1f}% (RMS {rmsB:.0f})")
        else:
            print("Chưa đo đủ hai vế.")
        print("=" * 64)
    finally:
        if cu and cu != "?":
            mix_set("ABOX NSRC1", cu)
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
