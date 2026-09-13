from types import SimpleNamespace

import pytest

from backend.pipeline.cong_cu_llm import loc_nhanh
from backend.pipeline.streaming_pipeline import _ghep_ngu_canh
from backend.pipeline.tra_loi_khoan_vay import tra_loi


DOC = """# Vay Tín Chấp
## Thông tin sản phẩm
- Lãi suất: từ 7.9%/năm
- Hạn mức: lên đến 500 triệu đồng
- Thời hạn: 12 - 60 tháng
- Giải ngân: trong vòng 24 giờ sau khi phê duyệt
## Hồ sơ cần thiết
- CMND/CCCD
- Xác nhận thu nhập hoặc sao kê lương 3 tháng gần nhất
## Ví dụ tính toán khoản trả góp
- Ví dụ: vay 300 triệu trong 48 tháng thì trả góp khoảng 8.2 triệu mỗi tháng
"""


def test_khong_do_ho_so_rieng_vao_moi_luot():
    phien = SimpleNamespace(ngu_canh_khach="Hạn mức đã duyệt: 300 triệu")
    chung = "Hạn mức sản phẩm: 500 triệu"
    assert _ghep_ngu_canh(phien, chung) == chung


@pytest.mark.parametrize("cau", [
    "anh muốn vay tầm bốn trăm triệu trong mười hai tháng",
    "tư vấn cho anh khoản vay nếu anh vay trong sáu mươi tháng",
    "mỗi tháng phải trả bao nhiêu",
])
def test_nhu_cau_moi_di_cong_cu_san_pham(cau):
    assert loc_nhanh(cau) == "tra_thong_tin_san_pham"


@pytest.mark.parametrize("cau", [
    "dư nợ của anh còn bao nhiêu",
    "hợp đồng của anh đến hạn ngày nào",
    "khoản vay của anh còn bao nhiêu tháng",
])
def test_hoi_rieng_moi_di_cong_cu_ho_so(cau):
    assert loc_nhanh(cau) == "tra_ho_so_khach"


def test_nhu_cau_moi_chi_dung_tran_san_pham_khong_tron_ho_so_rieng():
    got = tra_loi(
        "anh muốn vay tầm bốn trăm triệu trong vòng mười hai tháng", DOC,
        {"han_muc_da_duyet": "300.000.000 đồng"}, xung_ho="anh")
    assert got and got[0] == "nhu_cau_vay"
    cau = got[1]
    assert "500 triệu" in cau and "400 triệu" in cau
    assert "300 triệu" not in cau
    assert "cần thẩm định" in cau
    assert "vay mua nhà" not in cau


def test_tinh_tra_gop_tu_so_tien_luot_truoc_khong_de_llm_doan():
    history = [
        {"role": "user", "content": "anh muốn vay bốn trăm triệu"},
        {"role": "assistant", "content": "Dạ em ghi nhận."},
        {"role": "user", "content": "nếu vay sáu mươi tháng thì mỗi tháng bao nhiêu"},
    ]
    got = tra_loi(history[-1]["content"], DOC, history=history)
    assert got and got[0] == "tinh_tra_gop"
    assert "9,3 triệu" in got[1]
    assert "giảm dần" in got[1]
    assert "7,4 triệu" not in got[1]


def test_tinh_di_khong_cho_phep_bot_tu_xac_nhan_don_vi_thay_khach():
    """A previous assistant's invented unit is not customer confirmation."""
    history = [
        {"role": "user", "content": "anh muốn vay bốn trăm trong mười hai tháng thì"},
        {"role": "assistant", "content":
         "Anh vay 400 triệu trong 12 tháng thì em sẽ tính toán giúp anh khoản trả góp hàng tháng ạ."},
        {"role": "user", "content": "ờ tính ý"},
    ]
    got = tra_loi(history[-1]["content"], DOC, history=history)
    assert got and got[0] == "xac_nhan_don_vi_vay"
    assert "triệu hay tỷ" in got[1]
    assert "36,0 triệu" not in got[1]
    assert "chuyên viên" not in got[1]


def test_tinh_di_dung_rieng_khong_duoc_tu_bia_con_so():
    assert tra_loi("ờ tính đi", DOC, history=[]) is None


