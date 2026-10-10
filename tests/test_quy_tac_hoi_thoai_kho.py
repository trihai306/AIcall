"""Quy tắc có nguồn cho các lỗi hội thoại khó ghi nhận ngày 10-10-2026."""
from pathlib import Path

import pytest

from backend.pipeline.tra_loi_khoan_vay import tra_loi


ROOT = Path(__file__).resolve().parents[1]
TC = (ROOT / "knowledge/products/vay_tin_chap.md").read_text(encoding="utf-8")
NHA = (ROOT / "knowledge/products/vay_mua_nha.md").read_text(encoding="utf-8")
THE = (ROOT / "knowledge/products/the_tin_dung.md").read_text(encoding="utf-8")
TK = (ROOT / "knowledge/products/tiet_kiem.md").read_text(encoding="utf-8")


def test_giai_ngan_phi_hop_dong_moi_dap_du_hai_y():
    history = [{"role": "user", "content": "Anh muốn vay 200 triệu trong ba năm."}]
    ma, dap = tra_loi(
        "Thế bao lâu có tiền, có phí gì giấu trong hợp đồng không?", TC, history=history)
    assert ma == "giai_ngan_va_phi"
    assert "24 giờ sau khi phê duyệt" in dap
    assert "miễn phí tư vấn và thẩm định" in dap


@pytest.mark.parametrize("cau", [
    "phí trong hợp đồng cũ của anh là gì",
    "dư nợ của tôi còn bao nhiêu",
])
def test_hop_dong_cu_va_du_no_van_nhuong_cho_ho_so(cau):
    assert tra_loi(cau, TC) is None


def test_dong_the_thieu_nguon_khong_muon_phi_tra_no_vay():
    ma, dap = tra_loi("Nếu anh đóng thẻ ngày mai có bị phạt không?", THE)
    assert ma == "phi_dong_the_chua_co_nguon"
    assert "chưa nêu phí" in dap
    assert "trả trước hạn" not in dap and "miễn phí" not in dap


def test_dong_the_dung_chinh_sach_the_khi_nguon_co_neu():
    doc = THE + "\n## Đóng thẻ\n- Phí đóng thẻ: 100.000đ\n"
    ma, dap = tra_loi("đóng thẻ có mất phí không", doc)
    assert ma == "chinh_sach_dong_the" and "100.000đ" in dap


