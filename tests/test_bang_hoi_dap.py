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
