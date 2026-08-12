"""Xem cuộc gọi còn chạy không, và mạng đang ở loại nào — đọc TỪNG khe."""
import re, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

d = sh("dumpsys telephony.registry")
ten = {0: "rảnh", 1: "đang đổ chuông", 2: "đang trong cuộc gọi"}
trang = [int(m) for m in re.findall(r"mCallState=(\d)", d)]
print("Trạng thái cuộc gọi theo từng khe:")
for i, t in enumerate(trang, 1):
    print(f"  khe {i}: {ten.get(t, t)}")

print(f"\nmạng hiện tại : {sh('getprop gsm.network.type')}")
for l in d.splitlines():
    if "getRilVoiceRadioTechnology" in l:
        m = re.findall(r"getRilVoiceRadioTechnology=\d+\((\w+)\)", l)
        if m:
            print(f"sóng thoại    : {', '.join(m)}")
        break

print("\nCuộc gọi trong telecom:")
tc = sh("dumpsys telecom | grep -m6 -i -E 'mCallState|Call id|isRinging|connectTime'")
print("  " + (tc.replace("\n", "\n  ")[:500] if tc else "(không có cuộc gọi nào)"))

print("\nÂm thanh:")
print("  " + (sh("dumpsys audio | grep -m2 -i 'ring or call'").strip() or "(không đọc được)"))
