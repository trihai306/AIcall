"""Điện thoại có nối hồ sơ rảnh tay (HFP) với máy tính không?

Hướng mới: thay vì giành tuyến trộn với HAL, dùng đúng đường Android sinh ra cho
việc này - khi có thiết bị rảnh tay Bluetooth, hệ thống tự đẩy CẢ HAI CHIỀU tiếng
cuộc gọi sang đó. Máy tính Windows đã ghép đôi sẵn và hiện "Galaxy S9+ Hands-Free
HF Audio", nghĩa là nó đóng được vai thiết bị rảnh tay.

Cần xác nhận phía điện thoại: hồ sơ HFP có ĐANG NỐI không, và Telecom có thấy
tuyến Bluetooth trong danh sách chọn không.

    python scripts/kiem_bluetooth.py
"""

import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERIAL = "21f10e44220c7ece"


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def main() -> int:
    print("=== Bluetooth có bật không ===")
    print("   ", sh("settings get global bluetooth_on") or "?")

    print("\n=== Thiết bị đã ghép đôi / đang nối ===")
    bm = sh("dumpsys bluetooth_manager")
    for dong in bm.splitlines():
        s = dong.strip()
        if re.search(r"Bonded|Connected|State|Profile|mAdapter|address", s, re.I) \
                and len(s) < 160:
            print("   ", s[:150])

    print("\n=== Hồ sơ HEADSET (HFP) ===")
    thay = False
    for dong in bm.splitlines():
        if re.search(r"headset|hfp|sco", dong, re.I) and len(dong.strip()) < 170:
            print("   ", dong.strip()[:160]); thay = True
    if not thay:
        print("    (không thấy dòng nào nói về HFP)")

    print("\n=== Telecom thấy những tuyến tiếng nào ===")
    tc = sh("dumpsys telecom")
    for dong in tc.splitlines():
        if re.search(r"supportedRouteMask|BluetoothDevice|CallAudioState|route:", dong):
            print("   ", dong.strip()[:170])

    print("\n=== Tóm ===")
    co_bt = "true" in sh("settings get global bluetooth_on").lower() or \
            sh("settings get global bluetooth_on").strip() == "1"
    co_hfp = bool(re.search(r"HEADSET.*STATE_CONNECTED|mCurrentDevice.*[0-9A-F]{2}:",
                            bm, re.I))
    print(f"    Bluetooth bật: {'có' if co_bt else 'KHÔNG'}")
    print(f"    HFP đang nối : {'có' if co_hfp else 'KHÔNG - phải nối trước'}")
    if not co_hfp:
        print("\n    Nếu chưa nối: trên máy tính vào Cài đặt > Bluetooth > Galaxy S9+")
        print("    > Kết nối, và bật dịch vụ 'Hands-free Telephony' trong Thuộc tính.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
