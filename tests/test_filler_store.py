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


def test_tat_het_cau_duoi_KHONG_con_la_loi(conn):
    """ĐÃ ĐẢO NGƯỢC 06-09-2026.

    Lý do cũ vẫn đúng ở thời điểm đó: hồi ấy câu đệm CHỈ có câu đuôi, nên tắt
    hết là khách nghe im lặng trọn quãng chờ - phải nổ to lúc khởi động còn hơn
    để lọt ra cuộc gọi thật mới biết.

    Nay đảo vì đã có mẩu mở đầu theo tình huống, câu đệm đứng được một mình.
    Người dùng nói ba lần: "tôi không cần đuôi luôn vì có câu đệm rồi, nhiều cái
    lặp lại rất có vấn đề" - 29/42 câu đuôi cùng một ý "để em xem lại".

    CÁI GIÁ nhận về: lượt không nhận ra tình huống thì không còn gì để phát.
    Đo trên cuộc gọi thử cùng ngày: 7/9 lượt rơi vào đây, im 1,3-2,3 giây.
    """
    them_th(conn)
    them_duoi(conn, bat=0)
    kho = nap_tu_db(conn)
    assert kho.duoi == ()
    assert len(kho.tinh_huong) == 1, "tình huống phải còn nguyên"


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


def test_bang_cau_duoi_rong_KHONG_con_la_loi(conn):
    """Cùng một quyết định đã đảo - xem `test_tat_het_cau_duoi_KHONG_con_la_loi`.

    Bảng rỗng và tắt hết phải đi CÙNG một đường: người dùng xoá trên giao diện
    ra bảng rỗng, còn tắt công tắc ra bat=0, mà ý định thì y hệt nhau.
    """
    them_th(conn)
    assert nap_tu_db(conn).duoi == ()


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
