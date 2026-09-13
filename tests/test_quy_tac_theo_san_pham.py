"""Luật tài chính phải trả lời đúng SẢN PHẨM của tài liệu đang dùng.

Bộ thử 10.000 câu (13-09-2026) trên máy thật: luật viết cho vay tín chấp nhưng
pipeline truyền tài liệu của mọi sản phẩm, kèm FAQ chung nối phía sau.
- gửi tiết kiệm mọi kỳ hạn: "lãi suất của gói vay là 0.5%/năm" (dòng đầu tiên);
- thẻ Gold/Platinum: "hạn mức tối đa của gói vay 500 triệu" (lấy từ FAQ);
- vay mua nhà: "10000 triệu đồng", "vay bao nhiêu năm" ra hạn mức, lãi sau ưu đãi ra 6.5%.
Test dùng đúng đầu vào thật: `toan_van` = tài liệu sản phẩm + FAQ.
"""
import pytest

from backend.pipeline.ngu_canh_tai_lieu import toan_van
from backend.pipeline.tra_loi_khoan_vay import _fmt_trieu, tra_loi

TK = toan_van("tiết kiệm")
THE = toan_van("thẻ tín dụng")
NHA = toan_van("vay mua nhà")
TC = toan_van("vay tín chấp")


def test_tai_lieu_that_co_kem_faq():
    for tl in (TK, THE, NHA, TC):
        assert "Câu Hỏi Thường Gặp" in tl


# --- gửi tiết kiệm -----------------------------------------------------------
@pytest.mark.parametrize("cau, lai", [
    ("gửi tiết kiệm 1 tháng lãi bao nhiêu", "3,5%"),
    ("à em gửi tiết kiệm 3 tháng lãi bao nhiêu ạ", "3,8%"),
    ("em ơi 6 tháng lãi bao nhiêu", "4,5%"),
    ("gửi một năm lãi bao nhiêu phần trăm", "5,5%"),
    ("thế gửi 12 tháng lãi bao nhiêu thế", "5,5%"),
    ("gửi hai năm lãi bao nhiêu", "5,8%"),
    ("em ơi 24 tháng lãi bao nhiêu nhỉ", "5,8%"),
    ("36 tháng lãi bao nhiêu ạ", "6%"),
    ("gửi ba năm lãi bao nhiêu", "6%"),
    ("gửi ba sáu tháng lãi bao nhiêu", "6%"),
    ("gửi không kỳ hạn lãi bao nhiêu", "0,5%"),
])
def test_tiet_kiem_lai_theo_ky_han(cau, lai):
    got = tra_loi(cau, TK)
    assert got, cau
    assert lai in got[1]
    assert "gói vay" not in got[1]
    if "không kỳ hạn" not in cau:
        assert "0,5" not in got[1] and "0.5" not in got[1]


def test_tiet_kiem_khong_neu_ky_han_thi_doc_khoang():
    got = tra_loi("gửi tiết kiệm lãi suất bao nhiêu", TK)
    assert got and "3,5%" in got[1] and "6%" in got[1]


def test_tiet_kiem_ky_han_khong_co_trong_bieu():
    got = tra_loi("gửi 9 tháng lãi bao nhiêu", TK)
    assert got and "chưa có kỳ hạn 9 tháng" in got[1]
    assert "%" not in got[1]


@pytest.mark.parametrize("cau", [
    "gửi 100 triệu 12 tháng được bao nhiêu tiền lãi",
    "lãi tiết kiệm thấp quá",
    "gửi online được cộng thêm bao nhiêu",
    "rút tiền tiết kiệm trước hạn có mất lãi không",
    "gửi tiết kiệm tối thiểu bao nhiêu",
    "gửi tiết kiệm có cần chứng minh thu nhập không",
    "anh muốn gửi 200 triệu trong 12 tháng",
])
def test_tiet_kiem_khong_dung_luat_khoan_vay(cau):
    got = tra_loi(cau, TK)
    assert got is None or "vay" not in got[1], got


# --- thẻ tín dụng ------------------------------------------------------------
@pytest.mark.parametrize("cau, can", [
    ("cho chị hỏi là thẻ gold hạn mức bao nhiêu", "30-200 triệu"),
    ("ờ thẻ platinum hạn mức bao nhiêu thế", "100-500 triệu"),
    ("thế thẻ classic hạn mức bao nhiêu em", "10-50 triệu"),
    ("thẻ gold phí thường niên bao nhiêu", "400.000đ"),
    ("thẻ platinum phí bao nhiêu", "800.000đ"),
])
def test_the_theo_loai(cau, can):
    got = tra_loi(cau, THE)
    assert got and can in got[1]
    assert "gói vay" not in got[1]


def test_the_han_muc_chung_ke_theo_loai():
    got = tra_loi("thẻ tín dụng hạn mức tối đa bao nhiêu", THE)
    assert got and "500 triệu" in got[1] and "Gold" in got[1]
    assert "gói vay" not in got[1]


