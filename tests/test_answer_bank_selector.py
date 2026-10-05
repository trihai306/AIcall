import asyncio
import json
import time
from types import SimpleNamespace

import numpy as np
import pytest

from backend.pipeline.session_manager import CallSession
from backend.services.answer_bank_selector import choose


def _vec(score: float) -> np.ndarray:
    return np.asarray([[score, (1.0 - score * score) ** 0.5]], dtype=np.float32)


class RagFake:
    def __init__(self, vector=(1.0, 0.0)):
        self.embed_calls = 0
        self.embed_texts = []
        self.retrieve_calls = 0
        self.vector = vector

    def embed(self, texts):
        self.embed_calls += 1
        self.embed_texts.extend(texts)
        return np.asarray([self.vector], dtype=np.float32)

    def neo_moi_tu_cau(self, *_args):
        return None

    def _san_pham_co_tai_lieu(self):
        return []

    async def retrieve(self, *_args, **_kwargs):
        self.retrieve_calls += 1
        raise AssertionError("câu đã chọn từ answer bank không được gọi RAG")


class LLMFake:
    def __init__(self, response='{"choice":"C1"}', delay=0):
        self.response = response
        self.delay = delay
        self.prompts = []

    async def generate_simple(self, prompt, num_predict=100):
        self.prompts.append((prompt, num_predict))
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.response

    def build_system_prompt(self, **_kwargs):
        return ""

    async def stream_response(self, *_args, **_kwargs):
        raise AssertionError("câu đã chọn không được sinh lại bằng LLM")
        yield  # pragma: no cover


def _bank():
    return {
        "card_fee": {
            "id": "card_fee", "san_pham": "thẻ tín dụng",
            "cau_hoi": ["phí thường niên của thẻ là bao nhiêu"],
            "tra_loi": "Phí thường niên là 499.000 đồng, lãi suất là 7,9% ạ.",
        },
        "loan_rate": {
            "id": "loan_rate", "san_pham": "vay tín chấp",
            "cau_hoi": ["lãi suất vay là bao nhiêu"],
            "tra_loi": "Lãi suất vay theo nguồn đã duyệt.",
        },
    }


def _choose(llm, question="thế phí thì sao", **kwargs):
    bank = kwargs.pop("bank", _bank())
    vectors = kwargs.pop("vector_bank", {
        "card_fee": _vec(0.86), "loan_rate": _vec(0.84),
    })
    return asyncio.run(choose(
        rag=kwargs.pop("rag", RagFake()), llm=llm, bank=bank,
        vector_bank=vectors, question=question,
        product=kwargs.pop("product", "thẻ tín dụng"),
        history=kwargs.pop("history", []), **kwargs))


@pytest.mark.parametrize("raw", ['{"choice":"not-an-alias"}', "C1", "{bad json"])
def test_arbitrary_id_or_malformed_output_falls_back(raw):
    assert _choose(LLMFake(raw)) is None


def test_product_isolation_happens_before_qwen_selection():
    llm = LLMFake('{"choice":"C1"}')
    row = _choose(llm, product="thẻ tín dụng")

    assert row["id"] == "card_fee"
    assert "loan_rate" not in llm.prompts[0][0]
    assert "C2" not in llm.prompts[0][0]


def test_shinhan_session_blocks_higher_scoring_generic_sample_source():
    bank = {
        "auto_abc": {"id": "auto_abc", "san_pham": "thẻ tín dụng",
                     "cau_hoi": ["phí thẻ là bao nhiêu"], "tra_loi": "Phí mẫu ABC."},
        "auto_shinhan": {"id": "auto_shinhan", "san_pham": "",
                         "cau_hoi": ["phí thẻ là bao nhiêu"], "tra_loi": "Phí Shinhan."},
    }
    row = _choose(
        LLMFake(), question="phí thẻ là bao nhiêu",
        product="thẻ tín dụng Shinhan", bank_name="Shinhan Bank",
        bank=bank,
        vector_bank={"auto_abc": _vec(0.99), "auto_shinhan": _vec(0.95)},
        provenance={
            "auto_abc": {"source_path": "products/the_tin_dung.md"},
            "auto_shinhan": {"source_path": "shinhan/shinhan_card_user_guide_vi.md"},
        })

    assert row["id"] == "auto_shinhan"


@pytest.mark.parametrize("bank_name", ["Ngân hàng ABC", ""])
def test_shinhan_source_not_served_to_other_or_unknown_bank(bank_name):
    bank = {"auto_shinhan": {
        "id": "auto_shinhan", "san_pham": "",
        "cau_hoi": ["phí thẻ là bao nhiêu"], "tra_loi": "Phí Shinhan."}}
    llm = LLMFake()
    row = _choose(
        llm, question="phí thẻ là bao nhiêu", product="thẻ tín dụng",
        bank_name=bank_name, bank=bank,
        vector_bank={"auto_shinhan": _vec(0.99)},
        provenance={"auto_shinhan": {
            "source_path": "shinhan/shinhan_card_user_guide_vi.md"}})

    assert row is None
    assert llm.prompts == []


