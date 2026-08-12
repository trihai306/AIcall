"""Theo doi cuoc goi: trang thai may + so luot AI da noi.

Doc thang tu dumpsys telecom chu KHONG dung /api/.../call-state: endpoint do
bao 'idle' trong khi may dang DIALING that - da bat duoc o lan thu nay.
"""
import json
import re
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SERIAL = "21f10e44220c7ece"

_TT = re.compile(r"\b(DIALING|ACTIVE|RINGING|DISCONNECTED|ON_HOLD)\b")


def trang_thai():
    r = subprocess.run(["adb", "-s", SERIAL, "shell", "dumpsys telecom"],
                       capture_output=True, text=True, timeout=25)
    for d in r.stdout.splitlines():
        if "TelephonyConnectionService" in d:
            m = _TT.search(d)
            if m:
                return m.group(1)
    return "khong-co-cuoc-goi"


def cau_noi():
    with urllib.request.urlopen(
            "http://127.0.0.1:8100/api/devices/voice/status", timeout=15) as r:
        c = (json.loads(r.read()).get("calls") or [{}])[0]
    return c.get("turns", 0), c.get("khach_noi", ""), c.get("ai_noi", ""), c.get("last_error", "")


truoc = None
for i in range(30):
    tt = trang_thai()
    luot, khach, ai, loi = cau_noi()
    if tt != truoc or khach or ai:
        print(f"{i*3:>3}s  {tt:<18} luot={luot}")
        if khach: print(f"      khach: {khach[:80]}")
        if ai:    print(f"      AI   : {ai[:80]}")
        if loi:   print(f"      LOI  : {loi[:80]}")
        truoc = tt
    if tt == "DISCONNECTED" or tt == "khong-co-cuoc-goi":
        if i > 3:
            print("   -> cuoc goi ket thuc")
            break
    time.sleep(3)
