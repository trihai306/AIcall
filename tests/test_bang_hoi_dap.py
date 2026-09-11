"""Bảng hỏi-đáp: câu đệm + các cách hỏi + nội dung trả lời, trên CÙNG một dòng.

VÌ SAO. Hiện kho tình huống (chọn câu đệm) và `knowledge/*.md` (tra nội dung) là
HAI kho rời, khớp nhau bằng tay - nên câu đệm nói một đằng, nội dung trả về một
nẻo. Và khách hỏi chung chung ("cơ chế thế nào", 0.622) thì trượt cả hai.

Bảng này BỔ SUNG chứ không thay: tra bảng trước, trúng thì lấy nguyên dòng đó;
trượt thì chạy y như cũ. Cái đang chạy không bị đụng tới.
"""
import pytest

from backend.services.bang_hoi_dap import (LoiBang, bo_qua_khac_san_pham,
                                           doc_dong, kiem_dong)


def _dong(**kw):
    d = {"id": "lai_suat_chung", "cau_dem": "Dạ về lãi suất thì,",
         "cau_hoi": ["lãi suất bao nhiêu", "lãi thế nào"],
         "tra_loi": "Lãi suất vay tín chấp từ 10.5% một năm ạ.",
         "san_pham": "vay tín chấp", "bat": True}
    d.update(kw)
    return d


# --- Xác thực dữ liệu gõ tay ---------------------------------------------

def test_dong_hop_le_thi_qua():
    kiem_dong(_dong())


def test_cau_dem_khong_ket_bang_phay_thi_bao_loi():
    # Giống hệt luật của `mo_dau` trong kho tình huống: thiếu phẩy thì F5 hạ
    # giọng kết câu ngay giữa lượt, khách nghe như bot nói xong rồi lại nói tiếp.
    with pytest.raises(LoiBang, match="phẩy"):
        kiem_dong(_dong(cau_dem="Dạ về lãi suất thì"))


def test_khong_co_cach_hoi_nao_thi_bao_loi():
    with pytest.raises(LoiBang, match="cách hỏi"):
        kiem_dong(_dong(cau_hoi=[]))


def test_tra_loi_rong_thi_bao_loi():
    # Dòng không có nội dung mà vẫn khớp thì khách nghe câu đệm rồi im bặt.
    with pytest.raises(LoiBang, match="trả lời"):
        kiem_dong(_dong(tra_loi="   "))


def test_cau_dem_rong_thi_van_hop_le():
    # Không phải dòng nào cũng cần mở lời riêng - để rỗng thì rơi về rổ chung.
    kiem_dong(_dong(cau_dem=""))


# --- Lọc theo sản phẩm đang tư vấn ----------------------------------------

def test_dong_khac_san_pham_bi_loai():
    dk = {"lai_suat_vay": "vay tín chấp", "phi_the": "thẻ tín dụng"}
    assert "phi_the" in bo_qua_khac_san_pham(dk, "vay tín chấp")


def test_dong_dung_san_pham_khong_bi_loai():
    dk = {"lai_suat_vay": "vay tín chấp", "phi_the": "thẻ tín dụng"}
    assert "lai_suat_vay" not in bo_qua_khac_san_pham(dk, "vay tín chấp")


def test_dong_khong_gan_san_pham_thi_luon_duoc_dung():
    # Câu hỏi chung ("bên em ở đâu") không thuộc sản phẩm nào.
    assert bo_qua_khac_san_pham({"dia_chi": ""}, "vay tín chấp") == frozenset()


def test_chua_biet_san_pham_thi_khong_loai_gi():
    # Đầu cuộc gọi chưa rõ khách quan tâm gì - loại hết là mất trắng bảng.
    dk = {"lai_suat_vay": "vay tín chấp", "phi_the": "thẻ tín dụng"}
    assert bo_qua_khac_san_pham(dk, "") == frozenset()


# --- Đọc từ cơ sở dữ liệu -------------------------------------------------

def test_doc_dong_tra_ve_dung_kieu():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE hoi_dap (id TEXT PRIMARY KEY, cau_dem TEXT, "
                 "cau_hoi TEXT, tra_loi TEXT, san_pham TEXT, bat INTEGER)")
    conn.execute("INSERT INTO hoi_dap VALUES (?,?,?,?,?,?)",
                 ("a", "Dạ,", '["hỏi gì đó", "hỏi cách khác"]', "trả lời", "", 1))
    ra = doc_dong(conn)
    assert len(ra) == 1 and ra[0]["cau_hoi"] == ["hỏi gì đó", "hỏi cách khác"]


def test_dong_tat_thi_khong_doc_len():
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE hoi_dap (id TEXT PRIMARY KEY, cau_dem TEXT, "
                 "cau_hoi TEXT, tra_loi TEXT, san_pham TEXT, bat INTEGER)")
    conn.execute("INSERT INTO hoi_dap VALUES (?,?,?,?,?,?)",
                 ("a", "Dạ,", '["x", "y"]', "trả lời", "", 0))
    assert doc_dong(conn) == []


# --- Đọc thẳng hay để mô hình diễn giải -----------------------------------
# ĐO 2026-09-04 trên máy Win: bảng trúng `co_che_vay_chung` điểm 1.000, nội dung
# đã duyệt được đưa vào ngữ cảnh kèm nhãn "dùng ĐÚNG nội dung này". Mô hình VẪN
# tự viết lại và bỏ sạch các con số: 500 triệu, 12-60 tháng, 24-48 giờ đều mất.
# Nội dung đã duyệt mà bị diễn giải lại thì việc duyệt thành vô nghĩa.

