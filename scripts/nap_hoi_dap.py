"""Nạp bảng hỏi-đáp từ JSON vào bảng `hoi_dap`. Chạy lại được nhiều lần.

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\nap_hoi_dap.py
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.config import settings
from backend.services.bang_hoi_dap import kiem_dong


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tep", default="data/hoi_dap_seed.json")
    a = ap.parse_args()

    raw = json.loads(Path(a.tep).read_text(encoding="utf-8"))
    # Kết nối riêng, KHÔNG gọi db.init_db: init có bước dọn phiên "active" và sẽ
    # đóng nhầm cuộc gọi đang chạy thật. WAL cho phép nhiều tiến trình cùng mở.
    conn = sqlite3.connect(str(settings.db_file))
    conn.execute("""CREATE TABLE IF NOT EXISTS hoi_dap (
        id TEXT PRIMARY KEY, cau_dem TEXT, cau_hoi TEXT NOT NULL,
        tra_loi TEXT NOT NULL, san_pham TEXT,
        bat INTEGER NOT NULL DEFAULT 1, created_at REAL, updated_at REAL)""")
    now, n = time.time(), 0
    for d in raw["hoi_dap"]:
        kiem_dong(d)      # chặn TRƯỚC khi ghi: dữ liệu sai vào rồi thì hỏng câm
        conn.execute(
            "INSERT INTO hoi_dap (id, cau_dem, cau_hoi, tra_loi, san_pham, bat,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET cau_dem=excluded.cau_dem, "
            "cau_hoi=excluded.cau_hoi, tra_loi=excluded.tra_loi, "
            "san_pham=excluded.san_pham, bat=excluded.bat, updated_at=excluded.updated_at",
            (d["id"], d.get("cau_dem", ""), json.dumps(d["cau_hoi"], ensure_ascii=False),
             d["tra_loi"], d.get("san_pham", ""), int(d.get("bat", 1)), now, now))
        n += 1
    conn.commit()
    print(f"da nap {n} dong hoi-dap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
