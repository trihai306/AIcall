"""Danh thuc + vuot mo khoa roi moi goi.

BAY DA MAC: lenh goi ban ra khi may dang o man hinh khoa thi bi nuot, ma API
van bao "dialed: true" vi no chi bao "da gui lenh", khong bao "da ket noi".
Nhin ben ngoai y het nhu khach khong bat may.
"""
import json
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "http://127.0.0.1:8100"
DEV = "dev_643aeac5"
SERIAL = "21f10e44220c7ece"
SO = "0396130621"


def adb(*args):
    return subprocess.run(["adb", "-s", SERIAL, *args],
                          capture_output=True, text=True, timeout=30).stdout.strip()


def api(duong, du_lieu=None, cho=120):
    req = urllib.request.Request(
        API + duong,
        data=json.dumps(du_lieu).encode() if du_lieu is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if du_lieu is not None else "GET")
    with urllib.request.urlopen(req, timeout=cho) as r:
        return json.loads(r.read())


print("[1] Danh thuc man hinh")
adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
time.sleep(1)
print("[2] Vuot len de mo khoa")
adb("shell", "input", "swipe", "540", "1800", "540", "700", "200")
time.sleep(1.5)

kg = adb("shell", "dumpsys window | grep -E 'mDreamingLockscreen|mShowingLockscreen'")
print(f"    trang thai khoa: {kg or '(khong doc duoc)'}")

print(f"\n[3] Bam goi {SO}")
kq = api(f"/api/devices/{DEV}/test-call", {"number": SO})
print("   ", json.dumps(kq, ensure_ascii=False)[:200])

print("\n[4] Theo doi 40 giay")
for i in range(20):
    time.sleep(2)
    tt = api(f"/api/devices/{DEV}/call-state")
    vs = api("/api/devices/voice/status")
    c = vs.get("calls") or [{}]
    print(f"   {i*2+2:>2}s  goi={tt.get('state','?'):<12} luot={c[0].get('turns','?')} "
          f"khach='{c[0].get('khach_noi','')[:30]}' ai='{c[0].get('ai_noi','')[:40]}'")
    if tt.get("state") not in ("idle", "?", ""):
        print(f"        -> {tt}")
