"""Kho câu đuôi RỖNG là trạng thái hợp lệ, và phải ở lại rỗng.

Người dùng 06-09-2026, nói ba lần: *"tôi không cần đuôi luôn vì có câu đệm rồi,
nhiều cái lặp lại rất có vấn đề"*. 29/42 câu đuôi cùng một ý "để em xem lại" nên
khách nghe lặp suốt cuộc gọi, trong khi mẩu mở đầu theo tình huống đã đứng được
một mình.

Trước bản này, "xoá hết" cho ra đúng thứ người dùng KHÔNG muốn:
  1. `nap_tu_db` ném LoiKho  -> backend không khởi động nổi
  2. `do_json_vao_db` thấy bảng rỗng -> đổ lại nguyên 42 câu từ fillers.json
Xoá bao nhiêu lần thì mọc lại bấy nhiêu lần, và không có gì báo.
"""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.services import filler_store
from backend.services.filler_store import (CO_DA_SEED, Kho, do_json_vao_db,
                                           nap_tu_db)


def _db():
    """DB trống có đủ ba bảng mà kho câu đệm đụng tới."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE tinh_huong (id TEXT PRIMARY KEY, ten TEXT, vi_du TEXT,
            tu_khoa TEXT, mo_dau TEXT, speed REAL, bat INTEGER DEFAULT 1,
            created_at REAL, updated_at REAL);
        CREATE TABLE cau_duoi (id TEXT PRIMARY KEY, text TEXT, hop_cau_hoi INTEGER,
            bat INTEGER DEFAULT 1, created_at REAL, updated_at REAL);
        CREATE TABLE kho_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    return conn


def _them_tinh_huong(conn):
    conn.execute(
        "INSERT INTO tinh_huong (id,ten,vi_du,tu_khoa,mo_dau,speed,bat) VALUES (?,?,?,?,?,?,1)",
        ("hoi_lai_suat", "Khách hỏi lãi suất",
         json.dumps(["lãi suất bao nhiêu", "lãi mấy phần trăm"]),
         json.dumps([]), json.dumps(["Dạ về lãi suất thì,"]), None))
    conn.commit()


def test_kho_duoi_rong_KHONG_nem_loi():
    """Đây là thứ đổi: trước bản này backend không khởi động nổi."""
    conn = _db()
    _them_tinh_huong(conn)
    kho = nap_tu_db(conn)
    assert kho.duoi == ()
    assert len(kho.tinh_huong) == 1


def test_tat_het_cau_duoi_cung_hop_le():
    """bat=0 hết cũng là rỗng - cùng đường với bảng rỗng."""
    conn = _db()
    _them_tinh_huong(conn)
    conn.execute("INSERT INTO cau_duoi (id,text,hop_cau_hoi,bat) VALUES ('d1','Dạ',1,0)")
    conn.commit()
    assert nap_tu_db(conn).duoi == ()


def test_xoa_het_thi_KHONG_moc_lai(tmp_path):
    """Ràng buộc cốt lõi: đã seed một lần thì bảng rỗng cũng không đổ lại.

    Không có cờ này thì người dùng xoá sạch, khởi động lại, và 42 câu
    "để em xem lại" quay về nguyên vẹn.
    """
    js = tmp_path / "fillers.json"
    js.write_text(json.dumps({"chu_de": {}, "cau": [
        {"id": "ngan_01", "text": "Dạ", "hop_cau_hoi": True},
        {"id": "dai_03", "text": "Dạ, để em xem lại cho chính xác", "hop_cau_hoi": True},
    ]}), encoding="utf-8")

    conn = _db()
    assert do_json_vao_db(conn, js) == 2, "lần đầu phải seed"

    # người dùng xoá sạch trên giao diện
    conn.execute("DELETE FROM cau_duoi")
    conn.commit()

    assert do_json_vao_db(conn, js) == 0, "đã seed rồi thì KHÔNG được đổ lại"
    assert conn.execute("SELECT COUNT(*) FROM cau_duoi").fetchone()[0] == 0


def test_db_cu_da_co_du_lieu_thi_danh_dau_ngay():
    """DB có sẵn dữ liệu từ trước khi có cờ: phải đánh dấu, không thì lần đầu
    người dùng xoá sạch là nó đổ về ngay."""
    conn = _db()
    conn.execute("INSERT INTO cau_duoi (id,text,hop_cau_hoi,bat) VALUES ('d1','Dạ',1,1)")
    conn.commit()
    assert do_json_vao_db(conn, Path("khong-ton-tai.json")) == 0
    assert conn.execute("SELECT 1 FROM kho_meta WHERE key=?", (CO_DA_SEED,)).fetchone()


def test_thieu_bang_kho_meta_van_chay_nhu_cu(tmp_path):
    """DB cũ chưa migrate: thà seed như trước còn hơn chặn cả lần khởi động."""
    js = tmp_path / "fillers.json"
    js.write_text(json.dumps({"cau": [{"id": "a", "text": "Dạ"}]}), encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE cau_duoi (id TEXT PRIMARY KEY, text TEXT, hop_cau_hoi INTEGER,
            bat INTEGER DEFAULT 1, created_at REAL, updated_at REAL);
    """)
    assert do_json_vao_db(conn, js) == 1


# --- ghep(): mẩu mở đầu đứng một mình -------------------------------------

from backend.services.filler_pick import ghep  # noqa: E402

MO_DAU = "Dạ về lãi suất thì,"


def test_duoi_rong_tra_ve_dung_mau_mo_dau():
    """Không được rơi xuống f-string ghép - nó thừa một khoảng trắng cuối."""
    assert ghep(MO_DAU, "") == MO_DAU
    assert ghep(MO_DAU, "   ") == MO_DAU
    assert ghep(MO_DAU, None) == MO_DAU


def test_duoi_rong_va_duoi_tieu_tu_cho_CUNG_MOT_chuoi():
    """Ràng buộc tiền bạc: vân tay tính theo chuỗi text.

    Lệch một khoảng trắng là vân tay khác, là dựng lại toàn bộ clip bằng F5
    (~19 phút backend không trả lời API) thay vì đọc clip đã có trên đĩa.
    """
    assert ghep(MO_DAU, "") == ghep(MO_DAU, "Dạ") == ghep(MO_DAU, "Vâng ạ")


def test_van_giu_dau_phay_cuoi():
    """Câu trả lời thật nối ngay sau. Bỏ phẩy là F5 hạ giọng kết câu giữa lượt,
    khách nghe như AI đã nói xong trong khi câu trả lời chưa tới."""
    assert ghep(MO_DAU, "").endswith(",")


def test_ca_hai_rong_thi_rong():
    """Không tình huống + không đuôi = không có câu đệm. Đúng hành vi."""
    assert ghep("", "") == ""


# --- Đếm clip khi kho đuôi rỗng ------------------------------------------

from backend.api.fillers import dem_clip  # noqa: E402


def test_kho_duoi_rong_thi_moi_mau_ra_mot_clip():
    """Trang quản lý báo "0 clip" trong khi đĩa có hàng trăm là bẫy thật: người
    vận hành tưởng chưa dựng gì và bấm Dựng tiếng lại từ đầu."""
    assert dem_clip(so_mau_tong=142, so_duoi=0) == 142


def test_co_duoi_thi_giu_nguyen_cong_thuc_tich():
    """Mẩu và đuôi ghép sẵn thành clip liền nên số clip nhân theo TÍCH, cộng
    thêm rổ đuôi trần."""
    assert dem_clip(so_mau_tong=20, so_duoi=3) == 20 * 3 + 3
