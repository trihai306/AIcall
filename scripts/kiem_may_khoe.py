"""Máy có còn khoẻ sau khi khởi động lại không - gọi được, root được, ADB được."""
import subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=60)
    return ((r.stdout or "") + (r.stderr or "")).strip()

r = subprocess.run(["adb","devices"], capture_output=True, text=True, timeout=30)
print("ADB :", "OK" if S in (r.stdout or "") else "KHÔNG THẤY MÁY")
print("root:", "OK" if "uid=0" in sh("id", root=True) else "KHÔNG")
print("SIM :", sh("getprop gsm.sim.state"), "| nhà mạng", sh("getprop gsm.operator.alpha"))
print("mạng:", sh("getprop gsm.network.type"))

d = sh("dumpsys telephony.registry")
for ten, khoa in (("trạng thái dịch vụ", "mServiceState"), ("trạng thái cuộc gọi", "mCallState")):
    dong = [l.strip() for l in d.splitlines() if khoa in l]
    print(f"{ten}: {dong[0][:120] if dong else '(không thấy)'}")

print("\nApp cầu tiếng:", "còn cài" if "voicebridge" in sh("pm list packages | grep voicebridge") else "KHÔNG CÒN")
print("Module Magisk:", sh("ls /data/adb/modules 2>/dev/null", root=True).replace("\n", ", ") or "(không có)")
