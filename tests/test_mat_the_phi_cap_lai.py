"""Luật thẻ an toàn: mất thẻ, phí cấp lại và đổi sang hạng thẻ cụ thể."""
from pathlib import Path

import pytest

from backend.pipeline.tra_loi_khoan_vay import tra_loi


ROOT = Path(__file__).resolve().parents[1]
THE = (ROOT / "knowledge/products/the_tin_dung.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("cau", [
    "Chị không thấy thẻ sau khi đi chợ, giờ phải làm gì ngay?",
    "Chị nghi bị lấy cắp ở quán, giờ phải làm gì ngay?",
    "Chị để quên thẻ ở sân bay, giờ phải làm gì ngay?",
    "Chị mất cả điện thoại lẫn thẻ, giờ phải làm gì ngay?",
    "Chị rơi ví trên taxi, giờ phải làm gì ngay?",
])
def test_mat_the_uu_tien_khoa_va_kiem_tra_giao_dich(cau):
    ma, dap = tra_loi(cau, THE)
    assert ma == "mat_the"
    assert "khóa thẻ" in dap and "giao dịch gần đây" in dap
    assert "kênh hỗ trợ chính thức" in dap
    assert "OTP" in dap and "PIN" in dap and "mật khẩu" in dap
    assert "đã khóa" not in dap and not any(x in dap for x in ("1900", "200.000", "400.000", "800.000"))


@pytest.mark.parametrize("cau", [
    "Chị máy ATM giữ thẻ, giờ phải làm gì ngay?",
    "Thẻ bị nuốt khi rút tiền, tôi xử lý thế nào?",
])
def test_atm_giu_the_nhac_ghi_vi_tri_thoi_diem_va_khoa(cau):
    ma, dap = tra_loi(cau, THE)
    assert ma == "atm_giu_the"
    assert all(x in dap for x in ("vị trí máy", "thời điểm", "khóa thẻ", "kênh hỗ trợ chính thức"))
    assert "người lạ" in dap and "đã khóa" not in dap and "1900" not in dap


@pytest.mark.parametrize("cau, ma", [
    ("Với lại phí cấp lại bao nhiêu? Em trả lời cả hai ý nhé.", "phi_cap_lai_the_chua_co_nguon"),
    ("Có thu phí khóa thẻ không?", "phi_khoa_the_chua_co_nguon"),
    ("Phí tra soát hoặc tranh chấp giao dịch là bao nhiêu?", "phi_tranh_chap_the_chua_co_nguon"),
])
def test_phi_khac_khong_bi_doi_thanh_phi_thuong_nien(cau, ma):
    got_ma, dap = tra_loi(cau, THE)
    assert got_ma == ma
    assert "chưa nêu phí" in dap and "kênh hỗ trợ chính thức" in dap
    assert "khóa thẻ" in dap and "OTP" in dap
    assert not any(x in dap for x in ("200.000", "400.000", "800.000"))


def test_phi_cap_lai_doc_dung_dong_nguon_neu_tai_lieu_co_neu():
    doc = THE + "\n## Cấp lại thẻ\n- Phí cấp lại thẻ: 100.000đ\n"
    ma, dap = tra_loi("Thẻ mất rồi, phí cấp lại bao nhiêu?", doc)
    assert ma == "phi_cap_lai_the_tu_nguon"
    assert "khóa thẻ" in dap and "100.000đ" in dap
    assert "chưa nêu phí" not in dap


def test_doi_sang_the_gold_doc_du_dung_nguon_khong_muon_phi_vay():
    ma, dap = tra_loi("Khoan, bỏ khoản vay đó. Giờ anh muốn hỏi thẻ Gold cơ.", THE)
    assert ma == "gioi_thieu_loai_the"
    assert all(x in dap for x in ("Gold", "30-200 triệu", "400.000đ", "năm đầu được miễn phí"))
    assert "thẩm định" not in dap and "khoản vay" not in dap


def test_nhieu_hang_the_khong_tu_chon_mot_hang():
    ma, dap = tra_loi("Gold hay Classic phí bao nhiêu?", THE)
    assert ma == "xac_nhan_loai_the"
    assert "chọn một hạng" in dap
    assert not any(x in dap for x in ("200.000", "400.000", "800.000"))


@pytest.mark.parametrize("cau, expected", [
    ("Mở thẻ có mất phí thường niên không?", "phi_the"),
    ("Ví dụ thẻ Gold có hạn mức bao nhiêu?", "han_muc_loai_the"),
    ("Thẻ Gold rơi vào nhóm hạn mức nào?", "han_muc_loai_the"),
    ("Ví điện tử có cashback không?", "hoan_tien_the"),
    ("Thẻ tín dụng trả góp được không?", "tra_gop_the"),
])
def test_tu_mat_roi_vi_khong_chan_nham_luat_the_binh_thuong(cau, expected):
    ma, _ = tra_loi(cau, THE)
    assert ma == expected


def test_phi_thuong_nien_gold_van_doc_bang_phi_cu():
    ma, dap = tra_loi("Thẻ Gold phí thường niên bao nhiêu?", THE)
    assert ma == "phi_loai_the"
    assert "400.000đ" in dap and "năm đầu được miễn phí" in dap
    assert "chưa nêu phí" not in dap


@pytest.mark.parametrize("cau", [
    "Sao kê tôi có dư nợ, số tiền tối thiểu nghĩa là gì?",
    "Có phải luôn bằng đúng 5% dư nợ không?",
    "Tôi chưa đưa sao kê, chỉ hỏi khái niệm chung.",
    "Thanh toán tối thiểu là 5% hay 10%?",
])
def test_thanh_toan_toi_thieu_giai_thich_khai_niem_khong_doan_ty_le(cau):
    ma, dap = tra_loi(cau, THE)
    assert ma == "khai_niem_thanh_toan_toi_thieu"
    assert all(x in dap for x in (
        "phần", "sao kê", "tránh quá hạn", "không phải toàn bộ dư nợ",
        "phần dư nợ còn lại", "lãi hoặc phí", "chưa nêu tỷ lệ",
    ))
    assert "5%" not in dap and "10%" not in dap
    assert "tra được" not in dap and "Thu nhập" not in dap


def test_thanh_toan_toi_thieu_doc_quy_tac_ty_le_neu_nguon_co_neu_ro():
    doc = THE + "\n## Thanh toán tối thiểu\n- Thanh toán tối thiểu: 7% dư nợ sao kê\n"
    ma, dap = tra_loi("Số tiền thanh toán tối thiểu là bao nhiêu?", doc)
    assert ma == "thanh_toan_toi_thieu_tu_nguon"
    assert "7% dư nợ sao kê" in dap
    assert "chưa nêu tỷ lệ" not in dap
    assert "không phải toàn bộ dư nợ" in dap and "phần dư nợ còn lại" in dap


@pytest.mark.parametrize("cau, doc, expected", [
    ("Thu nhập tối thiểu để mở thẻ là bao nhiêu?", THE, "dieu_kien_thu_nhap"),
    ("Hạn mức tối thiểu thẻ Gold là bao nhiêu?", THE, "han_muc_loai_the"),
    ("Trả góp tối thiểu bao nhiêu tháng?", THE, "tra_gop_the"),
    ("Số tiền gửi tối thiểu là bao nhiêu?",
     (ROOT / "knowledge/products/tiet_kiem.md").read_text(encoding="utf-8"),
     "muc_tien_gui_toi_thieu"),
])
def test_toi_thieu_khac_khong_bi_nhan_la_thanh_toan_sao_ke(cau, doc, expected):
    ma, _ = tra_loi(cau, doc)
    assert ma == expected
