"""Khởi động lại dịch vụ IMS mà không khởi động cả máy, rồi xem có đăng ký không."""
import subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

def trang_thai():
    d = sh("dumpsys telephony.registry")
    reg = "mImsRegistered=true" in d
    vol = [l.strip() for l in d.splitlines() if "VoLteServiceState" in l]
    return reg, (vol[0] if vol else "(không thấy)")

print("TRƯỚC:")
r, v = trang_thai()
print(f"  IMS đăng ký: {r} | {v}")

print("\nKhởi động lại các gói IMS của Samsung ...")
for pkg in ("com.sec.imsservice", "com.sec.ims", "com.sec.epdgtestapp"):
    out = sh(f"am force-stop {pkg}", root=True)
    print(f"  force-stop {pkg}: {out or 'ok'}")

print("\nBật/tắt dữ liệu di động để ép nối lại ...")
sh("svc data disable", root=True)
time.sleep(3)
sh("svc data enable", root=True)

print("Chờ IMS đăng ký (tối đa 90s) ...")
for i in range(18):
    time.sleep(5)
    r, v = trang_thai()
    if r:
        print(f"  sau {(i+1)*5}s: ĐÃ ĐĂNG KÝ")
        break
    if (i + 1) % 4 == 0:
        print(f"  sau {(i+1)*5}s: chưa | {v}")
else:
    print("  hết 90s vẫn chưa đăng ký")

print("\nSAU:")
r, v = trang_thai()
print(f"  IMS đăng ký: {r}")
print(f"  {v}")
print(f"  mạng: {sh('getprop gsm.network.type')}")

print("\nNHÀ MẠNG CÓ CẤP VoLTE CHO SIM NÀY KHÔNG")
# Cấu hình nhà mạng: nếu carrier config tắt VoLTE thì máy có bật kiểu gì cũng vô ích
cc = sh("dumpsys carrier_config | grep -i -E 'volte|ims|enhanced_4g' | head -20")
print("  " + (cc.replace("\n", "\n  ") if cc else "(không đọc được carrier_config)"))
