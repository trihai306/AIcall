"""Gọi TRẦN - không cầu tiếng, không đụng mixer - để tách "mạng rớt" khỏi "code hỏng".

Cuộc gọi qua `goi_va_noi.py` rớt sau 12-19 giây với `Reason: OUT_OF_SERVICE`.
Nhưng script đó vừa dựng cầu tiếng, vừa đổi định tuyến mixer, vừa tắt micro -
nên không biết mạng tự rớt hay chính mình làm rớt.

Script này KHÔNG làm gì ngoài quay số và đọc trạng thái. So thời gian giữ được
với cuộc gọi có tiêm:

    giữ được ~45s  -> mạng bình thường, lỗi nằm ở cầu tiếng / mixer
    rớt ~15s       -> máy hoặc sóng, code không liên quan

    python scripts/goi_tran_khong_tiem.py 0396130621
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
TEN = {0: "rảnh", 1: "ĐANG NÓI CHUYỆN", 2: "đang giữ", 3: "đang quay số",
       4: "đang đổ chuông bên kia", 6: "có cuộc gọi đến", 7: "đã ngắt",
       8: "đang ngắt"}


def sh(lenh: str) -> str:
    return subprocess.run(["adb", "-s", SERIAL, "shell", lenh],
                          capture_output=True, text=True, timeout=40).stdout


def trang_thai() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--giay", type=int, default=45)
    a = ap.parse_args()

    print(f"\n  Gọi TRẦN tới {a.so} - không cầu tiếng, không đổi mixer.")
    print(f"  Mạng lúc này: {sh('getprop gsm.network.type').strip()}")
    sh("input keyevent KEYCODE_WAKEUP")
    sh("wm dismiss-keyguard")
    time.sleep(0.6)
    sh(f"am start -a android.intent.action.CALL -d tel:{a.so} "
       f"--ei com.android.phone.extra.slot 1")

    t_noi = None
    truoc = None
    t0 = time.time()
    while time.time() - t0 < a.giay + 20:
        t = trang_thai()
        if t != truoc:
            print(f"  {time.time()-t0:5.1f}s  {TEN.get(t, f'mã {t}')}")
            truoc = t
        if t == 1 and t_noi is None:
            t_noi = time.time()
            print(f"         mạng khi nối: {sh('getprop gsm.network.type').strip()}")
        if t_noi and t in (0, 7):
            print(f"\n  GIỮ ĐƯỢC {time.time()-t_noi:.1f}s rồi rớt")
            break
        if t_noi and time.time() - t_noi >= a.giay:
            print(f"\n  GIỮ ĐƯỢC ĐỦ {a.giay}s - mạng bình thường")
            sh("input keyevent KEYCODE_ENDCALL")
            break
        time.sleep(1)

    if t_noi is None:
        print("\n  không nối được máy")
    print("\n  Lý do rớt theo máy ghi lại:")
    for d in sh("dumpsys telecom").splitlines():
        if "DisconnectCause" in d:
            print(f"    {d.strip()[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
