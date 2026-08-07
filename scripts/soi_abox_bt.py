"""Hai việc trong một lượt: xem luồng phát của ta rơi vào SIFS nào, và xem
điện thoại đã ghép đôi với máy tính chưa.

SIFS: đặt `ABOX NSRC1 = SIFS0` mà đầu bên kia vẫn không nghe, nên phải kiểm xem
luồng phát của AudioFlinger có thật sự đi vào SIFS0 không - ABOX có 8 luồng phát
(SPUS OUT0..7), mỗi luồng chọn được SIFS0/1/2 riêng.

Bluetooth: hướng thứ hai là để Android tự đẩy tiếng cuộc gọi sang máy tính qua
hồ sơ rảnh tay. Cần biết máy tính đã nằm trong danh sách ghép đôi của điện thoại
chưa và địa chỉ của nó là gì.

    python scripts/soi_abox_bt.py
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


def sh(cmd: str, t: int = 120) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def mix_get(ten: str) -> str:
    ra = sh(f"""su -c '{MIXCTL} get "{ten}"'""")
    m = re.search(r"= \d+ \((.*)\)", ra)
    return m.group(1) if m else "?"


def main() -> int:
    print("=== Luồng phát ABOX: SPUS OUT0..7 đi vào SIFS nào ===")
    for i in range(8):
        print(f"    ABOX SPUS OUT{i} = {mix_get(f'ABOX SPUS OUT{i}')}")
    print("\n=== Đầu vào của các SIFS và nguồn đường lên ===")
    for c in ("ABOX SIFS0", "ABOX SIFS1", "ABOX SIFS2",
              "ABOX NSRC1", "ABOX UAIF0 SPK", "ABOX UAIF1 SPK", "ABOX SIFM1"):
        print(f"    {c:<18} = {mix_get(c)}")

    print("\n=== Thiết bị Bluetooth điện thoại đã ghép đôi ===")
    bm = sh("dumpsys bluetooth_manager")
    # Phần "Bonded devices" liệt kê địa chỉ và tên; lấy đúng khối đó thay vì
    # quét cả bản dump (bản dump có hàng nghìn dòng nhật ký cũ).
    trong_khoi = False
    for dong in bm.splitlines():
        s = dong.strip()
        if re.match(r"Bonded devices", s, re.I):
            trong_khoi = True
            print(f"    {s}")
            continue
        if trong_khoi:
            if not s or s.startswith("---") or len(s) > 120:
                trong_khoi = False
                continue
            print(f"      {s}")

    m = re.findall(r"([0-9A-F]{2}(?::[0-9A-F]{2}){5})\s+(.+)", bm)
    if m:
        print("\n    địa chỉ thấy trong bản dump:")
        for addr, ten in dict(m).items():
            print(f"      {addr}  {ten.strip()[:60]}")

    print("\n=== Hồ sơ đang nối ===")
    for dong in bm.splitlines():
        if re.search(r"Profile: (Headset|A2DP)|StateMachine|mCurrentDevice", dong) \
                and len(dong.strip()) < 150:
            print("   ", dong.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
