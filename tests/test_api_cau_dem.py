"""Trang quản lý kho câu đệm.

VÌ SAO CÓ. Câu đệm là thứ khách nghe ĐẦU TIÊN mỗi lượt, phát song song trong lúc
LLM còn đang nghĩ. Kho đang nằm trong SQLite, sửa phải vào thẳng DB - nên suốt
dự án nó đứng nguyên ở 20 tình huống × ĐÚNG MỘT mẩu mở đầu, và khách hỏi cùng
chủ đề hai lần thì nghe y hệt nhau.

`filler_store.nap_tu_db` đã ném lỗi cho dữ liệu sai, nhưng nó ném lúc KHỞI ĐỘNG
BACKEND. Người vận hành gõ thiếu dấu phẩy lúc 3 giờ chiều thì tới lần restart
sau mới biết, mà lúc đó không ai nhớ mình đã sửa gì. Vì thế API phải bắt đúng
những luật ấy ngay lúc lưu.
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")

from backend.api import fillers as fl  # noqa: E402


# --- luật dữ liệu (thuần, không cần DB) -----------------------------------------

def _th(**doi):
    goc = {"id": "hoi_phi", "ten": "Khách hỏi phí",
           "vi_du": ["mất phí gì không", "có tốn phí không"],
           "tu_khoa": ["phí"], "mo_dau": ["Dạ về phí thì,"]}
    goc.update(doi)
    return goc


def test_du_lieu_dung_thi_khong_bao_loi():
    assert fl.kiem_tinh_huong(_th()) == []


def test_mau_mo_dau_khong_ket_bang_phay_bi_chan():
    """Thiếu phẩy thì F5 hạ giọng kết câu ngay giữa lượt - khách nghe như AI nói
    xong rồi, trong khi câu trả lời thật còn chưa tới."""
    loi = fl.kiem_tinh_huong(_th(mo_dau=["Dạ về phí thì"]))
    assert any("phẩy" in l for l in loi)


def test_chi_mot_vi_du_bi_chan():
    """Một ví dụ thì điểm cosine dựa vào đúng một cách nói."""
    loi = fl.kiem_tinh_huong(_th(vi_du=["mất phí gì không"]))
    assert any("ví dụ" in l for l in loi)


def test_thieu_mau_mo_dau_bi_chan():
    loi = fl.kiem_tinh_huong(_th(mo_dau=[]))
    assert loi


def test_id_co_ky_tu_la_bi_chan():
    """id đi thẳng vào khoá chính và vào tên tệp clip."""
    assert fl.kiem_tinh_huong(_th(id="hoi phí/../x")) != []


def test_ten_rong_thi_bi_chan():
    assert fl.kiem_tinh_huong(_th(ten="  ")) != []


def test_bao_HET_loi_mot_lan_chu_khong_dung_o_loi_dau():
    """Sửa một lỗi rồi lưu lại mới thấy lỗi kế tiếp là kiểu hành người dùng."""
    loi = fl.kiem_tinh_huong(_th(vi_du=["một câu"], mo_dau=["Dạ thì"]))
    assert len(loi) >= 2


# --- đếm clip -------------------------------------------------------------------

def test_dem_clip_theo_tich_ba_con_so():
    """Clip = tình huống × mẩu × đuôi, CỘNG rổ đuôi trần. Đếm sai thì cảnh báo
    trước khi dựng cũng sai, mà đó là thứ giữ người dùng khỏi bấm nhầm rồi ngồi
    đợi hai mươi phút."""
    assert fl.dem_clip(so_mau_tong=4, so_duoi=42) == 4 * 42 + 42


def test_khong_co_mau_thi_chi_con_ro_duoi_tran():
    assert fl.dem_clip(so_mau_tong=0, so_duoi=42) == 42


# --- CRUD trên DB thật -----------------------------------------------------------

@pytest.fixture()
def db(tmp_path, monkeypatch):
    from backend.models import db as mdb
    from backend.services import filler_store as fs

    asyncio.run(mdb.init_db(tmp_path / "thu.db"))
    conn = mdb.connection()
    conn.execute("INSERT INTO cau_duoi (id, text, hop_cau_hoi, bat) VALUES "
                 "('d1', 'Dạ', 1, 1)")
    conn.commit()
    fs._kho = None
    # Nhúng lại ví dụ cần model embedding; test chỉ cần biết nó CÓ được gọi.
    goi = {"nap_lai": 0, "nhung_lai": 0}
    monkeypatch.setattr(fl, "_nhung_lai_vi_du", lambda: goi.__setitem__("nhung_lai", goi["nhung_lai"] + 1))
    yield goi
    asyncio.run(mdb.close_db()) if hasattr(mdb, "close_db") else None
    fs._kho = None


def test_luu_roi_thi_thay_trong_danh_sach(db):
    asyncio.run(fl.luu_tinh_huong(_th()))
    d = asyncio.run(fl.danh_sach())
    assert [t["id"] for t in d["tinh_huong"]] == ["hoi_phi"]
    assert d["tinh_huong"][0]["mo_dau"] == ["Dạ về phí thì,"]


def test_du_lieu_sai_thi_KHONG_ghi_vao_db(db):
    """Ghi rồi mới báo lỗi là để lại dữ liệu làm backend không khởi động nổi."""
    r = asyncio.run(fl.luu_tinh_huong(_th(mo_dau=["Dạ thiếu phẩy"])))
    assert "error" in r
    assert asyncio.run(fl.danh_sach())["tinh_huong"] == []


def test_luu_lai_cung_ma_thi_cap_nhat_chu_khong_nhan_doi(db):
    asyncio.run(fl.luu_tinh_huong(_th()))
    asyncio.run(fl.luu_tinh_huong(_th(ten="Khách hỏi phí dịch vụ")))
    d = asyncio.run(fl.danh_sach())
    assert len(d["tinh_huong"]) == 1
    assert d["tinh_huong"][0]["ten"] == "Khách hỏi phí dịch vụ"


def test_luu_xong_phai_nhung_lai_vi_du(db):
    """Thiếu bước này thì tình huống vừa thêm KHÔNG BAO GIỜ được cosine chọn,
    mà không có gì báo - kho có mục mới, đường chạy vẫn mù."""
    asyncio.run(fl.luu_tinh_huong(_th()))
    assert db["nhung_lai"] == 1


def test_tat_tinh_huong_thi_duong_chay_khong_thay_no(db):
    from backend.services.filler_store import nap_lai
    asyncio.run(fl.luu_tinh_huong(_th()))
    assert len(nap_lai().tinh_huong) == 1

    asyncio.run(fl.luu_tinh_huong(_th(bat=False)))
    assert nap_lai().tinh_huong == ()


def test_xoa_tinh_huong(db):
    asyncio.run(fl.luu_tinh_huong(_th()))
    asyncio.run(fl.xoa_tinh_huong(ma="hoi_phi"))
    assert asyncio.run(fl.danh_sach())["tinh_huong"] == []


def test_thong_ke_dem_dung_so_clip_can_dung(db):
    asyncio.run(fl.luu_tinh_huong(_th(mo_dau=["Dạ về phí thì,", "Dạ phí bên em,"])))
    tk = asyncio.run(fl.danh_sach())["thong_ke"]
    assert tk["so_tinh_huong"] == 1
    assert tk["so_mau"] == 2
    assert tk["so_duoi"] == 1
    assert tk["so_clip"] == 2 * 1 + 1


def test_khong_xoa_duoc_cau_duoi_cuoi_cung(db):
    """Rổ đuôi rỗng là khách nghe im lặng trọn quãng chờ, và backend không nạp
    nổi kho ở lần khởi động sau."""
    r = asyncio.run(fl.xoa_cau_duoi(ma="d1"))
    assert "error" in r


# --- thử một câu khách nói -------------------------------------------------------

class _RagGia:
    """Nhúng giả: câu chứa 'phí' nằm cùng hướng với ví dụ của hoi_phi."""

    def embed(self, texts):
        import numpy as np
        return np.array([[1.0, 0.0] if "phí" in t else [0.0, 1.0] for t in texts],
                        dtype=np.float32)


def _gan_rag(monkeypatch, rag=None):
    import types

    from backend.services.filler_situation import chuan_hoa
    from backend.services.filler_store import lay_kho

    gia = types.SimpleNamespace(rag=rag, kho_vector={})
    if rag is not None:
        gia.kho_vector = {t.id: chuan_hoa(rag.embed(list(t.vi_du)))
                          for t in lay_kho().tinh_huong if t.vi_du}
    monkeypatch.setattr(fl, "_trang_thai", lambda: gia)
    return gia


def test_thu_cau_khop_thi_bao_tinh_huong_va_diem(db, monkeypatch):
    asyncio.run(fl.luu_tinh_huong(_th()))
    _gan_rag(monkeypatch, _RagGia())

    d = asyncio.run(fl.thu({"cau": "cho hỏi mất phí gì không"}))

    assert d["id"] == "hoi_phi"
    assert d["dat_nguong"] is True
    assert d["mo_dau"] == ["Dạ về phí thì,"]


def test_thu_cau_khong_khop_thi_noi_ro_se_roi_ve_ro_duoi(db, monkeypatch):
    """Dưới ngưỡng KHÔNG phải lỗi - đó là hành vi cố ý, vì nói sai chủ đề tệ hơn
    nói 'Dạ' trung tính. Nhưng phải nói ra, không thì người dùng tưởng hỏng."""
    asyncio.run(fl.luu_tinh_huong(_th()))
    _gan_rag(monkeypatch, _RagGia())

    d = asyncio.run(fl.thu({"cau": "thôi tôi bận lắm"}))

    assert d["id"] is None
    assert d["dat_nguong"] is False
    assert d["diem"] < d["nguong"]


def test_thu_cau_rong_bi_tu_choi(db, monkeypatch):
    _gan_rag(monkeypatch, _RagGia())
    assert "error" in asyncio.run(fl.thu({"cau": "   "}))


def test_thu_khi_chua_nhung_vi_du_thi_bao_ro(db, monkeypatch):
    """kho_vector rỗng nghĩa là chưa ai nhúng - im lặng trả 'không khớp' ở đây
    sẽ khiến người dùng đi sửa ví dụ trong khi lỗi nằm chỗ khác."""
    asyncio.run(fl.luu_tinh_huong(_th()))
    _gan_rag(monkeypatch, None)

    assert "error" in asyncio.run(fl.thu({"cau": "mất phí gì không"}))


def test_trang_quan_ly_khong_keo_theo_tts():
    """`filler_store` ghi ngay đầu file: cả ba tệp câu đệm phải chạy được trên
    máy không GPU. Trang quản lý cũng vậy - nó chỉ cần ĐƯỜNG DẪN thư mục clip,
    mà import `tts_service` để lấy nó thì kéo cả soundfile lẫn torch theo, và
    mọi test của trang này chết trên máy Mac.

    Chạy trong TIẾN TRÌNH RIÊNG: soi `sys.modules` của tiến trình đang chạy chỉ
    nói lên test nào đã chạy trước đó, không nói gì về module này.
    """
    import subprocess
    import sys as _s

    ma = ("import sys; import backend.api.fillers; "
          "sys.exit(1 if 'backend.services.tts_service' in sys.modules else 0)")
    r = subprocess.run([_s.executable, "-c", ma], cwd=str(Path(__file__).resolve().parents[1]),
                       capture_output=True, text=True)
    assert r.returncode == 0, "import backend.api.fillers kéo theo tts_service"


def test_duong_dan_clip_lay_tu_mot_cho_duy_nhat():
    """Khai lại hằng ở hai nơi thì một ngày nào đó đổi một chỗ, và trang quản lý
    đếm clip trong thư mục KHÁC với thư mục TTS đang ghi vào."""
    from backend.services.filler_store import THU_MUC_FILLER
    assert THU_MUC_FILLER == fl._thu_muc_clip()


# --- dựng tiếng ------------------------------------------------------------------

def test_dung_tieng_bao_so_clip_va_nhan_viec(db, monkeypatch):
    """Người dùng phải thấy con số TRƯỚC khi việc chạy: 5.000 clip là hai mươi
    phút GPU, bấm nhầm rồi ngồi đợi là mất cả buổi."""
    asyncio.run(fl.luu_tinh_huong(_th(mo_dau=["Dạ về phí thì,", "Dạ phí bên em,"])))
    chay = []
    monkeypatch.setattr(fl, "_chay_dung_tieng", lambda: chay.append(1))

    d = asyncio.run(fl.dung_tieng())

    assert d["so_clip"] == 2 * 1 + 1
    assert chay == [1]


def test_khong_chay_hai_viec_dung_cung_luc(db, monkeypatch):
    """Hai lượt dựng song song giành cùng GPU với nhau và với cuộc gọi đang sống."""
    asyncio.run(fl.luu_tinh_huong(_th()))
    monkeypatch.setattr(fl, "_chay_dung_tieng", lambda: None)
    fl._viec["dang_chay"] = True
    try:
        assert "error" in asyncio.run(fl.dung_tieng())
    finally:
        fl._viec["dang_chay"] = False