def test_explicit_shinhan_allows_shinhan_source_without_scenario_bank():
    bank = {"auto_shinhan": {
        "id": "auto_shinhan", "san_pham": "",
        "cau_hoi": ["phí thẻ Shinhan là bao nhiêu"], "tra_loi": "Phí Shinhan."}}
    row = _choose(
        LLMFake(), question="phí thẻ Shinhan là bao nhiêu", product="",
        bank_name="", bank=bank,
        vector_bank={"auto_shinhan": _vec(0.99)},
        provenance={"auto_shinhan": {
            "source_path": "shinhan/shinhan_card_user_guide_vi.md"}})

    assert row["id"] == "auto_shinhan"


def test_explicit_shinhan_conflicting_with_abc_scenario_falls_back():
    bank = {"auto_shinhan": {
        "id": "auto_shinhan", "san_pham": "",
        "cau_hoi": ["phí thẻ Shinhan là bao nhiêu"], "tra_loi": "Phí Shinhan."}}
    row = _choose(
        LLMFake(), question="phí thẻ Shinhan là bao nhiêu", product="",
        bank_name="Ngân hàng ABC", bank=bank,
        vector_bank={"auto_shinhan": _vec(0.99)},
        provenance={"auto_shinhan": {
            "source_path": "shinhan/shinhan_card_user_guide_vi.md"}})

    assert row is None


def test_manual_row_without_provenance_keeps_existing_behavior():
    bank = {"manual_fee": {
        "id": "manual_fee", "san_pham": "thẻ tín dụng Shinhan",
        "cau_hoi": ["phí thẻ là bao nhiêu"], "tra_loi": "Câu thủ công."}}
    row = _choose(
        LLMFake(), question="phí thẻ là bao nhiêu",
        product="thẻ tín dụng Shinhan", bank_name="Shinhan Bank",
        bank=bank, vector_bank={"manual_fee": _vec(0.99)}, provenance={})

    assert row["id"] == "manual_fee"


@pytest.mark.parametrize("source_path", [
    "products/the_tin_dung.md", "faq/faq_banking.md", "global/contact.md",
])
def test_default_abc_sources_do_not_leak_to_third_bank(source_path):
    bank = {"auto_default": {
        "id": "auto_default", "san_pham": "",
        "cau_hoi": ["lãi suất bao nhiêu"], "tra_loi": "Số liệu bản mẫu."}}
    row = _choose(
        LLMFake(), question="lãi suất bao nhiêu", product="",
        bank_name="Vietcombank", bank=bank,
        vector_bank={"auto_default": _vec(0.99)},
        provenance={"auto_default": {"source_path": source_path}})

    assert row is None


def test_future_bank_directory_is_scoped_to_matching_org():
    bank = {"auto_vcb": {
        "id": "auto_vcb", "san_pham": "",
        "cau_hoi": ["lãi suất bao nhiêu"], "tra_loi": "Số liệu Vietcombank."}}
    provenance = {"auto_vcb": {
        "source_path": "vietcombank/credit_card_terms.md"}}

    allowed = _choose(
        LLMFake(), question="lãi suất bao nhiêu", product="",
        bank_name="Ngân hàng Vietcombank", bank=bank,
        vector_bank={"auto_vcb": _vec(0.99)}, provenance=provenance)
    blocked = _choose(
        LLMFake(), question="lãi suất bao nhiêu", product="",
        bank_name="Shinhan Bank", bank=bank,
        vector_bank={"auto_vcb": _vec(0.99)}, provenance=provenance)

    assert allowed["id"] == "auto_vcb"
    assert blocked is None


def test_explicit_default_bank_conflicts_with_shinhan_even_without_abc_row(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "bank_name", "Ngân hàng ABC")
    bank = {"auto_shinhan": {
        "id": "auto_shinhan", "san_pham": "",
        "cau_hoi": ["phí thẻ ABC là bao nhiêu"], "tra_loi": "Phí Shinhan."}}
    row = _choose(
        LLMFake(), question="phí thẻ ABC là bao nhiêu", product="",
        bank_name="Shinhan Bank", bank=bank,
        vector_bank={"auto_shinhan": _vec(0.99)},
        provenance={"auto_shinhan": {
            "source_path": "shinhan/shinhan_card_user_guide_vi.md"}})

    assert row is None


