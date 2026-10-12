"""Hồi quy đọc lại đúng sổ tiết kiệm và tính lãi từ nguồn."""
from pathlib import Path

import pytest

from backend.pipeline.tra_loi_khoan_vay import tra_loi


ROOT = Path(__file__).resolve().parents[1]
TK = (ROOT / "knowledge/products/tiet_kiem.md").read_text(encoding="utf-8")
NHAC_LAI = "Nhắc lại đúng tiền gửi, kỳ hạn, hình thức và ước tính lãi cuối kỳ."


@pytest.mark.parametrize(("khai_bao", "noi_chuyen_khac", "can_co"), [
    ("Sổ tiết kiệm của tôi là 100 triệu, 12 tháng, gửi online.",
     "Khoản vay của tôi là 24 tháng.",
     ("100 triệu đồng", "12 tháng", "gửi online", "5,7%", "5,7 triệu đồng")),
    ("Sổ tiết kiệm của tôi là 150 triệu, 6 tháng, gửi tại quầy.",
     "Tôi đổi mật khẩu online banking.",
     ("150 triệu đồng", "6 tháng", "gửi tại quầy", "4,5%", "3,375 triệu đồng")),
    ("Sổ tiết kiệm của tôi là 125 triệu, 36 tháng, gửi tại quầy.",
     "Xe của tôi dài 30m.",
     ("125 triệu đồng", "36 tháng", "gửi tại quầy", "6%", "22,5 triệu đồng")),
    ("Sổ tiết kiệm của tôi là 125 triệu, 36 tháng, gửi online.",
     "Tôi đổi mật khẩu online banking.",
     ("125 triệu đồng", "36 tháng", "gửi online", "6,2%", "23,25 triệu đồng")),
    ("Sổ tiết kiệm của tôi là 250 triệu, 36 tháng, gửi tại quầy.",
     "Khoản vay tham khảo là 80 triệu trong 60 tháng.",
     ("250 triệu đồng", "36 tháng", "gửi tại quầy", "6%", "45 triệu đồng")),
    ("Sổ tiết kiệm của tôi là 100 triệu, 12 tháng, gửi tại quầy.",
     "Thu nhập của tôi là 30 triệu.",
     ("100 triệu đồng", "12 tháng", "gửi tại quầy", "5,5%", "5,5 triệu đồng")),
])
def test_nhac_lai_so_giu_dung_tien_ky_han_kenh_va_tinh_lai(
        khai_bao, noi_chuyen_khac, can_co):
    history = [
        {"role": "user", "content": khai_bao},
        {"role": "user", "content": noi_chuyen_khac},
    ]

    ma, dap = tra_loi(NHAC_LAI, TK, history=history)

    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert all(cum in dap for cum in can_co)


def test_khai_bao_online_viet_lien_duoc_ghi_nhan_bang_du_kien_co_nguon():
    ma, dap = tra_loi("Chị gửi online100triệu kỳ hạn6tháng", TK)

    assert ma == "ghi_nhan_gui_tiet_kiem"
    assert "100 triệu đồng" in dap and "6 tháng" in dap and "gửi online" in dap
    assert "%" not in dap  # khai báo trần không tự sinh APR khi khách chưa hỏi


def test_cau_tinh_lai_thong_thuong_van_dung_duong_decimal_cu():
    ma, dap = tra_loi(
        "Cuối kỳ được bao nhiêu tiền lãi?", TK,
        history=[{"role": "user", "content":
                  "Tôi gửi online 100 triệu kỳ hạn 6 tháng"}],
    )

    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "4,7%" in dap and "2,35 triệu đồng" in dap


def test_so_khong_bi_du_kien_vay_mat_khau_va_so_do_xe_ghi_de():
    history = [
        {"role": "user", "content":
         "Sổ tiết kiệm của tôi là 100 triệu, 12 tháng, gửi online."},
        {"role": "user", "content": "Khoản vay của tôi là 24 tháng."},
        {"role": "user", "content": "Tôi đổi mật khẩu online banking."},
        {"role": "user", "content": "Xe của tôi dài 30m."},
    ]

    _, dap = tra_loi(NHAC_LAI, TK, history=history)

    assert all(x in dap for x in ("100 triệu đồng", "12 tháng", "gửi online",
                                  "5,7%", "5,7 triệu đồng"))
    assert "24 tháng" not in dap and "30 tháng" not in dap