def test_nhac_lai_nhu_cau_sau_mot_hoi_thoai_dai():
    history = [
        {"role": "user", "content":
         "anh đang cần vay tín chấp bốn trăm triệu trong mười hai tháng"},
        {"role": "assistant", "content": "Dạ em ghi nhận ạ."},
    ]
    for i in range(8):
        history.extend([
            {"role": "user", "content": f"câu hỏi khác số {i}"},
            {"role": "assistant", "content": f"câu trả lời khác số {i}"},
        ])
    history.extend([
        {"role": "user", "content": "nếu trả trước hạn sau sáu tháng thì sao"},
        {"role": "assistant", "content": "Dạ em giải thích phí tất toán ạ."},
    ])
    cau = "Em nhắc lại giúp anh số tiền và thời hạn anh nói lúc đầu."
    history.append({"role": "user", "content": cau})

    got = tra_loi(cau, DOC, history=history, xung_ho="anh")
    assert got and got[0] == "nhac_lai_nhu_cau"
    assert "400 triệu" in got[1] and "12 tháng" in got[1]


def test_nhac_lai_thu_nhap_va_tham_nien_sau_nhieu_luot():
    history = [
        {"role": "user", "content":
         "Anh làm công ty được ba năm rồi, lương chuyển khoản mười lăm triệu một tháng."},
        {"role": "assistant", "content": "Dạ em đã ghi nhận."},
    ]
    for i in range(9):
        history.extend([
            {"role": "user", "content": f"nội dung chen giữa {i}"},
            {"role": "assistant", "content": f"phản hồi chen giữa {i}"},
        ])
    cau = "Thu nhập và thời gian làm việc anh đã cung cấp là bao nhiêu?"
    history.append({"role": "user", "content": cau})

    got = tra_loi(cau, DOC, history=history, xung_ho="anh")
    assert got and got[0] == "nhac_lai_thu_nhap"
    assert "15 triệu" in got[1] and "3 năm" in got[1]


def test_luong_khong_bi_hieu_nham_thanh_khoan_vay_mot_thang():
    history = [
        {"role": "user", "content":
         "anh cần vay bốn trăm triệu trong mười hai tháng"},
        {"role": "assistant", "content": "Dạ em ghi nhận."},
        {"role": "user", "content":
         "anh làm công ty ba năm, lương mười lăm triệu một tháng"},
    ]
    got = tra_loi(history[-1]["content"], DOC, history=history, xung_ho="anh")
    assert got and got[0] == "ghi_nhan_thu_nhap"
    assert "15 triệu" in got[1] and "3 năm" in got[1]
    assert "400 triệu" not in got[1]


def test_hoi_dieu_kien_thu_nhap_khong_bi_nhan_la_ho_so_ca_nhan():
    assert tra_loi("thu nhập bao nhiêu thì được vay", DOC, history=[]) is None


def test_cau_voi_thu_nhap_khong_bi_nhan_nham_thanh_hoi_vo():
    got = tra_loi(
        "Với thu nhập đó thì hồ sơ của anh cần thêm giấy tờ gì?", DOC,
        history=[])
    assert got and got[0] == "ho_so_can_thiet"


def test_hoi_lai_suat_kem_tra_hang_thang_phai_dung_nhu_cau_cu():
    history = [
        {"role": "user", "content":
         "anh cần vay bốn trăm triệu trong mười hai tháng"},
        {"role": "assistant", "content": "Dạ em ghi nhận."},
    ]
    cau = "Lãi suất tính thế nào và mỗi tháng anh trả khoảng bao nhiêu?"
    history.append({"role": "user", "content": cau})
    got = tra_loi(cau, DOC, history=history)
    assert got and got[0] == "tinh_tra_gop"
    assert "400 triệu" in got[1] and "12 tháng" in got[1]


def test_cau_can_nhac_vay_duoc_ghi_nhan_la_nhu_cau():
    got = tra_loi(
        "Anh đang cân nhắc vay tín chấp bốn trăm triệu trong mười hai tháng.",
        DOC)
    assert got and got[0] == "nhu_cau_vay"
    assert "400 triệu" in got[1]