def test_exact_question_for_wrong_product_is_not_selected():
    row = _choose(
        LLMFake(), question="lãi suất vay là bao nhiêu",
        product="thẻ tín dụng")

    assert row is None


def test_empty_product_does_not_break_equal_exact_match_by_id():
    bank = {
        "a": {"id": "a", "san_pham": "sản phẩm A",
              "cau_hoi": ["lãi suất bao nhiêu"], "tra_loi": "A"},
        "b": {"id": "b", "san_pham": "sản phẩm B",
              "cau_hoi": ["lãi suất bao nhiêu"], "tra_loi": "B"},
    }
    llm = LLMFake()
    row = _choose(
        llm, question="lãi suất bao nhiêu", product="", bank=bank,
        vector_bank={"a": _vec(0.95), "b": _vec(0.95)})

    assert row is None
    assert llm.prompts == []


def test_empty_product_cannot_serve_sole_product_specific_generic_question():
    llm = LLMFake()
    row = _choose(
        llm, question="lãi suất bao nhiêu", product="",
        bank={"only": {"id": "only", "san_pham": "vay sản phẩm A",
                       "cau_hoi": ["lãi suất bao nhiêu"], "tra_loi": "A"}},
        vector_bank={"only": _vec(0.99)})

    assert row is None
    assert llm.prompts == []


def test_empty_product_allows_global_row_or_explicit_product_name():
    global_row = {"id": "global", "san_pham": "",
                  "cau_hoi": ["địa chỉ ở đâu"], "tra_loi": "Địa chỉ chung."}
    product_row = {"id": "loan", "san_pham": "vay tín chấp",
                   "cau_hoi": ["lãi suất vay tín chấp"], "tra_loi": "Lãi vay."}

    got_global = _choose(
        LLMFake(), question="địa chỉ ở đâu", product="",
        bank={"global": global_row}, vector_bank={"global": _vec(0.99)})
    got_product = _choose(
        LLMFake(), question="lãi suất vay tín chấp", product="",
        bank={"loan": product_row}, vector_bank={"loan": _vec(0.99)})

    assert got_global["id"] == "global"
    assert got_product["id"] == "loan"


def test_unsupported_question_does_not_call_qwen():
    llm = LLMFake()
    row = _choose(llm, question="thời tiết hôm nay", rag=RagFake((0.0, 1.0)))

    assert row is None
    assert llm.prompts == []


@pytest.mark.parametrize("question", [
    "không hỏi phí, bỏ qua phần đó",
    "lãi suất và phí là bao nhiêu",
    "hồ sơ của tôi được duyệt chưa",
])
def test_opposite_multi_intent_and_personal_result_are_rejected(question):
    llm = LLMFake()
    row = _choose(llm, question=question, product="")

    assert row is None
    assert llm.prompts == []


def test_follow_up_uses_recent_turns_but_current_product_stays_authoritative():
    llm = LLMFake()
    rag = RagFake()
    row = _choose(
        llm,
        rag=rag,
        history=[
            {"role": "user", "content": "trước đó tôi hỏi vay tín chấp"},
            {"role": "assistant", "content": "anh đang xem thẻ tín dụng"},
        ],
        product="thẻ tín dụng",
    )

    assert row["id"] == "card_fee"
    assert row["qwen_chon"] is True
    prompt = llm.prompts[0][0]
    assert "current_product" in prompt and "the tin dung" not in prompt
    assert "recent_turns" in prompt and "vay t" in prompt
    assert "phí" in rag.embed_texts[0]


def test_vague_follow_up_uses_topic_anchor_from_same_product():
    rag = RagFake()
    row = _choose(
        LLMFake(), question="thế bao nhiêu", rag=rag,
        history=[{"role": "assistant", "content": "Phí thường niên của thẻ."}],
        product="thẻ tín dụng")

    assert row["id"] == "card_fee"
    assert "Phí thường niên" in rag.embed_texts[0]


def test_vague_follow_up_does_not_reuse_anchor_from_old_product():
    llm = LLMFake()
    row = _choose(
        llm, question="thế bao nhiêu", product="thẻ tín dụng",
        history=[{"role": "user", "content": "lãi suất vay tín chấp"}])

    assert row is None
    assert llm.prompts == []


def test_exact_safe_match_stays_cheap_without_qwen():
    llm = LLMFake()
    rag = RagFake()
    row = _choose(
        llm, question="phí thường niên của thẻ là bao nhiêu",
        product="thẻ tín dụng", rag=rag,
        vector_bank={"card_fee": _vec(0.96), "loan_rate": _vec(0.1)})

    assert row["id"] == "card_fee"
    assert not row.get("qwen_chon")
    assert llm.prompts == []
    assert rag.embed_calls == 0  # trùng câu mẫu: tra chỉ mục, không nhúng


