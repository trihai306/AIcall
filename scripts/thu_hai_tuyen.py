"""Mot cuoc goi, thu CA HAI tuyen tiem tieng - do phai goi lam hai lan.

Tuyen A "codec": tron trong codec o AIF1TX1 Input 2  (dang dung, khong nghe thay)
Tuyen B "usb"  : duong thiet bi ngoai cua Samsung + co ERAP

Moi tuyen ban 3 tieng bip khac tan so de phan biet duoc khi nghe:
  tuyen A = 1000Hz (bip thap)
  tuyen B = 1800Hz (bip cao)
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
MIXCTL = "/data/local/tmp/mixctl"
_TT = re.compile(r"\b(DIALING|ACTIVE|RINGING|DISCONNECTED)\b")

TUYEN_USB = ([(f"ABOX SPUS OUT{i}", "SIFS2") for i in range(6)] +
             [("ABOX SIFS2", "SPUS OUT0"), ("ABOX NSRC1", "SIFS2"),
              ("ABOX SIFM1", "WDMA"), ("ABOX ERAP info USB On", "1"),
              ("ABOX UAIF0 SPK", "RESERVED")] +
             [(f"AIF1TX{tx} Input {i}", "None") for tx in (1, 2) for i in (1, 2, 3, 4)])


def adb(*a, cho=40):
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


def bip(f, lan):
    for i in range(lan):
        kq = api(f"/api/devices/{DEV}/voice/probe",
                 {"burst_ms": 1500, "freq": f, "amp": 22000}, cho=60)
        print(f"    bip {i+1}: dem_may={kq.get('dem_may_ms')}ms vong={kq.get('vong_ms')}")
        time.sleep(1.5)


if not api("/api/devices/voice/status").get("calls"):
    print("Mo cau noi")
    print("  " + json.dumps(api(f"/api/devices/{DEV}/voice/start",
          {"src": 4, "inject": True, "port": 8123, "customer_name": "Anh Hai"}),
          ensure_ascii=False)[:180])

adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
time.sleep(0.8)
adb("shell", "input", "swipe", "540", "1800", "540", "700", "200")
time.sleep(1.2)
print(f"\nBAM GOI {SO}")
adb("shell", f"am start -a android.intent.action.CALL -d tel:{SO}")

for i in range(30):
    time.sleep(2)
    tt = trang_thai()
    if tt == "ACTIVE":
        print(f"  bat may sau {i*2+2}s")
        break
    if tt in ("DISCONNECTED", "chua-co") and i > 4:
        sys.exit("  cuoc goi tat truoc khi bat may")
else:
    sys.exit("  khong ai bat may")

time.sleep(1.5)
print("\n>>> TUYEN A (codec) - 3 tieng bip THAP 1000Hz <<<")
bip(1000.0, 3)

print("\n=== Chuyen sang TUYEN B (usb) ===")
lenh = "; ".join(f'{MIXCTL} set "{t}" "{g}"' for t, g in TUYEN_USB)
out = adb("shell", f"su -c '{lenh}'", cho=45)
print(f"    dat {out.count('da dat')}/{len(TUYEN_USB)} control")
time.sleep(1)

print("\n>>> TUYEN B (usb) - 3 tieng bip CAO 1800Hz <<<")
bip(1800.0, 3)

print("\nGiu them 8 giay")
time.sleep(8)
print(f"trang thai cuoi: {trang_thai()}")
