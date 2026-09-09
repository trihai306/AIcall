"""PHÍ và số tiền bằng ĐỒNG - hai chỗ mù của lưới, đo được trên máy thật.

Ba câu AI bịa mà lưới không thấy gì (09-09-2026, qua trang Nhắn tin):

    "phí rút tiền mặt tại ATM là 2.000 đồng/giao dịch"   <- không tài liệu nào có
    "phí thường niên là 2% của hạn mức thẻ"              <- tài liệu ghi 200/400/800 nghìn
    "phí phạt trả trước hạn là 1%"                       <- FAQ ghi vay tín chấp MIỄN PHÍ

Hai nguyên nhân riêng biệt:

1. Bảng thuộc tính KHÔNG có "phí". Mọi con số gắn với phí đều không tìm được
   chủ, nên `cap_trong` bỏ qua và lưới im.

2. Đơn vị "đồng" không nằm trong `_SO`. Mà thêm nó vào thì đụng ngay dấu chấm
   phân cách nghìn của tiếng Việt: `chuan_so("1.500.000")` cho `"1.500"` và
   `chuan_so("200.000")` cho `"200"`. Dấu chấm phải được đọc theo ĐƠN VỊ - tiền
   thì là phân cách nghìn, phần trăm thì là thập phân.
"""
import pytest

from backend.pipeline.thuoc_tinh import (THUOC_TINH_MAC_DINH, cap_trong,
                                         chan_thuoc_tinh_sai, gia_tri_tai_lieu)

DOC_THE = """# Thẻ Tín Dụng
- Hạn mức: 10 triệu - 500 triệu đồng
- Thời gian miễn lãi: lên đến 55 ngày
- Cashback: hoàn tiền 1-3% cho mọi giao dịch
1. Thẻ Classic: phí thường niên 200.000 đồng/năm
2. Thẻ Gold: phí thường niên 400.000 đồng/năm
3. Thẻ Platinum: phí thường niên 800.000 đồng/năm
"""


# --- dấu chấm phân cách nghìn ------------------------------------------------

def test_so_tien_giu_nguyen_hang_nghin():
    """"200.000 đồng" là hai trăm nghìn, không phải hai trăm."""
    assert ("phí thường niên", "200000", "đồng") in cap_trong(
        "Phí thường niên 200.000 đồng một năm ạ.", THUOC_TINH_MAC_DINH)


def test_so_tien_nhieu_nhom_nghin():
    assert ("phí thường niên", "1500000", "đồng") in cap_trong(
        "Phí thường niên 1.500.000 đồng ạ.", THUOC_TINH_MAC_DINH)


def test_dau_cham_o_PHAN_TRAM_van_la_thap_phan():
    """Đổi luật cho tiền KHÔNG được đụng vào lãi suất."""
    assert ("lãi suất", "7.9", "%") in cap_trong(
        "Lãi suất từ 7.9% một năm", THUOC_TINH_MAC_DINH)


def test_dau_phay_thap_phan_van_chay():
    assert ("lãi suất", "7.9", "%") in cap_trong(
        "Lãi suất từ 7,9% một năm", THUOC_TINH_MAC_DINH)


# --- thuộc tính PHÍ ----------------------------------------------------------

def test_doc_duoc_phi_thuong_nien_tu_tai_lieu():
    kho = gia_tri_tai_lieu(DOC_THE, THUOC_TINH_MAC_DINH)
    so = {s for s, _ in kho.get("phí thường niên", set())}
    assert {"200000", "400000", "800000"} <= so, f"đọc ra {sorted(so)}"


def test_bia_phi_thuong_nien_thi_CHAN():
    """Câu thật AI đã nói: "phí thường niên là 2% của hạn mức thẻ"."""
    _, sua = chan_thuoc_tinh_sai(
        "Phí thường niên cho thẻ tín dụng là 2% của hạn mức thẻ ạ.",
        DOC_THE, THUOC_TINH_MAC_DINH)
    assert sua is not None, "phí bịa vẫn lọt"


def test_noi_dung_phi_thuong_nien_thi_cho_qua():
    _, sua = chan_thuoc_tinh_sai(
        "Dạ phí thường niên thẻ Gold là 400.000 đồng một năm ạ.",
        DOC_THE, THUOC_TINH_MAC_DINH)
    assert sua is None, f"chặn oan câu đúng tài liệu: {sua}"


def test_bia_phi_rut_tien_thi_CHAN():
    """Câu thật: "phí rút tiền mặt tại ATM là 2.000 đồng/giao dịch"."""
    _, sua = chan_thuoc_tinh_sai(
        "Dạ phí rút tiền mặt tại ATM là 2.000 đồng một giao dịch ạ.",
        DOC_THE, THUOC_TINH_MAC_DINH)
    assert sua is not None, "tài liệu không có phí rút tiền mà vẫn lọt"


def test_hoan_tien_co_nha_rieng_khong_con_bi_doc_thanh_lai_suat():
    """Trước đây "%" cạnh "hoàn tiền" bị VỨT để khỏi đọc nhầm thành lãi suất.

    Nay nó có thuộc tính riêng nên đối chiếu được thật, không phải né.
    """
    cap = cap_trong("Thẻ được hoàn tiền 3% cho mọi giao dịch ạ.",
                    THUOC_TINH_MAC_DINH)
    assert ("hoàn tiền", "3", "%") in cap
    assert not [x for x in cap if x[0] == "lãi suất"]


def test_hoan_tien_trong_dai_cua_tai_lieu_thi_cho_qua():
    """Tài liệu ghi "1-3%" là một DẢI - 3% nằm trong đó."""
    _, sua = chan_thuoc_tinh_sai("Dạ thẻ hoàn tiền 3% ạ.", DOC_THE,
                                 THUOC_TINH_MAC_DINH)
    assert sua is None, f"3% nằm trong dải 1-3% mà bị chặn: {sua}"


def test_hoan_tien_NGOAI_dai_thi_chan():
    _, sua = chan_thuoc_tinh_sai("Dạ thẻ hoàn tiền 10% ạ.", DOC_THE,
                                 THUOC_TINH_MAC_DINH)
    assert sua is not None


def test_mien_phi_khong_bi_doc_thanh_con_so():
    """"Miễn phí trả trước hạn" không có số - đừng vơ số của vế khác vào."""
    cap = cap_trong("Vay tín chấp miễn phí trả nợ trước hạn, hạn mức 500 triệu ạ.",
                    THUOC_TINH_MAC_DINH)
    assert not [x for x in cap if x[0].startswith("phí")], f"trích thừa: {cap}"