def test_gia_dinh_khong_ghi_de_so_da_xac_nhan():
    history = [
        {"role": "user", "content":
         "Sổ tiết kiệm của tôi là 100 triệu, 12 tháng, gửi online."},
        {"role": "user", "content": "Nếu gửi 200 triệu trong 6 tháng thì sao?"},
    ]

    _, dap = tra_loi(NHAC_LAI, TK, history=history)

    assert "100 triệu đồng" in dap and "12 tháng" in dap and "5,7 triệu đồng" in dap
    assert "200 triệu đồng" not in dap and "2,35 triệu đồng" not in dap


@pytest.mark.parametrize(("cap_nhat", "truong_can_hoi"), [
    ("Tôi không gửi online nữa", "hình thức gửi"),
    ("Tôi hủy số tiền gửi đó", "số tiền gửi"),
    ("Tôi gửi 50 hoặc 100 triệu", "nhiều số tiền"),
])
def test_phu_dinh_rut_lai_va_mo_ho_khong_duoc_tu_tinh(cap_nhat, truong_can_hoi):
    history = [
        {"role": "user", "content":
         "Sổ tiết kiệm của tôi là 100 triệu, 12 tháng, gửi online."},
        {"role": "user", "content": cap_nhat},
    ]

    ma, dap = tra_loi(NHAC_LAI, TK, history=history)

    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem"
    assert truong_can_hoi in dap and "5,7 triệu đồng" not in dap


@pytest.mark.parametrize("tai_lieu", [
    TK.replace("- Kỳ hạn 12 tháng: lãi suất 5.5%/năm\n", ""),
    TK + "\n- Kỳ hạn 12 tháng: lãi suất 9%/năm\n",
])
def test_khong_tinh_khi_apr_nguon_thieu_hoac_xung_dot(tai_lieu):
    history = [{"role": "user", "content":
                "Sổ tiết kiệm của tôi là 100 triệu, 12 tháng, gửi tại quầy."}]

    ma, dap = tra_loi(NHAC_LAI, tai_lieu, history=history)

    assert ma == "khong_co_lai_suat_tiet_kiem"
    assert "chưa có một mức lãi suất xác định" in dap
    assert "5,5 triệu đồng" not in dap and "9 triệu đồng" not in dap


def test_hoi_nhap_goc_va_phi_noi_ro_phan_nguon_khong_co_va_phan_nguon_co():
    ma, dap = tra_loi(
        "Lãi có tự nhập gốc hay không và phí mở sổ, tất toán thế nào?", TK)

    assert ma == "lai_nhap_goc_va_phi_tiet_kiem"
    assert "nhận lãi cuối kỳ, hoặc hàng tháng nếu khách chọn" in dap
    assert "chưa nêu lãi tự động nhập gốc" in dap
    assert "miễn phí mở sổ và tất toán" in dap
    assert "chuyển khoản" not in dap


def test_online_viet_lien_hoi_muc_cong_tra_diem_phan_tram_va_tong_apr():
    ma, dap = tra_loi("Online12tháng được cộng bao nhiêu lãi?", TK)

    assert ma == "cong_them_lai_online"
    assert "0,2 điểm phần trăm" in dap
    assert "từ 5,5%" in dap and "tổng 5,7%" in dap
    assert "0,2% của" not in dap


