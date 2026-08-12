"""Goi, doi bat may, roi ban tieng bip thang vao duong tiem.

Phep thu tach bach: bip di theo DUNG duong ma tieng AI se di (_out cua cau
noi). Nghe duoc bip => duong tiem thong, chi hong chieu thu. Khong nghe duoc
=> hong ca hai chieu. Mot cau tra loi cua anh la khoanh duoc dung nua nao.
"""
import json
import re
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SERIAL = "21f10e44220c7ece"
DEV = "dev_643aeac5"
SO = "0396130621"
API = "http://127.0.0.1:8100"
_TT = re.compile(r"\b(DIALING|ACTIVE|RINGING|DISCONNECTED)\b")


def adb(*a, cho=30):
    return subprocess.run(["adb", "-s", SERIAL, *a],
                          capture_output=True, text=True, timeout=cho).stdout


def api(duong, du_lieu=None, cho=60):
    req = urllib.request.Request(
        API + duong,
        data=json.dumps(du_lieu).encode() if du_lieu is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if du_lieu is not None else "GET")
    with urllib.request.urlopen(req, timeout=cho) as r:
        return json.loads(r.read())


def trang_thai():
    for d in adb("shell", "dumpsys telecom").splitlines():
        if "TelephonyConnectionService" in d:
            m = _TT.search(d)
            if m:
                return m.group(1)
    return "chua-co"


vs = api("/api/devices/voice/status")
print(f"cau noi: {json.dumps(vs, ensure_ascii=False)[:150]}")
if not vs.get("calls"):
    print("Cau noi chua chay - mo lai")
    kq = api(f"/api/devices/{DEV}/voice/start",
             {"src": 4, "inject": True, "port": 8123, "customer_name": "Anh Hai"})
    print(f"  {json.dumps(kq, ensure_ascii=False)[:200]}")

adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
time.sleep(0.8)
adb("shell", "input", "swipe", "540", "1800", "540", "700", "200")
time.sleep(1.2)
print(f"\nBAM GOI {SO} - nhac may roi nghe ky")
adb("shell", f"am start -a android.intent.action.CALL -d tel:{SO}")

for i in range(25):
    time.sleep(2)
    if trang_thai() == "ACTIVE":
        print(f"  da bat may sau {i*2+2}s")
        break
    if trang_thai() in ("DISCONNECTED", "chua-co") and i > 3:
        sys.exit("  cuoc goi tat truoc khi bat may")
else:
    sys.exit("  khong ai bat may")

time.sleep(1.5)
for lan in range(3):
    print(f"\n>>> BAN BIP lan {lan+1} (1000Hz, 2 giay) <<<")
    kq = api(f"/api/devices/{DEV}/voice/probe",
             {"burst_ms": 2000, "freq": 1000.0, "amp": 20000}, cho=60)
    print(f"    {json.dumps(kq, ensure_ascii=False)[:250]}")
    time.sleep(2)

print("\nGiu cuoc goi them 10 giay")
time.sleep(10)
