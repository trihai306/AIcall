"""Kiểm cuộc gọi còn chạy không; còn thì đo codec rồi cúp máy."""
import re, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

d = sh("dumpsys telephony.registry")
trang = [int(m) for m in re.findall(r"mCallState=(\d)", d)]
dang_goi = 2 in trang or 1 in trang
print(f"Trạng thái khe: {trang}  ->  {'ĐANG GỌI' if dang_goi else 'đã kết thúc'}")

if dang_goi:
    print(f"mạng lúc gọi: {sh('getprop gsm.network.type')}")
    for l in d.splitlines():
        if "getRilVoiceRadioTechnology" in l:
            m = re.findall(r"getRilVoiceRadioTechnology=\d+\((\w+)\)", l)
            print(f"sóng thoại  : {', '.join(m) if m else '?'}")
            break
    print("\nCÚP MÁY")
    sh("input keyevent KEYCODE_ENDCALL")
    time.sleep(2)
    trang = [int(m) for m in re.findall(r"mCallState=(\d)", sh("dumpsys telephony.registry"))]
    print(f"  sau khi cúp: {trang}")

time.sleep(2)
print("\nNHẬT KÝ CUỘC GỌI (3 mới nhất)")
out = sh("content query --uri content://call_log/calls "
         "--projection number:date:duration:type", root=True)
LOAI = {"1": "gọi đến", "2": "gọi đi", "3": "nhỡ", "5": "bị từ chối"}
for l in out.splitlines()[-3:]:
    so = re.search(r"number=([^,]*)", l)
    dt = re.search(r"date=(\d+)", l)
    du = re.search(r"duration=(\d+)", l)
    ty = re.search(r"type=(\d+)", l)
    if not dt:
        continue
    khi = time.strftime("%H:%M:%S", time.localtime(int(dt.group(1)) / 1000))
    giay = int(du.group(1)) if du else 0
    print(f"  {khi}  {so.group(1) if so else '?':<14}"
          f" {LOAI.get(ty.group(1) if ty else '', '?'):<10} {giay}s"
          + ("  -> NỐI ĐƯỢC" if giay > 0 else "  -> không nối / không ai nghe"))

print(f"\nmạng sau cuộc gọi: {sh('getprop gsm.network.type')}")
