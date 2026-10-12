"""Các lỗi của tầng luật lộ ra ở bộ thử 156 lượt ngày 12-10-2026."""

from pathlib import Path

from backend.pipeline.luot_thuong_gap import nhan_dang
from backend.pipeline.tra_loi_dieu_kien import nhan_xet_tuoi, tra_loi_dieu_kien
from backend.pipeline.tra_loi_khoan_vay import tra_loi

GOC = Path(__file__).resolve().parents[1] / "knowledge" / "products"


def _doc(ten: str) -> str:
    return (GOC / f"{ten}.md").read_text(encoding="utf-8")


def test_khong_ranh_khong_phai_khong_ranh_roi():
    assert nhan_dang("cháu ơi bác già rồi không rành cháu nói chậm thôi nhé") != "dang_ban"
    assert nhan_dang("anh không rảnh đâu") == "dang_ban"


def test_hai_chu_so_doc_roi_la_tuoi():
    ma, cau = tra_loi_dieu_kien("anh ba hai tuổi", "vay_tin_chap", _doc("vay_tin_chap"))
    assert ma == "dieu_kien_tuoi_khop" and "32" in cau


def test_khung_tuoi_tro_len_cua_the():
    doc = _doc("the_tin_dung")
    assert tra_loi_dieu_kien("chị mười chín tuổi làm thẻ được không", "the_tin_dung", doc)[0] \
        == "dieu_kien_tuoi_khop"
    assert tra_loi_dieu_kien("cháu mười sáu tuổi làm thẻ được không", "the_tin_dung", doc)[0] \
        == "dieu_kien_tuoi_khong_khop"
    assert "19 tuổi" in nhan_xet_tuoi("chị lương sáu triệu mười chín tuổi làm được không", doc)
    assert nhan_xet_tuoi("chị lương sáu triệu làm được không", doc) == ""


def test_khach_neu_ty_le_muon_vay():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    tl = toan_van("vay mua nhà")
    ma, cau = tra_loi("nhà hai tỷ tám anh vay bảy mươi phần trăm", tl)
    assert ma == "ty_le_vay_trong_muc" and "1,96 tỷ" in cau
    assert tra_loi("nhà ba tỷ anh muốn vay 90%", tl)[0] == "ty_le_vay_vuot_muc"
    assert tra_loi("nhà 20 tỷ vay 70 phần trăm", tl)[0] == "ty_le_vay_vuot_muc"
    assert tra_loi("vay mua nhà lãi bao nhiêu phần trăm", tl)[0] == "lai_suat_san_pham"


def test_luoi_lai_suat_chap_nhan_phep_cong_cua_tai_lieu():
    from backend.pipeline.text_normalizer import chan_lai_suat_bia
    tl = _doc("tiet_kiem")
    dung = "Gửi online kỳ hạn 12 tháng thì lãi suất là 5,7% một năm ạ."
    assert chan_lai_suat_bia(dung, tl) == (dung, None)
    assert chan_lai_suat_bia("Gửi online 12 tháng thì lãi suất là 5,9% một năm ạ.", tl)[1]
    # sản phẩm không có dòng "cộng thêm" thì không được nới
    assert chan_lai_suat_bia("Lãi suất 8,1% ạ.", _doc("vay_tin_chap"))[1]


def test_ba_luat_cho_luot_qwen_hay_lech():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    ma, cau = tra_loi("thế có cần sổ đỏ không em", toan_van("vay mua nhà"))
    assert ma == "can_so_do" and "sổ đỏ" in cau
    assert tra_loi("có cần sổ đỏ không", toan_van("vay tín chấp")) is None
    ke = ("chả là thế này em ạ nhà anh đang sửa cái bếp mà thợ nó báo giá cao quá vợ anh thì cứ "
          "giục mà tiền thì đang kẹt nên anh mới tính hỏi xem bên em cho vay thế nào")
    ma, cau = tra_loi(ke, toan_van("vay tín chấp"))
    assert ma == "gioi_thieu_vay" and "7.9%" in cau and "500 triệu" in cau
    assert tra_loi("anh muốn vay hai trăm triệu thì thế nào", toan_van("vay tín chấp"))[0] == "nhu_cau_vay"
    ma, cau = tra_loi("anh xài mỗi tháng chừng mười lăm hai chục củ thì nên làm thẻ gì", toan_van("thẻ tín dụng"))
    assert ma == "goi_y_the_theo_chi_tieu" and "15 đến 20 triệu" in cau and "Classic" in cau and "Gold" in cau
    assert tra_loi("anh tiêu tám trăm triệu một tháng nên làm thẻ nào", toan_van("thẻ tín dụng")) is None


def test_khach_moi_tu_van_san_pham():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    ma, cau = tra_loi("ừ tư vấn với anh về sản phẩm thẻ tín dụng", toan_van("thẻ tín dụng"))
    assert ma == "moi_tu_van" and "Classic" in cau and cau.endswith("?")
    assert tra_loi("em tư vấn gửi tiết kiệm cho chị đi", toan_van("tiết kiệm"))[0] == "moi_tu_van"
    vay = toan_van("vay tín chấp")
    assert tra_loi("tư vấn cho anh về vay tín chấp", vay)[0] == "moi_tu_van"
    assert tra_loi("không cần tư vấn vay đâu", vay) is None
    assert tra_loi("ai giới thiệu em gọi cho anh vay thế", vay) is None
    # hỏi một hạng thẻ cụ thể vẫn là việc của luật riêng
    assert tra_loi("tư vấn thẻ gold cho anh", toan_van("thẻ tín dụng"))[0] == "gioi_thieu_loai_the"


def test_hai_luot_cut_cua_khach_gui_tiet_kiem():
    from backend.pipeline.ngu_canh_tai_lieu import toan_van
    tl = toan_van("tiết kiệm")
    ma, cau = tra_loi("năm chục triệu", tl)
    assert ma == "ghi_nhan_tien_gui" and "50 triệu" in cau
    ma, cau = tra_loi("kỳ hạn", tl)
    assert ma == "ky_han_tiet_kiem" and "1, 3, 6, 12, 24 và 36 tháng" in cau
    assert tra_loi("bác có trăm triệu để trong nhà", tl) is None
    # sản phẩm vay: số tiền trần vẫn là nhu cầu vay
    assert tra_loi("năm chục triệu", toan_van("vay tín chấp"))[0] == "nhu_cau_vay"
