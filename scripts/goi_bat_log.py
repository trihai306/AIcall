"""Gọi và bắt log telecom ngay lúc đó để lấy lý do cuộc gọi hỏng."""
import re, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"
SO = "0396130621"

def sh(cmd, root=False, t=90):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

sh("logcat -c")
sh("input keyevent KEYCODE_WAKEUP")
time.sleep(1)

print(f"Gọi {SO} ...")
sh(f"am start -a android.intent.action.CALL -d tel:{SO}")

for i in range(10):
    time.sleep(3)
    d = sh("dumpsys telephony.registry")
    trang = [int(m) for m in re.findall(r"mCallState=(\d)", d)]
    mang = sh("getprop gsm.network.type")
    print(f"  {i*3:>2}s: khe={trang} mạng={mang}")
    if 2 in trang:
        print("  -> ĐÃ NỐI MÁY")
        break

print("\nLOG TELECOM / RIL trong lúc gọi:")
lg = sh("logcat -d -v brief")
quan_tam = []
for l in lg.splitlines():
    if re.search(r"disconnect|DisconnectCause|CallFailCause|dial|Dial|emergency|denied|reject|barred",
                 l, re.I) and len(l) < 220:
        quan_tam.append(l.strip())
for l in quan_tam[-18:]:
    print(f"  {l[:200]}")
if not quan_tam:
    print("  (không thấy dòng nào liên quan)")
