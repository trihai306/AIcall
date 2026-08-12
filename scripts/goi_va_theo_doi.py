"""Goi va theo doi trong CUNG mot tien trinh - khong co khoang ho.

Lan truoc goi o mot lenh, theo doi o lenh khac, giua hai lenh mat gan mot phut
nen cuoc goi da tat truoc khi bat dau nhin. Gop lai de thay tu giay dau.
"""
import json
import re
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SERIAL = "21f10e44220c7ece"
SO = "0396130621"
_TT = re.compile(r"\b(DIALING|ACTIVE|RINGING|DISCONNECTED|ON_HOLD)\b")


def adb(*a, cho=25):
    return subprocess.run(["adb", "-s", SERIAL, *a],
                          capture_output=True, text=True, timeout=cho).stdout


def trang_thai():
    for d in adb("shell", "dumpsys telecom").splitlines():
        if "TelephonyConnectionService" in d:
            m = _TT.search(d)
            if m:
                return m.group(1)
    return "chua-co"


def cau():
    with urllib.request.urlopen(
            "http://127.0.0.1:8100/api/devices/voice/status", timeout=15) as r:
        c = (json.loads(r.read()).get("calls") or [{}])[0]
    return c.get("turns", 0), c.get("khach_noi", ""), c.get("ai_noi", ""), c.get("last_error", "")


# Danh thuc + mo khoa truoc: man hinh khoa nuot lenh goi ma van bao thanh cong.
adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
time.sleep(0.8)
adb("shell", "input", "swipe", "540", "1800", "540", "700", "200")
time.sleep(1.2)

print(f"BAM GOI {SO}")
adb("shell", f"am start -a android.intent.action.CALL -d tel:{SO}")

truoc = None
for i in range(40):
    tt = trang_thai()
    luot, khach, ai, loi = cau()
    if tt != truoc or khach or ai or loi:
        print(f"{i*3:>3}s  {tt:<14} luot={luot}"
              + (f"  khach='{khach[:50]}'" if khach else "")
              + (f"  AI='{ai[:60]}'" if ai else "")
              + (f"  LOI={loi[:60]}" if loi else ""))
        truoc = tt
    if tt in ("DISCONNECTED", "chua-co") and i > 4:
        print("   -> cuoc goi da ket thuc")
        break
    time.sleep(3)
