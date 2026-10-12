"""Hồi quy nguồn thu nhập hộ gia đình và câu tổng thu nhập do mô hình sinh."""
import asyncio
from types import SimpleNamespace

import pytest

from backend.pipeline.chan_tuan_thu import (
    CAU_GHI_NHAN_THU_NHAP,
    chan_gan_thu_nhap,
)
from backend.pipeline.du_kien_khoan_vay import resolve
from backend.pipeline.session_manager import CallSession
from test_chat_phone_answer_routing import Sink, pipeline


@pytest.mark.parametrize("household_text", [
    "thu nhập chung của nhà tôi là 35 triệu mỗi tháng.",
    "tổng thu nhập của nhà anh là 35 triệu mỗi tháng.",
    "thu nhập tổng của nhà chị là 35 triệu mỗi tháng.",
])
def test_thu_nhap_cua_nha_thay_the_thu_nhap_rieng_bang_household(household_text):
    history = [{"role": "user", "content": "Thu nhập riêng của tôi là 12 triệu mỗi tháng."}]

    income = resolve(history, household_text).income

    assert income.status == "known"
    assert income.value == 35_000_000
    assert income.owner == "household"


def test_dieu_kien_trich_dan_cua_ho_khong_thanh_thu_nhap_khach():
    income = resolve(
        text="Ngân hàng yêu cầu tổng thu nhập của nhà anh 35 triệu mới được vay."
    ).income

    assert income.status == "unknown"
    assert income.value is None
    assert income.owner == ""


def test_thu_nhap_rieng_that_van_la_self():
    income = resolve(text="Thu nhập riêng của tôi là 12 triệu mỗi tháng.").income

    assert income.status == "known"
    assert income.value == 12_000_000
    assert income.owner == "self"


def test_tong_thu_nhap_sai_khong_duoc_muon_muc_toi_thieu_ngan_hang():
    facts = resolve(text="Thu nhập riêng của tôi là 12 triệu mỗi tháng.")
    generated = "Với tổng thu nhập 5 triệu, số tiền 80 triệu này là khả thi ạ."

    reply, reason = chan_gan_thu_nhap(generated, facts=facts)

    assert reason
    assert reply == CAU_GHI_NHAN_THU_NHAP
    assert "5 triệu" not in reply


def test_tong_thu_nhap_household_dung_duoc_nhac_lai():
    customer = "Thu nhập chung của nhà tôi là 35 triệu mỗi tháng."
    answer = "Tổng thu nhập của anh chị là 35 triệu mỗi tháng ạ."

    assert chan_gan_thu_nhap(answer, customer) == (answer, None)


def test_tong_hai_thu_nhap_rieng_co_chu_the_duoc_nhac_lai():
    customer = "Lương anh 30 triệu, vợ anh 20 triệu mỗi tháng."
    answer = "Tổng thu nhập của anh chị là 50 triệu mỗi tháng ạ."

    assert chan_gan_thu_nhap(answer, customer) == (answer, None)


@pytest.mark.parametrize("allowed", [
    "Với tổng thu nhập từ 5 triệu, khách hàng có thể đăng ký ạ.",
    "Tổng thu nhập của anh chị là 5 triệu phải không ạ?",
])
def test_dieu_kien_va_cau_hoi_tong_thu_nhap_van_duoc_phep(allowed):
    assert chan_gan_thu_nhap(allowed, "") == (allowed, None)


def test_pipeline_chan_tong_thu_nhap_sai_truoc_khi_phat(pipeline):
    from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH

    injected = "Với tổng thu nhập 5 triệu, số tiền 80 triệu này là khả thi ạ."
    pipeline._tra_bang_hoi_dap = lambda *_a, **_k: None
    pipeline._bang_thuoc_tinh = THUOC_TINH_MAC_DINH

    async def retrieve(*_a, **_k):
        return "THÔNG TIN THAM KHẢO: Thu nhập tối thiểu 5 triệu mỗi tháng."

    async def details(*args, **kwargs):
        return await retrieve(*args, **kwargs), []

    async def no_tool(*_a, **_k):
        return ""

    async def stream(*_a, **_k):
        yield injected

    async def route(task):
        assert task == "response"
        return SimpleNamespace(model="injected-regression", stream_response=stream)

    pipeline.rag.retrieve = retrieve
    pipeline.rag.retrieve_chi_tiet = details
    pipeline._tra_bang_cong_cu = no_tool
    pipeline.llm.route_for = route
    pipeline.llm.build_system_prompt = lambda **kw: kw["rag_context"]
    session = CallSession(product="vay tín chấp")
    session.so_can_cu = None
    session.add_turn("user", "Thu nhập riêng của tôi là 12 triệu mỗi tháng.")
    session.add_turn("assistant", "Dạ em ghi nhận ạ.")
    sink = Sink()

    asyncio.run(pipeline.process_text_turn(
        "So khoản vay với đúng thu nhập của tôi.", session, sink, soi=True))

    complete = next(event for event in sink.events if event["type"] == "turn_complete")
    assert complete["metrics"].get("chan_gan_thu_nhap")
    assert "5 triệu" not in complete["full_response"]
    chunks = [event.get("text", "") for event in sink.events
              if event["type"] == "response_chunk"]
    assert all("5 triệu" not in chunk for chunk in chunks)
