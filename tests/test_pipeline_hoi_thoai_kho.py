"""Đi trọn pipeline: quyền dừng và lưới số phải thắng câu sinh sai."""
import asyncio
from types import SimpleNamespace

import pytest

from test_chat_phone_answer_routing import pipeline, Sink
from backend.pipeline.session_manager import CallSession


@pytest.mark.parametrize("question", [
    "Thôi không trêu nữa, anh chưa có nhu cầu. Em đừng mời vay tiếp.",
    "Anh vừa nói chưa có nhu cầu rồi mà. Đừng đọc hạn mức nữa, dừng cuộc gọi giúp anh.",
    "thoi de chi tinh lai, dung hoi them nua",
    "Để cô hỏi con gái đã, cháu đừng hỏi nữa.",
])
def test_khach_dung_va_hoan_khong_bi_doc_han_muc(pipeline, monkeypatch, question):
    from backend.pipeline import streaming_pipeline as sp
    from backend.pipeline.luot_thuong_gap import tra_loi_san
    monkeypatch.setattr(sp, "tra_loi_san", tra_loi_san)
    session = CallSession(product="vay tín chấp")
    session.so_can_cu = None
    session.add_turn("user", "Anh muốn vay 200 triệu trong 24 tháng")
    session.add_turn("assistant", "Dạ em ghi nhận ạ.")
    sink = Sink()
    asyncio.run(pipeline.process_text_turn(question, session, sink, soi=True))
    complete = next(e for e in sink.events if e["type"] == "turn_complete")
    reply = complete["full_response"]
    assert complete["metrics"]["answer_route"]["mode"] == "rule"
    assert "200" not in reply and "500" not in reply and "?" not in reply
    assert not pipeline.llm.routes


@pytest.mark.parametrize("injected, flag, history", [
    ("Khoản trả góp khoảng 3.4 triệu mỗi triệu vay. Anh muốn vay bao nhiêu?", "chan_tu_tinh_tien", []),
    ("Anh chị đang cân nhắc khoản vay khoảng hai trăm triệu ạ.", "chan_gan_nhu_cau", []),
    ("Với thu nhập 20 triệu, anh đã đáp ứng điều kiện ạ.", "chan_gan_thu_nhap", [
        "Lương tôi 12 triệu", "Bạn tôi lương 20 triệu"]),
    ("Với thu nhập 20 triệu, anh đã đáp ứng điều kiện ạ.", "chan_gan_thu_nhap", [
        "Hồ sơ yêu cầu thu nhập 20 triệu đúng không em?"]),
])
@pytest.mark.parametrize("mode", ["generated", "speculative"])
def test_model_sai_bi_chan_truoc_chu_va_tieng(pipeline, monkeypatch, injected, flag, history, mode):
    from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH
    pipeline._tra_bang_hoi_dap = lambda *_a, **_k: None
    pipeline._bang_thuoc_tinh = THUOC_TINH_MAC_DINH

    async def retrieve(*_a, **_k):
        return "THÔNG TIN THAM KHẢO: Lãi suất từ 7.9%/năm. Hạn mức tối đa 500 triệu."

    async def details(*args, **kwargs):
        return await retrieve(*args, **kwargs), []

    async def no_tool(*_a, **_k):
        return ""

    async def stream(*_a, **_k):
        yield injected

    async def route(task):
        assert task == "response"
        return SimpleNamespace(model="injected-regression", stream_response=stream)

    pipeline.rag.retrieve, pipeline.rag.retrieve_chi_tiet = retrieve, details
    pipeline._tra_bang_cong_cu = no_tool
    pipeline.llm.route_for = route
    pipeline.llm.build_system_prompt = lambda **kw: kw["rag_context"]
    session = CallSession(product="vay tín chấp")
    session.so_can_cu = None
    for question in history:
        session.add_turn("user", question)
        session.add_turn("assistant", "Dạ em lắng nghe ạ.")
    question = "Ba năm đi nhưng anh chưa xác định số tiền muốn vay, em đừng đoán nhé"
    if mode == "speculative":
        session.spec_transcript, session.spec_answer = question, injected
        session.spec_model, session.spec_rag = "injected-regression", ""
    sink = Sink()
    asyncio.run(pipeline.process_text_turn(
        question, session, sink, soi=True))
    complete = next(e for e in sink.events if e["type"] == "turn_complete")
    assert complete["metrics"]["answer_route"]["mode"] == mode
    assert complete["metrics"].get(flag)
    assert "3.4" not in complete["full_response"]
    assert "hai trăm" not in complete["full_response"]
    if flag == "chan_gan_thu_nhap":
        assert "20 triệu" not in complete["full_response"]
    chunks = [e.get("text", "") for e in sink.events if e["type"] == "response_chunk"]
    assert all("3.4" not in chunk and "hai trăm" not in chunk for chunk in chunks)
    if flag == "chan_gan_thu_nhap":
        assert all("20 triệu" not in chunk for chunk in chunks)
