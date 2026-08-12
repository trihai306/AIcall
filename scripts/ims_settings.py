"""Thử app cấu hình IMS riêng của Samsung, và xem cấu hình nhà mạng nằm ở đâu."""
import re, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

print("1) CÁC MÀN HÌNH TRONG APP IMS SETTINGS CỦA SAMSUNG")
out = sh("dumpsys package com.samsung.advp.imssettings | grep -i -A2 'Activity Resolver\\|com.samsung.advp.imssettings/'", t=60)
acts = sorted(set(re.findall(r"(com\.samsung\.advp\.imssettings/[\w.$]+)", out)))
for a in acts[:12]:
    print(f"  {a}")
if not acts:
    print("  (không liệt kê được)")

print("\n2) CẤU HÌNH NHÀ MẠNG NẰM Ở ĐÂU (OMC/CSC)")
for d in ("/odm/omc", "/optics", "/system/omc", "/prism", "/carrier"):
    ra = sh(f"ls {d} 2>/dev/null", root=True)
    print(f"  {d:<16} {ra.replace(chr(10), ' ') if ra else '(không có)'}")

print("\n3) MÃ VÙNG ĐANG ÁP DỤNG")
for k in ("ro.csc.omcnw_code", "ro.omc.omcnw_code", "persist.sys.omc_path",
          "ril.nwk_setting", "ro.boot.sales_code", "ro.build.characteristics"):
    print(f"  {k:<28} {sh(f'getprop {k}') or '(trống)'}")

print("\n4) TỆP CẤU HÌNH VoLTE CỦA SAMSUNG")
for p in ("/system/etc/ims/", "/odm/etc/ims/", "/data/user_de/0/com.sec.imsservice/"):
    ra = sh(f"ls -1 {p} 2>/dev/null | head -8", root=True)
    print(f"  {p:<38} {ra.replace(chr(10), ', ') if ra else '(không có)'}")

print("\n5) THỬ MỞ APP IMS SETTINGS")
for comp in ("com.samsung.advp.imssettings/.MainActivity",
             "com.samsung.advp.imssettings/.ImsSettingsActivity",
             "com.samsung.advp.imssettings/.SettingsActivity"):
    o = sh(f"am start -n {comp}")
    ok = "Error" not in o and "Exception" not in o
    print(f"  {'MỞ ĐƯỢC' if ok else 'không'} {comp}")
    if ok:
        time.sleep(3)
        sh("uiautomator dump /sdcard/ui2.xml")
        xml = sh("cat /sdcard/ui2.xml")
        chu = re.findall(r'text="([^"]{2,50})"', xml)
        print("    nội dung:", ", ".join(chu[:14]) or "(trống)")
        break
