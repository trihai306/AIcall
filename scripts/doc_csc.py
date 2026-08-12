"""Đọc cơ chế chọn mã vùng (CSC) của Samsung. CHỈ ĐỌC, không ghi gì."""
import subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=True, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

print("1) MÃ ĐANG CHỌN — các tệp Samsung đọc lúc khởi động")
for p in ("/odm/omc/sales_code.dat", "/efs/sales_code.dat",
          "/efs/imei/mps_code.dat", "/efs/FactoryApp/factorymode",
          "/odm/omc/CSCVersion.txt"):
    ra = sh(f"cat {p} 2>/dev/null")
    ton_tai = sh(f"test -f {p} && echo co || echo khong")
    print(f"  {p:<34} [{ton_tai}] {ra[:60] if ra else '(rỗng)'}")

print("\n2) XXV CÓ ĐỦ NỘI DUNG KHÔNG (mã Việt Nam)")
ra = sh("ls -1 /odm/omc/XXV/ 2>/dev/null | head -12")
print("  " + (ra.replace("\n", "\n  ") if ra else "(trống)"))
kt = sh("du -sh /odm/omc/XXV 2>/dev/null")
print(f"  dung lượng: {kt}")

print("\n3) XXV CÓ BẬT VoLTE CHO VIETTEL (45204) KHÔNG")
# cấu hình nhà mạng của Samsung nằm trong các tệp xml theo mã mạng
tim = sh("find /odm/omc/XXV -iname '*45204*' -o -iname '*cscfeature*' 2>/dev/null | head -8")
print("  " + (tim.replace("\n", "\n  ") if tim else "(không thấy tệp theo mã mạng)"))
for f in [l for l in tim.splitlines() if l.strip()][:2]:
    volte = sh(f"grep -i -o -m5 '[^<]*volte[^<]*' '{f}' 2>/dev/null")
    if volte:
        print(f"    trong {f.split('/')[-1]}:")
        print("      " + volte.replace("\n", "\n      ")[:400])

print("\n4) MÃ VÙNG NÀO ĐANG ĐƯỢC NẠP")
for k in ("ro.csc.sales_code", "persist.sys.omc_path", "persist.sys.omc_etcpath",
          "ro.omc.build.version", "persist.omc.sales_code"):
    print(f"  {k:<26} {sh(f'getprop {k}', root=False) or '(trống)'}")

print("\n5) PHÂN VÙNG /efs CÓ GHI ĐƯỢC KHÔNG")
print("  " + sh("mount | grep -i efs").strip()[:140])
