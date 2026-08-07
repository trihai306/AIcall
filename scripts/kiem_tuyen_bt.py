"""Khi có cuộc gọi, Telecom có thấy tuyến Bluetooth không - và chuyển sang được không?

Đây là mắt xích cuối của hướng HFP. Đã có:
  - ghép đôi xong (bond state 12)
  - hồ sơ rảnh tay đã nối: HeadsetService mCurrentDevice = 58:02:05:E2:57:8D
  - Windows đã cài "Galaxy Note9 Hands-Free HF Audio"

Còn phải xác nhận: lúc có cuộc gọi, Telecom liệt Bluetooth trong danh sách tuyến,
và chuyển được tiếng sang đó. Nếu được thì tiếng cuộc gọi chảy sang máy tính qua
đường HAL chính thức, bỏ hẳn chỗ đang sinh tiếng dè.

Không cần ai bắt máy: tuyến âm thanh dựng ngay từ lúc quay số.

    python scripts/kiem_tuyen_bt.py 0396130621
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


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def tuyen() -> str:
    for l in sh("dumpsys telecom").splitlines():
        if "mCurrentCallAudioState" in l:
            return l.strip()
    return "(không đọc được)"


def tt() -> int:
    m = re.search(r"mForegroundCallState=(\d+)", sh("dumpsys telephony.registry"))
    return int(m.group(1)) if m else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--giay", type=int, default=30)
    a = ap.parse_args()

    print("[1] Trước khi gọi:")
    print("   ", tuyen()[:180])

    sh("input keyevent KEYCODE_WAKEUP")
    sh("wm dismiss-keyguard")
    time.sleep(0.6)
    print(f"\n[2] Gọi {a.so} — KHÔNG cần bắt máy")
    sh(f"am start -a android.intent.action.CALL -d tel:{a.so} "
       f"--ei com.android.phone.extra.slot 1")

    for i in range(20):
        time.sleep(1)
        if tt() in (3, 4, 1):
            print(f"    {i}s: tuyến đã dựng")
            break
    else:
        print("    không quay được số")
        return 1
    time.sleep(2.0)

    print("\n[3] Tuyến tiếng khi đang gọi:")
    t = tuyen()
    print("   ", t[:200])
    # Phải soi ĐÚNG trường supportedRouteMask. Tìm "BLUETOOTH" trong cả dòng là
    # sai: dòng đó luôn chứa `activeBluetoothDevice` và `supportedBluetoothDevices`
    # nên lúc nào cũng khớp - tôi đã báo nhầm "có tuyến Bluetooth" vì lỗi này.
    m = re.search(r"supportedRouteMask: ([^,\]]*(?:, [^,\]]*)*?)\]", t)
    mask = m.group(1) if m else ""
    co_bt = "BLUETOOTH" in mask.upper()
    print(f"    supportedRouteMask = {mask}")
    print(f"\n    Telecom {'CÓ' if co_bt else 'KHÔNG'} thấy tuyến Bluetooth")

    if co_bt:
        print("\n[4] Chuyển tiếng sang Bluetooth ...")
        # Nút Bluetooth trên giao diện gọi; đọc màn hình để bấm đúng chỗ.
        sh("rm -f /sdcard/u5.xml; uiautomator dump /sdcard/u5.xml")
        xml = sh("cat /sdcard/u5.xml")
        nut = None
        for m in re.finditer(
                r'(?:text|content-desc)="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                xml):
            if re.search(r"bluetooth", m.group(1), re.I):
                nut = ((int(m.group(2)) + int(m.group(4))) // 2,
                       (int(m.group(3)) + int(m.group(5))) // 2)
                break
        if nut:
            sh(f"input tap {nut[0]} {nut[1]}")
            print(f"    đã bấm nút Bluetooth tại {nut}")
            time.sleep(2.5)
            print("   ", tuyen()[:200])
        else:
            chu = re.findall(r'(?:text|content-desc)="([^"]{2,30})"', xml)
            print("    không thấy nút Bluetooth. Trên màn hình:",
                  ", ".join(dict.fromkeys(chu))[:180])

    print(f"\n[5] Giữ {a.giay}s để nhìn phía Windows ...")
    time.sleep(a.giay)
    print("   ", tuyen()[:200])
    sh("input keyevent KEYCODE_ENDCALL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