def test_tong_hop_ho_so_khong_duoc_chi_nhai_lai_loi_khach():
    got = tra_loi(
        "Tổng hợp ngắn gọn hồ sơ anh cần chuẩn bị, đừng lặp lại lời chào.", DOC)
    assert got and got[0] == "ho_so_can_thiet"
    assert "căn cước" in got[1].lower() and "sao kê" in got[1].lower()


def test_han_muc_chung_doc_thang_tu_tai_lieu():
    got = tra_loi("vay tín chấp tối đa được bao nhiêu", DOC)
    assert got and got[0] == "han_muc_san_pham"
    assert "500 triệu" in got[1]


def test_lai_suat_va_giai_ngan_doc_thang_tu_tai_lieu():
    lai = tra_loi("lãi suất vay tín chấp bao nhiêu", DOC)
    assert lai and lai[0] == "lai_suat_san_pham" and "7.9%/năm" in lai[1]

    giai_ngan = tra_loi("bao lâu thì được giải ngân", DOC)
    assert giai_ngan and giai_ngan[0] == "thoi_gian_giai_ngan"
    assert "24 giờ" in giai_ngan[1]

    giai_ngan_may_ngay = tra_loi("thời gian giải ngân mất mấy ngày em nhỉ", DOC)
    assert giai_ngan_may_ngay and giai_ngan_may_ngay[0] == "thoi_gian_giai_ngan"
    assert "24 giờ" in giai_ngan_may_ngay[1]


def test_phi_tra_truoc_han_doc_dung_san_pham_tu_faq():
    faq = """
# Câu Hỏi Thường Gặp
### Trả nợ trước hạn có mất phí không?
Vay tín chấp: miễn phí trả trước hạn. Vay mua nhà: miễn phí sau 3 năm, trước 3 năm phí 1-2% số tiền trả trước.
"""
    tin_chap = tra_loi("nếu anh muốn trả trước hạn thì có bị phạt gì không em", DOC + faq)
    assert tin_chap and tin_chap[0] == "phi_tra_truoc_han"
    assert "vay tín chấp" in tin_chap[1] and "miễn phí trả trước hạn" in tin_chap[1]

    mua_nha = tra_loi(
        "trả nợ trước hạn có mất phí không",
        DOC.replace("# Vay Tín Chấp", "# Vay Mua Nhà") + faq,
    )
    assert mua_nha and mua_nha[0] == "phi_tra_truoc_han"
    assert "sau 3 năm" in mua_nha[1] and "1-2%" in mua_nha[1]


def test_che_lai_cao_khong_them_cau_xin_loi_vo_co():
    doc = DOC + "\n## Xử lí tình huống khi khách chê\n- Chê lãi cao: do vay không tài sản thế chấp nên lãi sẽ hơi cao chút\n"
    got = tra_loi("lãi suất như vậy anh thấy hơi cao", doc)
    assert got and got[0] == "phan_hoi_lai_cao"
    assert "tài sản thế chấp" in got[1]
    assert "xin lỗi" not in got[1]


def test_no_xau_tat_toan_va_phi_tu_van_doc_thang_tu_tai_lieu():
    doc = DOC + """
## Ưu đãi hiện tại
- Miễn phí tư vấn và thẩm định
## Khách hỏi về nợ xấu
- Nợ đã tất toán trên 1 năm: có thể xem xét, cần kiểm tra hồ sơ cụ thể
"""
    no_xau = tra_loi("anh từng có nợ xấu nhưng đã tất toán hơn một năm rồi", doc)
    assert no_xau and no_xau[0] == "no_xau_da_tat_toan"
    assert "có thể được xem xét" in no_xau[1] and "cần kiểm tra" in no_xau[1]

    phi = tra_loi("nếu anh chưa quyết định thì có mất phí tư vấn không", doc)
    assert phi and phi[0] == "phi_tu_van"
    assert "miễn phí tư vấn" in phi[1]


def test_cau_han_muc_bi_stt_meo_van_doc_dung_tai_lieu():
    got = tra_loi("thuế vay tối đa được bao nhiêu tiền", DOC)
    assert got and got[0] == "han_muc_san_pham"
    assert "500 triệu" in got[1]


