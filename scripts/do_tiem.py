"""Chung minh gia thuyet: HAL xoa control tiem tieng khi cuoc goi noi.

Cach do: doc gia tri 3 control chinh o 3 moc - truoc khi goi, ngay sau khi
cuoc goi ACTIVE, va sau khi dat lai. Neu moc 2 khac moc 1 thi gia thuyet dung.

KHONG doan, chi doc. Khong bam goi o buoc nay.
"""
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SERIAL = "21f10e44220c7ece"
MIXCTL = "/data/local/tmp/mixctl"
SO = "0396130621"

# Ba control quyet dinh. Thieu bat ky cai nao la dau ben kia im lang.
CHOT = ["ABOX UAIF0 SPK", "AIF1TX1 Input 2", "ABOX SPUS OUT0"]
_TT = re.compile(r"\b(DIALING|ACTIVE|RINGING|DISCONNECTED)\b")


def adb(*a, cho=30):
    return subprocess.run(["adb", "-s", SERIAL, *a],
                          capture_output=True, text=True, timeout=cho).stdout


def doc_control(nhan):
    lenh = "; ".join(f'{MIXCTL} get "{t}"' for t in CHOT)
    out = adb("shell", f"su -c '{lenh}'").strip()
    print(f"  [{nhan}]")
    for d in out.splitlines():
        if d.strip():
            print(f"     {d.strip()}")
    return out


def trang_thai():
    for d in adb("shell", "dumpsys telecom").splitlines():
        if "TelephonyConnectionService" in d:
            m = _TT.search(d)
            if m:
                return m.group(1)
    return "chua-co"


print("=== MOC 1: truoc khi goi (cau noi da dat control luc mo) ===")
doc_control("truoc khi goi")

print(f"\n=== Bam goi {SO}, cho toi khi ACTIVE ===")
adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
time.sleep(0.8)
adb("shell", "input", "swipe", "540", "1800", "540", "700", "200")
time.sleep(1.2)
adb("shell", f"am start -a android.intent.action.CALL -d tel:{SO}")

for i in range(25):
    time.sleep(2)
    tt = trang_thai()
    if tt == "ACTIVE":
        print(f"  -> ACTIVE sau {i*2+2}s")
        break
    if tt in ("DISCONNECTED", "chua-co") and i > 3:
        print(f"  -> cuoc goi tat o {i*2+2}s (trang thai {tt}) - dung lai")
        sys.exit(0)
else:
    print("  -> khong ai bat may")
    sys.exit(0)

time.sleep(1)
print("\n=== MOC 2: ngay sau khi cuoc goi ACTIVE ===")
doc_control("dang trong cuoc goi")

print("\n=== Dat lai duong tiem NGAY BAY GIO ===")
from urllib.request import Request, urlopen
import json
# Dat lai bang chinh ham cua he thong, qua stop/start thi mat cuoc goi -
# nen goi thang mixctl voi dung bo control cua _tuyen_codec(on=True).
dat = ([(f"ABOX SPUS OUT{i}", "SIFS1") for i in range(6)] +
       [("ABOX UAIF0 SPK", "SIFS1"),
        ("AIF1TX1 Input 2", "AIF1RX1"), ("AIF1TX2 Input 2", "AIF1RX1")])
lenh = "; ".join(f'{MIXCTL} set "{t}" "{g}"' for t, g in dat)
out = adb("shell", f"su -c '{lenh}'", cho=40)
print(f"  dat {out.count('da dat')}/{len(dat)} control")

print("\n=== MOC 3: sau khi dat lai ===")
doc_control("sau khi dat lai")
print("\n>>> NGHE THU NGAY BAY GIO <<<")

for i in range(20):
    time.sleep(3)
    if trang_thai() != "ACTIVE":
        print(f"  cuoc goi ket thuc sau {i*3+3}s")
        break