@pytest.mark.parametrize("cau", [
    "làm sao để tăng hạn mức thẻ tín dụng",
    "muốn nâng hạn mức thẻ thì làm thế nào",
    "thẻ tín dụng miễn lãi bao nhiêu ngày",
])
def test_the_khong_dung_luat_khoan_vay(cau):
    got = tra_loi(cau, THE)
    assert got is None, got


# --- vay mua nhà -------------------------------------------------------------
@pytest.mark.parametrize("cau", [
    "vay mua nhà vay tối đa được bao nhiêu",
    "chị hỏi chút hạn mức là bao nhiêu em nhé",
])
def test_nha_han_muc_doc_ty_va_80_phan_tram(cau):
    got = tra_loi(cau, NHA)
    assert got and got[0] == "han_muc_san_pham"
    assert "10 tỷ" in got[1] and "80%" in got[1]
    assert "10000" not in got[1]


@pytest.mark.parametrize("cau", [
    "cho anh hỏi vay được bao nhiêu năm em nhé",
    "vay mua nhà vay được bao nhiêu năm vậy",
    "thời hạn vay mua nhà tối đa bao lâu",
])
def test_nha_thoi_han_khong_ra_han_muc(cau):
    got = tra_loi(cau, NHA)
    assert got and got[0] == "thoi_han_san_pham" and "25 năm" in got[1]


@pytest.mark.parametrize("cau", [
    "chị hỏi chút sau hai năm lãi thế nào",
    "hết ưu đãi thì lãi bao nhiêu",
    "sau ưu đãi lãi suất như nào em",
])
def test_nha_lai_sau_uu_dai(cau):
    got = tra_loi(cau, NHA)
    assert got and "8-10%" in got[1] and "6.5" not in got[1]


def test_nha_hoi_lai_chung_doc_ca_hai_giai_doan():
    got = tra_loi("vay mua nhà lãi suất bao nhiêu", NHA)
    assert got and "6.5%" in got[1] and "8-10%" in got[1]


def test_nha_vuot_tran_doc_bang_ty():
    got = tra_loi("anh muốn vay mua nhà 12 tỷ", NHA)
    assert got and got[0] == "vuot_han_muc"
    assert "10 tỷ đồng" in got[1] and "12 tỷ đồng" in got[1]


def test_fmt_ty():
    assert _fmt_trieu(10_000_000_000) == "10 tỷ đồng"
    assert _fmt_trieu(1_500_000_000) == "1,5 tỷ đồng"
    assert _fmt_trieu(500_000_000) == "500 triệu đồng"


# --- vay tín chấp giữ nguyên, kể cả khi có FAQ nối sau --------------------------
def test_tin_chap_khong_doi():
    assert tra_loi("lãi suất vay tín chấp bao nhiêu", TC)[1] == \
        "Dạ lãi suất của gói vay là từ 7.9%/năm ạ."
    hm = tra_loi("vay tín chấp tối đa được bao nhiêu", TC)
    assert hm[0] == "han_muc_san_pham" and "500 triệu đồng" in hm[1]
    th = tra_loi("vay tín chấp được bao nhiêu tháng", TC)
    assert th[0] == "thoi_han_san_pham" and "12 đến 60 tháng" in th[1]


@pytest.mark.parametrize("cau", [
    "chị hỏi chút vay tín chấp trả trong mấy năm ạ",
    "vay tín chấp trả góp bao lâu",
])
def test_tin_chap_tra_trong_may_nam_la_hoi_thoi_han(cau):
    got = tra_loi(cau, TC)
    assert got and got[0] == "thoi_han_san_pham", got


@pytest.mark.parametrize("tl, cau, can", [
    (THE, "mở thẻ tín dụng cần thu nhập bao nhiêu", "5 triệu"),
    (THE, "quẹt thẻ tín dụng trả góp được không", "0%"),
    (TC, "thu nhập bao nhiêu thì vay tín chấp được", "5 triệu"),
    (NHA, "à em yêu cầu lương bao nhiêu em nhé", "10 triệu"),
    (TC, "độ tuổi vay tín chấp là bao nhiêu", "22 đến 60 tuổi"),
    (THE, "thế mấy tuổi thì mở được ạ", "18 tuổi"),
    (TC, "ờ có cần hộ khẩu không vậy", "KT3"),
    (TC, "em ơi có cần kt ba không nhỉ", "KT3"),
    (TC, "không có hợp đồng lao động thì vay được không", "giấy phép kinh doanh"),
    (NHA, "vay mua nhà có cần tài sản đảm bảo không", "tài sản đảm bảo"),
    (TC, "sao kê lương mấy tháng", "3 tháng"),
    (TK, "gửi tiết kiệm có cần chứng minh thu nhập không", "không yêu cầu"),
    (TK, "cho anh hỏi cần điều kiện gì em", "18 tuổi"),
    (TK, "ờ sao lãi gửi thấp thế ạ", "bảo hiểm tiền gửi"),
    (TC, "ờ tất toán sớm vay tín chấp có bị phạt không thế", "miễn phí"),
    (NHA, "vay mua nhà tất toán sớm có bị phạt không", "3 năm"),
])
def test_dieu_kien_doc_thang_tai_lieu(tl, cau, can):
    """Nhóm câu mô hình trượt nhiều nhất trong bộ thử 10k, dù tài liệu có sẵn dòng."""
    got = tra_loi(cau, tl)
    assert got and can in got[1], got
    assert "kiểm tra" not in got[1] and "chưa có thông tin" not in got[1]


