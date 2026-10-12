import asyncio
import copy
import json
import os

import pytest

from backend.pipeline.grounded_contracts import DialogueState
from backend.pipeline.grounded_runtime import respond, product_family
from backend.pipeline.ngu_canh_tai_lieu import quen_nho, toan_van
from backend.pipeline.session_manager import CallSession
from backend.services.llm_service import LLMService


@pytest.fixture(autouse=True)
def _bat_duong_grounded(monkeypatch):
    # Đường grounded TẮT mặc định từ 11-10-2026 (xem `config.grounded_dialogue_enabled`);
    # các bài ở đây kiểm chính đường đó nên bật lại trong phạm vi tệp.
    from backend.config import settings
    monkeypatch.setattr(settings, "grounded_dialogue_enabled", True)


class StructuredLLM:
    model = "test-structured"

    def __init__(self, meaning):
        self.meaning = meaning
        self.calls = []

    async def generate_structured(self, messages, schema, **limits):
        self.calls.append((messages, schema, limits))
        if "claims" in schema.get("properties", {}):
            return {"claims": []}
        return copy.deepcopy(self.meaning)


def meaning(intent="calculate_interest", facts=()):
    return {"intent": intent, "product": "savings", "topic": "rate",
            "certainty": "clear", "facts": list(facts), "source_refs": [],
            "intent_quote": "Tính tiền lãi"}


def fact(field, value, quote, turn=0):
    return {"field": field, "value": value, "quote": quote, "turn": turn,
            "owner": "self", "modality": "actual", "operation": "assert",
            "product": "savings"}


SOURCE = """# Gửi Tiết Kiệm
- Số tiền gửi tối thiểu: 1 triệu đồng
## Lãi suất theo kỳ hạn
- Kỳ hạn 6 tháng: lãi suất 4.5%/năm
## Gửi online
- Lãi suất cộng thêm 0.2%/năm so với gửi tại quầy
"""


def test_runtime_uses_current_source_and_current_customer_proof():
    session = CallSession(product="tiết kiệm")
    session.add_turn("user", "Tôi gửi online 100 triệu kỳ hạn 6 tháng")
    session.add_turn("assistant", "Đã ghi nhận")
    session.add_turn("user", "Tính tiền lãi")
    llm = StructuredLLM(meaning(facts=[
        fact("amount", "100000000", "100 triệu"),
        fact("term_months", "6", "6 tháng"),
        fact("channel", "online", "online"),
    ]))
    metrics = {}
    answer_a = asyncio.run(respond(llm, "Tính tiền lãi", session, lambda _: SOURCE, metrics))
    assert "2,35" in answer_a.text
    assert "grounded_error" not in metrics
    assert metrics["du_kien_vay"]["amount"]["value"] == "100000000"
    answer_b = asyncio.run(respond(
        llm, "Tính tiền lãi", session,
        lambda _: SOURCE.replace("4.5", "5.1").replace("0.2", "0.4"), {}))
    assert "2,75" in answer_b.text
    assert answer_a.source_version != answer_b.source_version
    assert answer_a.evidence_refs and answer_b.evidence_refs
    assert set(answer_a.evidence_refs).isdisjoint(answer_b.evidence_refs)


def test_invalid_evidence_does_not_commit_or_guess():
    session = CallSession(product="tiết kiệm")
    session.add_turn("user", "Tính tiền lãi")
    original = DialogueState(product="savings")
    session.grounded_state = original
    llm = StructuredLLM(meaning(facts=[fact("amount", "100000000", "100 triệu")]))
    metrics = {}
    answer = asyncio.run(respond(llm, "Tính tiền lãi", session, lambda _: SOURCE, metrics))
    assert answer.reason == "clarify_unverified"
    assert "triệu" not in answer.text and "%" not in answer.text
    assert session.grounded_state is original and not original.facts
    assert metrics["grounded_error"]


def test_fresh_source_reads_same_size_and_timestamp_edit(tmp_path):
    product_dir = tmp_path / "knowledge" / "products"
    product_dir.mkdir(parents=True)
    path = product_dir / "tiet_kiem.md"
    path.write_text(SOURCE, encoding="utf-8")
    old_stat = path.stat()
    quen_nho()
    assert "4.5" in toan_van("tiết kiệm", str(tmp_path))
    path.write_text(SOURCE.replace("4.5", "5.1"), encoding="utf-8")
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    assert path.stat().st_size == old_stat.st_size
    assert "5.1" in toan_van("tiết kiệm", str(tmp_path), fresh=True)


def test_structured_generation_uses_schema_and_shared_context_without_stop():
    class Client:
        async def chat(self, **kwargs):
            self.kwargs = kwargs
            return {"message": {"content": json.dumps({"ok": True, "quote": "原文"}, ensure_ascii=False)}}
    service = LLMService.__new__(LLMService)
    service.model = "configured-model"
    service.client = Client()
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    assert asyncio.run(service.generate_structured([], schema)) == {"ok": True, "quote": "原文"}
    sent = service.client.kwargs
    assert sent["model"] == service.model and sent["format"] == schema
    assert sent["think"] is False and sent["stream"] is False
    assert sent["options"]["temperature"] == 0
    assert "stop" not in sent["options"]


