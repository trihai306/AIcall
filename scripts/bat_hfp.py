"""Bật hồ sơ rảnh tay (Calls) cho máy tính trong cài đặt Bluetooth của điện thoại.

Đã có: ghép đôi xong (bond 12), Windows báo "Galaxy Note9 Connected", và đã cài
"Galaxy Note9 Hands-Free HF Audio". Nhưng Telecom vẫn báo

    supportedRouteMask: EARPIECE, SPEAKER        (không có BLUETOOTH)
    supportedBluetoothDevices: []

và nhật ký không có sự kiện CONNECTED nào cho hồ sơ rảnh tay với 580205 - chỉ có
ACL_CONNECTED. Nghĩa là liên kết nền có nhưng hồ sơ chưa nối.

Samsung để công tắc riêng cho từng hồ sơ trong trang chi tiết thiết bị: "Calls"
(rảnh tay) và "Media" (A2DP). Tắt Calls thì HFP không bao giờ nối.

    python scripts/bat_hfp.py
"""

import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERIAL = "21f10e44220c7ece"


def sh(cmd: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def man_hinh() -> str:
    sh("rm -f /sdcard/u6.xml; uiautomator dump /sdcard/u6.xml")
    return sh("cat /sdcard/u6.xml")


def cac_nut(xml: str) -> list[tuple[str, str, int, int, str]]:
    """Trả (text, mô tả, x, y, checked) cho mọi phần tử có chữ hoặc mô tả."""
    ra = []
    for m in re.finditer(
            r'text="([^"]*)"[^>]*content-desc="([^"]*)"[^>]*'
            r'checked="(\w+)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
        ra.append((m.group(1).strip(), m.group(2).strip(),
                   (int(m.group(4)) + int(m.group(6))) // 2,
                   (int(m.group(5)) + int(m.group(7))) // 2, m.group(3)))
    return ra


def main() -> int:
    sh("input keyevent KEYCODE_WAKEUP")
    sh("wm dismiss-keyguard")
    time.sleep(0.6)

    print("[1] Mở cài đặt Bluetooth ...")
    sh("am start -n com.android.settings/.bluetooth.BluetoothSettings")
    time.sleep(3.5)

    xml = man_hinh()
    # Hàng ADMIN-PC: bấm vào biểu tượng bánh răng ở mép phải, không bấm vào tên
    # (bấm tên là nối/ngắt chứ không mở trang chi tiết).
    hang = None
    for m in re.finditer(
            r'text="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
        if "ADMIN-PC" in m.group(1):
            hang = (int(m.group(3)) + int(m.group(5))) // 2
            break
    if hang is None:
        chu = re.findall(r'text="([^"]{2,30})"', xml)
        print("    KHÔNG thấy ADMIN-PC. Trên màn hình:",
              ", ".join(dict.fromkeys(chu))[:180])
        return 1

    rong = int(re.search(r"(\d+)x(\d+)", sh("wm size")).group(1))
    print(f"[2] Bấm bánh răng của ADMIN-PC (y={hang}) ...")
    sh(f"input tap {int(rong * 0.93)} {hang}")
    time.sleep(3.0)

    print("[3] Trang chi tiết - các công tắc:")
    xml = man_hinh()
    nut = cac_nut(xml)
    for t, d, x, y, ch in nut:
        if t or d:
            print(f"    {(t or d)[:38]:<40}{'BẬT' if ch == 'true' else 'tắt'}")

    print("\n[4] Bật mục Calls nếu đang tắt ...")
    da_bat = False
    for t, d, x, y, ch in nut:
        nhan = (t or d).lower()
        if re.search(r"^(calls?|cuộc gọi|goi)$|call audio|hands.?free", nhan):
            if ch == "true":
                print(f"    '{t or d}' đã bật sẵn")
            else:
                sh(f"input tap {x} {y}")
                print(f"    đã bật '{t or d}'")
            da_bat = True
    if not da_bat:
        print("    không thấy công tắc nào tên Calls - xem danh sách ở trên")

    time.sleep(4.0)
    print("\n[5] Hồ sơ rảnh tay đã nối chưa:")
    d = sh("dumpsys bluetooth_manager")
    khoi = False
    for l in d.splitlines():
        s = l.strip()
        if "Profile: HeadsetService" in s:
            khoi = True
        elif khoi and s.startswith("Profile:"):
            break
        if khoi and s and len(s) < 120:
            print("   ", s[:110])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
