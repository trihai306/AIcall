"""Hồi quy kênh gửi online khi người dùng viết liền chữ và số."""
from pathlib import Path

import pytest

from backend.pipeline.tra_loi_khoan_vay import tra_loi


ROOT = Path(__file__).resolve().parents[1]
TK = (ROOT / "knowledge/products/tiet_kiem.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("mo_so", [
    "Chị gửi online100triệu kỳ hạn6tháng",
    "Chi gui online100trieu ky han6thang",
    "Chị gửi100triệu online kỳ hạn6tháng",
    "Chi gui100trieu online ky han6thang",
])
def test_online_viet_lien_dung_chung_kenh_cho_tien_lai_va_apr(mo_so):
    history = [{"role": "user", "content": mo_so}]

    ma, dap = tra_loi("Cuối kỳ được bao nhiêu tiền lãi?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi online" in dap and "4,7%" in dap and "2,35 triệu đồng" in dap

    ma, dap = tra_loi("Lãi suất tiền gửi bao nhiêu?", TK, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "gửi online" in dap and "6 tháng" in dap and "4,7%" in dap


@pytest.mark.parametrize("noi_chuyen_khac", [
    "Tôi đổi mật khẩu online banking",
    "Tôi đổi thẻ online",
    "Tôi chuyển tiền online100triệu cho con",
])
def test_online_khong_thuoc_khoan_gui_khong_ghi_de_kenh(noi_chuyen_khac):
    history = [
        {"role": "user", "content": "Tôi gửi tại quầy 100 triệu kỳ hạn 6 tháng"},
        {"role": "user", "content": noi_chuyen_khac},
    ]

    ma, dap = tra_loi("Cuối kỳ được bao nhiêu tiền lãi?", TK, history=history)
    assert ma == "uoc_tinh_tien_lai_tiet_kiem"
    assert "gửi tại quầy" in dap and "4,5%" in dap and "2,25 triệu đồng" in dap

    ma, dap = tra_loi("Lãi suất tiền gửi bao nhiêu?", TK, history=history)
    assert ma == "lai_tiet_kiem_theo_ky"
    assert "gửi tại quầy" in dap and "4,5%" in dap and "4,7%" not in dap


@pytest.mark.parametrize("phu_dinh", [
    "Tôi không gửi online nữa",
    "Online thì không",
])
def test_phu_dinh_online_sau_cau_viet_lien_van_buoc_xac_nhan_kenh(phu_dinh):
    history = [
        {"role": "user", "content": "Chị gửi online100triệu kỳ hạn6tháng"},
        {"role": "user", "content": phu_dinh},
    ]

    ma, dap = tra_loi("Cuối kỳ được bao nhiêu tiền lãi?", TK, history=history)
    assert ma == "thieu_du_kien_tinh_lai_tiet_kiem"
    assert "hình thức gửi" in dap and "2,35 triệu đồng" not in dap

    ma, dap = tra_loi("Lãi suất tiền gửi bao nhiêu?", TK, history=history)
    assert ma == "lai_tiet_kiem_kenh_mo_ho"
    assert "hình thức gửi" in dap and "4,7%" not in dap
