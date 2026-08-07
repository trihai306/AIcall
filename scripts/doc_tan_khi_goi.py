"""Tần số các mắt xích khi ĐANG trong cuộc gọi có khác lúc rảnh không?

Lúc máy rảnh đo được `ABOX UAIF0 rate = 48000`. Nhưng cuộc gọi CS dùng đường
`incall_nb-*` (nb = narrowband), rất có thể HAL hạ UAIF0 xuống 8000 khi dựng
tuyến. Nếu vậy mà ta vẫn bơm 48kHz vào `SIFS1 -> UAIF0` thì sóng sin thuần cũng
méo - đúng tiếng "dè" người nghe báo, và giải thích vì sao gọi tới máy nào cũng dè.

Không cần ai bắt máy: tuyến âm thanh dựng ngay từ lúc quay số (`setMode
(MODE_IN_CALL)` xuất hiện cùng lúc với DIALING), nên đọc lúc đang đổ chuông là đủ.

    python scripts/doc_tan_khi_goi.py 0396130621
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
MIXCTL = "/data/local/tmp/mixctl"

CAN_DOC = [
    "ABOX UAIF0 rate", "ABOX UAIF1 rate", "ABOX UAIF0 width",
    "ABOX Sound Type", "ABOX Audio Mode",
    "ABOX SPUS ASRC0", "ABOX SPUS ASRC1", "ABOX SPUS ASRC2",
    "ABOX SPUS ASRC3", "ABOX SPUS ASRC4", "ABOX SPUS ASRC5",
    "ABOX NSRC1", "ABOX UAIF0 SPK", "ABOX SPUS OUT0",
    "ASRC1 Rate 1", "ASRC1 Rate 2",
]


def sh(cmd: str, t: int = 120) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def doc_het() -> dict[str, str]:
    lenh = "; ".join(f'{MIXCTL} get "{c}"' for c in CAN_DOC)
    d = {}
    for dong in sh(f"su -c '{lenh}'").splitlines():
        m = re.match(r"(.+?)\[0\] = (\d+)(?: \((.*)\))?", dong.strip())
        if m:
            d[m.group(1)] = m.group(3) or m.group(2)
    return d


def tt() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    a = ap.parse_args()

    print("[1] Đọc lúc máy RẢNH ...")
    ranh = doc_het()

    print(f"[2] Gọi {a.so} — KHÔNG cần bắt máy, chỉ cần chuông reo")
    sh("input keyevent KEYCODE_WAKEUP")
    sh("wm dismiss-keyguard")
    time.sleep(0.6)
    sh(f"am start -a android.intent.action.CALL -d tel:{a.so} "
       f"--ei com.android.phone.extra.slot 1")

    for i in range(25):
        time.sleep(1)
        if tt() in (3, 4, 1):
            print(f"    {i}s: tuyến đã dựng (trạng thái {tt()})")
            break
    else:
        print("    không quay được số")
        return 1
    time.sleep(1.5)

    print("[3] Đọc lúc ĐANG GỌI ...")
    goi = doc_het()
    sh("input keyevent KEYCODE_ENDCALL")

    print(f"\n    {'control':<20}{'rảnh':>12}{'đang gọi':>12}")
    doi = []
    for c in CAN_DOC:
        r, g = ranh.get(c, "?"), goi.get(c, "?")
        dau = "  <-- ĐỔI" if r != g else ""
        print(f"    {c:<20}{r:>12}{g:>12}{dau}")
        if r != g:
            doi.append((c, r, g))

    print("\n" + "=" * 60)
    tan = goi.get("ABOX UAIF0 rate", "?")
    if tan not in ("48000", "?"):
        print(f"TÌM RA: UAIF0 hạ xuống {tan}Hz khi vào cuộc gọi.")
        print("Ta đang bơm 24000Hz qua AudioFlinger (48000) vào đó -> méo.")
        print(f"Cách sửa: bật ASRC cho luồng phát, hoặc đặt rate_xuong = {tan}.")
    elif doi:
        print("UAIF0 vẫn 48000. Nhưng có control khác đổi, xem cột ĐỔI ở trên.")
    else:
        print("Không có gì đổi. Tần số không phải nguyên nhân của tiếng dè.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