def test_structured_timeout_cancels_underlying_request():
    class Client:
        cancelled = False
        async def chat(self, **kwargs):
            try:
                await asyncio.sleep(1)
            finally:
                self.cancelled = True
    service = LLMService.__new__(LLMService)
    service.model = "configured-model"
    service.client = Client()
    with pytest.raises(TimeoutError):
        asyncio.run(service.generate_structured([], {}, timeout=.01))
    assert service.client.cancelled


from test_chat_phone_answer_routing import Sink, pipeline


def _wire_grounded(pipe, fake, monkeypatch, source):
    monkeypatch.setattr(pipe.llm, "generate_structured", fake.generate_structured, raising=False)
    async def route(task):
        assert task == "response"
        return pipe.llm
    monkeypatch.setattr(pipe.llm, "route_for", route)
    monkeypatch.setattr(pipe, "_grounded_context_for", lambda _session, _product: source)


def test_full_pipeline_verified_calculation_wins_over_prepared_answer(pipeline, monkeypatch):
    session = CallSession(product="tiết kiệm")
    session.add_turn("user", "Tôi gửi online 100 triệu kỳ hạn 6 tháng")
    session.add_turn("assistant", "Đã ghi nhận")
    fake = StructuredLLM(meaning(facts=[
        fact("amount", "100000000", "100 triệu"),
        fact("term_months", "6", "6 tháng"),
        fact("channel", "online", "online"),
    ]))
    _wire_grounded(pipeline, fake, monkeypatch, SOURCE)
    sink = Sink()
    asyncio.run(pipeline.process_text_turn("Tính tiền lãi", session, sink, soi=True))
    complete = next(event for event in sink.events if event["type"] == "turn_complete")
    assert "2,35 triệu" in complete["full_response"]
    metrics = complete["metrics"]
    assert metrics["grounded_dialogue"] is True
    assert metrics["answer_route"]["reason"].startswith("grounded_")
    assert metrics["answer_route"]["evidence_refs"]
    assert "bang_hoi_dap" not in metrics


def test_full_pipeline_invalid_model_evidence_asks_instead_of_answer_bank(pipeline, monkeypatch):
    fake = StructuredLLM(meaning(facts=[fact("amount", "100000000", "100 triệu")]))
    _wire_grounded(pipeline, fake, monkeypatch, SOURCE)
    session, sink = CallSession(product="tiết kiệm"), Sink()
    asyncio.run(pipeline.process_text_turn("Tính tiền lãi", session, sink, soi=True))
    complete = next(event for event in sink.events if event["type"] == "turn_complete")
    assert complete["metrics"]["answer_route"]["reason"] == "grounded_clarify_unverified"
    assert "triệu" not in complete["full_response"]
    assert "bang_hoi_dap" not in complete["metrics"]
    assert session.grounded_state is None


@pytest.mark.parametrize("intent", ["privacy", "unknown", "readback"])
def test_grounded_pipeline_does_not_append_legacy_sales_followup(pipeline, monkeypatch, intent):
    from backend.config import settings
    from backend.pipeline import dan_dat

    monkeypatch.setattr(settings, "dan_dat_bat", True)
    monkeypatch.setattr(dan_dat, "cau_hoi_tiep", lambda **_: (
        "legacy_sales", "Anh chị dự định vay khoảng bao nhiêu ạ?"))
    fake = StructuredLLM(meaning(intent=intent))
    _wire_grounded(pipeline, fake, monkeypatch, SOURCE)
    session, sink = CallSession(product="tiết kiệm"), Sink()
    asyncio.run(pipeline.process_text_turn("Kiểm tra thông tin của tôi", session, sink, soi=True))
    complete = next(event for event in sink.events if event["type"] == "turn_complete")
    assert complete["metrics"]["grounded_dialogue"] is True
    assert "dự định vay" not in complete["full_response"]
    assert "dan_dat" not in complete["metrics"]


def test_grounded_context_preserves_organization_and_tag_scope():
    from backend.pipeline.streaming_pipeline import StreamingPipeline
    scoped = CallSession(product="tiết kiệm", scenario={"knowledge_tag": "custom"})
    assert StreamingPipeline._grounded_context_for(scoped, scoped.product) == ""


@pytest.mark.parametrize("family", ["loan", "mortgage", "savings", "card"])
def test_internal_product_keys_are_supported_without_losing_source_scope(family):
    assert product_family(family) == family


@pytest.mark.parametrize("keeps_changing", [False, True])
def test_source_change_during_turn_retries_once_without_stale_commit(keeps_changing):
    session = CallSession(product="tiết kiệm")
    session.add_turn("user", "Tôi gửi online 100 triệu kỳ hạn 6 tháng")
    session.add_turn("user", "Tính tiền lãi")
    fake = StructuredLLM(meaning(facts=[
        fact("amount", "100000000", "100 triệu"),
        fact("term_months", "6", "6 tháng"), fact("channel", "online", "online"),
    ]))
    versions = [SOURCE, SOURCE.replace("4.5", "5.1").replace("0.2", "0.4")]
    reads = []
    def load(_product):
        value = versions[len(reads) % 2] if keeps_changing else versions[min(len(reads), 1)]
        reads.append(value)
        return value
    metrics = {}
    answer = asyncio.run(respond(fake, "Tính tiền lãi", session, load, metrics))
    assert metrics["grounded_source_retried"] is True
    if keeps_changing:
        assert answer.reason == "clarify_unverified" and session.grounded_state is None
        assert "triệu" not in answer.text
    else:
        assert "2,75 triệu" in answer.text
        assert session.grounded_state.get("amount").value == "100000000"
