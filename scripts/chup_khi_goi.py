"""Chụp toàn bộ trạng thái âm thanh của máy trước và trong cuộc gọi.

Mấy lần trước tôi đoán chỗ tiêm rồi thử, mỗi lần thử tốn một cuộc gọi của người
dùng mà thước đo lại yếu. Lần này gom hết dữ liệu trong MỘT cuộc rồi phân tích
ngoại tuyến: chụp giá trị của cả 861 control trộn, bản dump AudioFlinger, và
nhật ký app cầu nối - trước khi gọi và trong khi gọi. So hai bản là ra đúng
tuyến HAL dựng lên cho cuộc gọi.

    python scripts/chup_khi_goi.py 0396130621
"""

import argparse
import asyncio
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

SERIAL = "21f10e44220c7ece"
MIXCTL = "/data/local/tmp/mixctl"
RA = PROJECT / "data" / "chup_goi"


def sh(cmd: str, t: int = 180) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def soan_script_dump():
    """Đặt sẵn một script trên máy để đọc hết control trong MỘT lần chạy.

    Gọi mixctl 861 lần qua adb mất hàng chục phút; chạy vòng lặp ngay trên máy
    thì vài giây. Lọc bỏ control *Volume* để bản chụp còn đọc được.
    """
    noi_dung = (
        "#!/system/bin/sh\n"
        f"{MIXCTL} list | sed -n 's/^ *\\[[A-Z?]*\\] //p' | while read -r t; do\n"
        f"  case \"$t\" in *Volume) continue;; esac\n"
        f"  {MIXCTL} get \"$t\" 2>/dev/null | tail -1\n"
        "done\n"
    )
    p = PROJECT / "data" / "dumpmix.sh"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(noi_dung)
    subprocess.run(["adb", "-s", SERIAL, "push", str(p), "/data/local/tmp/dumpmix.sh"],
                   capture_output=True, text=True, timeout=60)
    sh("su -c 'chmod 755 /data/local/tmp/dumpmix.sh'")


def chup(nhan: str):
    RA.mkdir(parents=True, exist_ok=True)
    (RA / f"mixer_{nhan}.txt").write_text(
        sh("su -c /data/local/tmp/dumpmix.sh", t=300), encoding="utf-8")
    (RA / f"flinger_{nhan}.txt").write_text(
        sh("dumpsys media.audio_flinger"), encoding="utf-8")
    (RA / f"audio_{nhan}.txt").write_text(sh("dumpsys audio"), encoding="utf-8")
    n = len((RA / f"mixer_{nhan}.txt").read_text(encoding="utf-8").splitlines())
    print(f"    đã chụp '{nhan}': {n} control")


async def chay(a) -> int:
    from backend.pipeline.session_manager import CallSession
    from backend.services import adb_service
    from backend.services.phone_call_service import PhoneCallBridge

    print("[1] Soạn script đọc mixer trên máy ...")
    soan_script_dump()

    print("[2] Chụp trạng thái KHI CHƯA GỌI ...")
    chup("truoc")

    ok, msg = await adb_service.start_bridge(SERIAL, port=8123, src=1)
    print(f"[3] {msg}")
    if not ok:
        return 1
    bridge = PhoneCallBridge(None, CallSession(customer_name="Khách"), port=8123)
    bridge.tam_dung_nghe = True
    await bridge.start()
    sh("logcat -c")

    try:
        print(f"\n[4] Gọi {a.so} ... HÃY BẮT MÁY, giữ máy ~25 giây rồi cúp")
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

        # Phát tiếng liên tục trong lúc chụp: có tiếng đang chạy thì track mới
        # hiện trong AudioFlinger, chụp lúc im lặng là không thấy gì.
        print("[5] Vừa phát tiếng vừa chụp ...")
        import math, struct, wave
        from io import BytesIO
        n = int(20 * 24000)
        mau = b"".join(struct.pack("<h", int(14000 * math.sin(2 * math.pi * 900 * i / 24000)))
                       for i in range(n))
        buf = BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(mau)
        asyncio.create_task(bridge.play(buf.getvalue()))
        await asyncio.sleep(1.5)
        chup("trong")

        (RA / "logcat.txt").write_text(
            sh("logcat -d -v time"), encoding="utf-8")
        print("    đã chụp nhật ký")
    finally:
        sh("input keyevent KEYCODE_ENDCALL")
        await bridge.stop()
        await adb_service.stop_bridge(SERIAL, port=8123)
        print(f"\n[6] Xong. Dữ liệu ở {RA}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    return asyncio.run(chay(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
