"""Goi va cho AI DOC that bang giong vua train.

Khac han may lan truoc: khong ban tieng bip nua. Bo ma thoai dung cho tieng
NOI nen tong thuan luon meo - bip khong noi len gi ve chat giong.
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

CAU = [
    "Dạ em chào anh, em gọi từ ngân hàng ạ.",
    "Dạ bên em đang có gói vay tín chấp, lãi suất sáu phẩy năm phần trăm một năm ạ.",
    "Dạ thủ tục đơn giản, giải ngân trong vòng hai mươi bốn giờ, anh có muốn nghe thêm không ạ.",
]


def adb(*a, cho=40):
    return subprocess.run(["adb", "-s", SERIAL, *a],
                          capture_output=True, text=True, timeout=cho).stdout


def api(duong, du_lieu=None, cho=120):
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


def cau_noi_song():
    c = api("/api/devices/voice/status").get("calls") or []
    return bool(c) and c[0].get("running")


if not cau_noi_song():
    print("Mo cau noi")
    kq = api(f"/api/devices/{DEV}/voice/start",
             {"src": 4, "inject": True, "port": 8123, "customer_name": "Anh Hai"})
    print("  " + json.dumps(kq, ensure_ascii=False)[:180])
    if kq.get("error"):
        sys.exit("khong mo duoc cau noi")

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

time.sleep(1.0)
for n, text in enumerate(CAU, 1):
    # Kiem cau noi con song TRUOC moi cau: lan truoc no dong giua chung ma
    # script van ban tiep vao hu khong roi bao "khong gui duoc".
    if not cau_noi_song():
        print(f"  cau noi da dong truoc cau {n} - dung")
        break
    print(f"\n>>> AI DOC cau {n}: {text}")
    kq = api(f"/api/devices/{DEV}/voice/say", {"text": text}, cho=120)
    print(f"    {json.dumps(kq, ensure_ascii=False)[:200]}")
    # Doi cho doc het roi moi doc cau sau: khong doi thi ba cau chong len nhau.
    time.sleep(len(text) * 0.10 + 2.5)

print("\nGiu cuoc goi them 8 giay")
time.sleep(8)
print(f"trang thai cuoi: {trang_thai()}")
