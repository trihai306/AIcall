"""SIM có bị chặn chiều gọi đi, chuyển tiếp, hay hết tiền không?

Triệu chứng: máy báo `đang quay số` rồi `đang đổ chuông bên kia` đủ 45 giây,
nhưng KHÔNG máy nào ở đầu kia đổ chuông - kể cả hai số khác nhau. Mạng nhận cuộc
gọi và phát hồi chuông cho đầu gọi, mà không nối tới đích.

Ba nguyên nhân phía mạng đều hỏi được bằng mã dịch vụ:

    *#21#   chuyển tiếp mọi cuộc gọi (nếu bật, cuộc gọi bị lái đi chỗ khác)
    *#33#   chặn chiều gọi đi
    *101#   số dư (Viettel) - hết tiền thì chiều đi bị khoá

Câu trả lời hiện trong hộp thoại chứ không in ra log, nên phải đọc màn hình bằng
uiautomator.

    python scripts/kiem_chan_goi_di.py
    python scripts/kiem_chan_goi_di.py --ma "*101#"
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
MA_MAC_DINH = ["*#21#", "*#33#", "*101#"]


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def mo_khoa() -> None:
    sh("input keyevent KEYCODE_WAKEUP")
    sh("wm dismiss-keyguard")
    time.sleep(0.6)


def doc_man_hinh() -> list[str]:
    """Lấy mọi chuỗi text đang hiện trên màn hình."""
    sh("uiautomator dump /sdcard/ui.xml >/dev/null 2>&1")
    xml = sh("cat /sdcard/ui.xml")
    chu = re.findall(r'text="([^"]{2,})"', xml)
    # bỏ trùng, giữ thứ tự
    ra, thay = [], set()
    for c in chu:
        c = c.strip()
        if c and c not in thay:
            thay.add(c)
            ra.append(c)
    return ra


def hoi(ma: str) -> list[str]:
    # Mã dịch vụ phải đi qua ACTION_CALL và ký tự # phải mã hoá thành %23,
    # không thì shell nuốt mất phần sau dấu #.
    ma_url = ma.replace("#", "%23").replace("*", "*")
    sh(f'am start -a android.intent.action.CALL -d "tel:{ma_url}" '
       f'--ei com.android.phone.extra.slot 1')
    time.sleep(6)
    chu = doc_man_hinh()
    sh("input keyevent KEYCODE_BACK")
    time.sleep(0.5)
    sh("input keyevent KEYCODE_ENDCALL")
    return chu


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ma", nargs="*", default=MA_MAC_DINH)
    a = ap.parse_args()

    mo_khoa()
    bo_qua = re.compile(r"^(Trang chủ|Home|\d{1,2}:\d{2}|[A-Z]{2,4}$)")

    for ma in a.ma:
        print(f"\n=== {ma} ===")
        chu = hoi(ma)
        thay = [c for c in chu if not bo_qua.match(c) and len(c) > 3]
        if not thay:
            print("    (màn hình không có chữ nào - mạng chưa trả lời)")
        for c in thay[:14]:
            print("   ", c[:150])

    print("\n" + "=" * 60)
    print("Cách đọc:")
    print("  *#21#  'Chưa đăng ký' / 'Not forwarded'  -> không bị lái cuộc gọi")
    print("  *#33#  'Đã tắt' / 'Disabled'             -> không bị chặn chiều đi")
    print("  *101#  còn tiền                          -> không phải hết tiền")
    print("Nếu cả ba đều bình thường mà cuộc gọi vẫn không tới đích thì lỗi nằm")
    print("ở phía nhà mạng - gọi 198 hỏi xem SIM có bị hạn chế chiều đi không.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