def test_selected_answer_keeps_authoritative_text_and_numbers_verbatim():
    row = _choose(LLMFake())

    assert row["tra_loi"] == _bank()["card_fee"]["tra_loi"]
    assert "499.000" in row["tra_loi"] and "7,9%" in row["tra_loi"]


def test_timeout_returns_none_for_grounded_rag_fallback():
    assert _choose(LLMFake(delay=0.05), timeout_s=0.005) is None


def test_embedding_or_model_error_returns_none_for_grounded_fallback():
    class BrokenRag(RagFake):
        def embed(self, _texts):
            raise RuntimeError("embed unavailable")

    class BrokenLLM(LLMFake):
        async def generate_simple(self, *_args, **_kwargs):
            raise RuntimeError("model unavailable")

    assert _choose(LLMFake(), rag=BrokenRag()) is None
    assert _choose(BrokenLLM()) is None


def test_generated_source_change_during_qwen_wait_fails_closed():
    bank = {
        "auto_card_fee": {
            "id": "auto_card_fee", "san_pham": "thẻ tín dụng",
            "cau_hoi": ["phí thường niên là bao nhiêu"], "tra_loi": "499.000 đồng",
        }
    }
    current = {"value": True}

    class ChangingLLM(LLMFake):
        async def generate_simple(self, prompt, num_predict=100):
            current["value"] = False
            return await super().generate_simple(prompt, num_predict)

    row = _choose(
        ChangingLLM(), bank=bank,
        vector_bank={"auto_card_fee": _vec(0.86)},
        is_current=lambda _answer_id: current["value"])

    assert row is None


def test_stale_generated_direct_candidate_fails_closed_without_qwen():
    llm = LLMFake()
    row = _choose(
        llm, question="phí thường niên là bao nhiêu",
        bank={"auto_card_fee": {
            "id": "auto_card_fee", "san_pham": "thẻ tín dụng",
            "cau_hoi": ["phí thường niên là bao nhiêu"], "tra_loi": "499.000 đồng"}},
        vector_bank={"auto_card_fee": _vec(0.99)},
        is_current=lambda _answer_id: False)

    assert row is None
    assert llm.prompts == []


@pytest.mark.parametrize("prefix", [
    "auto_", "staff_", "mem_", "ab_auto_", "ab_staff_", "ab_mem_",
])
@pytest.mark.parametrize("missing_provenance", [False, True])
def test_generated_ids_fail_closed_on_direct_and_async_paths(prefix, missing_provenance):
    from backend.services.answer_bank_selector import best_candidate

    answer_id = prefix + "fee"
    question = "phí thẻ là bao nhiêu"
    bank = {answer_id: {
        "id": answer_id, "san_pham": "",
        "cau_hoi": [question], "tra_loi": "Phí có căn cứ.",
    }}
    vectors = {answer_id: _vec(0.99)}
    provenance = {} if missing_provenance else {
        answer_id: {"source_path": "shinhan/card.md"},
    }
    current = lambda _id: missing_provenance
    kwargs = dict(
        rag=RagFake(), bank=bank, vector_bank=vectors, question=question,
        product="", bank_name="Shinhan", provenance=provenance,
        is_current=current,
    )
    direct, _ = best_candidate(**kwargs)
    llm = LLMFake()
    selected = asyncio.run(choose(llm=llm, **kwargs))

    assert direct is None and selected is None
    assert llm.prompts == []


