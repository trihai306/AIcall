"""Tìm cổng PCM tiêm tiếng vào cuộc gọi (VPCMIN).

Trong danh sách control ABOX có `ABOX PCM ext VPCMIN ON` - "VPCMIN" là Voice PCM
IN, cổng Samsung dùng để đưa PCM vào tuyến thoại. Repo đã có sẵn `pcmplay.c` ghi
thẳng vào thiết bị ALSA bằng ioctl, nên nếu tìm được đúng số card/device thì đây
là đường ngắn nhất: không qua AudioFlinger, không phải giành mixer với HAL.

    python scripts/soi_pcm.py
"""

import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERIAL = "21f10e44220c7ece"
MIXCTL = "/data/local/tmp/mixctl"

NOI_DUNG = """#!/system/bin/sh
echo "=== /dev/snd ==="
ls -l /dev/snd/ 2>&1
echo
echo "=== SPUS IN (RDMA nao vao luong phat nao) ==="
for i in 0 1 2 3 4 5 6 7; do
  printf "  SPUS IN%s = " "$i"; MIXCTL get "ABOX SPUS IN$i" 2>&1 | tail -1
done
echo
for c in "ABOX PCM ext VPCMIN ON" "ABOX PCM ext APCALL BUFFTYPE" \
         "ABOX OEM AP Call type" "ABOX OEM AP Call BW" \
         "ABOX SIFMS" "ABOX SIFSM" "ABOX Audio Mode" "ABOX Echo Cancellation"; do
  echo "--- $c"
  MIXCTL info "$c" 2>&1 | head -10
done
""".replace("MIXCTL", MIXCTL)


def sh(cmd: list[str], t: int = 120) -> str:
    r = subprocess.run(["adb", "-s", SERIAL] + cmd,
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def main() -> int:
    # Viết ra file rồi push: chuỗi ssh -> PowerShell -> adb -> sh nuốt dấu nháy,
    # và cú pháp chuyển hướng của cmd (`>nul`) không chạy trong PowerShell.
    p = Path(__file__).resolve().parent.parent / "data" / "soi_pcm.sh"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(NOI_DUNG, newline="\n")
    ra = sh(["push", str(p), "/data/local/tmp/soi_pcm.sh"])
    if "1 file pushed" not in ra:
        print("KHÔNG PUSH ĐƯỢC:", ra)
        return 1
    print(sh(["shell", "su -c 'chmod 755 /data/local/tmp/soi_pcm.sh; "
                       "/data/local/tmp/soi_pcm.sh'"], t=180))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
