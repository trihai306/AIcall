"""Xem THẬT trạng thái cuộc gọi đổi thế nào khi người bên kia bắt máy.

Không đoán định dạng dumpsys nữa. Script gọi một cuộc rồi in mọi dòng có mùi
trạng thái, cứ 2 giây một lần, để nhìn tận mắt dòng nào đổi vào đúng lúc bắt
máy. Có dữ liệu thật rồi mới viết hàm nhận biết.

    python scripts/soi_trang_thai_goi.py 0396130621
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


def sh(cmd: str, t: int = 30) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def loc(d: str) -> list[str]:
    ra = []
    for dong in d.splitlines():
        s = dong.strip()
        if not s or len(s) > 200:
            continue
        if re.search(r"state|connectTime|isRinging|Ringing|Active|Dialing|"
                     r"mCallState|disconnect", s, re.I):
            ra.append(s)
    return ra


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--giay", type=int, default=40)
    a = ap.parse_args()

    print(f"Gọi {a.so} ... HÃY BẮT MÁY, rồi nói vài tiếng, rồi cúp.")
    sh("input keyevent KEYCODE_WAKEUP")
    sh(f"am start -a android.intent.action.CALL -d tel:{a.so}")

    truoc_tel, truoc_reg, truoc_au = set(), set(), set()
    t0 = time.time()
    while time.time() - t0 < a.giay:
        t = int(time.time() - t0)
        tel = set(loc(sh("dumpsys telecom")))
        reg = set(loc(sh("dumpsys telephony.registry")))
        au = {d.strip() for d in sh("dumpsys audio").splitlines()
              if re.search(r"\bmode\b", d, re.I) and len(d.strip()) < 160}

        for ten, moi, cu in (("TELECOM", tel, truoc_tel),
                             ("REGISTRY", reg, truoc_reg),
                             ("AUDIO", au, truoc_au)):
            them = moi - cu
            if them:
                for d in sorted(them):
                    print(f"  {t:>3}s [{ten}] + {d[:170]}")
        truoc_tel, truoc_reg, truoc_au = tel, reg, au
        time.sleep(2)

    print("\nCúp máy.")
    sh("input keyevent KEYCODE_ENDCALL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