def test_selected_fixed_row_bypasses_rag_and_generation(monkeypatch):
    from backend.pipeline import streaming_pipeline as sp
    from backend.services import answer_bank_learning
    import backend.main as main

    answer = _bank()["card_fee"]["tra_loi"]
    rag = RagFake()
    llm = LLMFake()
    state = SimpleNamespace(
        rag=rag, llm=llm,
        hoi_dap={"card_fee": _bank()["card_fee"]},
        hoi_dap_vector={"card_fee": _vec(0.86)},
    )
    monkeypatch.setattr(main, "app_state", state, raising=False)
    monkeypatch.setattr(answer_bank_learning, "row_is_current", lambda _answer_id: True)
    monkeypatch.setattr(sp, "_schedule_persist", lambda _session: None)
    monkeypatch.setattr(sp, "_toan_van_tai_lieu", lambda _product: "")
    monkeypatch.setattr(sp, "tra_loi_san", lambda *_a, **_k: None)
    monkeypatch.setattr(sp, "tra_loi_danh_muc", lambda *_a, **_k: None)
    monkeypatch.setattr(sp, "tra_loi_khoan_vay", lambda *_a, **_k: None)
    monkeypatch.setattr(sp, "tra_loi_ho_so", lambda *_a, **_k: None)
    monkeypatch.setattr(sp.settings, "ngu_canh_tron_tai_lieu", False)
    monkeypatch.setattr(sp.settings, "tieng_san_bat", False)

    async def no_tool(*_args, **_kwargs):
        raise AssertionError("câu answer bank không được mở task công cụ")

    class Sink:
        def __init__(self):
            self.events = []

        async def send_json(self, event):
            self.events.append(event)

    pipe = sp.StreamingPipeline.__new__(sp.StreamingPipeline)
    pipe.rag = rag
    pipe.llm = llm
    pipe.tts = SimpleNamespace(
        _is_loaded=False, toc_do_cua=lambda _voice: 1.0,
        he_so_thoai=lambda: 1.0)
    pipe._tra_bang_cong_cu = no_tool
    session = CallSession(product="thẻ tín dụng")
    session.so_can_cu = None
    session.add_turn("assistant", "Anh đang xem thẻ tín dụng.")
    session.add_turn("user", "thế phí thì sao")
    sink = Sink()
    metrics = {"la_thoai": False}

    asyncio.run(pipe._generate_response(
        "thế phí thì sao", session, sink, time.perf_counter(), metrics, soi=True))

    complete = [event for event in sink.events if event["type"] == "turn_complete"]
    assert complete[0]["full_response"] == answer
    assert rag.retrieve_calls == 0
    assert metrics["bang_chon_qwen"] == "card_fee"
    assert metrics["bang_doc_thang"] is True


def test_large_provenance_snapshot_is_chunked_and_cached(monkeypatch):
    from backend.pipeline import streaming_pipeline as sp
    from backend.services import answer_bank_learning

    bank = {f"auto_{i}": {"id": f"auto_{i}"} for i in range(1205)}
    vectors = {key: object() for key in bank}
    calls = []

    def load(ids):
        calls.append(tuple(ids))
        return {answer_id: {"source_path": "products/sample.md"}
                for answer_id in ids}

    monkeypatch.setattr(answer_bank_learning, "provenance_for_ids", load)
    state = SimpleNamespace()

    first = sp._answer_bank_provenance(state, bank, vectors)
    second = sp._answer_bank_provenance(state, bank, vectors)

    assert len(first) == 1205 and second is first
    assert [len(batch) for batch in calls] == [400, 400, 400, 5]


def test_answer_only_novel_request_uses_actual_answer_selection_and_exact_text():
    from backend.services.answer_bank_selector import best_candidate

    answer = "  Hồ sơ gồm CCCD và giấy xác nhận thu nhập.\nChỉ áp dụng khách từ 22 tuổi.  "
    bank = {"ab_manual_docs": {"id": "ab_manual_docs", "san_pham": "",
                                "cau_hoi": [], "tra_loi": answer}}
    vectors = {"ab_manual_docs": _vec(0.99)}
    question = "Muốn bắt đầu vay thì mang theo thứ gì đến quầy"
    llm = LLMFake()
    row, _ = best_candidate(rag=RagFake(), bank=bank, vector_bank=vectors, question=question)
    assert row["can_chon_qwen"] is True
    selected = _choose(llm, question=question, product="", bank=bank, vector_bank=vectors)
    assert selected["qwen_chon"] and selected["tra_loi"] == answer
    payload = json.loads(llm.prompts[0][0].split("DATA=", 1)[1])
    assert payload["candidates"][0]["prepared_answer"] == answer
    assert payload["candidates"][0]["prepared_questions"] == []


def test_same_optional_question_different_answers_requires_qwen_content_choice():
    question = "Cần chuẩn bị gì để vay"
    bank = {
        "ab_manual_a": {"id": "ab_manual_a", "san_pham": "", "cau_hoi": [question],
                        "tra_loi": "Vay thế chấp cần giấy chứng nhận nhà đất."},
        "ab_manual_b": {"id": "ab_manual_b", "san_pham": "", "cau_hoi": [question],
                        "tra_loi": "Vay tín chấp cần CCCD và giấy xác nhận thu nhập."},
    }
    llm = LLMFake('{"choice":"C2"}')
    got = _choose(llm, question=question, product="", bank=bank,
                  vector_bank={"ab_manual_a": _vec(0.99), "ab_manual_b": _vec(0.85)})
    assert got["id"] == "ab_manual_b" and got["qwen_chon"]
    payload = json.loads(llm.prompts[0][0].split("DATA=", 1)[1])
    assert [row["prepared_answer"] for row in payload["candidates"]] == [
        bank["ab_manual_a"]["tra_loi"], bank["ab_manual_b"]["tra_loi"]]


