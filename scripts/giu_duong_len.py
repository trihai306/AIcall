"""HAL có giật lại nguồn đường lên sau khi ta đặt không?

Nghi vấn cuối của hướng tiêm ALSA. Đã biết chắc:
  - `ABOX SPUS OUT0..5 = SIFS0`, tức luồng phát của AudioFlinger ĐI VÀO SIFS0.
  - `ABOX NSRC1` là nguồn của đường lên; lúc gọi mặc định nó là `UAIF0` (mic).
  - Đặt `NSRC1 = SIFS0` thì đọc lại NGAY thấy đúng, nhưng đầu bên kia vẫn im.

Điều chưa kiểm: đọc lại SAU KHI PHÁT. HAL dựng lại tuyến mỗi lần có thay đổi
luồng âm thanh, rất có thể nó ghi đè `NSRC1` về `UAIF0` ngay khi AudioTrack bắt
đầu chạy - lúc đó phép đọc ngay sau khi ghi vẫn thấy đúng mà thực tế đã hỏng.

Script chạy ba vế trong một cuộc gọi:
  A. đặt một lần, phát, đọc lại              -> HAL có giật không
  B. đặt lại liên tục 200ms/lần trong lúc phát -> nếu A hỏng thì B chữa được không
  C. phát lời chào bằng giọng AI kèm giữ liên tục -> để nghe bằng tai

    python scripts/giu_duong_len.py 0396130621
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

LOI_CHAO = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng. "
            "Anh chị có cần em hỗ trợ thông tin gì không ạ?")


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


def tao_tone(giay: float, rate: int = 24000) -> bytes:
    n = int(giay * rate)
    mau = b"".join(struct.pack("<h", int(13000 * math.sin(2 * math.pi * 900 * i / rate)))
                   for i in range(n))
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(mau)
    return buf.getvalue()


async def giu_lien_tuc(dung: asyncio.Event):
    """Đặt lại NSRC1 mỗi 200ms cho tới khi được bảo dừng."""
    while not dung.is_set():
        mix_set("ABOX NSRC1", "SIFS0")
        try:
            await asyncio.wait_for(dung.wait(), timeout=0.2)
        except asyncio.TimeoutError:
            pass


async def chay(a) -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge
    from backend.services.tts_service import F5TTSService

    print("[1] Nạp TTS ...")
    tts = F5TTSService()
    tts.load()

    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=3)
    print(f"[2] {msg}")
    if not ok:
        return 1
    bridge = PhoneCallBridge(None, CallSession(customer_name="Khách"), port=8123)
    bridge.tam_dung_nghe = True
    await bridge.start()

    try:
        print(f"\n[3] Gọi {a.so} ... HÃY BẮT MÁY")
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

        print("\n[A] Đặt MỘT LẦN rồi phát — xem HAL có giật lại không")
        print(f"    trước khi đặt        NSRC1 = {mix_get('ABOX NSRC1')}")
        mix_set("ABOX UAIF0 SPK", "SIFS0")
        mix_set("ABOX NSRC1", "SIFS0")
        print(f"    ngay sau khi đặt     NSRC1 = {mix_get('ABOX NSRC1')}")
        await bridge.play(tao_tone(2.5))
        await asyncio.sleep(0.8)
        giua = mix_get("ABOX NSRC1")
        print(f"    ĐANG PHÁT            NSRC1 = {giua}")
        await asyncio.sleep(2.5)
        sau = mix_get("ABOX NSRC1")
        print(f"    sau khi phát xong    NSRC1 = {sau}")
        bi_giat = giua != "SIFS0" or sau != "SIFS0"
        print(f"    -> HAL {'GIẬT LẠI' if bi_giat else 'không đụng tới'}")

        print("\n[B] Giữ liên tục 200ms/lần rồi phát bíp — NGHE THỬ")
        dung = asyncio.Event()
        canh = asyncio.create_task(giu_lien_tuc(dung))
        await asyncio.sleep(0.4)
        await bridge.play(tao_tone(2.5))
        await asyncio.sleep(3.5)
        print(f"    trong lúc giữ        NSRC1 = {mix_get('ABOX NSRC1')}")

        print("\n[C] Phát lời chào giọng AI, vẫn đang giữ — NGHE THỬ")
        wav = await tts.synthesize(LOI_CHAO, use_cache=False)
        await bridge.play(wav)
        await asyncio.sleep(10)
        dung.set()
        await canh

        print(f"\n[D] Giữ máy thêm {a.giay}s ...")
        for _ in range(max(0, a.giay // 5)):
            if trang_thai() != 1:
                print("    cuộc gọi đã kết thúc")
                break
            await asyncio.sleep(5)
    finally:
        print("\n[E] Trả tuyến cũ ...")
        mix_set("ABOX NSRC1", "UAIF0")
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
