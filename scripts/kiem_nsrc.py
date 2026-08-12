import subprocess
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
S, M = "21f10e44220c7ece", "/data/local/tmp/mixctl"
ten = ["ABOX NSRC1", "ABOX ERAP info USB On"]
lenh = "; ".join(f'{M} get "{t}"' for t in ten)
r = subprocess.run(["adb", "-s", S, "shell", f"su -c '{lenh}'"],
                   capture_output=True, text=True, timeout=40)
print(r.stdout.strip() or (r.stderr or "").strip())