@pytest.mark.parametrize("cau, so", [
    ("anh vay ba trăm triệu có được không", "300 triệu"),
    ("ờ thế em anh muốn may tầm bốn trăm triệu được không", "400 triệu"),
])
def test_hoi_so_tien_duoc_khong_chi_xac_nhan_nam_trong_tran(cau, so):
    got = tra_loi(cau, DOC)
    assert got and got[0] == "nhu_cau_vay"
    assert so in got[1] and "500 triệu" in got[1]
    assert "cần thẩm định" in got[1]
    assert "được duyệt" not in got[1]


def test_hoi_giay_to_doc_thang_tu_muc_ho_so():
    got = tra_loi("vay tín chấp thì cần giấy tờ gì", DOC)
    assert got and got[0] == "ho_so_can_thiet"
    assert "căn cước" in got[1].lower()
    assert "sao kê lương" in got[1].lower()


def test_ho_so_uu_tien_giay_to_tuy_than_va_thu_nhap_thay_vi_doc_hai_dong_dau():
    doc = DOC.replace(
        "- Xác nhận thu nhập hoặc sao kê lương 3 tháng gần nhất",
        "- Hộ khẩu hoặc KT3\n- Xác nhận thu nhập hoặc sao kê lương 3 tháng gần nhất",
    )
    got = tra_loi("cần giấy tờ gì", doc)
    assert got and got[0] == "ho_so_can_thiet"
    assert "căn cước" in got[1].lower() and "sao kê lương" in got[1].lower()
    assert "hộ khẩu" not in got[1].lower()


def test_moi_tu_van_thi_tom_tat_du_lieu_chinh_khong_tu_bia():
    got = tra_loi("em tư vấn cho anh về khoản vay bên mình này", DOC)
    assert got and got[0] == "gioi_thieu_san_pham"
    assert "7,9%" in got[1]
    assert "500 triệu" in got[1]
    assert "12 đến 60 tháng" in got[1]


def test_hoi_uu_diem_cung_tom_tat_du_lieu_thay_vi_de_model_tu_khen():
    got = tra_loi("gói này có ưu điểm gì em", DOC)
    assert got and got[0] == "gioi_thieu_san_pham"
    assert "7,9%" in got[1] and "500 triệu" in got[1]
    assert "thấp" not in got[1].lower() and "tốt nhất" not in got[1].lower()


def test_hoi_tien_lai_dung_lai_so_tien_luot_truoc_va_chi_hoi_ky_han():
    history = [
        {"role": "user", "content": "anh vay ba trăm triệu có được không"},
        {"role": "assistant", "content": "Dạ mức đó nằm trong trần sản phẩm ạ."},
        {"role": "user", "content": "cho anh số lãi phải chi trả bao nhiêu"},
    ]
    got = tra_loi(history[-1]["content"], DOC, history=history)
    assert got and got[0] == "thieu_du_kien_tinh_lai"
    assert "300 triệu" in got[1] and "thời hạn" in got[1]
    assert "số tiền muốn vay" not in got[1]


def test_khong_tu_khang_dinh_vo_chong_co_phai_ky_khi_tai_lieu_khong_noi():
    got = tra_loi("vợ anh có phải ký hồ sơ không", DOC)
    assert got and got[0] == "thieu_quy_dinh_nguoi_than_ky"
    assert "chưa nêu" in got[1] and "chưa thể khẳng định" in got[1]
    assert "không cần ký" not in got[1]


def test_lam_tu_do_chi_doc_dieu_kien_co_trong_tai_lieu():
    doc = DOC.replace(
        "## Hồ sơ cần thiết",
        "## Điều kiện vay\n- Có thu nhập ổn định từ 5 triệu đồng/tháng trở lên\n"
        "- Có hợp đồng lao động hoặc giấy phép kinh doanh\n\n## Hồ sơ cần thiết",
    )
    got = tra_loi("anh làm tự do, thu nhập không đều thì có vay được không", doc)
    assert got and got[0] == "dieu_kien_lam_tu_do"
    assert "thu nhập ổn định" in got[1] and "giấy phép kinh doanh" in got[1]
    assert "hợp đồng kinh doanh" not in got[1]
    assert "cần thẩm định" in got[1]


def test_cau_khong_co_so_van_de_llm_xu_ly():
    assert tra_loi("em giới thiệu giúp anh về ngân hàng", DOC) is None
