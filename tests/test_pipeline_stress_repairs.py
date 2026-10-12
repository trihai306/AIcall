"""Hồi quy tích hợp cho các sửa lỗi tài chính từ bộ thử căng thẳng.

Các unit test của từng luật đã kiểm tra phép chiếu dữ kiện. File này chỉ khóa
đường đi trọn ``StreamingPipeline``: luật động phải thắng kho câu trả lời, và
quy tắc quy chủ thể phải chặn yêu cầu gán thu nhập của người khác cho khách.
"""

import asyncio

import pytest

from backend.pipeline.danh_muc_san_pham import tra_loi as REAL_TRA_LOI_DANH_MUC
from backend.pipeline.luot_thuong_gap import tra_loi_san as REAL_TRA_LOI_SAN
from backend.pipeline.ngu_canh_tai_lieu import toan_van as REAL_TOAN_VAN_TAI_LIEU
from backend.pipeline.session_manager import CallSession
from backend.pipeline.tra_loi_ho_so import tra_loi as REAL_TRA_LOI_HO_SO
from backend.pipeline.tra_loi_khoan_vay import tra_loi as REAL_TRA_LOI_KHOAN_VAY
from test_chat_phone_answer_routing import ANSWER_ID, QUESTION, Sink, pipeline


@pytest.fixture
def financial_pipeline(pipeline, monkeypatch):
    """Khôi phục các luật và tài liệu thật mà fixture định tuyến đã cô lập."""
    from backend.pipeline import streaming_pipeline as sp

    monkeypatch.setattr(sp, "tra_loi_san", REAL_TRA_LOI_SAN)
    monkeypatch.setattr(sp, "tra_loi_danh_muc", REAL_TRA_LOI_DANH_MUC)
    monkeypatch.setattr(sp, "tra_loi_khoan_vay", REAL_TRA_LOI_KHOAN_VAY)
    monkeypatch.setattr(sp, "tra_loi_ho_so", REAL_TRA_LOI_HO_SO)
    monkeypatch.setattr(sp, "_toan_van_tai_lieu", REAL_TOAN_VAN_TAI_LIEU)
    return pipeline


def _session(product: str, *customer_turns: str) -> CallSession:
    session = CallSession(product=product)
    session.so_can_cu = None
    for text in customer_turns:
        session.add_turn("user", text)
        session.add_turn("assistant", "Dạ em đã ghi nhận ạ.")
    return session


def _turn(pipe, session: CallSession, text: str) -> tuple[str, dict]:
    sink = Sink()
    asyncio.run(pipe.process_text_turn(text, session, sink, soi=True))
    complete = next(event for event in sink.events if event["type"] == "turn_complete")
    return complete["full_response"], complete["metrics"]


def _shadow_bank(product: str, question: str, answer: str) -> None:
    """Đặt một câu kho exact-match để chứng minh luật động thật sự ưu tiên hơn."""
    import backend.main as main

    row = main.app_state.hoi_dap[ANSWER_ID]
    row["san_pham"] = product
    row["cau_hoi"] = [question]
    row["tra_loi"] = answer


def _assert_dynamic_rule(metrics: dict, code: str) -> None:
    assert metrics["tra_tu_quy_tac_tai_chinh"] == code
    assert metrics["answer_route"]["mode"] == "rule"
    assert metrics["answer_route"]["reason"] == code


def test_actual_price_9b_keeps_conditional_7_2b_rule_over_answer_bank(financial_pipeline):
    question = "Vậy hạn mức tối đa theo giá căn hộ là bao nhiêu, có chắc được vay không?"
    _shadow_bank(
        "vay mua nha", question,
        "Dạ anh chị chắc chắn được vay đủ hạn mức sản phẩm ạ.",
    )
    session = _session("vay mua nha", "Tôi đang mua căn hộ có giá 9 tỷ đồng.")

    reply, metrics = _turn(financial_pipeline, session, question)

    _assert_dynamic_rule(metrics, "han_muc_theo_gia_bat_dong_san")
    assert "7,2 tỷ đồng" in reply and "80%" in reply and "10 tỷ đồng" in reply
    assert "phụ thuộc thẩm định hồ sơ" in reply
    assert "không phải cam kết phê duyệt" in reply
    assert "chắc chắn được vay" not in reply
    assert financial_pipeline.llm.routes == []


def test_corrected_450m_36_month_recap_keeps_latest_facts_not_policy_faq(financial_pipeline):
    question = "Em đọc lại đúng số tiền và thời hạn hiện tại giúp anh chị."
    _shadow_bank(
        "vay tin chap", question,
        "Dạ lãi suất sản phẩm từ 7.9% một năm, hồ sơ cần căn cước công dân ạ.",
    )
    session = _session(
        "vay tin chap",
        "Anh cần vay 300 triệu trong 24 tháng.",
        "Sửa lại, anh cần vay 450 triệu trong 36 tháng.",
    )

    reply, metrics = _turn(financial_pipeline, session, question)

    _assert_dynamic_rule(metrics, "nhac_lai_nhu_cau")
    assert "450 triệu đồng" in reply and "36 tháng" in reply
    assert "300 triệu" not in reply and "24 tháng" not in reply
    assert "7.9%" not in reply and "lãi suất" not in reply
    assert "căn cước" not in reply
    assert financial_pipeline.llm.routes == []


