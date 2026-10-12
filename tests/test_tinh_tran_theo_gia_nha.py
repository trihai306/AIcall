"""Tính LTV chỉ từ giới hạn nguồn và giá BĐS khách nói rõ."""

from decimal import Decimal
from pathlib import Path

import pytest

from backend.pipeline.tra_loi_khoan_vay import (
    _gia_bds_hien_tai, _gioi_han_ltv, tra_loi,
)


ROOT = Path(__file__).resolve().parents[1]
MUA_NHA = (ROOT / "knowledge/products/vay_mua_nha.md").read_text(encoding="utf-8")
CAU_HOI = (
    "Nếu chỉ xét hạn mức sản phẩm thì 80% tối đa là bao nhiêu, "
    "có chắc được vay mức đó không?"
)


def users(*contents: str) -> list[dict]:
    return [{"role": "user", "content": content} for content in contents]


def test_nguon_ltv_la_decimal_va_9_ty_tinh_chinh_xac_7_2_ty():
    ratio, cap = _gioi_han_ltv(MUA_NHA)
    assert ratio == Decimal("80")
    assert cap == Decimal("10000000000")
    assert Decimal("9000000000") * ratio / Decimal(100) == Decimal("7200000000")

    code, answer = tra_loi(
        CAU_HOI, MUA_NHA,
        history=users("Tôi định mua căn hộ giá 9 tỷ đồng."),
    )
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "7,2 tỷ đồng" in answer and "80%" in answer and "10 tỷ đồng" in answer
    assert "phụ thuộc thẩm định hồ sơ" in answer and "không phải cam kết phê duyệt" in answer


def test_20_ty_ap_dung_tran_tuyet_doi_10_ty():
    code, answer = tra_loi(
        CAU_HOI, MUA_NHA,
        history=users("Giá trị căn nhà là 20 tỷ đồng."),
    )
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "80% tương đương 16 tỷ đồng" in answer
    assert "hạn mức tối đa theo sản phẩm là 10 tỷ đồng" in answer


@pytest.mark.parametrize("gia", [
    "can ho gia 9 ty dong",
    "Căn hộ giá 9tỷ.",
    "Giá nhà là chín tỷ đồng.",
])
def test_gia_viet_ascii_dinh_lien_hoac_bang_chu(gia):
    got = tra_loi(CAU_HOI, MUA_NHA, history=users(gia))
    assert got and got[0] == "han_muc_theo_gia_bat_dong_san"
    assert "7,2 tỷ đồng" in got[1]


def test_gia_sua_ro_thay_the_gia_cu():
    history = users(
        "Tôi định mua căn hộ giá 9 tỷ đồng.",
        "Sửa lại, giá căn hộ là 8 tỷ đồng.",
    )
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=history)
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "6,4 tỷ đồng" in answer
    assert "7,2 tỷ" not in answer and "9 tỷ" not in answer


@pytest.mark.parametrize("history", [
    users("Căn thứ nhất giá 9 tỷ, căn thứ hai giá 8 tỷ."),
    users("Tôi xem căn hộ giá 9 tỷ.", "Tôi cũng cân nhắc căn khác giá 8 tỷ."),
    users("Tôi xem căn hộ giá 9 tỷ.", "Tôi chưa chốt giá căn hộ."),
    users("Tôi xem căn hộ giá 9 tỷ.", "Bỏ mức giá 9 tỷ đó đi."),
])
def test_nhieu_gia_hoac_rut_gia_phai_hoi_lai(history):
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=history)
    assert code == "xac_nhan_gia_bat_dong_san"
    assert "xác nhận" in answer and "một giá trị bất động sản" in answer
    assert "7,2 tỷ" not in answer and "6,4 tỷ" not in answer


def test_chi_lay_gia_khach_noi_khong_lay_khoan_vay_thu_nhap_hay_loi_ai():
    history = [
        {"role": "user", "content": "Căn hộ có giá 9 tỷ đồng."},
        {"role": "assistant", "content": "Tài liệu nói tối đa 10 tỷ đồng."},
        {"role": "user", "content": "Tôi muốn vay 4 tỷ và thu nhập 30 triệu một tháng."},
        {"role": "user", "content": "Tôi còn có thu nhập 2.000 USD từ nước ngoài."},
    ]
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=history)
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "7,2 tỷ đồng" in answer
    assert "4 tỷ" not in answer and "30 triệu" not in answer and "2.000 USD" not in answer


