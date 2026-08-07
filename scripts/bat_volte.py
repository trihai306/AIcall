"""Bật VoLTE trên máy phone farm. Ghi lại giá trị cũ để hoàn tác được.

Ba việc, từ nhẹ tới nặng:
  1. settings global volte_vt_enabled = 1   (không cần root, hiệu lực ngay)
  2. persist.dbg.volte_avail_ovr = 1        (cần root, hiện mục VoLTE trong Cài đặt)
  3. bật/tắt chế độ máy bay                 (ép đăng ký lại IMS, không cần khởi động lại)
"""
import subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False, t=40):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

print("GIÁ TRỊ CŨ (ghi lại để hoàn tác):")
cu = {}
for k in ("volte_vt_enabled", "vt_ims_enabled", "wfc_ims_enabled"):
    cu[k] = sh(f"settings get global {k}")
    print(f"  settings global {k:<22} = {cu[k]}")
cu["ovr"] = sh("getprop persist.dbg.volte_avail_ovr")
print(f"  persist.dbg.volte_avail_ovr        = {cu['ovr'] or '(trống)'}")

print("\n1) Bật volte_vt_enabled")
print("  " + (sh("settings put global volte_vt_enabled 1") or "(im lặng = ok)"))
print(f"  đọc lại: {sh('settings get global volte_vt_enabled')}")

print("\n2) Bật cờ hiện mục VoLTE (cần root)")
print("  " + (sh("setprop persist.dbg.volte_avail_ovr 1", root=True) or "(im lặng = ok)"))
print(f"  đọc lại: {sh('getprop persist.dbg.volte_avail_ovr') or '(trống)'}")

print("\n3) Ép đăng ký lại IMS bằng chế độ máy bay")
sh("settings put global airplane_mode_on 1")
sh("am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true", root=True)
time.sleep(6)
sh("settings put global airplane_mode_on 0")
sh("am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false", root=True)
print("  đã bật/tắt, chờ mạng bắt lại ...")
for i in range(12):
    time.sleep(5)
    mang = sh("getprop gsm.network.type")
    if "LTE" in mang:
        print(f"  sau {(i+1)*5}s: mạng = {mang}")
        break
else:
    print(f"  sau 60s: mạng = {sh('getprop gsm.network.type')}")

print("\nKẾT QUẢ")
ims = sh("dumpsys telephony.registry | grep -i -E 'mImsRegistered|VoLteServiceState'")
print("  " + (ims.replace("\n", "\n  ") or "(không đọc được)"))
print(f"  volte_vt_enabled = {sh('settings get global volte_vt_enabled')}")
print(f"  mạng             = {sh('getprop gsm.network.type')}")

print("\nHOÀN TÁC NẾU CẦN:")
print(f"  adb shell settings put global volte_vt_enabled {cu['volte_vt_enabled']}")
ovr_cu = cu["ovr"] if cu["ovr"] else '""'
print("  adb shell su -c 'setprop persist.dbg.volte_avail_ovr " + ovr_cu + "'")
