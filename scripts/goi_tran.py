"""Gọi trần, in trạng thái từng giây. Không nạp model nên chuông reo ngay.

Dùng khi nhiều cuộc liên tiếp không nối được, để phân biệt:
  - tới ALERTING (4) rồi thôi  -> chuông có reo, người kia không bắt
  - không qua nổi DIALING (3)  -> cuộc gọi không ra được khỏi máy

    python scripts/goi_tran.py 0396130621
"""

import argparse
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERIAL = "21f10e44220c7ece"
TEN = {0: "rảnh", 1: "ĐÃ NỐI MÁY", 2: "giữ máy", 3: "đang quay số",
       4: "đang đổ chuông bên kia", 5: "gọi đến", 6: "chờ", 7: "đã ngắt",
       8: "đang ngắt"}


def sh(cmd: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def tt() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--giay", type=int, default=40)
    a = ap.parse_args()

    print(f"Gọi {a.so} — CHUÔNG REO NGAY BÂY GIỜ")
    sh("input keyevent KEYCODE_WAKEUP")
    sh(f"am start -a android.intent.action.CALL -d tel:{a.so}")

    truoc, t0 = None, time.time()
    while time.time() - t0 < a.giay:
        t = tt()
        if t != truoc:
            print(f"    {int(time.time() - t0):>3}s: {TEN.get(t, t)}")
            truoc = t
        if t == 1:
            print("    -> nối được. Giữ máy vài giây rồi cúp.")
        time.sleep(1)

    sh("input keyevent KEYCODE_ENDCALL")
    print("Đã cúp.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
