"""Liệt kê các control trộn tiếng liên quan tới đường lên/xuống của cuộc gọi.

Lý do có script này: đường tiêm đang dùng là `AIF1TX1 Input 2 = AIF1RX1`. AIF1
là dây nối codec <-> CHIP ỨNG DỤNG, còn modem nối qua AIF2. Đặt như vậy chỉ là
vòng lặp AP -> AP: tiếng quay về chính máy ghi lại, KHÔNG lên sóng. Cần tìm
control của AIF2TX (codec -> modem) để tiêm cho đúng chỗ.

    python scripts/soi_mixer.py            # liệt kê
    python scripts/soi_mixer.py --doc      # đọc giá trị hiện tại của AIF*TX
"""

import argparse
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERIAL = "21f10e44220c7ece"
MIXCTL = "/data/local/tmp/mixctl"


def sh(cmd: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def mixctl(args: str, t: int = 60) -> str:
    return sh(f"""su -c '{MIXCTL} {args}'""", t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", action="store_true", help="đọc giá trị hiện tại")
    a = ap.parse_args()

    ds = mixctl("list")
    ten = re.findall(r"\[\w+\]\s+(.+)$", ds, re.M)
    print(f"Tổng {len(ten)} control\n")

    nhom = {
        "AIF1TX (codec -> chip ứng dụng: thứ MÁY GHI ÂM nghe được)": r"^AIF1TX",
        "AIF2TX (codec -> MODEM: ĐƯỜNG LÊN, thứ đầu bên kia nghe)": r"^AIF2TX",
        "AIF3TX (codec -> bluetooth / phụ)": r"^AIF3TX",
        "AIF2RX / đường xuống từ modem": r"AIF2RX",
    }
    for tieu_de, mau in nhom.items():
        khop = [t for t in ten if re.search(mau, t)]
        print(f"--- {tieu_de} — {len(khop)} control")
        for t in khop[:40]:
            print(f"    {t}")
        if not khop:
            print("    (không có)")
        print()

    if a.doc:
        print("=== GIÁ TRỊ HIỆN TẠI của các đầu vào AIF*TX ===")
        for t in ten:
            if re.match(r"^AIF[12]TX\d+ Input \d+$", t):
                out = mixctl(f'get "{t}"').strip().splitlines()
                gt = out[-1] if out else "?"
                if "None" not in gt:
                    print(f"    {gt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
