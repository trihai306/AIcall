"""Máy có sóng không - đọc TỪNG khe, đừng lấy dòng đầu."""
import re, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd):
    r = subprocess.run(["adb","-s",S,"shell",cmd], capture_output=True, text=True, timeout=60)
    return ((r.stdout or "") + (r.stderr or "")).strip()

d = sh("dumpsys telephony.registry")
dong = [l.strip() for l in d.splitlines() if "mServiceState=" in l]
print(f"Có {len(dong)} khe báo trạng thái dịch vụ:\n")
for i, l in enumerate(dong, 1):
    voice = re.search(r"mVoiceRegState=\d+\((\w+)\)", l)
    data = re.search(r"mDataRegState=\d+\((\w+)\)", l)
    op = re.search(r"mOperatorAlphaLong=(\w*)", l)
    rat = re.search(r"getRilVoiceRadioTechnology=\d+\((\w+)\)", l)
    print(f"  khe {i}: thoại={voice.group(1) if voice else '?':<16}"
          f" dữ liệu={data.group(1) if data else '?':<16}"
          f" nhà mạng={op.group(1) if op else '(trống)':<10}"
          f" sóng={rat.group(1) if rat else '?'}")

print(f"\nCường độ sóng:")
for l in d.splitlines():
    if "mSignalStrength" in l:
        m = re.search(r"(\d+) dBm", l)
        print(f"  {m.group(0) if m else l.strip()[:100]}")
        break

print(f"\ngsm.sim.state       : {sh('getprop gsm.sim.state')}")
print(f"gsm.operator.alpha  : {sh('getprop gsm.operator.alpha')}")
print(f"gsm.network.type    : {sh('getprop gsm.network.type')}")
print(f"gsm.operator.isroaming: {sh('getprop gsm.operator.isroaming')}")

co_song = any("IN_SERVICE" in l for l in dong)
print("\n=> " + ("CÓ SÓNG, gọi được" if co_song
                else "KHÔNG KHE NÀO CÓ SÓNG - cần xem lại"))