def test_tinh_lai_tiet_kiem_tu_tien_da_gui_khong_lay_gia_dinh():
    history = [
        {"role": "user", "content": "Cô gửi năm chục triệu thì được tặng quà gì?"},
        {"role": "assistant", "content": "Dạ sổ chưa đạt ngưỡng quà ạ."},
        {"role": "user", "content": "Nếu cô có đúng một trăm triệu thì sao?"},
        {"role": "assistant", "content": "Dạ đó là trường hợp giả định ạ."},
    ]
    ma, dap = tra_loi("Cô gửi sáu tháng, lãi được bao nhiêu tiền?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "50 triệu đồng" in dap and "1,125 triệu đồng" in dap
    assert "4,5%" in dap and "ước tính" in dap
    assert "số ngày gửi thực tế" in dap and "lịch lãi chính thức" in dap


def test_tien_lai_thieu_tien_gui_thi_hoi_lai_khong_doc_moi_apr():
    history = [{"role": "user", "content": "Nếu cô có 100 triệu thì sao?"}]
    ma, dap = tra_loi("Cô gửi sáu tháng, lãi được bao nhiêu tiền?", TK, history=history)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem"
    assert "số tiền gửi" in dap and "4,5%" not in dap


def test_tien_lai_khong_tinh_khi_rut_som_hoac_du_kien_mau_thuan():
    history = [{"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"}]
    ma, dap = tra_loi("Nếu rút sớm thì nhận bao nhiêu tiền lãi?", TK, history=history)
    assert ma == "khong_tinh_lai_rut_truoc_han"
    assert "chưa thể dùng lãi suất kỳ hạn" in dap

    history.append({"role": "user", "content": "Tôi gửi 200 triệu"})
    ma, dap = tra_loi("Mười hai tháng được bao nhiêu tiền lãi?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "200 triệu đồng" in dap and "11 triệu đồng" in dap


def test_tien_lai_khong_tinh_khi_ky_han_khong_co_apr_nguon():
    ma, dap = tra_loi("Tôi gửi 100 triệu trong 9 tháng được bao nhiêu tiền lãi?", TK)
    assert ma == "khong_co_lai_suat_tiet_kiem"
    assert "chưa có một mức lãi suất xác định" in dap and "ước tính khoảng" not in dap


def test_tinh_lai_tiet_kiem_du_tien_va_ky_han_cung_luot():
    ma, dap = tra_loi(
        "Anh gửi tiết kiệm năm trăm triệu kỳ hạn mười hai tháng thì cuối kỳ được bao nhiêu tiền lãi", TK)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "27,5 triệu đồng" in dap and "5,5%" in dap


def test_tiet_kiem_loi_khang_dinh_moi_thay_tien_va_ky_han_cu():
    history = [
        {"role": "user", "content": "Tôi gửi 50 triệu trong 6 tháng"},
        {"role": "assistant", "content": "Dạ em ghi nhận ạ."},
        {"role": "user", "content": "Đổi thành 200 triệu trong 12 tháng nhé"},
        {"role": "assistant", "content": "Dạ em ghi nhận thay đổi ạ."},
    ]
    ma, dap = tra_loi("Cuối kỳ tôi được bao nhiêu tiền lãi?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "200 triệu đồng" in dap and "12 tháng" in dap and "11 triệu đồng" in dap
    assert "50 triệu" not in dap and "6 tháng" not in dap


def test_tiet_kiem_lua_chon_mo_ho_duoc_loi_chot_sau_giai_quyet():
    history = [
        {"role": "user", "content": "Tôi gửi 50 hay 100 triệu, 6 hoặc 12 tháng"},
        {"role": "assistant", "content": "Anh chị chốt giúp em số tiền và kỳ hạn ạ."},
        {"role": "user", "content": "Chốt 100 triệu kỳ hạn 12 tháng"},
        {"role": "assistant", "content": "Dạ em ghi nhận ạ."},
    ]
    ma, dap = tra_loi("Tiền lãi được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "100 triệu đồng" in dap and "12 tháng" in dap and "5,5 triệu đồng" in dap


def test_tiet_kiem_lua_chon_cung_luot_va_gui_them_deu_phai_hoi_ro():
    ma, dap = tra_loi("Tôi gửi 50 hoặc 100 triệu trong 12 tháng thì được bao nhiêu tiền lãi?", TK)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem" and "nhiều số tiền" in dap

    history = [{"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
               {"role": "user", "content": "Tháng sau tôi gửi thêm 50 triệu"}]
    ma, dap = tra_loi("Cuối kỳ được bao nhiêu tiền lãi?", TK, history=history)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem" and "xác nhận" in dap


def test_tiet_kiem_bo_qua_moc_rut_som_va_so_tien_khong_lien_quan():
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": "Nếu rút sau 3 tháng thì sao?"},
        {"role": "user", "content": "Lương tôi 30 triệu, giá nhà khoảng 2 tỷ"},
    ]
    ma, dap = tra_loi("Nếu giữ đến cuối kỳ thì được bao nhiêu tiền lãi?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "100 triệu đồng" in dap and "12 tháng" in dap and "5,5 triệu đồng" in dap


def test_tiet_kiem_nhan_cau_tra_loi_tran_sau_khi_hoi_dung_du_kien():
    history = [
        {"role": "assistant", "content": "Anh chị dự định gửi khoảng bao nhiêu ạ?"},
        {"role": "user", "content": "100 triệu nhé"},
        {"role": "assistant", "content": "Anh chị muốn gửi kỳ hạn bao lâu ạ?"},
        {"role": "user", "content": "mười hai tháng"},
    ]
    ma, dap = tra_loi("Tiền lãi cuối kỳ được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "100 triệu đồng" in dap and "12 tháng" in dap and "5,5 triệu đồng" in dap


@pytest.mark.parametrize("sua, can", [
    ("À không 150 thôi, cuối kỳ được bao nhiêu tiền lãi?", "kèm đơn vị"),
    ("À không, chưa chốt số tiền. Cuối kỳ được bao nhiêu tiền lãi?", "số tiền gửi"),
    ("Thôi rút lại số tiền đó. Cuối kỳ được bao nhiêu tiền lãi?", "số tiền gửi"),
])
def test_sua_tien_gui_chua_du_khong_duoc_dung_lai_tien_cu(sua, can):
    history = [{"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"}]
    ma, dap = tra_loi(sua, TK, history=history)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem"
    assert can in dap and "5,5 triệu đồng" not in dap


@pytest.mark.parametrize("sua", [
    "À không 150 thôi, cuối kỳ được bao nhiêu tiền lãi?",
    "À không, chưa chốt số tiền.",
    "Thôi rút lại số tiền đó.",
])
def test_xac_nhan_tien_day_du_sau_khi_huy_sua_thi_khoi_phuc(sua):
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": sua},
        {"role": "assistant", "content": "Anh chị xác nhận lại số tiền gửi giúp em ạ."},
        {"role": "user", "content": "Chốt 150 triệu"},
    ]
    ma, dap = tra_loi("Cuối kỳ được bao nhiêu tiền lãi?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "150 triệu đồng" in dap and "8,25 triệu đồng" in dap


def test_sua_rieng_ky_han_khong_xoa_tien_gui():
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": "À không, đổi thành kỳ hạn 6 tháng"},
    ]
    ma, dap = tra_loi("Cuối kỳ được bao nhiêu tiền lãi?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "100 triệu đồng" in dap and "6 tháng" in dap and "2,25 triệu đồng" in dap


def test_cau_hoi_chuyen_tien_khong_tao_tien_gui():
    history = [
        {"role": "assistant", "content": "Anh chị muốn chuyển tiền online số tiền bao nhiêu ạ?"},
        {"role": "user", "content": "100 triệu"},
    ]
    ma, dap = tra_loi(
        "Tôi gửi kỳ hạn 12 tháng thì tiền lãi được bao nhiêu?", TK, history=history)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem"
    assert "số tiền gửi" in dap and "5,5 triệu đồng" not in dap


def test_sua_khoan_vay_thu_nhap_va_ky_han_vay_khong_ro_sang_tiet_kiem():
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": "À không, khoản vay đổi thành 200 triệu trong 24 tháng"},
        {"role": "user", "content": "À không, thu nhập đổi thành 30 triệu"},
    ]
    ma, dap = tra_loi("Tiền lãi cuối kỳ được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "100 triệu đồng" in dap and "12 tháng" in dap and "5,5 triệu đồng" in dap
    assert "200 triệu" not in dap and "24 tháng" not in dap and "30 triệu" not in dap


def test_hai_truong_cung_luot_chi_so_co_neo_gui_duoc_cap_nhat():
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": "Thu nhập đổi thành 30 triệu, còn tiền gửi chốt 150 triệu"},
    ]
    ma, dap = tra_loi("Tiền lãi cuối kỳ được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "150 triệu đồng" in dap and "8,25 triệu đồng" in dap
    assert "30 triệu" not in dap


def test_loi_sua_tien_gui_khong_neo_khac_van_hop_le():
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": "À không, đổi thành 150 triệu"},
    ]
    ma, dap = tra_loi("Tiền lãi cuối kỳ được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "150 triệu đồng" in dap and "8,25 triệu đồng" in dap


@pytest.mark.parametrize("sua", [
    "Tiền gửi chốt 150 triệu, thu nhập 30 triệu",
    "Tiền gửi chốt 150 triệu, khoản vay 200 triệu",
    "Thu nhập 30 triệu, tiền gửi chốt 150 triệu",
    "Khoản vay 200 triệu, tiền gửi chốt 150 triệu",
])
def test_neo_sau_dau_phay_khong_cuop_so_tien_gui_menh_de_truoc(sua):
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": sua},
    ]
    ma, dap = tra_loi("Tiền lãi cuối kỳ được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "150 triệu đồng" in dap and "8,25 triệu đồng" in dap


@pytest.mark.parametrize("sua", [
    "Tiền gửi kỳ hạn 6 tháng, khoản vay 24 tháng",
    "Khoản vay 24 tháng, tiền gửi kỳ hạn 6 tháng",
])
def test_ky_han_khoan_vay_khac_menh_de_khong_cuop_ky_gui(sua):
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": sua},
    ]
    ma, dap = tra_loi("Tiền lãi cuối kỳ được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "6 tháng" in dap and "2,25 triệu đồng" in dap and "24 tháng" not in dap


def test_cu_phap_dao_so_truoc_truong_chi_nhan_dung_tien_gui():
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": "150 triệu là tiền gửi, 30 triệu là thu nhập"},
    ]
    ma, dap = tra_loi("Tiền lãi cuối kỳ được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "150 triệu đồng" in dap and "8,25 triệu đồng" in dap
    assert "30 triệu" not in dap


def test_dau_thap_phan_va_hang_nghin_khong_cat_menh_de_so_tien():
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": "Tiền gửi chốt 150,5 triệu, thu nhập 30.000.000 đồng"},
    ]
    ma, dap = tra_loi("Tiền lãi cuối kỳ được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "150,5 triệu đồng" in dap and "8,2775 triệu đồng" in dap


@pytest.mark.parametrize("cau", [
    "Khoản vay 24 tháng, còn tiền gửi được bao nhiêu tiền lãi?",
    "Thời hạn vay 24 tháng, tiền gửi lãi được bao nhiêu tiền?",
])
def test_ky_han_vay_bi_loai_khong_duoc_fallback_lay_lai_khi_thieu_ky_gui(cau):
    history = [{"role": "user", "content": "Tôi gửi 100 triệu"}]
    ma, dap = tra_loi(cau, TK, history=history)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem"
    assert "kỳ hạn gửi" in dap and "11,6 triệu đồng" not in dap


def test_ky_han_vay_bi_loai_khong_ghi_de_ky_gui_da_chot():
    history = [
        {"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 12 tháng"},
        {"role": "user", "content": "Khoản vay đổi thành 24 tháng, còn tiền gửi lãi được bao nhiêu tiền?"},
    ]
    ma, dap = tra_loi("Tiền lãi cuối kỳ được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "12 tháng" in dap and "5,5 triệu đồng" in dap and "24 tháng" not in dap


@pytest.mark.parametrize("ky", ["ba sáu tháng", "ba sau thang"])
def test_ky_gui_dac_biet_van_di_qua_typed_quantity(ky):
    history = [{"role": "user", "content": "Tôi gửi 100 triệu"}]
    ma, dap = tra_loi(f"Tôi gửi kỳ hạn {ky}, tiền lãi được bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "36 tháng" in dap and "6%" in dap and "18 triệu đồng" in dap


@pytest.mark.parametrize("cau", [
    "Khoản vay 24 tháng, còn tiền gửi lãi suất bao nhiêu?",
    "Thời hạn vay 24 tháng, lãi suất tiền gửi bao nhiêu?",
])
def test_apr_khong_lay_ky_han_vay_cung_luot(cau):
    ma, dap = tra_loi(cau, TK)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "3,5%" in dap and "6%" in dap
    assert "5,8%" not in dap and "kỳ hạn 24 tháng lãi suất" not in dap


def test_apr_khong_lay_ky_han_vay_tu_lich_su():
    history = [{"role": "user", "content": "Khoản vay 24 tháng"}]
    ma, dap = tra_loi("Tiền gửi lãi suất bao nhiêu?", TK, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "3,5%" in dap and "6%" in dap and "5,8%" not in dap


def test_apr_ky_gui_da_chot_khong_bi_ky_vay_sau_ghi_de():
    history = [
        {"role": "user", "content": "Tôi gửi kỳ hạn 12 tháng"},
        {"role": "user", "content": "Khoản vay đổi thành 24 tháng"},
    ]
    ma, dap = tra_loi("Tiền gửi lãi suất bao nhiêu?", TK, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "12 tháng" in dap and "5,5%" in dap and "24 tháng" not in dap


@pytest.mark.parametrize("cau, ky, lai", [
    ("sáu tháng thì được mấy phần trăm?", "6 tháng", "4,5%"),
    ("sau thang thi duoc may phan tram?", "6 tháng", "4,5%"),
])
def test_apr_cau_ky_han_doc_lap_co_hoi_phan_tram(cau, ky, lai):
    ma, dap = tra_loi(cau, TK)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert ky in dap and lai in dap


def test_apr_the_mot_nam_theo_ngu_canh_lai_gui_truoc_do():
    history = [{"role": "assistant", "content": "Dạ lãi suất gửi tiết kiệm phụ thuộc kỳ hạn ạ."}]
    ma, dap = tra_loi("thế một năm", TK, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "12 tháng" in dap and "5,5%" in dap


@pytest.mark.parametrize("cau, ky, lai", [
    ("sau thang", "6 tháng", "4,5%"),
    ("the mot nam", "12 tháng", "5,5%"),
])
def test_ky_han_tiet_kiem_khong_dau(cau, ky, lai):
    history = [{"role": "assistant", "content": "Dạ lãi suất gửi tiết kiệm đang tính theo kỳ hạn ạ."}]
    ma, dap = tra_loi(cau, TK, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert ky in dap and lai in dap


def test_tien_lai_gui_online_ap_dung_dung_muc_cong_them_nguon():
    ma, dap = tra_loi(
        "Chị gửi online 100 triệu kỳ hạn 6 tháng, cuối kỳ tiền lãi bao nhiêu?", TK)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi online" in dap and "4,7%" in dap and "2,35 triệu đồng" in dap


def test_kenh_online_trong_lich_su_duoc_dung_chung_cho_phep_tinh():
    history = [{"role": "user", "content": "Tôi gửi online 100 triệu kỳ hạn 6 tháng"}]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi online" in dap and "4,7%" in dap and "2,35 triệu đồng" in dap


def test_sua_kenh_gui_tu_online_sang_quay_thay_muc_lai_ap_dung():
    history = [
        {"role": "user", "content": "Tôi gửi online 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": "À không, đổi từ online sang tại quầy"},
    ]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi tại quầy" in dap and "4,5%" in dap and "2,25 triệu đồng" in dap
    assert "4,7%" not in dap


def test_chuyen_tien_online_khong_ghi_de_kenh_gui_tai_quay():
    history = [
        {"role": "user", "content": "Tôi gửi tại quầy 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": "Tôi chuyển tiền online cho con"},
    ]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi tại quầy" in dap and "4,5%" in dap and "2,25 triệu đồng" in dap


def test_gia_dinh_gui_online_khong_thay_kenh_da_xac_nhan():
    history = [
        {"role": "user", "content": "Tôi gửi tại quầy 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": "Nếu gửi online thì lãi có cao hơn không?"},
    ]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi tại quầy" in dap and "4,5%" in dap and "2,25 triệu đồng" in dap


def test_apr_online_dung_cung_phep_chieu_kenh_va_muc_cong_nguon():
    ma, dap = tra_loi("Tiền gửi online kỳ hạn 6 tháng lãi suất bao nhiêu?", TK)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "gửi online" in dap and "6 tháng" in dap and "4,7%" in dap


@pytest.mark.parametrize("thay_the", [
    "",
    ("- Lãi suất cộng thêm 0.2%/năm so với gửi tại quầy\n"
     "- Lãi suất cộng thêm 0.3%/năm so với gửi tại quầy"),
])
def test_muc_cong_online_nguon_thieu_hoac_xung_dot_khong_dung_lai_co_so(thay_the):
    doc = TK.replace(
        "- Lãi suất cộng thêm 0.2%/năm so với gửi tại quầy",
        thay_the)
    ma, dap = tra_loi(
        "Chị gửi online 100 triệu kỳ hạn 6 tháng, cuối kỳ tiền lãi bao nhiêu?", doc)
    assert ma == "khong_co_lai_suat_tiet_kiem"
    assert "mức cộng thêm online" in dap and "2,25 triệu đồng" not in dap

    ma, dap = tra_loi("Tiền gửi online kỳ hạn 6 tháng lãi suất bao nhiêu?", doc)
    assert ma == "khong_co_lai_suat_tiet_kiem"
    assert "mức cộng thêm online" in dap and "4,5%" not in dap


def test_phuong_an_gui_gia_dinh_chi_dung_du_kien_cua_cau_hien_tai():
    history = [{"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 6 tháng"}]
    gia_dinh = "Nếu tôi gửi 200 triệu kỳ hạn 12 tháng thì tiền lãi bao nhiêu?"
    ma, dap = tra_loi(gia_dinh, TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "nếu gửi 200 triệu đồng" in dap.lower()
    assert "12 tháng" in dap and "11 triệu đồng" in dap
    assert "100 triệu đồng" not in dap and "2,25 triệu đồng" not in dap

    # Kể cả khi lưu câu giả định vào lịch sử, trạng thái thực vẫn là 100m/6th.
    ma, dap = tra_loi(
        "Tiền lãi cuối kỳ được bao nhiêu?", TK,
        history=history + [{"role": "user", "content": gia_dinh}])
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "100 triệu đồng" in dap and "6 tháng" in dap and "2,25 triệu đồng" in dap
    assert "11 triệu đồng" not in dap


def test_phuong_an_gui_gia_dinh_thieu_ky_khong_muon_ky_cu():
    history = [{"role": "user", "content": "Tôi gửi 100 triệu kỳ hạn 6 tháng"}]
    ma, dap = tra_loi(
        "Nếu tôi gửi 200 triệu thì tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem"
    assert "kỳ hạn gửi" in dap
    assert "2,25 triệu đồng" not in dap and "6 tháng" not in dap


@pytest.mark.parametrize("cau_ky", ["sáu tháng", "sau thang"])
def test_ky_gui_tran_luot_dau_duoc_nho_cho_cau_hoi_lai_sau(cau_ky):
    history = [
        {"role": "user", "content": cau_ky},
        {"role": "assistant", "content": "(đường khác)"},
    ]
    ma, dap = tra_loi("lãi bao nhiêu", TK, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "kỳ hạn 6 tháng" in dap and "4,5%" in dap


def test_ky_tran_sau_cau_hoi_khoan_vay_khong_thanh_ky_gui():
    history = [
        {"role": "assistant", "content": "Anh chị muốn vay trong bao lâu ạ?"},
        {"role": "user", "content": "sáu tháng"},
        {"role": "assistant", "content": "(đường khác)"},
    ]
    ma, dap = tra_loi("lãi bao nhiêu", TK, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "3,5%" in dap and "6%" in dap
    assert "kỳ hạn 6 tháng" not in dap


@pytest.mark.parametrize("cap_nhat_khac", [
    "Tôi đổi mật khẩu online banking",
    "Tôi đổi thẻ online",
    "Tôi sửa thông tin online",
])
def test_sua_truong_khac_co_chu_online_khong_doi_kenh_gui(cap_nhat_khac):
    history = [
        {"role": "user", "content": "Tôi gửi online 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": cap_nhat_khac},
    ]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi online" in dap and "4,7%" in dap and "2,35 triệu đồng" in dap


def test_phu_dinh_khong_chot_kenh_moi_buoc_xac_nhan_phuong_thuc():
    history = [
        {"role": "user", "content": "Tôi gửi online 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": "Tôi không gửi online nữa"},
    ]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem"
    assert "hình thức gửi" in dap and "2,25 triệu đồng" not in dap

    ma, dap = tra_loi("Tiền gửi lãi suất bao nhiêu?", TK, history=history)
    assert ma == "lai_tiet_kiem_kenh_mo_ho"
    assert "hình thức gửi" in dap and "4,5%" not in dap


@pytest.mark.parametrize("sua_kenh", [
    "Không online, tại quầy thôi",
    "Tôi không gửi online nữa, chuyển sang tại quầy",
])
def test_phu_dinh_online_roi_chot_quay_lay_khang_dinh_cuoi(sua_kenh):
    history = [
        {"role": "user", "content": "Tôi gửi online 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": sua_kenh},
    ]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi tại quầy" in dap and "4,5%" in dap and "2,25 triệu đồng" in dap

    ma, dap = tra_loi("Tiền gửi lãi suất bao nhiêu?", TK, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "gửi tại quầy" in dap and "4,5%" in dap


def test_lo_ganh_tra_dung_phep_tinh_khoan_vay_va_thu_nhap_da_noi():
    history = [
        {"role": "user", "content": "Anh lương tám triệu một tháng"},
        {"role": "user", "content": "Anh cần vay ba trăm rưỡi trong năm rưỡi"},
    ]
    ma, dap = tra_loi(
        "Lương tám triệu mà tháng đóng thế thì lấy gì ăn em?", TC, history=history)
    assert ma == "can_nhac_kha_nang_tra"
    assert "350 triệu đồng" in dap and "18 tháng" in dap
    assert "7,9%" in dap and "21,7 triệu đồng" in dap
    assert "cao hơn" in dap and "8 triệu đồng" in dap
    assert "chưa đủ để kết luận" in dap and "được duyệt" in dap


def test_lo_ganh_tra_thieu_phuong_an_chi_hoi_tien_va_ky_han():
    ma, dap = tra_loi("Lương tám triệu mà tháng đóng thế thì lấy gì ăn em?", TC)
    assert ma == "can_nhac_kha_nang_tra"
    assert "số tiền muốn vay" in dap and "thời hạn vay" in dap
    assert "thu nhập mỗi tháng" not in dap and "tháng đầu khoảng" not in dap


def test_lo_ganh_tra_thieu_thu_nhap_chi_hoi_thu_nhap():
    history = [{"role": "user", "content": "Tôi vay 100 triệu trong 24 tháng"}]
    ma, dap = tra_loi("Khoản đóng hàng tháng thế này tôi không kham nổi", TC, history=history)
    assert ma == "can_nhac_kha_nang_tra"
    assert "thu nhập mỗi tháng" in dap
    assert "số tiền muốn vay" not in dap and "thời hạn vay" not in dap


def test_khoan_tra_thap_hon_thu_nhap_khong_tu_ket_luan_phu_hop():
    history = [{"role": "user", "content": "Tôi vay 50 triệu trong 60 tháng"}]
    ma, dap = tra_loi(
        "Lương tôi 20 triệu mà vẫn áp lực tiền trả hàng tháng", TC, history=history)
    assert ma == "can_nhac_kha_nang_tra"
    assert "thấp hơn" in dap and "20 triệu đồng" in dap
    assert "chưa đủ để kết luận" in dap and "chi phí sinh hoạt" in dap
    assert "đủ điều kiện" not in dap and "kham được" not in dap


def test_thu_nhap_khoang_khi_lo_ganh_tra_duoc_hoi_mot_muc_cu_the():
    history = [{"role": "user", "content": "Tôi vay 100 triệu trong 24 tháng"}]
    ma, dap = tra_loi(
        "Lương tôi khoảng 8 đến 10 triệu mà tiền đóng thế thì lấy gì ăn?", TC,
        history=history)
    assert ma == "can_nhac_kha_nang_tra"
    assert "nhiều mức thu nhập" in dap and "chưa thể so sánh" in dap
    assert "mức thu nhập dự kiến cụ thể" in dap and "tháng đầu khoảng" not in dap


def test_ky_han_ngoai_khung_khi_lo_ganh_tra_khong_dung_cong_thuc():
    history = [{"role": "user", "content": "Tôi vay 100 triệu trong 4 tháng"}]
    ma, dap = tra_loi(
        "Lương tôi 20 triệu mà vẫn áp lực tiền trả hàng tháng", TC, history=history)
    assert ma == "can_nhac_kha_nang_tra"
    assert "4 tháng" in dap and "từ 12 đến 60 tháng" in dap
    assert "chưa dùng công thức" in dap and "tháng đầu khoảng" not in dap


@pytest.mark.parametrize("phu_dinh", [
    "Không phải online",
    "Không phải tôi gửi online",
])
def test_khong_phai_online_buoc_xac_nhan_lai_kenh_cho_tien_va_apr(phu_dinh):
    history = [
        {"role": "user", "content": "Tôi gửi online 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": phu_dinh},
    ]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem"
    assert "hình thức gửi" in dap and "2,35 triệu đồng" not in dap

    ma, dap = tra_loi("Tiền gửi lãi suất bao nhiêu?", TK, history=history)
    assert ma == "lai_tiet_kiem_kenh_mo_ho"
    assert "hình thức gửi" in dap and "4,7%" not in dap


def test_khong_phai_online_roi_chot_quay_lay_khang_dinh_sau():
    history = [
        {"role": "user", "content": "Tôi gửi online 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": "Không phải tôi gửi online, chuyển sang tại quầy"},
    ]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi tại quầy" in dap and "4,5%" in dap and "2,25 triệu đồng" in dap


@pytest.mark.parametrize("nguon_thu_nhap", [
    "Vợ tôi lương 20 triệu",
    "Bạn tôi lương 20 triệu",
    "Ngân hàng nói lương 20 triệu mới được vay",
])
def test_khong_dung_thu_nhap_nguoi_khac_de_so_khoan_tra(nguon_thu_nhap):
    history = [
        {"role": "user", "content": "Tôi vay 100 triệu trong 24 tháng"},
        {"role": "user", "content": nguon_thu_nhap},
    ]
    ma, dap = tra_loi(
        "Khoản trả hàng tháng thế này tôi không kham nổi", TC, history=history)
    assert ma == "can_nhac_kha_nang_tra"
    assert "thu nhập" in dap and ("chính anh chị" in dap or "người sẽ trả" in dap)
    assert "20 triệu đồng" not in dap and "thấp hơn" not in dap


def test_thu_nhap_cua_minh_khong_bi_thu_nhap_nguoi_khac_sau_ghi_de():
    history = [
        {"role": "user", "content": "Tôi vay 100 triệu trong 24 tháng"},
        {"role": "user", "content": "Lương tôi 12 triệu một tháng"},
        {"role": "user", "content": "Bạn tôi lương 20 triệu"},
    ]
    ma, dap = tra_loi(
        "Khoản trả hàng tháng thế này tôi vẫn áp lực", TC, history=history)
    assert ma == "can_nhac_kha_nang_tra"
    assert "12 triệu đồng" in dap and "20 triệu đồng" not in dap


def test_thu_nhap_ho_gia_dinh_khong_bi_goi_la_thu_nhap_rieng():
    history = [
        {"role": "user", "content": "Tôi vay 100 triệu trong 24 tháng"},
        {"role": "user", "content": "Thu nhập hai vợ chồng là 20 triệu một tháng"},
    ]
    ma, dap = tra_loi(
        "Khoản trả hàng tháng thế này tôi vẫn áp lực", TC, history=history)
    assert ma == "can_nhac_kha_nang_tra"
    assert "thu nhập chung" in dap or "người sẽ trả" in dap
    assert "mức thu nhập 20 triệu đồng anh chị" not in dap


def test_thu_nhap_chung_khong_duoc_dung_de_ket_luan_dat_muc_ca_nhan():
    ma, dap = tra_loi(
        "Thu nhập hai vợ chồng tôi là 40 triệu thì có vay được không?", TC)
    assert ma == "xac_nhan_thu_nhap_ca_nhan"
    assert "yêu cầu thu nhập cá nhân từ 5 triệu đồng" in dap
    assert "thu nhập chung" in dap and "thu nhập riêng" in dap
    assert "đạt mức" not in dap and "đủ điều kiện" not in dap


def test_lam_tu_do_thu_nhap_khong_deu_khong_bi_hoi_nham_so_thu_nhap():
    ma, dap = tra_loi(
        "Anh làm tự do, thu nhập không đều thì có vay được không?", TC)
    assert ma == "dieu_kien_lam_tu_do"
    assert "thu nhập ổn định" in dap and "giấy phép kinh doanh" in dap
    assert "cần thẩm định" in dap
    assert "thu nhập riêng" not in dap


def test_thu_nhap_rieng_thap_khong_duoc_lay_luong_vo_de_nang_muc():
    ma, dap = tra_loi(
        "Lương anh ba triệu, vợ anh hai mươi triệu thì có vay được không?", TC)
    assert ma == "thu_nhap_duoi_muc"
    assert "yêu cầu thu nhập từ 5 triệu đồng" in dap
    assert "thu nhập 3 triệu đồng" in dap
    assert "đạt mức" not in dap


def test_hai_muc_thu_nhap_rieng_van_duoc_xac_nhan_day_du():
    ma, dap = tra_loi("Lương anh ba chục vợ anh hai chục", NHA)
    assert ma == "ghi_nhan_thu_nhap"
    assert dap == ("Dạ em ghi nhận anh chị thu nhập hai vợ chồng là 30 triệu "
                   "và 20 triệu đồng một tháng ạ.")


@pytest.mark.parametrize("sua_kenh", [
    "Online thì không, tại quầy thôi",
    "Online thì không gửi, tại quầy",
])
def test_phu_dinh_kenh_o_hau_to_roi_chot_quay(sua_kenh):
    history = [
        {"role": "user", "content": "Tôi gửi online 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": sua_kenh},
    ]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi tại quầy" in dap and "4,5%" in dap and "2,25 triệu đồng" in dap
    assert "4,7%" not in dap and "2,35 triệu đồng" not in dap

    ma, dap = tra_loi("Tiền gửi lãi suất bao nhiêu?", TK, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "gửi tại quầy" in dap and "4,5%" in dap and "4,7%" not in dap


def test_phu_dinh_kenh_hau_to_khong_chot_kenh_moi_buoc_xac_nhan():
    history = [
        {"role": "user", "content": "Tôi gửi online 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": "Online thì không"},
    ]
    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem"
    assert "hình thức gửi" in dap and "2,35 triệu đồng" not in dap

    ma, dap = tra_loi("Tiền gửi lãi suất bao nhiêu?", TK, history=history)
    assert ma == "lai_tiet_kiem_kenh_mo_ho"
    assert "hình thức gửi" in dap and "4,7%" not in dap


def test_phu_dinh_hau_to_khong_bat_nham_mo_ta_tien_ich_online():
    history = [{"role": "user", "content": "Tôi gửi online 100 triệu kỳ hạn 6 tháng"}]
    ma, dap = tra_loi(
        "Gửi online thì không mất phí mở sổ, cuối kỳ tiền lãi bao nhiêu?", TK,
        history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi online" in dap and "4,7%" in dap and "2,35 triệu đồng" in dap


@pytest.mark.parametrize("cau_trich_dan", [
    "Anh nghe nói yêu cầu lương 20 triệu thì anh có vay được không?",
    "Hồ sơ yêu cầu thu nhập 20 triệu đúng không?",
])
def test_muc_thu_nhap_trich_dan_khong_thanh_thu_nhap_ca_nhan(cau_trich_dan):
    got = tra_loi(cau_trich_dan, TC)
    assert got is None or "20 triệu đồng" not in got[1]
    if got:
        assert "đạt mức" not in got[1] and "đủ điều kiện" not in got[1]


@pytest.mark.parametrize("nguoi_khac", [
    "Người yêu tôi lương 20 triệu",
    "Sếp của tôi lương 20 triệu",
    "Chị tôi lương 20 triệu",
])
def test_thu_nhap_nguoi_khac_khong_thanh_ack_hay_so_sanh_ca_nhan(nguoi_khac):
    ack = tra_loi(nguoi_khac, TC)
    assert ack is None or not (
        ack[0] in ("ghi_nhan_thu_nhap", "thu_nhap_dat_muc") and "20 triệu đồng" in ack[1])

    history = [
        {"role": "user", "content": "Tôi vay 100 triệu trong 24 tháng"},
        {"role": "user", "content": nguoi_khac},
    ]
    ma, dap = tra_loi(
        "Khoản trả hàng tháng thế này tôi không kham nổi", TC, history=history)
    assert ma == "can_nhac_kha_nang_tra"
    assert "người sẽ trả khoản vay" in dap or "chính anh chị" in dap
    assert "20 triệu đồng" not in dap and "thấp hơn" not in dap


@pytest.mark.parametrize("nguoi_khac", [
    "Người yêu tôi lương 20 triệu",
    "Sếp của tôi lương 20 triệu",
    "Chị tôi lương 20 triệu",
])
def test_thu_nhap_rieng_cu_khong_bi_nguoi_khac_sau_ghi_de(nguoi_khac):
    history = [
        {"role": "user", "content": "Tôi vay 100 triệu trong 24 tháng"},
        {"role": "user", "content": "Lương tôi 12 triệu một tháng"},
        {"role": "user", "content": nguoi_khac},
    ]
    ma, dap = tra_loi(
        "Khoản trả hàng tháng thế này tôi vẫn áp lực", TC, history=history)
    assert ma == "can_nhac_kha_nang_tra"
    assert "12 triệu đồng" in dap and "20 triệu đồng" not in dap


@pytest.mark.parametrize("tuoi, ma", [(21, "dieu_kien_tuoi_khong_khop"),
                                       (22, "dieu_kien_tuoi_khop"),
                                       (60, "dieu_kien_tuoi_khop"),
                                       (70, "dieu_kien_tuoi_khong_khop")])
def test_tuoi_doi_chieu_bien_nhung_khong_pham_duyet(tuoi, ma):
    got_ma, dap = tra_loi(f"Tôi {tuoi} tuổi vay tín chấp được không?", TC)
    assert got_ma == ma
    assert "22" in dap and "60" in dap
    assert "chắc chắn" not in dap and "được duyệt" not in dap
    assert "dự định vay" not in dap


def test_ky_han_bon_thang_neu_chua_co_tien_van_neu_muc_12():
    ma, dap = tra_loi("Anh muốn vay bốn tháng", TC)
    assert ma == "ky_han_ngoai_khung"
    assert "chưa được" in dap and "ngắn nhất là 12 tháng" in dap


def test_tai_san_gia_tuong_va_tien_gui_khac_loai_khong_duoc_hua_chung():
    ma, dap = tra_loi("Đất Sao Hỏa có thế chấp vay mua nhà được không?", NHA)
    assert ma == "tai_san_khong_co_chinh_sach" and "không có chính sách" in dap
    ma, dap = tra_loi("Gửi tiết kiệm bằng vàng với USD có giống vậy không?", TK)
    assert ma == "tien_gui_khong_co_chinh_sach" and "chưa nêu chính sách" in dap
    assert "chỉ nhận" not in dap
