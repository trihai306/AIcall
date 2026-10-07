"""Chế độ chỉ chọn trong kho: kho không có thì hẹn liên hệ sau, mô hình không sinh."""
import asyncio
from types import SimpleNamespace

from tests.test_chat_phone_answer_routing import (ANSWER, QUESTION, Sink, _session,
                                                  pipeline)  # noqa: F401


def _khong_co_trong_kho(pipeline):
    from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH
    pipeline._tra_bang_hoi_dap = lambda *_a, **_k: None
    pipeline._bang_thuoc_tinh = THUOC_TINH_MAC_DINH

    async def retrieve(*_a, **_k):
        return "THÔNG TIN THAM KHẢO: Khách có thể liên hệ tổng đài."

    async def retrieve_details(*args, **kwargs):
        return await retrieve(*args, **kwargs), []

    async def no_tool(*_a, **_k):
        return ""

    async def stream(*_a, **_k):
        raise AssertionError("Chế độ chỉ chọn: mô hình không được sinh câu trả lời")
        yield ""

    async def route(task):
        return SimpleNamespace(model="grounded-response", stream_response=stream)

    pipeline.rag.retrieve = retrieve
    pipeline.rag.retrieve_chi_tiet = retrieve_details
    pipeline._tra_bang_cong_cu = no_tool
    pipeline.llm.route_for = route
    pipeline.llm.build_system_prompt = lambda **kw: kw["rag_context"]


def _hoi(pipeline, session, cau):
    sink = Sink()
    asyncio.run(pipeline.process_text_turn(cau, session, sink, soi=True))
    return next(e for e in sink.events if e["type"] == "turn_complete")


def test_kho_khong_co_thi_hen_lien_he_sau_va_luan_phien(pipeline):  # noqa: F811
    from backend.pipeline.streaming_pipeline import CAU_KHO_KHONG_CO
    _khong_co_trong_kho(pipeline)
    session = _session()
    dau = _hoi(pipeline, session, "Tư vấn giúp cách liên hệ hỗ trợ")
    assert dau["full_response"] == CAU_KHO_KHONG_CO[0]
    assert dau["metrics"]["answer_route"]["mode"] == "kho_khong_co"
    assert dau["metrics"]["answer_route"]["reason"] == "kho_khong_co_0"
    sau = _hoi(pipeline, session, "Nhà anh ở xa chi nhánh thì làm thế nào")
    assert sau["full_response"] == CAU_KHO_KHONG_CO[1]


def test_kho_co_thi_van_doc_dap_an(pipeline):  # noqa: F811
    xong = _hoi(pipeline, _session(), QUESTION)
    assert xong["full_response"] == ANSWER
    assert xong["metrics"]["answer_route"]["mode"] == "answer_bank"
