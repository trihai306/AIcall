"""Nạp tình huống từ JSON vào bảng `tinh_huong`. Chạy lại được nhiều lần.

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\nap_tinh_huong.py
    .venv\\python.exe scripts\\nap_tinh_huong.py --tep data\\tinh_huong_seed.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.config import settings


def mo_db():
    """Kết nối sqlite3 RIÊNG, không gọi `db.init_db`.

    `init_db` có bước dọn phiên "active" và sẽ đóng nhầm cuộc gọi đang chạy
    thật - xem `scripts/kiem_thu_crud.py:gieo_phien_mau`. WAL cho phép nhiều
    tiến trình cùng mở nên kết nối riêng là an toàn.
    """
    import sqlite3
    return sqlite3.connect(str(settings.db_file))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tep", default="data/tinh_huong_seed.json")
    a = ap.parse_args()

    raw = json.loads(Path(a.tep).read_text(encoding="utf-8"))
    conn, now = mo_db(), time.time()
    n = 0
    for t in raw["tinh_huong"]:
        for m in t.get("mo_dau", []):
            if not m.rstrip().endswith(","):
                print(f"BO {t['id']}: mau mo dau khong ket bang phay: {m!r}")
                break
        else:
            conn.execute(
                "INSERT INTO tinh_huong "
                "(id,ten,vi_du,tu_khoa,mo_dau,speed,bat,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,1,?,?) "
                "ON CONFLICT(id) DO UPDATE SET ten=excluded.ten, "
                "vi_du=excluded.vi_du, tu_khoa=excluded.tu_khoa, "
                "mo_dau=excluded.mo_dau, speed=excluded.speed, "
                "updated_at=excluded.updated_at",
                (t["id"], t["ten"], json.dumps(t["vi_du"], ensure_ascii=False),
                 json.dumps(t.get("tu_khoa", []), ensure_ascii=False),
                 json.dumps(t.get("mo_dau", []), ensure_ascii=False),
                 t.get("speed"), now, now))
            n += 1
    conn.commit()
    print(f"da nap {n} tinh huong")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
