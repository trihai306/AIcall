"""Các bộ đổi tần số lấy mẫu (ASRC) của ABOX đang ở trạng thái nào?

Nghi vấn: đường micro thật đi qua ASRC trước khi vào AIF1TX1

    IN3L -> LHPF1 -> ASRC1IN1L -> AIF1TX1

ASRC ở đó để đưa tiếng về tần số của cuộc gọi (8kHz với AMR-NB). Đường tiêm hiện
tại vào thẳng `AIF1TX1 Input 2`, NHẢY QUA ASRC. Nhồi luồng 48kHz vào tuyến đang
chạy 8kHz mà không đổi tần thì sóng sin thuần cũng thành tiếng rè - khớp với
việc người nghe báo chính TIẾNG BÍP bị "siêu dè".

    python scripts/soi_asrc.py
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


def main() -> int:
    print("=== ASRC của các luồng phát (SPUS) và thu (SPUM) ===")
    lenh = "; ".join(
        [f'{MIXCTL} get "ABOX SPUS ASRC{i}"' for i in range(8)] +
        [f'{MIXCTL} get "ABOX SPUM ASRC{i}"' for i in range(4)])
    for d in sh(f"su -c '{lenh}'").splitlines():
        if "=" in d:
            print("   ", d.strip()[:110])

    print("\n=== Các control ASRC khác trên codec ===")
    ds = sh(f"su -c '{MIXCTL} list ASRC'")
    ten = re.findall(r"\[\w+\]\s+(.+)$", ds, re.M)
    for t in ten[:40]:
        print("   ", t)

    print("\n=== Tần số các mắt xích lúc này ===")
    lenh2 = "; ".join(f'{MIXCTL} get "{c}"' for c in
                      ("ABOX UAIF0 rate", "ABOX UAIF1 rate", "ABOX UAIF0 width",
                       "ABOX Sound Type", "ABOX Audio Mode"))
    for d in sh(f"su -c '{lenh2}'").splitlines():
        print("   ", d.strip()[:110])

    print("\n=== Mọi control có chữ 'rate' ===")
    ds2 = sh(f"su -c '{MIXCTL} list rate'")
    for t in re.findall(r"\[\w+\]\s+(.+)$", ds2, re.M)[:25]:
        print("   ", t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