def test_high_answer_cosine_does_not_bypass_null_or_timeout_selection():
    bank = {"ab_manual_fee": {"id": "ab_manual_fee", "san_pham": "",
                               "cau_hoi": [], "tra_loi": "Phí theo biểu phí hiện hành."}}
    kwargs = dict(question="Tôi mất thêm khoản nào khi làm thẻ", product="", bank=bank,
                  vector_bank={"ab_manual_fee": _vec(1.0)})
    assert _choose(LLMFake('{"choice":null}'), **kwargs) is None
    assert _choose(LLMFake(delay=0.05), timeout_s=0.005, **kwargs) is None


def test_novel_legacy_question_also_requires_selection_at_high_cosine():
    llm = LLMFake('{"choice":null}')
    got = _choose(llm, question="Thẻ này mỗi năm thu tiền ra sao",
                  vector_bank={"card_fee": _vec(0.99)})
    assert got is None and len(llm.prompts) == 1


def test_managed_multiintent_coverage_is_checked_against_actual_answer():
    bank = {"ab_manual_partial": {"id": "ab_manual_partial", "san_pham": "",
                                   "cau_hoi": ["lãi suất", "hồ sơ"],
                                   "tra_loi": "Lãi suất là 7,9%."}}
    llm = LLMFake()
    assert _choose(llm, question="lãi suất và hồ sơ", product="", bank=bank,
                   vector_bank={"ab_manual_partial": _vec(0.99)}) is None
    assert llm.prompts == []
    bank["ab_manual_partial"]["tra_loi"] += " Hồ sơ cần CCCD."
    assert _choose(llm, question="lãi suất và hồ sơ", product="", bank=bank,
                   vector_bank={"ab_manual_partial": _vec(0.99)})["qwen_chon"]


def test_full_answer_conditions_are_sent_and_oversized_answer_fails_closed(monkeypatch):
    from backend.config import settings
    from backend.services.answer_bank_selector import MAX_PREPARED_ANSWER_CHARS

    # This case tests intact answer conditions independently of the deployment's
    # context size. The separate budget case verifies fail-closed overflow.
    monkeypatch.setattr(settings, "llm_num_ctx", 8192)
    answer = "Điều khoản. " * 150 + "Chỉ áp dụng sau khi xác minh thu nhập."
    bank = {"ab_manual_long": {"id": "ab_manual_long", "san_pham": "",
                                "cau_hoi": [], "tra_loi": answer}}
    llm = LLMFake()
    got = _choose(llm, question="Tôi có thể đăng ký bằng cách nào", product="", bank=bank,
                  vector_bank={"ab_manual_long": _vec(0.9)})
    assert got["tra_loi"] == answer
    payload = json.loads(llm.prompts[0][0].split("DATA=", 1)[1])
    assert payload["candidates"][0]["prepared_answer"].endswith("xác minh thu nhập.")
    bank["ab_manual_long"]["tra_loi"] = "x" * (MAX_PREPARED_ANSWER_CHARS + 1)
    llm = LLMFake()
    assert _choose(llm, question="Tôi có thể đăng ký bằng cách nào", product="", bank=bank,
                   vector_bank={"ab_manual_long": _vec(0.9)}) is None
    assert llm.prompts == []


def test_complete_candidate_set_over_context_budget_falls_back_without_truncation(monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "llm_num_ctx", 8192)
    bank = {f"ab_manual_{i}": {"id": f"ab_manual_{i}", "san_pham": "",
                               "cau_hoi": [], "tra_loi": "A" * 2500 + " Late condition."}
            for i in range(4)}
    llm = LLMFake()
    assert _choose(llm, question="Tôi có thể đăng ký bằng cách nào", product="", bank=bank,
                   vector_bank={key: _vec(0.9) for key in bank}) is None
    assert llm.prompts == []


def _card_bank():
    return {
        "grace": {"id": "grace", "san_pham": "thẻ tín dụng",
                  "cau_hoi": ["thẻ tín dụng miễn lãi bao lâu"],
                  "tra_loi": "Dạ thời gian miễn lãi của thẻ tín dụng lên đến 55 ngày ạ."},
        "cash": {"id": "cash", "san_pham": "thẻ tín dụng",
                 "cau_hoi": ["ứng tiền mặt có miễn lãi không"],
                 "tra_loi": "Dạ ứng trước tiền mặt bằng thẻ không được miễn lãi ạ."},
    }


def test_narrow_topic_never_served_by_answer_about_something_else():
    # 02-10-2026: "ứng tiền mặt ... miễn lãi không" được đọc "miễn lãi 55 ngày".
    bank = {"grace": _card_bank()["grace"]}
    llm = LLMFake('{"choice":"C1"}')
    row = _choose(llm, question="ứng tiền mặt bằng thẻ tín dụng có được miễn lãi không",
                  bank=bank, vector_bank={"grace": _vec(0.9)})
    assert row is None and llm.prompts == []


