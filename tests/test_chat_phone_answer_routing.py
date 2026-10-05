"""Chat and handset turns select the same immutable prepared answer."""
import asyncio
import io
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from backend.pipeline.session_manager import CallSession


ANSWER = "Anh chị có thể khóa thẻ trong ứng dụng rồi liên hệ tổng đài ạ."
QUESTION = "Lỡ đánh rơi thẻ thì giờ xử lý ra sao?"
ANSWER_ID = "ab_manual_call_routing"


def _wav():
    out = io.BytesIO()
    with wave.open(out, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(b"\0\0" * 2400)
    return out.getvalue()


class Rag:
    def embed(self, _texts):
        return np.asarray([[1.0, 0.0]], dtype=np.float32)

    def neo_moi_tu_cau(self, *_args):
        return None

    def _san_pham_co_tai_lieu(self):
        return []

    async def retrieve(self, *_args, **_kwargs):
        raise AssertionError("A selected prepared answer must bypass RAG")


class LLM:
    model = "production"

    def __init__(self):
        self.routes = []

    async def route_for(self, task):
        self.routes.append(task)
        if task != "answer_selection":
            raise AssertionError("Prepared answers must not be generated again")
        return SimpleNamespace(model="qwen-selector", generate_simple=self.generate_simple)

    async def generate_simple(self, _prompt, **_kwargs):
        return '{"choice":"C1"}'

    def build_system_prompt(self, **_kwargs):
        return ""


class Sink:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


@pytest.fixture
def pipeline(monkeypatch):
    import backend.main as main
    from backend.pipeline import streaming_pipeline as sp
    from backend.services import answer_bank_learning as learning

    bank = {ANSWER_ID: {
        "id": ANSWER_ID, "san_pham": "thẻ tín dụng", "cau_hoi": [],
        "tra_loi": ANSWER, "bat": True,
    }}
    rag, llm = Rag(), LLM()
    provenance = {ANSWER_ID: {"source_path": "products/card.md"}}
    monkeypatch.setattr(main, "app_state", SimpleNamespace(
        rag=rag, llm=llm, hoi_dap=bank,
        hoi_dap_vector={ANSWER_ID: np.asarray([[0.86, (1-0.86**2)**0.5]], dtype=np.float32)},
        hoi_dap_provenance=provenance))
    monkeypatch.setattr(learning, "row_is_current", lambda *_a, **_k: True)
    monkeypatch.setattr(sp, "_answer_bank_provenance", lambda *_a: provenance)
    monkeypatch.setattr(sp, "_schedule_persist", lambda _session: None)
    monkeypatch.setattr(sp, "_toan_van_tai_lieu", lambda _product: "")
    for name in ("tra_loi_san", "tra_loi_danh_muc", "tra_loi_khoan_vay", "tra_loi_ho_so"):
        monkeypatch.setattr(sp, name, lambda *_a, **_k: None)
    monkeypatch.setattr(sp.settings, "ngu_canh_tron_tai_lieu", False)
    monkeypatch.setattr(sp.settings, "tieng_san_bat", False)
    pipe = sp.StreamingPipeline.__new__(sp.StreamingPipeline)
    pipe.rag, pipe.llm = rag, llm
    pipe._da_bao_tts_chet = False

    async def synth(*_args, **_kwargs):
        return _wav()

    pipe.tts = SimpleNamespace(
        _is_loaded=True, toc_do_cua=lambda _voice: 1.0,
        he_so_thoai=lambda: 1.0, synthesize=synth,
    )
    async def no_filler(*_args, **_kwargs):
        return None
    pipe._send_filler = no_filler
    pipe._phan_loai_dong_bo = lambda *_a: None
    async def transcribe(_audio, sample_rate):
        assert sample_rate == 8000
        return QUESTION
    pipe.stt = SimpleNamespace(transcribe=transcribe)
    return pipe


def _session(direction="outbound"):
    session = CallSession(product="thẻ tín dụng", direction=direction)
    session.so_can_cu = None
    return session


def test_text_chat_routes_to_selector_and_reads_zero_example_answer(pipeline):
    session, sink = _session(), Sink()
    asyncio.run(pipeline.process_text_turn(QUESTION, session, sink, soi=True))
    complete = next(e for e in sink.events if e["type"] == "turn_complete")
    assert complete["full_response"] == ANSWER
    assert complete["metrics"]["answer_route"] == {
        "mode": "answer_bank", "model": "qwen-selector", "selector_model": "qwen-selector",
        "answer_id": ANSWER_ID, "source_path": "products/card.md", "reason": "ai_selected",
    }
    assert pipeline.llm.routes == ["answer_selection"]
    assert pipeline.llm.model == "production"
    assert not any(e["type"] == "audio" for e in sink.events)


@pytest.mark.parametrize("direction", ["outbound", "inbound"])
def test_phone_bridge_stt_selection_audio_and_status(pipeline, direction):
    from backend.services.phone_call_service import PhoneCallBridge, PhoneCallManager

    session = _session(direction)
    session.audio_rate = 8000
    bridge = PhoneCallBridge(pipeline, session, serial="fixture")
    played = []
    async def play(wav, **_kwargs):
        with wave.open(io.BytesIO(wav)) as stream:
            assert stream.getnframes() > 0
        played.append(wav)
    bridge.play = play
    asyncio.run(bridge._handle_turn(b"\0\0" * 8000))
    assert not bridge.last_error
    assert bridge.sink.last_transcript == QUESTION
    assert bridge.sink.last_reply == ANSWER
    assert played, "Selected answer must reach the phone audio sink"
    assert bridge.sink.last_metrics["la_thoai"] is True
    manager = PhoneCallManager()
    manager._calls["fixture"] = bridge
    state = manager.status()[0]
    assert state["session_id"] == session.session_id
    assert state["answer_route"]["answer_id"] == ANSWER_ID
    assert state["answer_route"]["model"] == "qwen-selector"


def test_changing_web_scenario_cancels_turn_and_clears_old_scope(monkeypatch):
    from backend.api import websocket as api
    session = _session()
    session.add_turn("user", "Câu hỏi ngân hàng cũ")
    session.spec_answer, session.spec_model = "Câu trả lời cũ", "old-model"
    session._answer_bank_vector = ("old-question", object())
    called = []
    async def get_scenario(_id):
        return {"scenario_id": "shinhan", "org_name": "Shinhan"}
    async def cancel():
        called.append("cancelled")
    monkeypatch.setattr(api.scenarios_db, "get_scenario", get_scenario)
    asyncio.run(api._configure_web_session(session, {"scenario_id": "shinhan"}, cancel))
    assert called == ["cancelled"]
    assert session.scenario_id == "shinhan"
    assert session.history == []
    assert session.spec_answer == session.spec_model == ""
    assert "_answer_bank_vector" not in session.__dict__


def test_invalid_scenario_does_not_partially_update_session(monkeypatch):
    from backend.api import websocket as api
    session = _session()
    original = session.customer_name
    async def get_scenario(_id):
        return None
    async def cancel():
        raise AssertionError("Invalid configuration must not interrupt the active turn")
    monkeypatch.setattr(api.scenarios_db, "get_scenario", get_scenario)
    with pytest.raises(ValueError, match="không tồn tại"):
        asyncio.run(api._configure_web_session(session, {
            "scenario_id": "missing", "customer_name": "changed",
        }, cancel))
    assert session.customer_name == original


def test_empty_default_scenario_preserves_legacy_configuration(monkeypatch):
    from backend.api import websocket as api
    async def resolve(_id):
        return {}
    async def cancel():
        pass
    monkeypatch.setattr(api.scenarios_db, "resolve", resolve)
    session = _session()
    asyncio.run(api._configure_web_session(session, {"scenario_id": ""}, cancel))
    assert session.scenario == {}


def test_no_bank_match_uses_routed_response_model_with_grounded_context(pipeline):
    from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH
    pipeline._tra_bang_hoi_dap = lambda *_a, **_k: None
    pipeline._bang_thuoc_tinh = THUOC_TINH_MAC_DINH
    seen = []
    async def retrieve(*_a, **_k):
        return "THÔNG TIN THAM KHẢO: Khách có thể liên hệ tổng đài để được hỗ trợ."
    async def retrieve_details(*args, **kwargs):
        return await retrieve(*args, **kwargs), []
    async def no_tool(*_a, **_k):
        return ""
    async def stream(history, prompt, **_kwargs):
        seen.append((history, prompt))
        yield "Anh chị có thể liên hệ tổng đài để được hỗ trợ ạ."
    async def route(task):
        assert task == "response"
        return SimpleNamespace(model="grounded-response", stream_response=stream)
    pipeline.rag.retrieve = retrieve
    pipeline.rag.retrieve_chi_tiet = retrieve_details
    pipeline._tra_bang_cong_cu = no_tool
    pipeline.llm.route_for = route
    pipeline.llm.build_system_prompt = lambda **kw: kw["rag_context"]
    session, sink = _session(), Sink()
    asyncio.run(pipeline.process_text_turn("Tư vấn giúp cách liên hệ hỗ trợ", session, sink, soi=True))
    complete = next(e for e in sink.events if e["type"] == "turn_complete")
    assert seen and "THÔNG TIN THAM KHẢO" in seen[0][1]
    assert complete["metrics"]["answer_route"]["mode"] == "generated"
    assert complete["metrics"]["answer_route"]["model"] == "grounded-response"
    assert pipeline.llm.model == "production"


def test_scoped_scenario_never_reads_general_product_shortcut(monkeypatch):
    from backend.pipeline import streaming_pipeline as sp
    monkeypatch.setattr(sp, "_toan_van_tai_lieu", lambda _product: "Generic bank facts")
    generic = CallSession(product="thẻ tín dụng")
    assert sp.StreamingPipeline._product_context_for(generic) == "Generic bank facts"
    shinhan = CallSession(product="thẻ tín dụng", scenario={
        "org_name": "Shinhan", "knowledge_tag": "shinhan"})
    assert sp.StreamingPipeline._product_context_for(shinhan) == ""
    another_bank = CallSession(product="thẻ tín dụng", scenario={"org_name": "Other bank"})
    assert sp.StreamingPipeline._product_context_for(another_bank) == ""


def test_static_rule_yields_to_prepared_answer(pipeline, monkeypatch):
    # 05-10-2026: kho có sẵn câu của người vận hành mà trang Nhắn tin vẫn đọc
    # câu của luật "lãi suất của gói vay là từ 7.9%/năm".
    from backend.pipeline import streaming_pipeline as sp
    monkeypatch.setattr(sp, "tra_loi_khoan_vay",
                        lambda *_a, **_k: ("lai_suat_san_pham", "Dạ lãi suất của gói vay là từ 7.9%/năm ạ."))
    session, sink = _session(), Sink()
    asyncio.run(pipeline.process_text_turn(QUESTION, session, sink, soi=True))
    complete = next(e for e in sink.events if e["type"] == "turn_complete")
    assert complete["full_response"] == ANSWER
    assert complete["metrics"]["answer_route"]["mode"] == "answer_bank"
    assert complete["metrics"]["luat_nhuong_kho"] == "lai_suat_san_pham"


@pytest.mark.parametrize("code, question", [
    ("tinh_tra_gop", QUESTION),                      # phép tính: không nhường
    ("lai_suat_san_pham", "vay 200 triệu lãi sao"),  # có con số của khách: không nhường
])
def test_dynamic_rule_or_customer_numbers_keep_rule(pipeline, monkeypatch, code, question):
    from backend.pipeline import streaming_pipeline as sp
    monkeypatch.setattr(sp, "tra_loi_khoan_vay", lambda *_a, **_k: (code, "Dạ câu của luật ạ."))
    session, sink = _session(), Sink()
    asyncio.run(pipeline.process_text_turn(question, session, sink, soi=True))
    complete = next(e for e in sink.events if e["type"] == "turn_complete")
    assert "câu của luật" in complete["full_response"]
    assert complete["metrics"]["answer_route"]["mode"] == "rule"


def test_static_rule_stays_when_bank_has_no_match(pipeline, monkeypatch):
    import backend.main as main
    from backend.pipeline import streaming_pipeline as sp
    monkeypatch.setattr(main.app_state, "hoi_dap", {})
    monkeypatch.setattr(main.app_state, "hoi_dap_vector", {})
    monkeypatch.setattr(sp, "tra_loi_khoan_vay",
                        lambda *_a, **_k: ("lai_suat_san_pham", "Dạ câu của luật ạ."))
    session, sink = _session(), Sink()
    asyncio.run(pipeline.process_text_turn(QUESTION, session, sink, soi=True))
    complete = next(e for e in sink.events if e["type"] == "turn_complete")
    assert "câu của luật" in complete["full_response"]
