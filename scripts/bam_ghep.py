"""Bấm nút xác nhận ghép đôi Bluetooth trên điện thoại.

Chạy song song với phía Windows: Windows gửi yêu cầu ghép đôi, điện thoại hiện
hộp thoại xác nhận, script này tìm nút rồi bấm.
"""
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

S = "21f10e44220c7ece"
NHAN = ["pair", "ghép đôi", "ghep doi", "ok", "đồng ý", "accept", "kết nối", "cho phép"]


def sh(c: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", S, "shell", c],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def main() -> int:
    for lan in range(20):
        sh("rm -f /sdcard/u2.xml; uiautomator dump /sdcard/u2.xml")
        xml = sh("cat /sdcard/u2.xml")
        for m in re.finditer(
                r'text="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
            chu = m.group(1).strip()
            if chu.lower() in NHAN:
                x = (int(m.group(2)) + int(m.group(4))) // 2
                y = (int(m.group(3)) + int(m.group(5))) // 2
                sh(f"input tap {x} {y}")
                print(f"đã bấm '{chu}' tại ({x},{y})")
                return 0
        if lan % 4 == 0:
            chu = re.findall(r'text="([^"]{1,30})"', xml)
            print(f"  {lan*2}s: màn hình có: "
                  f"{', '.join(dict.fromkeys(chu))[:110]}")
        time.sleep(2)
    print("không thấy hộp thoại ghép đôi")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
