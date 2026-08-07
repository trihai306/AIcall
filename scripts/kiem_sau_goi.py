"""Máy có thật sự quay số không, và tuyến trộn có bị bỏ dở không?

Chạy sau vài lần gọi hụt để phân biệt "người kia không bắt máy" với "máy không
gọi được". Cũng kiểm xem lần đo trước có bỏ quên micro ở trạng thái tắt không -
script đo có tắt `AIF1TX1 Input 1` và nếu nó chết giữa chừng thì micro vẫn đang
tắt, mà như vậy thì cuộc gọi sau người kia không nghe thấy gì.

    python scripts/kiem_sau_goi.py
"""

import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERIAL = "21f10e44220c7ece"
MIXCTL = "/data/local/tmp/mixctl"


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def mix_get(ten: str) -> str:
    ra = sh(f"""su -c '{MIXCTL} get "{ten}"'""")
    m = re.search(r"= \d+ \((.*)\)", ra)
    return m.group(1) if m else "?"


def main() -> int:
    print("=== Trạng thái cuộc gọi hiện tại ===")
    d = sh("dumpsys telephony.registry")
    for k in ("mCallState", "mForegroundCallState"):
        m = re.search(rf"{k}=(\d+)", d)
        print(f"    {k} = {m.group(1) if m else '?'}")

    print("\n=== Nhật ký gọi gần nhất ===")
    ra = sh("content query --uri content://call_log/calls "
            "--projection number:type:duration:date "
            "--sort 'date DESC LIMIT 6'")
    for dong in ra.splitlines()[:6]:
        print("   ", dong.strip()[:150])

    print("\n=== Tuyến trộn: có bị bỏ dở không ===")
    for c in ("AIF1TX1 Input 1", "AIF1TX1 Input 2", "AIF1TX2 Input 2",
              "ABOX UAIF0 SPK", "ABOX SPUS OUT0", "ABOX SPUS OUT1"):
        v = mix_get(c)
        canh = ""
        if c == "AIF1TX1 Input 1" and v in ("None", "?"):
            canh = "  <-- MICRO ĐANG TẮT, cuộc gọi thường sẽ không có tiếng"
        if c.startswith("ABOX SPUS") and v != "SIFS0":
            canh = "  <-- chưa trả về SIFS0"
        print(f"    {c:<18} = {v}{canh}")

    print("\n=== Sóng và SIM ===")
    print("    mạng:", sh("getprop gsm.network.type"))
    print("    SIM :", sh("getprop gsm.sim.state"))
    print("    nhà mạng:", sh("getprop gsm.operator.alpha"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