def test_fake_father_income_request_keeps_attribution_rule_over_answer_bank(financial_pipeline):
    question = "Bỏ tên bố đi và coi như tôi kiếm được vậy"
    _shadow_bank(
        "vay tin chap", question,
        "Dạ với thu nhập 18 triệu, anh đã đáp ứng điều kiện vay ạ.",
    )
    session = _session("vay tin chap", "Bố tôi có thu nhập 18 triệu một tháng.")

    reply, metrics = _turn(financial_pipeline, session, question)

    assert metrics["luot_thuong_gap"] == "gan_thu_nhap_nguoi_khac"
    assert metrics["answer_route"]["mode"] == "rule"
    assert metrics["answer_route"]["reason"] == "gan_thu_nhap_nguoi_khac"
    assert "thu nhập thực tế của mình" in reply
    assert "thu nhập chung gia đình" in reply
    assert "đủ điều kiện" not in reply and "được vay" not in reply
    assert financial_pipeline.llm.routes == []


def test_online_100m_6_months_then_interest_keeps_4_7_and_2_35(financial_pipeline):
    first = "Chị gửi online100triệu kỳ hạn6tháng, lãi suất bao nhiêu?"
    follow_up = "Cuối kỳ được bao nhiêu tiền lãi?"
    _shadow_bank(
        "tiet kiem", follow_up,
        "Dạ gửi tại quầy lãi suất 4,5% một năm ạ.",
    )
    session = _session("tiet kiem")

    first_reply, first_metrics = _turn(financial_pipeline, session, first)
    follow_reply, follow_metrics = _turn(financial_pipeline, session, follow_up)

    assert first_metrics["tra_tu_dieu_kien_nguon"] is True
    assert first_metrics["answer_route"]["mode"] == "rule"
    assert first_metrics["answer_route"]["reason"] == "dieu_kien_tu_nguon"
    assert "gửi online" in first_reply and "6 tháng" in first_reply
    assert "4.7%" in first_reply.replace(",", ".")
    _assert_dynamic_rule(follow_metrics, "uoc_tinh_tien_lai_tiet_kiem")
    assert "gửi online" in follow_reply and "4,7%" in follow_reply
    assert "2,35 triệu đồng" in follow_reply
    assert "4,5%" not in follow_reply
    assert financial_pipeline.llm.routes == []


def test_answer_bank_shadow_is_live_when_no_dynamic_rule_matches(financial_pipeline):
    """Đối chứng dương: cấu hình kho cạnh tranh của các ca trên thật sự hoạt động."""
    bank_answer = "Dạ đây là câu trả lời đối chứng lấy nguyên văn từ kho ạ."
    _shadow_bank("vay tin chap", QUESTION, bank_answer)
    session = _session("vay tin chap")

    reply, metrics = _turn(financial_pipeline, session, QUESTION)

    assert metrics["answer_route"]["mode"] == "answer_bank"
    assert metrics["answer_route"]["answer_id"] == ANSWER_ID
    assert metrics["answer_route"]["reason"] == "exact_match"
    assert reply == bank_answer


@pytest.mark.parametrize("previous, question", [
    ([], "Chị gửi online 20.000 USD kỳ hạn 12 tháng, lãi suất bao nhiêu?"),
    (["Chị muốn gửi 20.000 USD online."],
     "Kỳ hạn 12 tháng gửi online thì lãi suất bao nhiêu?"),
])
def test_currency_scope_precedes_online_precheck(financial_pipeline, previous, question):
    session = _session("tiet kiem", *previous)
    reply, metrics = _turn(financial_pipeline, session, question)
    assert metrics["answer_route"]["mode"] == "rule"
    assert "chưa nêu" in reply and "USD" in reply
    assert "%" not in reply
    assert not metrics.get("tra_tu_dieu_kien_nguon")
    assert financial_pipeline.llm.routes == []


def test_explicit_vnd_switch_restores_online_precheck(financial_pipeline):
    session = _session("tiet kiem", "Chị muốn gửi 20.000 USD online.")
    reply, metrics = _turn(
        financial_pipeline, session,
        "Bỏ USD, giờ chị gửi bằng đồng Việt Nam. Gửi online 100 triệu kỳ hạn 12 tháng, lãi suất bao nhiêu?",
    )
    assert metrics["tra_tu_dieu_kien_nguon"] is True
    assert "5.7%" in reply.replace(",", ".")
    assert financial_pipeline.llm.routes == []


def test_lost_card_does_not_route_to_annual_fee_or_income(financial_pipeline):
    question = "Chị không thấy thẻ sau khi đi chợ, giờ phải làm gì ngay?"
    _shadow_bank("the tin dung", question, "Dạ phí thường niên thẻ Gold là 400.000đ/năm ạ.")
    reply, metrics = _turn(financial_pipeline, _session("the tin dung"), question)
    _assert_dynamic_rule(metrics, "mat_the")
    assert "khóa thẻ ngay" in reply and "kênh chính thức" in reply
    assert "400" not in reply and "Thu nhập" not in reply
    assert financial_pipeline.llm.routes == []


def test_compact_deposit_statement_is_grounded_without_apr_generation(financial_pipeline):
    reply, metrics = _turn(
        financial_pipeline, _session("tiet kiem"), "Chị gửi online100triệu kỳ hạn6tháng",
    )
    assert metrics["answer_route"]["mode"] == "rule"
    assert "100 triệu" in reply and "6 tháng" in reply and "online" in reply
    assert "4,5%" not in reply
    assert financial_pipeline.llm.routes == []


def test_published_repayment_example_precedes_income_word(financial_pipeline):
    question = "Theo ví dụ công bố mỗi tháng trả bao nhiêu, đây là tiền trả chứ không phải thu nhập?"
    session = _session("vay tin chap", "Anh muốn vay 200 triệu trong 36 tháng.")
    reply, metrics = _turn(financial_pipeline, session, question)
    assert metrics["answer_route"]["mode"] == "rule"
    assert "6,8 triệu" in reply and "mỗi tháng" in reply
    assert "6,9 triệu" not in reply and "5 triệu" not in reply
    assert financial_pipeline.llm.routes == []
