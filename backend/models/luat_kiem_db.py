"""Bảng luật kiểm chứng - thứ trang quản lý sửa được.

Bản gốc của bảng thuộc tính nằm ở `pipeline/thuoc_tinh.THUOC_TINH_MAC_DINH`; ở
đây chỉ gieo và cho sửa. Giữ bản gốc trong code để mất DB vẫn còn.

Dùng chung kết nối và khoá ghi của `models/db.py`, không mở handle thứ hai vào
cùng file SQLite - cùng lý do với `scenarios_db.py`.
"""

import asyncio
import json

from backend.models import db


def doc_bang_sync(conn) -> dict[str, dict]:
    """Bảng thuộc tính đang BẬT, đúng dạng `cap_trong` nhận."""
    ra = {}
    for ten, tu_khoa, don_vi in conn.execute(
            "SELECT ten, tu_khoa, don_vi FROM thuoc_tinh_kiem WHERE bat=1"):
        ra[ten] = {"khoa": tuple(json.loads(tu_khoa)), "dvi": tuple(json.loads(don_vi))}
    return ra


def gieo_mac_dinh_sync(conn) -> int:
    """Gieo bảng mặc định. Chạy lại được: chỉ thêm thuộc tính còn thiếu.

    KHÔNG ghi đè dòng đã có - người dùng sửa trên UI rồi thì lần khởi động sau
    không được xoá công của họ. Có test canh đúng điều này
    (`test_gieo_lai_KHONG_ghi_de_ban_nguoi_dung_da_sua`).
    """
    from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH
    n = 0
    for ten, d in THUOC_TINH_MAC_DINH.items():
        cur = conn.execute(
            "INSERT OR IGNORE INTO thuoc_tinh_kiem (ten, tu_khoa, don_vi, bat) "
            "VALUES (?, ?, ?, 1)",
            (ten, json.dumps(list(d["khoa"]), ensure_ascii=False),
             json.dumps(list(d["dvi"]), ensure_ascii=False)))
        n += cur.rowcount
    conn.commit()
    return n


# --- vỏ async cho tầng API (I/O SQLite chạy ngoài vòng lặp sự kiện) ----------

async def doc_bang() -> dict[str, dict]:
    def _lam():
        c = db.connection()
        if c is None:
            return {}
        gieo_mac_dinh_sync(c)
        return doc_bang_sync(c)
    return await asyncio.to_thread(_lam)


async def sua(ten: str, tu_khoa: list[str] | None,
              don_vi: list[str] | None, bat: bool | None) -> bool:
    def _lam():
        c = db.connection()
        if c is None:
            return False
        with db.write_lock:
            cu = c.execute("SELECT tu_khoa, don_vi, bat FROM thuoc_tinh_kiem WHERE ten=?",
                           (ten,)).fetchone()
            if cu is None:
                return False
            c.execute(
                "UPDATE thuoc_tinh_kiem SET tu_khoa=?, don_vi=?, bat=? WHERE ten=?",
                (json.dumps(tu_khoa, ensure_ascii=False) if tu_khoa is not None else cu[0],
                 json.dumps(don_vi, ensure_ascii=False) if don_vi is not None else cu[1],
                 cu[2] if bat is None else int(bat), ten))
            c.commit()
        return True
    return await asyncio.to_thread(_lam)


async def khoi_phuc() -> int:
    """Xoá sạch rồi gieo lại bản gốc trong code."""
    def _lam():
        c = db.connection()
        if c is None:
            return 0
        with db.write_lock:
            c.execute("DELETE FROM thuoc_tinh_kiem")
            return gieo_mac_dinh_sync(c)
    return await asyncio.to_thread(_lam)
