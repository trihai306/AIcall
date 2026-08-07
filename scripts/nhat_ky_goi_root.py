"""Đọc nhật ký cuộc gọi bằng quyền root và xem thời lượng từng cuộc.

Dùng khi đầu gọi báo "đang đổ chuông bên kia" mà máy nhận không thấy gì. Thời
lượng 0 trên hàng loạt cuộc liên tiếp là dấu hiệu mạng nhận cuộc gọi rồi thả -
thường do bộ lọc chống spam của nhà mạng sau khi quay quá nhiều lần vào một số.

`content query` chạy bằng shell thường bị từ chối (CallLogProvider đòi quyền),
nên đọc thẳng cơ sở dữ liệu bằng sqlite3 với su.

    python scripts/nhat_ky_goi_root.py
"""

import subprocess
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SERIAL = "21f10e44220c7ece"
DB = "/data/user_de/0/com.android.providers.contacts/databases/calllog.db"
LOAI = {1: "gọi đến", 2: "gọi đi", 3: "nhỡ", 5: "bị từ chối", 6: "chặn"}


def sh(cmd: str, t: int = 90) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def main() -> int:
    truy = ("SELECT number,type,duration,date FROM calls "
            "ORDER BY date DESC LIMIT 15;")
    ra = sh(f"""su -c 'sqlite3 {DB} "{truy}"'""")
    if "no such" in ra.lower() or "not found" in ra.lower() or not ra:
        print("Không đọc được nhật ký:", ra[:200] or "(rỗng)")
        print("\nThử đường khác ...")
        ra = sh(f"""su -c 'ls -l /data/user_de/0/com.android.providers.contacts/databases/'""")
        print(ra[:400])
        return 1

    print(f"    {'số':<14}{'loại':<12}{'thời lượng':>11}   lúc")
    for dong in ra.splitlines():
        c = dong.split("|")
        if len(c) < 4:
            continue
        so, loai, dai, khi = c[0], int(c[1]), int(c[2]), int(c[3]) / 1000
        gio = datetime.fromtimestamp(khi).strftime("%H:%M:%S")
        canh = "  <-- không ai bắt" if dai == 0 and loai == 2 else ""
        print(f"    {so:<14}{LOAI.get(loai, loai):<12}{dai:>9}s   {gio}{canh}")

    khong = sum(1 for d in ra.splitlines()
                if len(d.split("|")) >= 3 and d.split("|")[1] == "2"
                and d.split("|")[2] == "0")
    print(f"\n    {khong}/15 cuộc gọi đi có thời lượng 0.")
    if khong >= 5:
        print("    Nhiều cuộc liên tiếp không nối - hợp với việc nhà mạng lọc")
        print("    chống spam. Đổi số đích hoặc chờ vài chục phút rồi thử lại.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
