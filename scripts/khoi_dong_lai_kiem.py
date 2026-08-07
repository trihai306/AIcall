"""Khởi động lại máy để cờ persist.dbg.volte_avail_ovr có hiệu lực, rồi kiểm."""
import subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    try:
        r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
        return ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:
        return f"(lỗi {e})"

print("Khởi động lại máy ...")
subprocess.run(["adb","-s",S,"reboot"], capture_output=True, timeout=30)
time.sleep(10)

print("Chờ máy khởi động xong ...")
subprocess.run(["adb","-s",S,"wait-for-device"], capture_output=True, timeout=180)
for i in range(30):
    if sh("getprop sys.boot_completed").strip() == "1":
        print(f"  xong sau ~{10 + i*5}s")
        break
    time.sleep(5)
else:
    print("  hết giờ chờ boot_completed")

print("\nChờ mạng bắt lại và IMS đăng ký (tối đa 2 phút) ...")
for i in range(24):
    time.sleep(5)
    d = sh("dumpsys telephony.registry")
    reg = "mImsRegistered=true" in d
    mang = sh("getprop gsm.network.type")
    if reg:
        print(f"  sau {(i+1)*5}s: IMS ĐÃ ĐĂNG KÝ | mạng {mang}")
        break
    if (i + 1) % 6 == 0:
        print(f"  sau {(i+1)*5}s: chưa đăng ký | mạng {mang}")

print("\nKẾT QUẢ SAU KHỞI ĐỘNG LẠI")
print(f"  persist.dbg.volte_avail_ovr = {sh('getprop persist.dbg.volte_avail_ovr') or '(trống)'}")
print(f"  volte_vt_enabled            = {sh('settings get global volte_vt_enabled')}")
print(f"  mạng                        = {sh('getprop gsm.network.type')}")
d = sh("dumpsys telephony.registry")
print(f"  IMS đăng ký                 = {'CÓ' if 'mImsRegistered=true' in d else 'CHƯA'}")
for l in d.splitlines():
    if "VoLteServiceState" in l:
        print(f"  {l.strip()}")
        break
print("\n  cấu hình nhà mạng:")
cc = sh("dumpsys carrier_config | grep -i -E 'carrier_volte_available_bool|carrier_volte_provisioned_bool'")
print("  " + (cc.replace("\n", "\n  ") if cc else "(không đọc được)"))