def test_narrow_topic_keeps_answer_that_mentions_it():
    llm = LLMFake('{"choice":"C1"}')
    row = _choose(llm, question="ứng tiền mặt bằng thẻ tín dụng có được miễn lãi không",
                  bank=_card_bank(), vector_bank={"grace": _vec(0.92), "cash": _vec(0.88)})
    assert row["id"] == "cash"
    assert "55 ngày" not in llm.prompts[0][0]


def test_question_without_narrow_topic_is_unaffected():
    llm = LLMFake('{"choice":"C1"}')
    row = _choose(llm, question="thẻ tín dụng được miễn lãi bao lâu",
                  bank={"grace": _card_bank()["grace"]}, vector_bank={"grace": _vec(0.9)})
    assert row["id"] == "grace"


def test_exception_answer_not_served_for_general_question():
    # Đáp án về NGOẠI LỆ (ứng tiền mặt) không được dùng cho câu hỏi chung.
    llm = LLMFake('{"choice":"C1"}')
    row = _choose(llm, question="thẻ tín dụng miễn lãi bao nhiêu ngày",
                  bank={"cash": _card_bank()["cash"]}, vector_bank={"cash": _vec(0.9)})
    assert row is None and llm.prompts == []


def _rate_bank():
    q = "lãi suất vay tín chấp bao nhiêu"
    return {
        "ab_mem_1": {"id": "ab_mem_1", "san_pham": "vay tín chấp", "cau_hoi": [q],
                     "tra_loi": "Dạ, lãi suất vay tín chấp cá nhân từ 7.9%/năm ạ."},
        "ab_mem_2": {"id": "ab_mem_2", "san_pham": "vay tín chấp", "cau_hoi": [q],
                     "tra_loi": "Dạ, lãi suất vay tín chấp cá nhân của chúng em từ 7.9%/năm ạ."},
    }


def test_customer_words_matching_example_are_read_without_qwen():
    # 05-10-2026: khách hỏi đúng câu đã soạn mà vẫn phải chờ Qwen chọn (tới 1,2s).
    from backend.services.answer_bank_selector import best_candidate
    from backend.services.bang_hoi_dap import doc_nguyen_van
    bank = _rate_bank()
    vectors = {"ab_mem_1": _vec(0.97), "ab_mem_2": _vec(0.96)}
    llm = LLMFake()
    row = _choose(llm, question="lãi suất vay tín chấp là bao nhiêu", product="vay tín chấp",
                  bank=bank, vector_bank=vectors)
    assert row["id"] in bank and row["khop_vi_du"] and llm.prompts == []
    fast, _ = best_candidate(rag=RagFake(), bank=bank, vector_bank=vectors,
                             question="lãi suất vay tín chấp là bao nhiêu", product="vay tín chấp")
    assert fast["id"] in bank and doc_nguyen_van(fast)


def test_matching_example_with_conflicting_numbers_still_needs_qwen():
    bank = _rate_bank()
    bank["ab_mem_2"]["tra_loi"] = "Dạ, lãi suất vay tín chấp cá nhân từ 8.5%/năm ạ."
    llm = LLMFake('{"choice":"C1"}')
    row = _choose(llm, question="lãi suất vay tín chấp bao nhiêu", product="vay tín chấp",
                  bank=bank, vector_bank={"ab_mem_1": _vec(0.97), "ab_mem_2": _vec(0.96)})
    assert row["qwen_chon"] and len(llm.prompts) == 1


def test_matching_example_prefers_tersest_consistent_answer():
    bank = _rate_bank()
    bank["ab_mem_3"] = {"id": "ab_mem_3", "san_pham": "vay tín chấp",
                        "cau_hoi": ["lãi suất vay tín chấp bao nhiêu"],
                        "tra_loi": "Dạ, lãi suất từ 7,9%/năm, hạn mức đến 500 triệu, thời hạn 12-60 tháng ạ."}
    llm = LLMFake()
    row = _choose(llm, question="lãi suất vay tín chấp bao nhiêu", product="vay tín chấp", bank=bank,
                  vector_bank={"ab_mem_3": _vec(0.99), "ab_mem_1": _vec(0.9), "ab_mem_2": _vec(0.9)})
    assert row["id"] in ("ab_mem_1", "ab_mem_2") and llm.prompts == []  # không đọc dòng dài


class NoEmbed(RagFake):
    def embed(self, texts):
        raise AssertionError("đường nhanh không được nhúng câu hỏi")


