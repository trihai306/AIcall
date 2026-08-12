"""Mở màn hình cài đặt mạng di động rồi chụp lại xem có mục VoLTE không."""
import subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False, t=40):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

# Đánh thức và mở khoá màn hình - không có màn hình bật thì chụp ra màn đen
sh("input keyevent KEYCODE_WAKEUP")
time.sleep(1)
sh("input keyevent KEYCODE_MENU")
time.sleep(1)

print("Thử các đường mở màn hình mạng di động:")
duong = [
    ("android.settings.NETWORK_OPERATOR_SETTINGS", None),
    ("android.settings.DATA_ROAMING_SETTINGS", None),
    (None, "com.android.phone/.MobileNetworkSettings"),
    (None, "com.samsung.android.app.telephonyui/.callsettings.ui.CallSettingsActivity"),
]
for action, comp in duong:
    if action:
        out = sh(f"am start -a {action}")
        ten = action
    else:
        out = sh(f"am start -n {comp}")
        ten = comp
    ok = "Error" not in out and "Exception" not in out
    print(f"  {'OK  ' if ok else 'HỎNG'} {ten}")
    if ok:
        time.sleep(2)
        break

time.sleep(2)
print("\nMàn hình đang hiện:")
print("  " + sh("dumpsys activity activities | grep -m1 mResumedActivity").strip()[:140])

print("\nNội dung chữ trên màn hình (tìm VoLTE):")
sh("uiautomator dump /sdcard/ui.xml", t=60)
xml = sh("cat /sdcard/ui.xml", t=60)
import re
chu = re.findall(r'text="([^"]{2,60})"', xml)
for t in chu:
    print(f"  {t}")
volte = [t for t in chu if re.search(r"volte|vo-?lte|cu[oộ]c g[oọ]i|4g|nâng cao", t, re.I)]
print("\n=> Mục liên quan VoLTE:", volte if volte else "KHÔNG THẤY trên màn này")
