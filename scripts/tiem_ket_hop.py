"""Thử ba cấu hình tiêm trong MỘT cuộc gọi - đếm tiếng bíp là biết cái nào ăn.

Vì sao ghép: đo được cả hai nửa nhưng chưa bao giờ bật cùng lúc.

  nửa 1  `ABOX UAIF0 SPK = SIFS0`     đưa tiếng phát tới CODEC qua UAIF0
  nửa 2  `AIF1TX1 Input 2 = AIF1RX1`  trộn tiếng đó vào đường lên của codec

Lần thử `tiem_rx2tx` chỉ đặt nửa 1 (kèm NSRC1=SIFS0), lần `do_duong_len` chỉ đặt
nửa 2. Chuỗi chỉ thông khi có đủ hai: tiếng phải tới được codec thì AIF1RX1 mới
có gì để trộn vào AIF1TX1, mà AIF1TX1 chính là dây mic đi lên modem.

Mỗi cấu hình phát một số tiếng bíp khác nhau nên chỉ cần nghe rồi đếm:

    cấu hình 1 -> 1 tiếng bíp
    cấu hình 2 -> 2 tiếng bíp
    cấu hình 3 -> 3 tiếng bíp

    python scripts/tiem_ket_hop.py 0396130621
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

SERIAL = "21f10e44220c7ece"
MIXCTL = "/data/local/tmp/mixctl"

# Mỗi cấu hình là danh sách (control, giá trị). Chạy xong lại trả về như cũ.
CAU_HINH = [
    ("1. UAIF0<-SIFS0  +  AIF1TX1 Input 2", [
        ("ABOX UAIF0 SPK", "SIFS0"),
        ("AIF1TX1 Input 2", "AIF1RX1"),
    ]),
    ("2. thêm AIF1TX2 (kênh phải)", [
        ("ABOX UAIF0 SPK", "SIFS0"),
        ("AIF1TX1 Input 2", "AIF1RX1"),
        ("AIF1TX2 Input 2", "AIF1RX1"),
    ]),
    ("3. trộn sớm hơn, ở ASRC1IN1L", [
        ("ABOX UAIF0 SPK", "SIFS0"),
        ("ASRC1IN1L Input 2", "AIF1RX1"),
        ("AIF1TX1 Input 2", "AIF1RX1"),
    ]),
]

# Trả về sau khi thử: đường lên phải quay lại lấy mic, không thì cuộc gọi sau hỏng.
TRA_VE = [
    ("AIF1TX1 Input 2", "None"),
    ("AIF1TX2 Input 2", "None"),
    ("ASRC1IN1L Input 2", "None"),
    ("ABOX UAIF0 SPK", "RESERVED"),
]


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def mix_set(ten: str, gt: str) -> None:
    sh(f"""su -c '{MIXCTL} set "{ten}" {gt}'""")


def mix_get(ten: str) -> str:
    ra = sh(f"""su -c '{MIXCTL} get "{ten}"'""")
    m = re.search(r"= \d+ \((.*)\)", ra)
    return m.group(1) if m else "?"


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def bip(so_tieng: int, rate: int = 24000) -> bytes:
    """Chuỗi `so_tieng` tiếng bíp 0.35s, cách nhau 0.25s im lặng."""
    mau = bytearray()
    for _ in range(so_tieng):
        for i in range(int(0.35 * rate)):
            mau += struct.pack("<h", int(13000 * math.sin(2 * math.pi * 900 * i / rate)))
        mau += b"\x00\x00" * int(0.25 * rate)
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(bytes(mau))
    return buf.getvalue()


async def chay(a) -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge

    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=3)
    print(f"[1] {msg}")
    if not ok:
        return 1
    bridge = PhoneCallBridge(None, CallSession(customer_name="Khách"), port=8123)
    bridge.tam_dung_nghe = True
    await bridge.start()

    try:
        print(f"\n[2] Gọi {a.so} ... HÃY BẮT MÁY rồi ĐẾM SỐ TIẾNG BÍP nghe được")
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
        await asyncio.sleep(1.5)

        for so, (ten, dat) in enumerate(CAU_HINH, start=1):
            if trang_thai() != 1:
                print("    cuộc gọi kết thúc giữa chừng")
                break
            # Xoá cấu hình trước rồi mới đặt cấu hình này, không thì các đường
            # chồng lên nhau và không biết cái nào ăn.
            for c, _ in TRA_VE:
                mix_set(c, dict(TRA_VE)[c])
            for c, v in dat:
                mix_set(c, v)
            doc = {c: mix_get(c) for c, _ in dat}
            print(f"\n    --- {ten}  ->  {so} tiếng bíp")
            for c, v in doc.items():
                print(f"        {c:<20} = {v}")
            await bridge.play(bip(so))
            await asyncio.sleep(so * 0.6 + 3.0)

        print("\n    Xong ba cấu hình. Nghe được MẤY tiếng bíp?")
        print("    (1 / 2 / 3 tiếng = cấu hình đó ăn; không nghe gì = cả ba đều hỏng)")
        for _ in range(max(0, a.giay // 5)):
            if trang_thai() != 1:
                break
            await asyncio.sleep(5)
    finally:
        print("\n[3] Trả tuyến cũ ...")
        for c, v in TRA_VE:
            mix_set(c, v)
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--giay", type=int, default=10)
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