def test_exact_example_skips_embedding_and_qwen():
    from backend.services.answer_bank_selector import best_candidate
    bank = _rate_bank()
    row, q = best_candidate(rag=NoEmbed(), bank=bank, vector_bank={"ab_mem_1": _vec(0.9), "ab_mem_2": _vec(0.9)},
                            question="lãi suất vay tín chấp là bao nhiêu", product="vay tín chấp")
    assert row["id"] in bank and row["khop_vi_du"] and q is None


def test_fast_path_still_respects_product_isolation():
    bank = _rate_bank()
    llm = LLMFake('{"choice":null}')
    row = _choose(llm, question="lãi suất vay tín chấp là bao nhiêu", product="thẻ tín dụng",
                  bank=bank, vector_bank={"ab_mem_1": _vec(0.9), "ab_mem_2": _vec(0.9)})
    assert row is None


def test_qwen_choice_is_remembered_until_bank_reloads():
    bank = {"ab_x": {"id": "ab_x", "san_pham": "vay tín chấp", "cau_hoi": ["lãi suất vay là bao nhiêu"],
                     "tra_loi": "Dạ lãi suất vay tín chấp từ 7.9%/năm ạ."}}
    vectors = {"ab_x": _vec(0.9)}
    question = "vay tín chấp thì lãi tính ra sao hả em"
    llm = LLMFake('{"choice":"C1"}')
    first = _choose(llm, question=question, product="vay tín chấp", bank=bank, vector_bank=vectors)
    assert first["qwen_chon"] and len(llm.prompts) == 1
    again = _choose(llm, question=question, product="vay tín chấp", bank=bank, vector_bank=vectors,
                    rag=NoEmbed())
    assert again["id"] == "ab_x" and again["tu_bo_nho"] and len(llm.prompts) == 1
    # Kho nạp lại (dict mới): quên hết, hỏi lại Qwen.
    fresh = {k: dict(v) for k, v in bank.items()}
    _choose(llm, question=question, product="vay tín chấp", bank=fresh, vector_bank=vectors)
    assert len(llm.prompts) == 2


@pytest.mark.parametrize("question, follow", [
    ("vay tín chấp lãi bao nhiêu", False),      # "vay" là khoản vay, không phải "vậy"
    ("thẻ tín dụng phí bao nhiêu", False),      # "thẻ" không phải "thế"
    ("vậy lãi bao nhiêu", True),
    ("thế phí thì sao", True),
    ("con phi thi sao", True),                  # gõ không dấu
])
def test_follow_up_detection_uses_accented_connectors(question, follow):
    from backend.services.answer_bank_selector import _is_follow_up
    assert _is_follow_up(question) is follow


def test_equivalent_answers_rotate_instead_of_repeating():
    from backend.services import answer_bank_selector as selector
    selector._luot_xoay.clear()
    bank = _rate_bank()
    bank["ab_mem_3"] = {"id": "ab_mem_3", "san_pham": "vay tín chấp",
                        "cau_hoi": ["lãi suất vay tín chấp bao nhiêu"],
                        "tra_loi": "Dạ, mức lãi suất vay tín chấp là từ 7.9%/năm ạ."}
    bank["ab_dai"] = {"id": "ab_dai", "san_pham": "vay tín chấp",
                      "cau_hoi": ["lãi suất vay tín chấp bao nhiêu"],
                      "tra_loi": "Dạ, lãi suất từ 7.9%/năm, hạn mức đến 500 triệu ạ."}
    vectors = {k: _vec(0.9) for k in bank}
    llm = LLMFake()
    picks = [_choose(llm, question="lãi suất vay tín chấp là bao nhiêu", product="vay tín chấp",
                     bank=bank, vector_bank=vectors)["id"] for _ in range(6)]
    assert picks[:3] == ["ab_mem_1", "ab_mem_2", "ab_mem_3"] and picks[3:] == picks[:3]
    assert "ab_dai" not in picks and llm.prompts == []


def test_single_digit_term_is_part_of_the_question():
    # "1 tháng" và "3 tháng" không phải cùng một câu hỏi.
    from backend.services.answer_bank_selector import best_candidate, khoa_cau_hoi
    assert khoa_cau_hoi("lãi suất tiết kiệm 1 tháng") != khoa_cau_hoi("lãi suất tiết kiệm 3 tháng")
    bank = {"ab_3": {"id": "ab_3", "san_pham": "tiết kiệm", "cau_hoi": ["lãi suất tiết kiệm 3 tháng bao nhiêu"],
                     "tra_loi": "Dạ, gửi tiết kiệm 3 tháng lãi suất 3.8%/năm ạ."}}
    row, _ = best_candidate(rag=RagFake(), bank=bank, vector_bank={"ab_3": _vec(0.95)},
                            question="lãi suất tiết kiệm 6 tháng là bao nhiêu", product="tiết kiệm")
    assert not (row or {}).get("khop_vi_du")
