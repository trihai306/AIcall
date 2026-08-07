"""Mở khoá màn hình rồi gọi, chỉ định thẳng khe SIM.

Hai cái bẫy đã gặp thật:

  1. Màn hình KHOÁ thì `ACTION_CALL` khởi động nhưng giao diện gọi không lên
     được, cuộc gọi đứng im ở trạng thái "rảnh" - trông y như "không ai bắt máy".
  2. Máy HAI KHE bật hộp chọn SIM cho số chưa gọi bao giờ. Số đã gọi nhiều lần
     thì máy nhớ khe nên đi thẳng - vì vậy số cũ gọi được mà số mới thì không,
     rất dễ tưởng nhầm là nhà mạng chặn.

Khe 1 trống (`gsm.sim.state=ABSENT,LOADED`), SIM Viettel ở khe 2, nên chỉ định
khe 2 là hết hộp chọn.

    python scripts/mo_khoa_va_goi.py 0965833706
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


def mo_khoa() -> str:
    sh("input keyevent KEYCODE_WAKEUP")
    sh("wm dismiss-keyguard")
    time.sleep(0.6)
    w = sh("dumpsys window")
    m = re.search(r"mDreamingLockscreen=(\w+)", w)
    return m.group(1) if m else "?"


def goi(so: str, khe: int) -> str:
    # Samsung nhận `com.android.phone.extra.slot` (0 = khe 1, 1 = khe 2). Có
    # extra này thì không bật hộp chọn SIM nữa.
    return sh(f"am start -a android.intent.action.CALL -d tel:{so} "
              f"--ei com.android.phone.extra.slot {khe}")


def tt() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--khe", type=int, default=1, help="0 = khe 1, 1 = khe 2")
    ap.add_argument("--giay", type=int, default=30)
    a = ap.parse_args()

    print("Mở khoá màn hình ...")
    print("    màn khoá còn không:", mo_khoa())

    print(f"Gọi {a.so} qua khe SIM {a.khe + 1} ...")
    print("   ", goi(a.so, a.khe)[:120])

    truoc, t0 = None, time.time()
    while time.time() - t0 < a.giay:
        t = tt()
        if t != truoc:
            print(f"    {int(time.time() - t0):>3}s: {TEN.get(t, t)}")
            truoc = t
        if t == 1:
            break
        time.sleep(1)

    if truoc in (None, 0):
        print("\n    Vẫn không quay số. Đang có gì trên màn hình:")
        w = sh("dumpsys window")
        for l in w.splitlines():
            if "mCurrentFocus" in l or "mFocusedApp" in l:
                print("       ", l.strip()[:150])
    sh("input keyevent KEYCODE_ENDCALL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