from backend.services.bang_hoi_dap import NGUONG_DOC_THANG, doc_thang


def test_khach_hoi_dung_cach_da_soan_thi_doc_thang():
    assert doc_thang(1.0) is True


def test_diem_cao_vua_du_nguong_thi_doc_thang():
    assert doc_thang(NGUONG_DOC_THANG) is True


def test_diem_thap_hon_nguong_thi_de_mo_hinh_dien_giai():
    # Khớp lỏng nghĩa là khách hỏi hơi khác - đọc nguyên văn câu soạn sẵn dễ
    # thành trả lời trớt câu hỏi. Đưa mô hình để nó bám ngữ cảnh.
    assert doc_thang(NGUONG_DOC_THANG - 0.01) is False


def test_nguong_doc_thang_cao_hon_nguong_trung():
    # Trúng bảng (0.75) và đọc nguyên văn là hai mức khác nhau. Bằng nhau thì
    # mọi lần trúng đều đọc cứng, kể cả lần khớp lỏng.
    from backend.services.filler_situation import NGUONG_DIEM
    assert NGUONG_DOC_THANG > NGUONG_DIEM


# --- Tình huống CHÊ: dòng đi theo tình huống, không theo cosine ------------
#
# Cuộc 08c0d3e0 diễn lại 11-09-2026: khách "lãi cao thế", bộ phân loại (có cổng
# ngữ cảnh) chọn ĐÚNG `che_lai_cao`, nhưng câu trả lời vẫn do mô hình sinh và
# đọc lại "7.9%" chứ không nói câu kịch bản. Đo với đúng lịch sử cuộc đó: 4 mẩu
# mở đầu hiện có cho 0/5 câu theo kịch bản (tách riêng thì 5/5 - lịch sử dài
# làm mô hình bỏ qua mục kịch bản). Nên câu trả lời phải là câu ĐÃ DUYỆT.
#
# Và dòng chê KHÔNG được chọn bằng cosine: "hỏi lãi" và "chê lãi" chỉ cách nhau
# 0.026 - đúng lý do bộ phân loại tình huống phải có cổng ngữ cảnh. Khách HỎI
# lãi mà nghe câu chống chê là còn tệ hơn lỗi đang sửa.
import json
import re
import unicodedata
from pathlib import Path

from backend.services.bang_hoi_dap import (NGUONG_DOC_THANG,
                                           bo_qua_chi_theo_tinh_huong,
                                           doc_nguyen_van, dong_theo_tinh_huong)

CHE = frozenset({"che_lai_cao", "che_han_muc_thap", "che_phi_cao"})
BANG = {"che_lai_cao": {}, "che_han_muc_thap": {}, "can_nhung_gi": {}}
GOC = Path(__file__).resolve().parents[1]


def test_tinh_huong_che_co_dong_thi_lay_dung_dong_do():
    assert dong_theo_tinh_huong("che_lai_cao", BANG, CHE) == "che_lai_cao"


def test_tinh_huong_hoi_thi_khong_keo_dong_nao_theo_tinh_huong():
    assert dong_theo_tinh_huong("hoi_lai_suat", BANG, CHE) is None
    assert dong_theo_tinh_huong(None, BANG, CHE) is None


def test_tinh_huong_che_ma_bang_khong_co_dong_thi_de_mo_hinh_tra_loi():
    assert dong_theo_tinh_huong("che_phi_cao", BANG, CHE) is None


def test_dong_ngoai_nhom_che_thi_khong_di_theo_tinh_huong():
    # `can_nhung_gi` có dòng trong bảng nhưng không phải tình huống chê - đường
    # cosine vẫn lo nó như cũ.
    assert dong_theo_tinh_huong("can_nhung_gi", BANG, CHE) is None


def test_dong_che_khong_bao_gio_duoc_chon_bang_cosine():
    assert bo_qua_chi_theo_tinh_huong(BANG, CHE) == {"che_lai_cao", "che_han_muc_thap"}


def test_dong_theo_tinh_huong_thi_doc_nguyen_van_du_diem_thap():
    assert doc_nguyen_van({"theo_tinh_huong": True, "diem": 0.5})


def test_dong_theo_cosine_van_theo_nguong_cu():
    assert not doc_nguyen_van({"diem": 0.5})
    assert doc_nguyen_van({"diem": NGUONG_DOC_THANG})


def _gon(t):
    t = unicodedata.normalize("NFC", t)
    return re.sub(r"\s+", " ", t).strip(" .").lower()


def test_dong_che_trong_bang_mau_la_nguyen_van_kich_ban():
    """Câu đọc cho khách phải là câu TÀI LIỆU dặn, không phải câu viết lại.

    Sửa kịch bản trong tài liệu mà quên bảng thì test này đỏ để nhắc.
    """
    tl = _gon((GOC / "knowledge/products/vay_tin_chap.md").read_text("utf-8"))
    dong = {d["id"]: d for d in json.loads(
        (GOC / "data/hoi_dap_seed.json").read_text("utf-8"))["hoi_dap"]}
    for ma in ("che_lai_cao", "che_han_muc_thap"):
        assert ma in dong, f"bảng mẫu thiếu dòng {ma}"
        kiem_dong(dong[ma])
        assert dong[ma]["san_pham"] == "vay tín chấp"
        assert _gon(dong[ma]["tra_loi"]) in tl, \
            f"{ma}: câu trả lời không có nguyên văn trong tài liệu"