@pytest.mark.parametrize("noi_chuyen_khac", [
    "Tôi đổi mật khẩu online banking.",
    "Tôi mở thẻ online.",
    "Khoản vay online của tôi là 24 tháng.",
])
def test_online_o_chuyen_khac_khong_doi_kenh_gui(noi_chuyen_khac):
    history = [
        {"role": "user", "content":
         "Tôi gửi tại quầy 100 triệu kỳ hạn 12 tháng."},
        {"role": "user", "content": noi_chuyen_khac},
    ]

    ma, dap = tra_loi("Lãi suất tiền gửi 12 tháng bao nhiêu?", TK, history=history)

    assert ma == "lai_tiet_kiem_theo_ky"
    assert "gửi tại quầy" in dap and "5,5%" in dap and "5,7%" not in dap


def test_rut_mot_phan_holdout_doc_dung_hai_quy_tac_nguon():
    history = [
        {"role": "user", "content":
         "Tôi có sổ 200 triệu kỳ hạn 12 tháng, gửi tại quầy."},
        {"role": "user", "content":
         "Tôi muốn rút trước 50 triệu, còn 150 triệu để lại."},
    ]

    ma, dap = tra_loi(
        "Hai phần sẽ hưởng lãi thế nào theo tài liệu?", TK, history=history)

    assert ma == "lai_rut_mot_phan_tiet_kiem"
    assert "50 triệu đồng" in dap and "không kỳ hạn 0,5%" in dap
    assert "150 triệu đồng" in dap and "giữ nguyên lãi suất ban đầu 5,5%" in dap
    assert "số ngày gửi thực tế" in dap and "chưa ước tính số tiền lãi" in dap


def test_sau_rut_mot_phan_khong_tinh_lai_tren_toan_bo_so_goc():
    history = [
        {"role": "user", "content":
         "Tôi có sổ 200 triệu kỳ hạn 12 tháng, gửi tại quầy."},
        {"role": "user", "content":
         "Tôi muốn rút trước 50 triệu, còn 150 triệu để lại."},
    ]

    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)

    assert ma == "lai_rut_mot_phan_tiet_kiem"
    assert "50 triệu đồng" in dap and "150 triệu đồng" in dap
    assert "11 triệu đồng" not in dap


def test_rut_mot_phan_nhieu_muc_buoc_xac_nhan_lai():
    history = [{"role": "user", "content":
                "Tôi có sổ 200 triệu kỳ hạn 12 tháng, gửi tại quầy."}]

    ma, dap = tra_loi(
        "Tôi muốn rút trước 50 hoặc 80 triệu.", TK, history=history)

    assert ma == "xac_nhan_rut_mot_phan_tiet_kiem"
    assert "xác nhận" in dap and "mỗi phần một số tiền" in dap
    assert "0,5%" not in dap and "11 triệu đồng" not in dap


def test_rut_mot_phan_gia_dinh_duoc_tra_loi_co_dieu_kien_nhung_khong_luu():
    base = [{"role": "user", "content":
             "Tôi có sổ 200 triệu kỳ hạn 12 tháng, gửi tại quầy."}]
    gia_dinh = "Nếu tôi rút trước 50 triệu thì phần còn lại hưởng lãi thế nào?"

    ma, dap = tra_loi(gia_dinh, TK, history=base)
    assert ma == "lai_rut_mot_phan_tiet_kiem"
    assert "nếu rút trước hạn 50 triệu đồng" in dap and "150 triệu đồng" in dap

    ma, dap = tra_loi(
        "Cuối kỳ tiền lãi bao nhiêu?", TK,
        history=base + [{"role": "user", "content": gia_dinh}],
    )
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "200 triệu đồng" in dap and "11 triệu đồng" in dap


