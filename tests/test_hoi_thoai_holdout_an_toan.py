"""Các guard an toàn hữu hạn rút ra từ holdout độc lập 11-10."""

import asyncio
from pathlib import Path

import pytest

from backend.pipeline.danh_muc_san_pham import tra_loi as REAL_TRA_LOI_DANH_MUC
from backend.pipeline.luot_thuong_gap import tra_loi_san as REAL_TRA_LOI_SAN
from backend.pipeline.ngu_canh_tai_lieu import toan_van as REAL_TOAN_VAN_TAI_LIEU
from backend.pipeline.session_manager import CallSession
from backend.pipeline.tra_loi_ho_so import tra_loi as REAL_TRA_LOI_HO_SO
from backend.pipeline.tra_loi_khoan_vay import _tra_loi_pham_vi_nguon, tra_loi
from test_chat_phone_answer_routing import Sink, pipeline


ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ROOT / "knowledge" / "products"
THE = (PRODUCTS / "the_tin_dung.md").read_text(encoding="utf-8")
TIET_KIEM = (PRODUCTS / "tiet_kiem.md").read_text(encoding="utf-8")


def users(*texts: str) -> list[dict]:
    return [{"role": "user", "content": text} for text in texts]


@pytest.fixture
def safety_pipeline(pipeline, monkeypatch):
    """Khôi phục luật thật trong fixture pipeline vốn cô lập các router."""
    from backend.pipeline import streaming_pipeline as sp

    monkeypatch.setattr(sp, "tra_loi_san", REAL_TRA_LOI_SAN)
    monkeypatch.setattr(sp, "tra_loi_danh_muc", REAL_TRA_LOI_DANH_MUC)
    monkeypatch.setattr(sp, "tra_loi_khoan_vay", tra_loi)
    monkeypatch.setattr(sp, "tra_loi_ho_so", REAL_TRA_LOI_HO_SO)
    monkeypatch.setattr(sp, "_toan_van_tai_lieu", REAL_TOAN_VAN_TAI_LIEU)
    return pipeline


def pipeline_turn(pipe, session: CallSession, text: str) -> tuple[str, dict]:
    sink = Sink()
    asyncio.run(pipe.process_text_turn(text, session, sink, soi=True))
    complete = next(event for event in sink.events if event["type"] == "turn_complete")
    return complete["full_response"], complete["metrics"]


def test_holdout_047_mat_the_dao_nguoc_va_otp_uu_tien_an_toan():
    ma, dap = tra_loi(
        "Thẻ tôi bị mất, có người gọi bảo đọc OTP để cấp lại.", THE)

    assert ma == "mat_the_otp"
    assert all(x in dap for x in (
        "không đọc hoặc cung cấp OTP", "ngắt cuộc gọi", "khóa thẻ",
        "giao dịch gần đây", "kênh chính thức"))
    assert "đã khóa" not in dap and "1900" not in dap and "thu nhập" not in dap


@pytest.mark.parametrize("fee", ["350 nghìn", "720 nghìn", "1,2 triệu"])
def test_holdout_047_cau_chung_giu_buoc_khan_cap_va_phi_chua_xac_nhan(fee):
    ma, dap = tra_loi(
        "Tôi nên làm gì ngay?", THE,
        history=users(
            "Thẻ tôi bị mất, có người gọi bảo đọc OTP để cấp lại.",
            f"Họ còn nói phí thay thẻ là {fee}.",
        ))

    assert ma == "mat_the_otp_theo_ngu_canh"
    assert all(x in dap for x in (
        "không đọc hoặc cung cấp OTP", "khóa thẻ", "kênh chính thức",
        "Mức phí thay thẻ do người gọi nêu", "chưa được tài liệu sản phẩm xác nhận"))
    assert "1900545414" not in dap and "thu nhập" not in dap


def test_pipeline_holdout_047_followup_di_thang_quy_tac_an_toan(safety_pipeline):
    session = CallSession(product="the tin dung")
    session.so_can_cu = None
    for cau in (
        "Thẻ tôi bị mất, có người gọi bảo đọc OTP để cấp lại.",
        "Họ còn nói phí thay thẻ là 350 nghìn.",
    ):
        session.add_turn("user", cau)
        session.add_turn("assistant", "Dạ em đã ghi nhận ạ.")

    dap, metrics = pipeline_turn(safety_pipeline, session, "Tôi nên làm gì ngay?")

    assert metrics["tra_tu_quy_tac_tai_chinh"] == "mat_the_otp_theo_ngu_canh"
    assert metrics["answer_route"]["mode"] == "rule"
    assert all(x in dap for x in (
        "không đọc hoặc cung cấp OTP", "khóa thẻ", "Mức phí thay thẻ do người gọi nêu"))
    assert safety_pipeline.llm.routes == []


