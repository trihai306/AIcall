"""Đổi `F5TTS_SPEED` trong .env mà KHÔNG làm hỏng mã hoá phần còn lại.

Vì sao cần script chứ không sửa tay bằng PowerShell: `.env` chứa tiếng Việt có
dấu (`F5TTS_REF_TEXT`). `Get-Content | Set-Content` của PowerShell đọc/ghi theo
codepage của console, nên một lần sửa dòng khác là đủ để câu tham chiếu biến
thành chữ hỏng - và giọng nhân bản sẽ sai mà không báo lỗi gì.

Đọc/ghi bằng UTF-8 tường minh, chỉ đụng đúng một dòng.

    python scripts\\doi_toc_do_noi.py 0.76
"""

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KHOA = "F5TTS_SPEED"


def main() -> int:
    if len(sys.argv) < 2:
        print(f"  dùng: python scripts/doi_toc_do_noi.py <tốc độ>   (vd 0.76)")
        return 1
    try:
        moi = float(sys.argv[1])
    except ValueError:
        print("  tốc độ phải là số")
        return 1
    # Chậm quá thì giọng kéo dài nghe méo, nhanh quá thì nuốt chữ trên đường thoại.
    if not 0.5 <= moi <= 1.5:
        print("  chỉ nhận 0.5 - 1.5")
        return 1

    f = Path(__file__).resolve().parent.parent / ".env"
    goc = f.read_text(encoding="utf-8")
    cu = None
    m = re.search(rf"^{KHOA}=(.*)$", goc, re.M)
    if m:
        cu = m.group(1).strip()
        ra = re.sub(rf"^{KHOA}=.*$", f"{KHOA}={moi}", goc, count=1, flags=re.M)
    else:
        ra = goc.rstrip("\n") + f"\n{KHOA}={moi}\n"

    f.write_text(ra, encoding="utf-8")
    print(f"  {KHOA}: {cu} -> {moi}")
    print("  PHẢI khởi động lại backend: settings đọc .env một lần lúc nạp,")
    print("  và bộ nhớ đệm TTS không có tốc độ trong khoá nên câu cũ vẫn ra")
    print("  giọng cũ cho tới khi đệm bị xoá.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