@pytest.mark.parametrize(("sau_rut", "can_co", "khong_co"), [
    ("Tôi không rút nữa, cuối kỳ tiền lãi bao nhiêu?",
     ("200 triệu đồng", "11 triệu đồng"), ("50 triệu đồng",)),
    ("Tôi gửi mới 100 triệu kỳ hạn 6 tháng tại quầy.",
     ("100 triệu đồng", "6 tháng"), ("150 triệu đồng",)),
])
def test_huy_rut_hoac_so_moi_thay_trang_thai_rut_cu(sau_rut, can_co, khong_co):
    history = [
        {"role": "user", "content":
         "Tôi có sổ 200 triệu kỳ hạn 12 tháng, gửi tại quầy."},
        {"role": "user", "content":
         "Tôi muốn rút trước 50 triệu, còn 150 triệu để lại."},
    ]
    if "gửi mới" in sau_rut:
        history.append({"role": "user", "content": sau_rut})
        cau = "Cuối kỳ tiền lãi bao nhiêu?"
    else:
        cau = sau_rut

    _, dap = tra_loi(cau, TK, history=history)

    assert all(x in dap for x in can_co)
    assert all(x not in dap for x in khong_co)


def test_tra_truoc_khoan_vay_khong_thanh_rut_so_tiet_kiem():
    history = [
        {"role": "user", "content":
         "Tôi có sổ 200 triệu kỳ hạn 12 tháng, gửi tại quầy."},
        {"role": "user", "content": "Tôi trả trước khoản vay 50 triệu."},
    ]

    ma, dap = tra_loi("Cuối kỳ tiền lãi bao nhiêu?", TK, history=history)

    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "200 triệu đồng" in dap and "11 triệu đồng" in dap
    assert "không kỳ hạn 0,5%" not in dap


def test_de_xuat_900_nghin_duoc_doi_chieu_muc_toi_thieu_khong_hua_duyet():
    ma, dap = tra_loi("Mẹ tôi có 900 nghìn muốn gửi, còn tôi không gửi.", TK)

    assert ma == "tien_gui_duoi_muc_toi_thieu"
    assert "900 nghìn đồng" in dap and "tối thiểu 1 triệu đồng" in dap
    assert "gửi được" not in dap and "đủ điều kiện" not in dap and "tuổi" not in dap


def test_sua_xuong_500_nghin_khong_giu_muc_5_trieu_cu():
    history = [{"role": "user", "content": "Tôi muốn gửi 5 triệu."}]

    ma, dap = tra_loi(
        "Xin sửa: chỉ có 500 nghìn thôi, không phải 5 triệu.", TK, history=history)

    assert ma == "tien_gui_duoi_muc_toi_thieu"
    assert "500 nghìn đồng" in dap and "tối thiểu 1 triệu đồng" in dap
    assert "gửi 5 triệu" not in dap and "đủ điều kiện" not in dap


def test_hoi_muc_toi_thieu_sau_de_xuat_cua_nguoi_khac_chi_doc_nguon():
    history = [{"role": "user", "content":
                "Mẹ tôi có 900 nghìn muốn gửi, còn tôi không gửi."}]

    ma, dap = tra_loi("Mức tối thiểu của sản phẩm là bao nhiêu?", TK, history=history)

    assert ma == "muc_tien_gui_toi_thieu"
    assert "tối thiểu" in dap and "1 triệu đồng" in dap
    assert "900 nghìn" not in dap and "tiền của anh" not in dap


def test_de_xuat_nhieu_muc_khong_tu_chon_mot_so_tien():
    ma, dap = tra_loi("Tôi muốn gửi 500 hoặc 900 nghìn.", TK)

    assert ma == "xac_nhan_tien_gui"
    assert "nhiều số tiền" in dap and "xác nhận một mức cụ thể" in dap
    assert "đủ điều kiện" not in dap


def test_de_xuat_duoi_muc_gia_dinh_giu_nhan_neu():
    ma, dap = tra_loi("Nếu tôi chỉ gửi 500 nghìn thì sao?", TK)

    assert ma == "tien_gui_duoi_muc_toi_thieu"
    assert "nếu khoản dự kiến" in dap and "500 nghìn đồng" in dap
    assert "tối thiểu 1 triệu đồng" in dap