def test_ngu_canh_mat_the_dung_lai_khi_da_chuyen_ro_sang_hang_the():
    got = tra_loi(
        "Tôi nên làm gì ngay?", THE,
        history=users(
            "Thẻ tôi bị mất, có người gọi bảo đọc OTP để cấp lại.",
            "Bỏ việc đó, giờ tôi muốn hỏi thẻ Gold và phí thường niên.",
        ))

    assert got is None or got[0] != "mat_the_otp_theo_ngu_canh"


def test_holdout_058_tu_choi_doc_du_lieu_the_khong_thanh_phi_dong_the():
    ma, dap = tra_loi(
        "Tôi không đồng ý đọc số thẻ hay ngày hết hạn.", THE,
        history=users("Bạn là ai, có thật từ ngân hàng không?"))

    assert ma == "tu_choi_cung_cap_du_lieu_nhay_cam"
    assert "không đồng ý" in dap and "không hỏi thêm" in dap
    assert "toàn bộ số thẻ" in dap and "ngày hết hạn" in dap
    assert "phí" not in dap and "thu nhập" not in dap


def test_holdout_058_bi_giuc_doc_otp_ngat_va_tu_tim_kenh_chinh_thuc():
    ma, dap = tra_loi(
        "Có người đang giục tôi đọc OTP để xác minh.", THE,
        history=users(
            "Bạn là ai, có thật từ ngân hàng không?",
            "Tôi không đồng ý đọc số thẻ hay ngày hết hạn.",
        ))

    assert ma == "canh_bao_otp_cuoc_goi"
    assert all(x in dap for x in (
        "không đọc hoặc cung cấp OTP", "ngắt cuộc gọi", "kênh chính thức đã kiểm chứng"))
    assert "1900" not in dap and "thu nhập" not in dap


def test_cau_hoi_otp_khai_niem_khong_bi_coi_la_cuoc_goi_gia_mao():
    assert tra_loi("OTP dùng để làm gì?", THE) is None


def test_holdout_036_yeu_cau_noi_ro_pham_vi_crypto_chi_noi_nguon_vang_mat():
    ma, dap = tra_loi(
        "Nếu tài liệu không nói về crypto thì nói rõ phạm vi giúp tôi.",
        TIET_KIEM,
        history=users("Tôi có 0,2 Bitcoin, gửi tiết kiệm online được 5,7% chứ?"),
    )

    assert ma == "tien_gui_khong_co_chinh_sach"
    assert "tài liệu sản phẩm hiện chưa nêu" in dap and "tiền mã hóa" in dap
    assert "5,7%" not in dap and "không hỗ trợ" not in dap and "bị cấm" not in dap


def test_crypto_duoc_nguon_neu_dich_danh_thi_guard_pham_vi_nhuong_nguon():
    doc = TIET_KIEM + "\n- Chính sách crypto: chỉ áp dụng theo thỏa thuận riêng.\n"
    assert _tra_loi_pham_vi_nguon(
        "Nếu tài liệu có nói về crypto thì đọc đúng phạm vi giúp tôi.", doc) is None


def test_holdout_042_khong_nhan_don_vi_goi_hay_so_du_khach():
    ma, dap = tra_loi(
        "Số này của đơn vị nào, sao biết tôi đang có tiền nhàn rỗi?", TIET_KIEM)

    assert ma == "danh_tinh_va_nguon_lien_he_chua_xac_minh"
    assert "trợ lý tư vấn tự động" in dap
    assert "không có thông tin đã được xác minh" in dap
    assert "không có dữ liệu" in dap and "tiền nhàn rỗi hay số dư" in dap
    assert "Ngân hàng Quân đội" not in dap and "MB" not in dap


def test_holdout_058_danh_tinh_khong_tu_nhan_la_ngan_hang():
    ma, dap = tra_loi("Bạn là ai, có thật từ ngân hàng không?", THE)

    assert ma == "danh_tinh_va_nguon_lien_he_chua_xac_minh"
    assert "trợ lý tư vấn tự động" in dap and "kênh chính thức" in dap
    assert "em là ngân hàng" not in dap and "bên ngân hàng" not in dap


def test_holdout_048_mo_classic_chi_doc_thong_tin_khong_phe_duyet():
    ma, dap = tra_loi(
        "Tôi muốn tự đứng tên mở thẻ Classic.", THE,
        history=users("Vợ tôi lương 20 triệu, còn tôi chưa có thu nhập đều."))

    assert ma == "thong_tin_mo_loai_the"
    assert all(x in dap for x in ("Classic", "10-50 triệu", "200.000đ/năm"))
    assert "chưa phải xác nhận" in dap and "được duyệt" in dap
    assert "được mở thẻ" not in dap and "lương vợ" not in dap


def test_phi_thuong_nien_thong_thuong_van_di_dung_nhanh_the():
    ma, dap = tra_loi("Thẻ Gold phí thường niên bao nhiêu?", THE)

    assert ma == "phi_loai_the"
    assert "400.000đ" in dap and "năm đầu được miễn phí" in dap