def test_gia_gia_dinh_hien_tai_khong_dung_gia_that_cu_va_phai_noi_co_dieu_kien():
    code, answer = tra_loi(
        "Nếu căn nhà giá 20 tỷ thì vay tối đa bao nhiêu?", MUA_NHA,
        history=users("Căn hộ tôi đang xem giá 9 tỷ đồng."),
    )
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert answer.startswith("Dạ nếu bất động sản có giá 20 tỷ đồng")
    assert "tối đa theo sản phẩm là 10 tỷ đồng" in answer
    assert "đủ điều kiện" not in answer and "chắc chắn" not in answer


@pytest.mark.parametrize("gia_dinh", [
    "Nếu căn hộ giá 9 tỷ thì vay tối đa bao nhiêu?",
    "Gia dinh can ho gia 9 ty thi vay toi da bao nhieu?",
])
def test_gia_gia_dinh_trong_lich_su_khong_thanh_gia_that(gia_dinh):
    code, answer = tra_loi(
        "Hạn mức vay tối đa bao nhiêu?", MUA_NHA,
        history=users(gia_dinh),
    )
    assert code == "han_muc_san_pham"
    assert "80%" in answer and "10 tỷ đồng" in answer
    assert "7,2 tỷ" not in answer and not answer.startswith("Dạ nếu")


def test_gia_that_cu_khong_bi_gia_gia_dinh_sau_do_thay_the():
    history = users(
        "Căn hộ tôi đang xem giá 9 tỷ đồng.",
        "Nếu căn khác giá 20 tỷ thì vay tối đa bao nhiêu?",
    )
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=history)
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "7,2 tỷ đồng" in answer
    assert "16 tỷ" not in answer and "20 tỷ" not in answer


def test_gia_gia_dinh_truoc_roi_gia_nha_cua_gia_dinh_toi_van_la_gia_that():
    history = users(
        "Giả định căn hộ giá 9 tỷ thì vay tối đa bao nhiêu?",
        "Giá trị nhà của gia đình tôi là 8 tỷ đồng.",
    )
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=history)
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "6,4 tỷ đồng" in answer
    assert "7,2 tỷ" not in answer and "9 tỷ" not in answer


def test_so_tien_muon_vay_sau_gia_nha_khong_thanh_gia_canh_tranh():
    history = users("Giá căn hộ là 9 tỷ và tôi muốn vay 4 tỷ.")
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=history)
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "7,2 tỷ đồng" in answer
    assert "xác nhận giúp em một giá trị" not in answer


@pytest.mark.parametrize("gia_tai_san", [
    "Xe của tôi trị giá 500 triệu.",
    "Ô tô của tôi giá 2 tỷ.",
    "Bitcoin của tôi trị giá 1 tỷ.",
    "Vàng của tôi trị giá 3 tỷ.",
])
def test_gia_tai_san_khac_khong_duoc_tinh_ltv_nha(gia_tai_san):
    code, answer = tra_loi(
        "Hạn mức theo giá nhà là bao nhiêu?", MUA_NHA,
        history=users(gia_tai_san),
    )
    assert code == "xac_nhan_gia_bat_dong_san"
    assert "một giá trị bất động sản" in answer
    assert all(value not in answer for value in (
        "400 triệu", "1,6 tỷ", "800 triệu", "2,4 tỷ"))


@pytest.mark.parametrize("mixed", [
    "Nhà của tôi giá 9 tỷ, còn xe trị giá 2 tỷ.",
    "Ô tô của tôi giá 2 tỷ, còn căn hộ giá 9 tỷ.",
])
def test_gia_tai_san_khac_cung_luot_khong_lam_nhap_nhang_gia_nha(mixed):
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=users(mixed))
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "7,2 tỷ đồng" in answer
    assert "xác nhận giúp em một giá trị" not in answer