@pytest.mark.parametrize("tai_lieu", [
    TK.replace("- Số tiền gửi tối thiểu: 1 triệu đồng\n", ""),
    TK + "\n- Số tiền gửi tối thiểu: 2 triệu đồng\n",
])
def test_nguon_muc_toi_thieu_thieu_hoac_xung_dot_khong_tu_doi_chieu(tai_lieu):
    ma, dap = tra_loi("Tôi muốn gửi 500 nghìn.", tai_lieu)

    assert ma == "muc_tien_gui_toi_thieu_chua_ro"
    assert "500 nghìn đồng" in dap and "chưa có một mức tiền gửi tối thiểu duy nhất" in dap
    assert "đủ điều kiện" not in dap


@pytest.mark.parametrize("cau", [
    "Sổ VND online lãi suất bao nhiêu?",
    "Sổ online lãi suất bao nhiêu?",
    "Sổ thật là100triệu đồng online; lãi suất bao nhiêu?",
])
def test_so_online_khong_neu_ky_han_van_ap_dung_bonus_cho_ca_dai(cau):
    assert tra_loi(cau, TK) == (
        "lai_tiet_kiem_theo_ky",
        "Dạ lãi suất gửi online từ 3,7% một năm cho kỳ hạn 1 tháng đến "
        "6,2% một năm cho kỳ hạn 36 tháng ạ.",
    )


def test_bitcoin_online_khong_cuop_cau_hoi_so_vnd_online_sau_do():
    history = [{"role": "user", "content":
                "Tôi đang xem giá Bitcoin online, không liên quan sổ tiết kiệm."}]

    ma, dap = tra_loi("Sổ VND online lãi suất bao nhiêu?", TK, history=history)

    assert ma == "lai_tiet_kiem_theo_ky"
    assert "gửi online" in dap and "3,7%" in dap and "6,2%" in dap
    assert "12 tháng" not in dap


@pytest.mark.parametrize("cau", [
    "Số CCCD online của tôi là 123, lãi suất bao nhiêu?",
    "Số điện thoại online của tôi đổi rồi, lãi suất bao nhiêu?",
    "Khoản vay online lãi suất bao nhiêu?",
    "Thẻ online lãi suất bao nhiêu?",
])
def test_online_khong_co_neo_so_khong_duoc_ap_bonus_tiet_kiem(cau):
    got = tra_loi(cau, TK)

    assert got is None or (
        "3,7%" not in got[1] and "6,2%" not in got[1]
        and "lãi suất gửi online" not in got[1])


def test_online_duoc_trich_dan_khong_thanh_kenh_gui_that():
    ma, dap = tra_loi('Sổ của tôi ghi chữ "online", lãi suất bao nhiêu?', TK)

    assert ma == "lai_tiet_kiem_theo_ky"
    assert "3,5%" in dap and "6%" in dap
    assert "3,7%" not in dap and "6,2%" not in dap


@pytest.mark.parametrize("cau", [
    "Sổ của tôi không phải online, lãi suất bao nhiêu?",
    "Sổ online hay tại quầy lãi suất bao nhiêu?",
])
def test_online_bi_phu_dinh_hoac_canh_tranh_buoc_xac_nhan_kenh(cau):
    ma, dap = tra_loi(cau, TK)

    assert ma == "lai_tiet_kiem_kenh_mo_ho"
    assert "xác nhận" in dap and "hình thức gửi" in dap
    assert "3,7%" not in dap and "6,2%" not in dap


@pytest.mark.parametrize("tai_lieu", [
    TK.replace("- Lãi suất cộng thêm 0.2%/năm so với gửi tại quầy\n", ""),
    TK.replace(
        "- Lãi suất cộng thêm 0.2%/năm so với gửi tại quầy",
        "- Lãi suất cộng thêm 0.2%/năm so với gửi tại quầy\n"
        "- Lãi suất cộng thêm 0.4%/năm so với gửi tại quầy",
    ),
])
def test_dai_lai_online_khong_dung_bonus_nguon_thieu_hoac_xung_dot(tai_lieu):
    ma, dap = tra_loi("Sổ VND online lãi suất bao nhiêu?", tai_lieu)

    assert ma == "khong_co_lai_suat_tiet_kiem"
    assert "mức cộng thêm online" in dap
    assert "3,7%" not in dap and "6,2%" not in dap
