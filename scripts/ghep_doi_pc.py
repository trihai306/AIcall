"""Cho điện thoại quét và ghép đôi với máy tính qua Bluetooth.

Ghép từ phía Windows thất bại: `PairAsync()` trả Failed ngay và điện thoại không
hiện hộp thoại nào - nghi thức mặc định không hợp, mà PowerShell lại không gắn
được bộ xử lý sự kiện WinRT để làm ghép đôi tuỳ biến. Nên đổi chiều: bật hiện
diện cho máy tính (scripts/pc_hien.ps1) rồi để điện thoại chủ động.

Mục đích cuối: dùng hồ sơ rảnh tay HFP - đường HAL CHÍNH THỨC để đưa tiếng cuộc
gọi ra thiết bị ngoài, thay cho việc chen vào mixer vốn đang cho tiếng dè.

    python scripts/ghep_doi_pc.py
    python scripts/ghep_doi_pc.py --ten ADMIN-PC
"""

import argparse
import re
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERIAL = "21f10e44220c7ece"
NUT_GHEP = ["pair", "ghép đôi", "ghep doi", "ok", "đồng ý", "accept", "kết nối"]


def sh(cmd: str, t: int = 60) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def man_hinh() -> str:
    sh("rm -f /sdcard/u3.xml; uiautomator dump /sdcard/u3.xml")
    return sh("cat /sdcard/u3.xml")


def tim(xml: str, muc: list[str], khop_gan: bool = False) -> tuple[str, int, int] | None:
    for m in re.finditer(
            r'text="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
        chu = m.group(1).strip()
        thap = chu.lower()
        hop = any(thap == t.lower() for t in muc) or \
            (khop_gan and any(t.lower() in thap for t in muc))
        if hop and chu:
            return (chu,
                    (int(m.group(2)) + int(m.group(4))) // 2,
                    (int(m.group(3)) + int(m.group(5))) // 2)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ten", default="ADMIN-PC", help="tên máy tính cần tìm")
    a = ap.parse_args()

    sh("input keyevent KEYCODE_WAKEUP")
    sh("wm dismiss-keyguard")
    time.sleep(0.6)

    print("[1] Mở cài đặt Bluetooth ...")
    # Gọi thẳng activity. Ý định `android.settings.BLUETOOTH_SETTINGS` trên bản
    # Samsung này rơi về màn hình chính chứ không mở gì - dò được bằng cách thử
    # từng ứng viên rồi đọc cửa sổ đang có tiêu điểm.
    sh("am start -n com.android.settings/.bluetooth.BluetoothSettings")
    time.sleep(3.5)
    sh("input swipe 700 1200 700 2200 300")     # kéo xuống để bắt đầu quét lại
    time.sleep(2.0)

    print(f"[2] Tìm '{a.ten}' trong danh sách ...")
    thay = None
    for lan in range(15):
        xml = man_hinh()
        thay = tim(xml, [a.ten], khop_gan=True)
        if thay:
            break
        if lan % 4 == 0:
            ten = [t for t in dict.fromkeys(re.findall(r'text="([^"]{2,30})"', xml))]
            print(f"    {lan*3}s: đang thấy: {', '.join(ten)[:130]}")
        # BẤM NÚT SCAN, đừng vuốt. Vuốt không kích hoạt quét lại: đo được danh
        # sách đứng im y nguyên suốt 36 giây, tức chỉ đang đọc kết quả cũ.
        if lan % 3 == 0:
            nut = tim(xml, ["Scan", "Quét", "Tìm kiếm", "Search"])
            if nut:
                sh(f"input tap {nut[1]} {nut[2]}")
                if lan == 0:
                    print(f"    bấm '{nut[0]}' để quét lại")
        time.sleep(4.0)

    if not thay:
        print(f"    KHÔNG thấy '{a.ten}'. Kiểm máy tính còn hiện diện không -")
        print("    chế độ đó tự tắt sau vài phút, chạy lại pc_hien.ps1.")
        return 1

    print(f"[3] Bấm vào '{thay[0]}' tại ({thay[1]},{thay[2]})")
    sh(f"input tap {thay[1]} {thay[2]}")
    time.sleep(3.0)

    print("[4] Xác nhận ghép đôi ...")
    for lan in range(10):
        xml = man_hinh()
        nut = tim(xml, NUT_GHEP)
        if nut:
            sh(f"input tap {nut[1]} {nut[2]}")
            print(f"    đã bấm '{nut[0]}'")
            break
        time.sleep(2.0)
    else:
        print("    không thấy nút xác nhận (có thể đã ghép sẵn)")

    time.sleep(4.0)
    print("\n[5] Kết quả phía điện thoại:")
    bm = sh("dumpsys bluetooth_manager")
    for dong in bm.splitlines():
        if re.search(r"Bonded|mCurrentDevice|Profile: Headset|STATE_CONNECTED", dong) \
                and len(dong.strip()) < 150:
            print("   ", dong.strip()[:140])
    tc = sh("dumpsys telecom")
    for dong in tc.splitlines():
        if "supportedBluetoothDevices" in dong:
            print("   ", dong.strip()[:170])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
