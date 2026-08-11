"""Kho câu đệm đọc từ SQLite. Không cần GPU."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.services.filler_store import (
    LoiKho, do_json_vao_db, nap_tu_db,
)

DDL = """
CREATE TABLE tinh_huong (
  id TEXT PRIMARY KEY, ten TEXT NOT NULL, vi_du TEXT NOT NULL,
  tu_khoa TEXT, mo_dau TEXT, speed REAL,
  bat INTEGER NOT NULL DEFAULT 1, created_at REAL, updated_at REAL);
CREATE TABLE cau_duoi (
  id TEXT PRIMARY KEY, text TEXT NOT NULL,
  hop_cau_hoi INTEGER NOT NULL DEFAULT 1,
  bat INTEGER NOT NULL DEFAULT 1, created_at REAL, updated_at REAL);
"""


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(DDL)
    return c


def them_th(c, id="hoi_lai_suat", vi_du=("lãi suất bao nhiêu", "lãi thế nào"),
            mo_dau=("Dạ về lãi suất thì,",), speed=None, bat=1):
    c.execute("INSERT INTO tinh_huong (id,ten,vi_du,tu_khoa,mo_dau,speed,bat) "
              "VALUES (?,?,?,?,?,?,?)",
              (id, "Hỏi lãi suất", json.dumps(list(vi_du)), "[]",
               json.dumps(list(mo_dau)), speed, bat))


def them_duoi(c, id="d1", text="anh chị chờ em một chút ạ.", bat=1):
    c.execute("INSERT INTO cau_duoi (id,text,bat) VALUES (?,?,?)", (id, text, bat))


def test_nap_binh_thuong(conn):
    them_th(conn); them_duoi(conn)
    kho = nap_tu_db(conn)
    assert [t.id for t in kho.tinh_huong] == ["hoi_lai_suat"]
    assert kho.tinh_huong[0].vi_du == ("lãi suất bao nhiêu", "lãi thế nào")
    assert kho.duoi[0].text == "anh chị chờ em một chút ạ."


def test_bo_qua_tinh_huong_da_tat(conn):
    them_th(conn, bat=0)  # tình huống tắt
    them_duoi(conn)       # câu đuôi vẫn bật
    kho = nap_tu_db(conn)
    assert kho.tinh_huong == ()
    assert len(kho.duoi) == 1


def test_cau_duoi_tat_het_thi_loi(conn):
    them_th(conn)
    them_duoi(conn, bat=0)
    with pytest.raises(LoiKho, match="đuôi"):
        nap_tu_db(conn)


def test_vi_du_duoi_hai_cau_thi_loi(conn):
    them_th(conn, vi_du=("chỉ một câu",)); them_duoi(conn)
    with pytest.raises(LoiKho, match="hoi_lai_suat"):
        nap_tu_db(conn)


def test_mo_dau_khong_ket_bang_phay_thi_loi(conn):
    """Mẩu mở đầu phải kết bằng phẩy để F5 nghỉ ngắn thay vì hạ giọng kết câu."""
    them_th(conn, mo_dau=("Dạ về lãi suất thì",)); them_duoi(conn)
    with pytest.raises(LoiKho, match="phẩy"):
        nap_tu_db(conn)


def test_duoi_text_rong_thi_loi(conn):
    them_th(conn); them_duoi(conn, text="   ")
    with pytest.raises(LoiKho, match="d1"):
        nap_tu_db(conn)


def test_khong_co_duoi_nao_thi_loi(conn):
    """Rổ đuôi rỗng là mất hoàn toàn đường xuống cấp - khách nghe im lặng."""
    them_th(conn)
    with pytest.raises(LoiKho, match="đuôi"):
        nap_tu_db(conn)


def test_do_json_vao_db_khi_bang_rong(conn, tmp_path):
    p = tmp_path / "fillers.json"
    p.write_text(json.dumps({
        "chu_de": [{"id": "chung", "ten": "Chung"}],
        "cau": [{"id": "c1", "text": "dạ vâng ạ.", "chu_de": "chung",
                 "hop_cau_hoi": True}],
    }, ensure_ascii=False), encoding="utf-8")
    assert do_json_vao_db(conn, p) == 1
    assert nap_tu_db(conn).duoi[0].text == "dạ vâng ạ."


def test_do_json_khong_ghi_de_khi_da_co_du_lieu(conn, tmp_path):
    them_duoi(conn, id="san_co", text="câu đã có ạ.")
    p = tmp_path / "fillers.json"
    p.write_text(json.dumps({"chu_de": [], "cau": [
        {"id": "c1", "text": "câu mới ạ.", "chu_de": "chung"}]},
        ensure_ascii=False), encoding="utf-8")
    assert do_json_vao_db(conn, p) == 0
    assert [d.id for d in nap_tu_db(conn).duoi] == ["san_co"]


# ---------------------------------------------------------------------------
# van_tay — khôi phục nguyên văn từ 6a19b57 (không đổi logic, chỉ thêm import)
# ---------------------------------------------------------------------------

from backend.services.filler_store import van_tay  # noqa: E402

_GOC = dict(text="Dạ", giong="fosd_1", nfe=16, speed=1.0, ref_text="xin chào")


def test_van_tay_on_dinh_giua_hai_lan_goi():
    assert van_tay(**_GOC) == van_tay(**_GOC)


def test_van_tay_an_toan_lam_ten_file():
    vt = van_tay(**_GOC)
    assert len(vt) == 12
    assert all(k in "0123456789abcdef" for k in vt)


@pytest.mark.parametrize("truong,gia_tri_moi", [
    ("text", "Vâng ạ"),
    ("giong", "giong_khac"),
    ("nfe", 12),
    ("speed", 1.2),
    ("ref_text", "câu mẫu khác"),
])
def test_van_tay_doi_khi_bat_ky_tham_so_nao_doi(truong, gia_tri_moi):
    khac = {**_GOC, truong: gia_tri_moi}
    assert van_tay(**khac) != van_tay(**_GOC)


def test_van_tay_khong_nham_ranh_gioi_truong():
    # "A\x00B" + "C" va "A" + "B\x00C" tao ra cung chuoi neu dung \x00 lam ngan
    vt1 = van_tay(text="A\x00B", giong="C", nfe=16, speed=1.0, ref_text="ref")
    vt2 = van_tay(text="A", giong="B\x00C", nfe=16, speed=1.0, ref_text="ref")
    assert vt1 != vt2