@pytest.mark.parametrize("tl, cau, can", [
    (TC, "ờ vay tính chấp có ưu đãi gì không vậy", "voucher"),
    (TC, "thế đang có khuyến mãi gì không thế", "miễn phí tư vấn"),
    (NHA, "vay mua nhà có ưu đãi gì không", "thẩm định"),
    (TK, "gửi tiết kiệm có ưu đãi gì không", "bảo hiểm tai nạn"),
    (THE, "thẻ tín dụng hoàn tiền bao nhiêu phần trăm em", "1-3%"),
    (THE, "cho anh hỏi mở được hạng mức tối đa bao nhiêu thế", "500 triệu"),
    (TC, "chị hỏi chút làm tự do có vay vay tín chấp được không nhỉ", "giấy phép kinh doanh"),
])
def test_uu_dai_hoan_tien_tu_do(tl, cau, can):
    got = tra_loi(cau, tl)
    assert got and can in got[1], got


def test_lai_uu_dai_van_la_hoi_lai_suat():
    got = tra_loi("lãi ưu đãi vay mua nhà là bao nhiêu", NHA)
    assert got and got[0] == "lai_suat_san_pham" and "6.5%" in got[1]


@pytest.mark.parametrize("cau", [
    "à em quẹt thẻ tín dụng trả góp được không vậy",
    "thẻ tín dụng trả góp được không vậy em",
])
def test_the_tra_gop_co_chu_vay_cuoi_cau(cau):
    """Bộ thử 10k #5342: bỏ dấu thì "vậy" thành "vay", luật trả góp thẻ bỏ qua câu."""
    got = tra_loi(cau, THE)
    assert got and got[0] == "tra_gop_the" and "0%" in got[1]


def test_the_vay_tra_gop_van_khong_dung_luat_the():
    assert tra_loi("khoản vay trả góp được không", THE) is None


@pytest.mark.parametrize("tl, cau, can", [
    (TC, "à em vay tính chấp lãi mấy phần trăm vậy", "7.9%"),
    (TC, "vay tín chấp lãi bao nhiêu phần trăm một năm", "7.9%"),
    (NHA, "vay mua nhà lãi mấy phần trăm", "6.5%"),
])
def test_lai_may_phan_tram_la_hoi_lai_suat(tl, cau, can):
    got = tra_loi(cau, tl)
    assert got and got[0] == "lai_suat_san_pham" and can in got[1], got


@pytest.mark.parametrize("cau", [
    "khi nào thì có tiền thế",
    "vay tín chấp bao lâu thì nhận được tiền",
    "có tiền trong bao lâu em",
])
def test_khi_nao_co_tien_la_hoi_giai_ngan(cau):
    """Bộ thử 10k #3380: mô hình đáp "chưa có thông tin về thời gian giải ngân"."""
    got = tra_loi(cau, TC)
    assert got and got[0] == "thoi_gian_giai_ngan" and "24 giờ" in got[1], got


def test_khi_nao_co_tien_de_tra_khong_phai_giai_ngan():
    got = tra_loi("khi nào có tiền thì anh trả nợ trước hạn được không", TC)
    assert not got or got[0] != "thoi_gian_giai_ngan"


@pytest.mark.parametrize("tl, cau, can", [
    (TC, "khi nào có tiền thì anh trả nợ trước hạn được không", "miễn phí"),
    (TC, "vay tín chấp trả nợ trước hạn được không em", "miễn phí"),
    (TC, "tất toán trước hạn thì sao em", "miễn phí"),
    (TC, "anh trả hết nợ sớm có sao không", "miễn phí"),
    (NHA, "vay mua nhà trả trước hạn được không", "3 năm"),
])
def test_tra_truoc_han_khong_can_chu_phi(tl, cau, can):
    got = tra_loi(cau, tl)
    assert got and got[0] == "phi_tra_truoc_han" and can in got[1], got


def test_tra_truoc_han_kem_tinh_tien_khong_bi_bat():
    got = tra_loi("anh muốn trả trước hạn 100 triệu thì mỗi tháng còn đóng bao nhiêu", TC)
    assert not got or got[0] != "phi_tra_truoc_han"
