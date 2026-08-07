"""Tiêm tiếng AI vào ĐƯỜNG LÊN bằng chính đường Rx2Tx của Samsung.

Vì sao đường cũ sai: AudioFlinger cho thấy track của cầu nối chạy tốt, âm lượng
0 dB, không bị tắt tiếng - nhưng `output devices 1` là LOA THOẠI. Tiếng đi vào
đường XUỐNG (tai mình), chưa bao giờ chạm đường lên. Còn `AIF1TX1 Input 2 =
AIF1RX1` thì vô nghĩa vì lúc gọi bằng loa thoại, ABOX đẩy tiếng ra UAIF1 (mạch
khuếch đại), không qua codec, nên AIF1RX1 rỗng.

Đường đúng nằm sẵn trong /vendor/etc/mixer_paths.xml của máy, tên
`call_forwarding_master-mic`, chú thích là "Rx2Tx" - Samsung dùng nó cho tính
năng chuyển tiếp cuộc gọi, tức là ĐƯA TIẾNG PHÁT RA THÀNH TIẾNG ĐƯỜNG LÊN:

    ABOX UAIF0 SPK = SIFS0
    ABOX NSRC1     = SIFS0     <- nguồn đường lên lấy từ bộ trộn phát, không từ mic
    ABOX SIFM1     = WDMA

Lưu ý: đặt như vậy thì micro của máy KHÔNG còn lên sóng nữa. Với việc này thì
đúng ý - ta chỉ cần AI nói, không cần tiếng phòng.

    python scripts/tiem_rx2tx.py 0396130621
    python scripts/tiem_rx2tx.py 0396130621 --chi-xem    # chỉ đọc, không đổi
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

RX2TX = [
    ("ABOX UAIF0 SPK", "SIFS0"),
    ("ABOX NSRC1", "SIFS0"),
    ("ABOX SIFM1", "WDMA"),
]

LOI_CHAO = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
            "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def mix(lenh: str, ten: str, gt: str = "") -> str:
    # Nháy đơn bọc cả lệnh su, nháy kép bọc tên có dấu cách. Thiếu lớp nào thì
    # shell tách "ABOX NSRC1" thành hai tham số và mixctl báo sai tên.
    cmd = f"""su -c '{MIXCTL} {lenh} "{ten}" {gt}'"""
    ra = sh(cmd)
    return ra.strip()


def doc(ten: str) -> str:
    ra = mix("get", ten)
    m = re.search(r"= \d+ \((.*)\)", ra)
    return m.group(1) if m else ra.splitlines()[-1] if ra else "?"


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def tao_tone(giay: float, tan: float = 900.0, rate: int = 24000) -> bytes:
    n = int(giay * rate)
    mau = b"".join(struct.pack("<h", int(13000 * math.sin(2 * math.pi * tan * i / rate)))
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

    print("[1] Giá trị hợp lệ của các control cần dùng:")
    for ten, _ in RX2TX:
        info = mix("info", ten)
        gt = re.findall(r"^\s*\d+: (.+)$", info, re.M)
        print(f"    {ten:<18} hiện = {doc(ten):<10} chọn được: {', '.join(gt[:12]) or '?'}")
    if a.chi_xem:
        return 0

    tts = None
    if not a.khong_tts:
        from backend.services.tts_service import F5TTSService
        print("\n[2] Nạp TTS ...")
        tts = F5TTSService()
        tts.load()

    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=3)
    print(f"\n[3] {msg}")
    if not ok:
        return 1
    bridge = PhoneCallBridge(None, CallSession(customer_name="Khách"), port=8123)
    bridge.tam_dung_nghe = True
    await bridge.start()

    cu: dict[str, str] = {}
    try:
        print(f"\n[4] Gọi {a.so} ... HÃY BẮT MÁY")
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

        print("\n[5] Tuyến ABOX khi đang gọi, TRƯỚC khi tiêm:")
        for ten, _ in RX2TX:
            cu[ten] = doc(ten)
            print(f"    {ten:<18} = {cu[ten]}")

        print("\n[6] Đặt đường Rx2Tx ...")
        for ten, gt in RX2TX:
            mix("set", ten, gt)
            print(f"    {ten:<18} -> {doc(ten)}")

        print("\n[7] Phát 2 giây bíp 900Hz — NGHE THỬ")
        await bridge.play(tao_tone(2.0))
        await asyncio.sleep(3.5)

        if tts is not None:
            print("[8] Phát lời chào bằng giọng AI — NGHE THỬ")
            wav = await tts.synthesize(LOI_CHAO, use_cache=False)
            await bridge.play(wav)
            await asyncio.sleep(10)

        print(f"\n[9] Giữ máy thêm {a.giay}s, bíp mỗi 5s ...")
        for _ in range(max(0, a.giay // 5)):
            if trang_thai() != 1:
                print("    cuộc gọi đã kết thúc")
                break
            await bridge.play(tao_tone(1.0))
            await asyncio.sleep(5)
    finally:
        print("\n[10] Trả lại tuyến cũ ...")
        for ten, _ in RX2TX:
            if ten in cu and cu[ten] not in ("?", ""):
                mix("set", ten, cu[ten])
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--giay", type=int, default=15)
    ap.add_argument("--chi-xem", action="store_true")
    ap.add_argument("--khong-tts", action="store_true")
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
