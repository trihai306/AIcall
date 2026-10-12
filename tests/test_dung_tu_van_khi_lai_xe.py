"""Quyền dừng rõ ràng phải thắng trạng thái bận/lái xe và lời hẹn."""

import pytest

from backend.pipeline.luot_thuong_gap import (
    nhan_dang,
    tra_loi_san,
    y_dinh_dung_tu_van,
)


def _tra(cau: str) -> tuple[str, str]:
    ket_qua = tra_loi_san(
        cau,
        bank="Ngân hàng thử nghiệm",
        agent="Linh",
        product="vay tín chấp",
        luot_thu=4,
    )
    assert ket_qua is not None
    return ket_qua


@pytest.mark.parametrize("cau", [
    "Tôi đang lái xe, dừng trao đổi ngay và đừng hỏi thêm nhé.",
    "toi dang lai xe tren duong rat on va khong the tiep tuc, dung trao doi ngay va dung hoi them nhe",
    "Dừng tư vấn ngay, tôi đang lái xe nên đang bận.",
    "Tôi đang bận, ngừng nói chuyện ngay giúp tôi.",
    "Ngừng trao đổi giúp tôi, để hôm khác tính.",
])
def test_dung_ro_rang_thang_lai_xe_ban_va_hen(cau):
    assert y_dinh_dung_tu_van(cau) == "tu_choi"
    ma, dap = _tra(cau)
    assert ma == "tu_choi"
    assert "không làm phiền thêm" in dap.lower()
    assert all(cum not in dap.lower() for cum in (
        "mấy giờ", "gọi lại", "dự định vay", "quan tâm",
    ))


@pytest.mark.parametrize("cau", [
    "Tôi không đồng ý nghe giới thiệu và không cung cấp số dư.",
    "toi khong dong y nghe gioi thieu hay tu van san pham nua va cung khong cung cap so du",
    "Anh không đồng ý nhận quảng cáo, giờ anh đang họp.",
    "Tôi không đồng ý nhận thông tin quảng cáo, gọi lại sau cũng không cần.",
])
def test_tu_choi_nghe_gioi_thieu_la_dung_han(cau):
    assert y_dinh_dung_tu_van(cau) == "tu_choi"
    ma, dap = _tra(cau)
    assert ma == "tu_choi"
    assert "không làm phiền thêm" in dap.lower()
    assert "mấy giờ" not in dap.lower() and "gọi lại" not in dap.lower()


@pytest.mark.parametrize("cau", [
    "Dừng trao đổi ngay nhưng giờ tôi muốn nghe tiếp.",
    "Không đồng ý nghe giới thiệu, nhưng giờ tôi đồng ý nghe giới thiệu.",
    "Đừng dừng tư vấn, cứ tư vấn tiếp đi.",
    "Không dừng trao đổi, cứ nói tiếp đi.",
])
def test_yeu_cau_tiep_tuc_sau_cung_huy_lenh_dung_truoc(cau):
    assert y_dinh_dung_tu_van(cau) is None


def test_lenh_dung_sau_yeu_cau_tiep_tuc_van_thang():
    cau = "Tôi muốn nghe tiếp nhưng dừng trao đổi ngay."
    assert y_dinh_dung_tu_van(cau) == "tu_choi"


@pytest.mark.parametrize("cau", [
    "Vợ tôi bảo dừng trao đổi, nhưng tôi vẫn muốn nghe tiếp.",
    "Vợ tôi không đồng ý nghe giới thiệu, còn tôi muốn nghe tiếp.",
    'Tôi chỉ nhắc lại câu "dừng trao đổi ngay", em cứ nói tiếp đi.',
])
def test_lenh_dung_trich_dan_hoac_cua_nguoi_nha_khong_dung_khach(cau):
    assert y_dinh_dung_tu_van(cau) is None


@pytest.mark.parametrize("cau", [
    "Tôi không đồng ý với mức lãi suất này.",
    "Tôi không đồng ý số tiền vay 200 triệu.",
    "Tôi không đồng ý kỳ hạn 12 tháng.",
    "Tôi không đồng ý cung cấp số dư.",
])
def test_bat_dong_y_tai_chinh_khong_bi_coi_la_lenh_dung(cau):
    assert y_dinh_dung_tu_van(cau) is None
    assert nhan_dang(cau) != "tu_choi"


@pytest.mark.parametrize(("cau", "mong_doi"), [
    ("Tôi đang lái xe.", "dang_ban"),
    ("Tôi đang lái xe, gọi lại lúc 3 giờ.", "hen_lai"),
    ("Tôi đang lái xe, để hôm khác gọi lại.", "hen_lai"),
    ("Vợ tôi đang lái xe, nhưng tôi vẫn muốn nghe tiếp.", None),
])
def test_lai_xe_chi_hen_khi_khach_that_su_yeu_cau(cau, mong_doi):
    assert y_dinh_dung_tu_van(cau) == mong_doi
