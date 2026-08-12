"""Kéo tệp cấu hình nhà mạng về rồi đọc bằng Python — tránh địa ngục dấu nháy shell."""
import re, subprocess, sys, tempfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=True, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

d = Path(tempfile.mkdtemp())
for ten in ("cscfeature.xml", "cscfeature_network.xml"):
    # copy sang chỗ đọc được rồi pull, vì /odm cần root mà adb pull thì không có
    sh(f"cp /odm/omc/XXV/conf/{ten} /data/local/tmp/{ten}")
    sh(f"chmod 644 /data/local/tmp/{ten}")
    subprocess.run(["adb","-s",S,"pull",f"/data/local/tmp/{ten}",str(d/ten)],
                   capture_output=True, timeout=60)
    p = d / ten
    if not p.exists():
        print(f"{ten}: không kéo về được")
        continue
    noi_dung = p.read_text(encoding="utf-8", errors="replace")
    print(f"\n=== {ten} ({len(noi_dung)} ký tự) ===")
    dong = [l.strip() for l in noi_dung.splitlines()
            if re.search(r"volte|ims|vowifi|rcs|4g", l, re.I)]
    if dong:
        for l in dong[:22]:
            print(f"  {l[:130]}")
    else:
        print("  (không có dòng nào nhắc VoLTE/IMS)")
    sh(f"rm -f /data/local/tmp/{ten}")

print("\n=== VÌ SAO OMC KHÔNG NẠP ===")
print(f"  model máy      : {sh('getprop ro.product.model', root=False)}")
print(f"  CSC dành cho   : {sh('cat /odm/omc/CSCVersion.txt')}")
print(f"  firmware máy   : {sh('getprop ro.build.PDA', root=False) or sh('getprop ro.build.display.id', root=False)}")
print(f"  mã đã chọn     : {sh('cat /odm/omc/sales_code.dat')}")
print(f"  ro.csc.sales_code = {sh('getprop ro.csc.sales_code', root=False) or '(trống)'}")
