"""Tìm ĐÚNG chỗ tiêm tiếng vào đường lên của cuộc gọi.

Nền tảng: codec nối với hai bên bằng hai dây khác nhau.
    AIF1  <-> chip ứng dụng (AP)     AIF1RX = AP phát ra, AIF1TX = AP ghi vào
    AIF2  <-> MODEM                  AIF2RX = modem xuống, AIF2TX = LÊN SÓNG

Đường tiêm cũ đặt `AIF1TX1 Input 2 = AIF1RX1`, tức AP -> AP: tiếng quay ngược
về chính máy ghi âm chứ không lên sóng. Đó là lý do đầu bên kia im lặng còn
nguồn thu 4 lại nghe thấy chính mình.

Script gọi một cuộc, chờ bắt máy, chụp lại toàn bộ tuyến trộn HAL dựng lên,
rồi thử tiêm vào AIF2TX và phát tiếng để nghe.

    python scripts/tiem_duong_len.py 0396130621
    python scripts/tiem_duong_len.py 0396130621 --tx 2     # thử khe TX khác
"""

import argparse
import math
import re
import struct
import subprocess
import sys
import time
import wave
from io import BytesIO

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERIAL = "21f10e44220c7ece"
MIXCTL = "/data/local/tmp/mixctl"


def sh(cmd: str, t: int = 120) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def doc_tuyen() -> dict[str, str]:
    """Đọc mọi đầu vào AIF*TX trong MỘT lần gọi adb.

    Gọi mixctl 128 lần qua adb mất hơn một phút; gộp thành một vòng lặp chạy
    ngay trên máy thì xong trong vài giây.
    """
    lenh = (f'for t in AIF1TX1 AIF1TX2 AIF2TX1 AIF2TX2 AIF2TX3 AIF2TX4; do '
            f'for i in 1 2 3 4; do {MIXCTL} get "$t Input $i" 2>/dev/null | tail -1; '
            f'done; done')
    ra = sh(f"""su -c '{lenh}'""")
    d = {}
    for dong in ra.splitlines():
        m = re.match(r"(AIF\dTX\d Input \d)\[0\] = \d+ \((.*)\)", dong.strip())
        if m:
            d[m.group(1)] = m.group(2)
    return d


def in_tuyen(d: dict[str, str], tieu_de: str):
    print(f"  {tieu_de}")
    dung = {k: v for k, v in d.items() if v and v != "None"}
    if not dung:
        print("      (tất cả None)")
    for k, v in sorted(dung.items()):
        cho = " <-- LÊN SÓNG" if k.startswith("AIF2TX") else ""
        print(f"      {k:<20} = {v}{cho}")


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)",
                  sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def tao_tone(giay: float = 2.0, tan: float = 900.0, rate: int = 24000) -> bytes:
    """Tiếng bíp - không lẫn vào đâu được, loại trừ mọi nghi ngờ về TTS."""
    n = int(giay * rate)
    mau = b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * tan * i / rate)))
                   for i in range(n))
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(mau)
    return buf.getvalue()


async def chay(a) -> int:
    import asyncio
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge

    print("[0] Tuyến trộn khi KHÔNG có cuộc gọi:")
    in_tuyen(doc_tuyen(), "trước khi gọi")

    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=3)
    print(f"\n[1] {msg}")
    if not ok:
        return 1
    bridge = PhoneCallBridge(None, CallSession(customer_name="Khách"), port=8123)
    bridge.tam_dung_nghe = True
    await bridge.start()

    try:
        print(f"\n[2] Gọi {a.so} ... HÃY BẮT MÁY")
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

        print("\n[3] Tuyến trộn HAL dựng lên KHI ĐANG GỌI:")
        truoc = doc_tuyen()
        in_tuyen(truoc, "đang gọi, chưa tiêm")

        dich = f"AIF2TX{a.tx} Input {a.khe}"
        print(f"\n[4] Tiêm: {dich} = AIF1RX1")
        ra = sh(f"""su -c '{MIXCTL} set "{dich}" AIF1RX1'""")
        print("    " + (ra.strip().splitlines()[-1] if ra.strip() else "(im lặng)"))

        print("\n[5] Phát 2 giây tiếng bíp 900Hz — NGHE THỬ")
        await bridge.play(tao_tone())
        await asyncio.sleep(4)

        print("\n[6] Đọc lại xem HAL có xoá đường tiêm không:")
        in_tuyen(doc_tuyen(), "sau khi phát")

        print(f"\n[7] Giữ máy thêm {a.giay}s, phát bíp mỗi 4s ...")
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < a.giay and trang_thai() == 1:
            await bridge.play(tao_tone(1.0))
            await asyncio.sleep(4)
    finally:
        print("\n[8] Dọn dẹp ...")
        sh(f"""su -c '{MIXCTL} set "AIF2TX{a.tx} Input {a.khe}" None'""")
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
    return 0


def main() -> int:
    import asyncio
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--tx", type=int, default=1, help="khe AIF2TX nào")
    ap.add_argument("--khe", type=int, default=2, help="Input mấy của khe đó")
    ap.add_argument("--giay", type=int, default=20)
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
