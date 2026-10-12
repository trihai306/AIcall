"""Hồi quy cho lượt nhắc lại danh tính AI và nguồn số điện thoại."""

import pytest

from backend.pipeline.luot_thuong_gap import bo_dau, nhan_dang, tra_loi_san


def _tra(cau: str) -> tuple[str, str]:
    ket_qua = tra_loi_san(
        cau,
        bank="Ngân hàng thử nghiệm",
        agent="Linh",
        product="vay tín chấp",
        luot_thu=3,
    )
    assert ket_qua is not None
    return ket_qua


@pytest.mark.parametrize("cau", [
    "Anh hỏi hai chuyện: em có phải robot không và số anh ở đâu ra?",
    "Vậy nhắc lại ngắn: em là AI và có biết chính xác nguồn số không?",
    "Vay nhac lai ngan: em la AI va co biet chinh xac nguon sdt khong?",
    "Robot hay người thật, nguồn số điện thoại này từ đâu?",
    "robot hay nguoi that, nguon sdt nay o dau?",
])
def test_cau_ghep_ai_va_nguon_so_tra_du_hai_y(cau):
    ma, dap = _tra(cau)
    dap_khong_dau = bo_dau(dap)

    assert ma == "danh_tinh_va_nguon"
    assert "tro ly tu van tu dong su dung ai" in dap_khong_dau
    assert "khong co thong tin da duoc xac minh ve nguon so dien thoai" in dap_khong_dau
    assert all(cum not in dap_khong_dau for cum in (
        "danh sach", "dong y nhan", "doi tac", "chien dich",
    ))


@pytest.mark.parametrize("cau", [
    "em là AI",
    "em la AI",
    "robot hay người thật",
    "robot hay nguoi that",
])
def test_danh_tinh_ai_ro_rang_duoc_cong_khai(cau):
    ma, dap = _tra(cau)
    assert ma == "danh_tinh_tu_dong"
    assert "tự động" in dap and "AI" in dap


@pytest.mark.parametrize("cau", [
    "nguồn số điện thoại ở đâu?",
    "nguon sdt nay tu dau?",
])
def test_nguon_so_dien_thoai_dung_rieng_van_duoc_nhan_dien(cau):
    ma, dap = _tra(cau)
    assert ma == "sao_co_so"
    assert "không có thông tin đã được xác minh" in dap.lower()


@pytest.mark.parametrize("cau", ["em là ai", "em la ai"])
def test_em_la_ai_van_la_hoi_danh_tinh_nhan_vien(cau):
    ma, dap = _tra(cau)
    assert ma == "ai_day"
    assert "Linh" in dap
    assert "VoiceBankAI" not in dap


@pytest.mark.parametrize("cau", [
    "số tiền anh muốn vay là 200 triệu",
    "em có biết số tiền được vay không",
    "lãi suất bao nhiêu một tháng",
    "đơn vị tính lãi là gì",
    "số điện thoại tư vấn là bao nhiêu",
    "nguồn thu nhập của anh là lương",
])
def test_cau_hoi_so_luong_lai_suat_don_vi_khong_bi_coi_la_nguon_so(cau):
    assert nhan_dang(cau) not in {
        "sao_co_so", "danh_tinh_tu_dong", "danh_tinh_va_nguon",
    }


@pytest.mark.parametrize(("cau", "mong_doi"), [
    ("em là AI nhưng đừng gọi nữa", "tu_choi"),
    ("robot hay người thật, anh đang bận", "dang_ban"),
])
def test_quyen_dung_hoac_ban_van_thang_danh_tinh_ai(cau, mong_doi):
    assert nhan_dang(cau) == mong_doi
