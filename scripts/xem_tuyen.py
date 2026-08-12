"""Doc trang thai mixer de biet dang o TUYEN NAO.

codec: UAIF0 SPK=SIFS1, AIF1TX1 Input 2=AIF1RX1, SPUS OUT0=SIFS1
usb  : UAIF0 SPK=RESERVED, AIF1TX1 Input 2=None,  SPUS OUT0=SIFS2
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
S, M = "21f10e44220c7ece", "/data/local/tmp/mixctl"
TEN = ["ABOX UAIF0 SPK", "AIF1TX1 Input 2", "AIF1TX2 Input 2", "ABOX SPUS OUT0"]

lenh = "; ".join(f'{M} get "{t}"' for t in TEN)
r = subprocess.run(["adb", "-s", S, "shell", f"su -c '{lenh}'"],
                   capture_output=True, text=True, timeout=40)
print(r.stdout.strip())
print("---")
out = r.stdout
if "SIFS1" in out and "AIF1RX1" in out:
    print("=> DANG O TUYEN CODEC (dung mac dinh)")
elif "SIFS2" in out or "RESERVED" in out:
    print("=> DANG O TUYEN USB (con sot lai tu phep thu) hoac DA TAT")
else:
    print("=> khong doan duoc")