@pytest.mark.parametrize("property_price", [
    "Giá lô đất là 9 tỷ đồng.",
    "Bất động sản này trị giá 9 tỷ đồng.",
    "Căn hộ của tôi có giá trị 9 tỷ đồng.",
])
def test_gia_co_chu_the_bat_dong_san_ro_rang_van_duoc_tinh(property_price):
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=users(property_price))
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "7,2 tỷ đồng" in answer


def test_gia_dung_rieng_khong_co_chu_the_phai_hoi_lai():
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=users("Giá là 9 tỷ đồng."))
    assert code == "xac_nhan_gia_bat_dong_san"
    assert "một giá trị bất động sản" in answer
    assert "7,2 tỷ" not in answer


def test_sua_gia_dung_rieng_duoc_gan_vao_gia_nha_da_co():
    history = users(
        "Căn hộ của tôi giá 9 tỷ đồng.",
        "Sửa lại giá là 8 tỷ đồng.",
    )
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=history)
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "6,4 tỷ đồng" in answer
    assert "7,2 tỷ" not in answer


@pytest.mark.parametrize("aside", [
    "Ô tô của tôi trị giá 2 tỷ đồng.",
    "Nếu ô tô của tôi trị giá 2 tỷ thì sao?",
])
def test_gia_tai_san_khac_khong_thay_gia_nha_that_truoc_do(aside):
    history = users(
        "Căn hộ của tôi giá 9 tỷ đồng.",
        aside,
    )
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=history)
    assert code == "han_muc_theo_gia_bat_dong_san"
    assert "7,2 tỷ đồng" in answer
    assert "1,6 tỷ" not in answer


def test_gia_that_va_cau_hoi_neu_vay_cung_luot_van_duoc_luu_lai():
    factual_then_question = "Giá nhà tôi là 9 tỷ. Nếu vay thì tối đa bao nhiêu?"

    status, price, hypothetical = _gia_bds_hien_tai(factual_then_question, None)
    assert status == "known" and price == Decimal("9000000000")
    assert hypothetical is False

    next_code, next_answer = tra_loi(
        CAU_HOI, MUA_NHA, history=users(factual_then_question))
    assert next_code == "han_muc_theo_gia_bat_dong_san"
    assert "7,2 tỷ đồng" in next_answer
    assert "xác nhận giúp em một giá trị" not in next_answer


@pytest.mark.parametrize("gia", [
    "Căn hộ giá 9 tỷ USD.",
    "Giá nhà là 9.",
])
def test_ngoai_te_hoac_gia_thieu_don_vi_khong_duoc_doan(gia):
    code, answer = tra_loi(CAU_HOI, MUA_NHA, history=users(gia))
    assert code == "xac_nhan_gia_bat_dong_san"
    assert "bằng VND" in answer and "đơn vị triệu hoặc tỷ đồng" in answer
    assert "7,2 tỷ" not in answer


@pytest.mark.parametrize("han_muc", [
    "- Hạn mức: lên đến 80% giá trị bất động sản, tối đa 10 tỷ",
    "- Hạn mức: tối đa 10 tỷ đồng",
    "- Hạn mức: lên đến 70% hoặc 80% giá trị bất động sản, tối đa 10 tỷ đồng",
])
def test_nguon_thieu_tien_te_thieu_ty_le_hoac_nhieu_ty_le_khong_tinh(han_muc):
    doc = "# Vay Mua Nhà\n\n## Thông tin sản phẩm\n" + han_muc
    got = tra_loi(CAU_HOI, doc, history=users("Căn hộ giá 9 tỷ đồng."))
    assert got
    assert got[0] == "han_muc_san_pham"
    assert "7,2 tỷ" not in got[1]


def test_khong_co_gia_nhung_hoi_phep_tinh_ltv_thi_hoi_gia():
    code, answer = tra_loi(CAU_HOI, MUA_NHA)
    assert code == "xac_nhan_gia_bat_dong_san"
    assert "một giá trị bất động sản" in answer
