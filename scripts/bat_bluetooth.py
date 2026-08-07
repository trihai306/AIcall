"""Bật Bluetooth trên điện thoại và cho nó hiện ra để máy tính quét thấy.

Đường Bluetooth HFP là đường HAL chính thức cho việc đưa tiếng cuộc gọi ra thiết
bị ngoài - không phải chen vào mixer như cách đang làm. Máy tính Windows đã chạy
được hồ sơ này với một máy khác nên phần cứng có sẵn; chỉ thiếu bước ghép đôi.

    python scripts/bat_bluetooth.py
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


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def bam_nut(nhan: list[str]) -> tuple[str, int, int] | None:
    """Tìm nút theo chữ rồi bấm đúng toạ độ của nó.

    Đoán toạ độ theo tỉ lệ màn hình đã bấm trượt một lần, và tệ hơn là script vẫn
    báo thành công. Đọc cây giao diện thì biết chắc.
    """
    sh("rm -f /sdcard/ui.xml; uiautomator dump /sdcard/ui.xml")
    xml = sh("cat /sdcard/ui.xml")
    for m in re.finditer(
            r'text="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
        chu = m.group(1).strip()
        if chu.lower() in [n.lower() for n in nhan]:
            x = (int(m.group(2)) + int(m.group(4))) // 2
            y = (int(m.group(3)) + int(m.group(5))) // 2
            sh(f"input tap {x} {y}")
            return chu, x, y
    return None


def don_man_hinh() -> None:
    """Đóng hộp thoại hệ thống còn kẹt.

    Hộp thoại MMI của Samsung (hiện sau khi tra số dư bằng *101#) là cửa sổ hệ
    thống - phím Back KHÔNG đóng được, và nó chắn mọi hộp thoại phía sau. Đã mất
    hai lượt vì tưởng máy không nhận lệnh.
    """
    for _ in range(4):
        n = bam_nut(["Cancel", "Huỷ", "Hủy", "Đóng", "Close", "OK"])
        if not n:
            break
        print(f"    đóng hộp thoại: bấm '{n[0]}'")
        time.sleep(0.8)
    sh("input keyevent KEYCODE_HOME")
    time.sleep(0.8)


def main() -> int:
    sh("input keyevent KEYCODE_WAKEUP")
    sh("wm dismiss-keyguard")
    time.sleep(0.6)
    # Dọn hộp thoại còn kẹt trên màn hình. Lần trước hộp thoại USSD của lệnh
    # tra số dư còn nguyên đó và chặn mất hộp thoại Bluetooth - script bấm vào
    # khoảng không rồi báo thành công.
    don_man_hinh()

    print("Bluetooth:", sh("settings get global bluetooth_on"))
    print("Địa chỉ  :", sh("settings get secure bluetooth_address"))
    print("Tên máy  :", sh("settings get secure bluetooth_name")
          or sh("getprop ro.product.model"))

    # Cho máy hiện ra 300 giây để máy tính quét thấy. Hộp thoại xin phép sẽ hiện,
    # bấm nút Cho phép giúp luôn - không thì nó đứng đó chờ người.
    print("\nCho máy hiện ra 300 giây ...")
    sh("am start -a android.bluetooth.adapter.action.REQUEST_DISCOVERABLE "
       "--ei android.bluetooth.adapter.extra.DISCOVERABLE_DURATION 300")
    time.sleep(1.5)
    # ĐỌC màn hình rồi bấm đúng nút, đừng đoán toạ độ - lần trước đoán 0.72/0.62
    # và bấm trượt, máy không hiện ra nên máy tính quét không thấy.
    nut = bam_nut(["Cho phép", "Allow", "OK", "Đồng ý", "Cho phep"])
    if nut:
        print(f"    đã bấm '{nut[0]}' tại ({nut[1]},{nut[2]})")
    else:
        xml = sh("cat /sdcard/ui.xml")
        chu = re.findall(r'text="([^"]{1,40})"', xml)
        print("    KHÔNG thấy nút cho phép. Chữ trên màn hình:",
              ", ".join(dict.fromkeys(chu))[:200])
    time.sleep(1.0)

    d = sh("dumpsys bluetooth_manager")
    ch = [l.strip() for l in d.splitlines()
          if re.search(r"ScanMode|Discoverab|mScanMode", l, re.I)][:4]
    print("    chế độ hiện diện:", "; ".join(ch)[:200] or "(không thấy)")
    print("\nGiờ quét từ máy tính trong vòng 5 phút.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
