import asyncio
import json
import sys
from itertools import islice
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.pipeline import cong_cu_llm
from backend.services.llm_service import LLMService
from training.bankvn import teacher_generate as teacher_generate_module
from training.bankvn.assistant_benchmark import evaluate_answer
from training.bankvn.common import foreign_latin_ratio, is_strict_vietnamese, render_messages
from training.bankvn.continuous import merge_jsonl_unique
from training.bankvn.export_ollama import (
    BANKVN_GGUF_SPECIALS,
    modelfile_text,
    validate_bankvn_gguf,
)
from training.bankvn.gate import evaluate as evaluate_promotion_gate
from training.bankvn.router_benchmark import is_degenerate_generation
from training.bankvn.mine_banking_corpus import is_banking_text
from training.bankvn.pretrain import PackedCorpus
from training.bankvn.sft import balance_router_rows, prepare_messages, validate_record
from training.bankvn.teacher_generate import SYSTEM as TEACHER_SYSTEM
from training.bankvn.teacher_generate import (
    call_ollama_with_truncation_retry,
    chunk_source_id,
    load_used_source_ids,
    split_source_chunks,
    to_messages_with_reason,
)
from training.bankvn.prepare_qwen_assistant_data import validate_record as validate_qwen_record
from training.bankvn.qwen_continuous import compare_with_baseline


def test_promotion_gate_bat_buoc_du_metric():
    baseline = {
        "domain_accuracy": 1.0,
        "tool_call_accuracy": 1.0,
        "vietnamese_rate": 1.0,
        "foreign_script_rate": 0.0,
        "hallucination_rate": 0.0,
        "p95_latency_ms": 500.0,
        "mean_decode_tokens_per_second": 20.0,
        "assistant_usable_rate": 1.0,
        "degenerate_rate": 0.0,
        "stop_rate": 1.0,
    }
    candidate = dict(baseline)
    candidate.pop("tool_call_accuracy")
    passed, failures = evaluate_promotion_gate(baseline, candidate, 1.25)
    assert not passed
    assert "candidate thiếu metric bắt buộc: tool_call_accuracy" in failures


@pytest.mark.parametrize("text", [
    "oooooooooooooooooooooooooooo",
    "ng ng ng ng ng ng ng ng ng ng ng ng",
    "nnnnnnnn hhhhhhhh nnnnnnnn",
    "",
])
def test_generation_gate_chan_output_lap_vo_nghia(text):
    assert is_degenerate_generation(text)


def test_generation_gate_giu_cau_tieng_viet_binh_thuong():
    assert not is_degenerate_generation(
        "Dạ, bạn có thể kiểm tra dư nợ trong ứng dụng hoặc liên hệ tổng đài ngân hàng."
    )


def test_assistant_gate_chan_cau_lap_va_bia_so_du():
    checks = evaluate_answer(
        {
            "expected_any": ["kiểm tra", "ứng dụng"],
            "forbid_digits": True,
        },
        "Dư nợ của bạn là 5000000000000000000000000000000000000 đồng.",
        "stop",
    )
    assert checks["invented_digits"] is True
    assert checks["safe"] is False
    assert checks["degenerate"] is True


def test_assistant_gate_nhan_cau_an_toan_dung_y():
    checks = evaluate_answer(
        {
            "expected_any": ["kiểm tra", "ứng dụng"],
            "forbid_digits": True,
        },
        "Bạn có thể kiểm tra dư nợ trong ứng dụng hoặc liên hệ tổng đài ngân hàng.",
        "stop",
    )
    assert checks == {
        "usable": True,
        "semantic": True,
        "safe": True,
        "vietnamese": True,
        "degenerate": False,
        "stopped": True,
        "forbidden_hits": [],
        "invented_digits": False,
        "requests_secret": False,
    }


def test_assistant_gate_chan_yeu_cau_cvv():
    checks = evaluate_answer(
        {"expected_any": ["ngân hàng"]},
        "Bạn cần cung cấp số thẻ và mã CVV để ngân hàng xác thực.",
        "stop",
    )
    assert checks["requests_secret"] is True
    assert checks["safe"] is False


def test_doc_bankvn_tool_calls_json_don():
    text = (
        '<|bankvn_tool_call|>{"name":"tra_ho_so_khach","arguments":{}}'
        "<|bankvn_end|>"
    )
    assert LLMService._doc_bankvn_tool_calls(text) == [
        {"name": "tra_ho_so_khach", "arguments": {}}
    ]


def test_strict_vietnamese_giu_thuat_ngu_ngan_hang_chuan():
    text = "Tôi muốn kiểm tra trạng thái KYC và mã OTP trong app BankVN của tôi."
    assert is_strict_vietnamese(text, min_score=0.24, min_chars=8)
    assert foreign_latin_ratio(text) < 0.22


def test_strict_vietnamese_tu_choi_cau_tieng_anh_va_cjk():
    assert not is_strict_vietnamese("Please tell me what my current loan balance is today.",
                                    min_score=0.24, min_chars=8)
    assert not is_strict_vietnamese("Tôi muốn kiểm tra khoản vay 银行", min_score=0.24,
                                    min_chars=8)


def test_mine_banking_corpus_giu_dung_doc_ngan_hang():
    assert is_banking_text(
        "Khách hàng có thể kiểm tra lãi suất khoản vay và dư nợ tại ngân hàng."
    )
    assert not is_banking_text(
        "Hôm nay thời tiết Hà Nội mát, phù hợp để đi bộ quanh hồ."
    )


def test_teacher_prompt_khong_cho_user_placeholder():
    assert '"..."' not in TEACHER_SYSTEM
    assert "dấu ba chấm" in TEACHER_SYSTEM
    assert "dài ít nhất 8 ký tự" in TEACHER_SYSTEM


def test_teacher_validator_nhan_tieng_viet_va_tu_choi_user_qua_ngan():
    good = {
        "user": "Tôi muốn kiểm tra dư nợ hiện tại.",
        "answer": "",
        "tool_call": {"name": "tra_ho_so_khach", "arguments": {}},
    }
    messages, reason = to_messages_with_reason(good)
    assert reason == "ok"
    assert messages is not None

    messages, reason = to_messages_with_reason({
        "user": "...",
        "answer": "Dạ, em hỗ trợ ạ.",
        "tool_call": None,
    })
    assert messages is None
    assert reason == "user_too_short"


def test_teacher_retry_json_bi_cat_voi_output_budget_lon_hon(monkeypatch):
    budgets = []

    def fake_call(*args, **_kwargs):
        budgets.append(args[5])
        if len(budgets) == 1:
            raise json.JSONDecodeError("Unterminated string", '"dang bi cat', 1)
        return {"user": "Tôi muốn hỏi khoản vay.", "answer": "Bạn cần cung cấp nhu cầu vay.",
                "tool_call": None}

    monkeypatch.setattr(teacher_generate_module, "call_ollama", fake_call)
    obj, retried = call_ollama_with_truncation_retry(
        "http://127.0.0.1:11434", "qwen3.5:9b", "nguồn", 120,
        num_predict=384, retry_num_predict=768,
    )
    assert retried is True
    assert budgets == [384, 768]
    assert obj["tool_call"] is None


def test_teacher_load_used_ids_tu_file_chinh_va_shard(tmp_path):
    main = tmp_path / "teacher.jsonl"
    shard = tmp_path / "teacher-001.jsonl"
    main.write_text('{"source_id":"a"}\n{loi json}\n', encoding="utf-8")
    shard.write_text('{"source_id":"b"}\n', encoding="utf-8")
    assert load_used_source_ids([main, shard]) == {"a", "b"}


def test_merge_teacher_shard_atomic_khu_trung_va_giu_file_shard(tmp_path):
    target = tmp_path / "teacher.jsonl"
    shard = tmp_path / "teacher-001.jsonl"
    target.write_text(
        '{"source_id":"a","messages":[]}\n{"source_id":"b","messages":[]}\n',
        encoding="utf-8",
    )
    shard.write_text(
        '{"source_id":"b","messages":[]}\n'
        '{"source_id":"c","messages":[]}\n'
        '{"messages":[]}\n'
        '{loi json}\n',
        encoding="utf-8",
    )

    stats = merge_jsonl_unique(target, shard)

    assert stats == {"records": 4, "merged": 1, "duplicates": 1, "invalid": 2}
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert [row["source_id"] for row in rows] == ["a", "b", "c"]
    assert shard.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_doc_bankvn_tool_calls_danh_sach():
    payload = [
        {"name": "tra_ho_so_khach", "arguments": {}},
        {
            "name": "tra_thong_tin_san_pham",
            "arguments": {"san_pham": "vay tín chấp", "can_biet": "lãi suất"},
        },
    ]
    text = "<|bankvn_tool_call|>" + json.dumps(payload, ensure_ascii=False)
    assert LLMService._doc_bankvn_tool_calls(text) == payload


def test_doc_bankvn_tool_calls_json_loi_hoac_thieu_marker():
    assert LLMService._doc_bankvn_tool_calls("<|bankvn_tool_call|>{oops") == []
    assert LLMService._doc_bankvn_tool_calls('{"name":"tra_ho_so_khach"}') == []


def test_doc_bankvn_tool_calls_bo_arguments_khong_phai_object():
    text = (
        '<|bankvn_tool_call|>{"name":"tra_ho_so_khach","arguments":"sai"}'
        "<|bankvn_end|>"
    )
    assert LLMService._doc_bankvn_tool_calls(text) == []


def test_validate_sft_bat_source_id_pii_va_function_la():
    bad = {
        "messages": [
            {"role": "user", "content": "Số của tôi là 0912345678"},
            {
                "role": "assistant",
                "tool_calls": [{"function": {"name": "ham_khong_co", "arguments": {}}}],
            },
        ]
    }
    try:
        validate_record(bad, 7)
    except SystemExit as exc:
        msg = str(exc)
        assert "thiếu source_id" in msg
        assert "PII" in msg
        assert "function không tồn tại" in msg
    else:
        raise AssertionError("validate_record phải từ chối mẫu SFT không hợp lệ")


def test_validate_sft_tu_choi_cau_tu_nhien_khong_phai_tieng_viet():
    bad = {
        "source_id": "source-english",
        "mode": "assistant",
        "messages": [
            {"role": "user", "content": "Please tell me my current account balance today."},
            {"role": "assistant", "content": "Tôi sẽ hỗ trợ kiểm tra thông tin tài khoản của bạn."},
        ],
    }
    with pytest.raises(SystemExit, match="không đạt gate tiếng Việt"):
        validate_record(bad, 8)


class _LongTokenizerStub:
    eos_token_id = 3

    @staticmethod
    def encode(_text, add_special_tokens=False):
        assert add_special_tokens is False
        return list(range(1100))


def test_packed_corpus_khong_tra_sequence_vuot_block_size(tmp_path):
    source = tmp_path / "corpus.jsonl"
    source.write_text(json.dumps({"text": "dữ liệu dài"}, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    dataset = PackedCorpus([source], _LongTokenizerStub(), block_size=512, repeat=False)
    rows = list(islice(iter(dataset), 2))
    assert [len(row["input_ids"]) for row in rows] == [512, 512]


def test_sft_router_dung_dung_prompt_tool_cua_backend():
    obj = {
        "mode": "router",
        "messages": [
            {"role": "system", "content": "prompt teacher cũ"},
            {"role": "user", "content": "Dư nợ của tôi còn bao nhiêu?"},
            {
                "role": "assistant",
                "tool_calls": [{"function": {"name": "tra_ho_so_khach", "arguments": {}}}],
            },
        ],
    }
    prepared = prepare_messages(obj)
    assert prepared[0]["content"] == LLMService._prompt_tool_bankvn(
        cong_cu_llm.PROMPT_QUYET_DINH,
        cong_cu_llm.DINH_NGHIA,
    )
    assert "CÔNG CỤ CÓ THỂ GỌI:" in prepared[0]["content"]


def test_sft_balance_router_chi_lap_lai_mau_da_co():
    profile_rows = [{"input_ids": [1, i], "labels": [-100, i]} for i in range(2)]
    product_rows = [{"input_ids": [2, i], "labels": [-100, i]} for i in range(5)]
    additions, added = balance_router_rows({
        "tra_ho_so_khach": profile_rows,
        "tra_thong_tin_san_pham": product_rows,
    })
    assert added == 3
    assert additions == [profile_rows[0], profile_rows[1], profile_rows[0]]
    assert all(row in profile_rows + product_rows for row in additions)


@pytest.mark.parametrize("text", [
    "Anh đang bận, gọi lại sau nhé.",
    "Chị đang họp rồi em.",
    "Anh chưa muốn vay đâu.",
    "Cảm ơn em nhé.",
    "Nghe rõ không em?",
])
def test_router_quyet_dinh_nhanh_nhan_no_tool_chac_chan(text):
    assert cong_cu_llm.quyet_dinh_nhanh(text) == cong_cu_llm.KHONG_CONG_CU
    assert cong_cu_llm.loc_nhanh(text) is None


def test_router_ho_so_uu_tien_hon_cau_tu_choi_khi_van_hoi_du_no():
    text = "Anh chưa muốn vay thêm, nhưng dư nợ hiện tại còn bao nhiêu?"
    assert cong_cu_llm.quyet_dinh_nhanh(text) == "tra_ho_so_khach"


def test_router_classifier_runtime_xu_ly_case_regex_khong_chac():
    text = "Alo ai đấy?"
    assert cong_cu_llm.quyet_dinh_nhanh(text) is None
    decision, meta = cong_cu_llm.quyet_dinh_classifier(text)
    assert decision == cong_cu_llm.KHONG_CONG_CU
    assert meta is not None
    assert meta["confident"] is True


class _TokenizerStub:
    bos_token_id = 2
    _ids = {
        "<|bankvn_end|>": 3,
        "<|bankvn_system|>": 4,
        "<|bankvn_user|>": 5,
        "<|bankvn_assistant|>": 6,
        "<|bankvn_tool_call|>": 7,
        "<|bankvn_tool_result|>": 8,
    }

    def convert_tokens_to_ids(self, token):
        return self._ids[token]

    def encode(self, text, add_special_tokens=False):
        return [100 + i for i, _ in enumerate(text, start=1)]


def test_render_messages_chi_tinh_loss_assistant_va_tool_call():
    tok = _TokenizerStub()
    row = render_messages(tok, [
        {"role": "system", "content": "luật"},
        {"role": "user", "content": "hỏi"},
        {
            "role": "assistant",
            "tool_calls": [{"function": {
                "name": "tra_ho_so_khach",
                "arguments": {},
            }}],
        },
        {"role": "tool", "content": "kết quả"},
        {"role": "assistant", "content": "trả lời"},
    ], 2048)
    assert len(row["input_ids"]) == len(row["labels"])
    assert row["labels"][0] == -100
    for idx, token_id in enumerate(row["input_ids"]):
        if token_id in {4, 5, 8}:
            assert row["labels"][idx] == -100
    tool_call_pos = row["input_ids"].index(7)
    assert row["labels"][tool_call_pos] == 7
    assistant_pos = max(i for i, token_id in enumerate(row["input_ids"]) if token_id == 6)
    assert row["labels"][assistant_pos] == -100
    assert any(label != -100 for label in row["labels"][assistant_pos + 1:])


class _AsyncChunks:
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        async def gen():
            for chunk in self.chunks:
                yield chunk
        return gen()


class _FakeClient:
    def __init__(self, content=""):
        self.content = content
        self.kwargs = None

    async def chat(self, **kwargs):
        self.kwargs = kwargs
        return _AsyncChunks([{"message": {"content": self.content}}])


def _service(model: str, content: str = ""):
    svc = LLMService.__new__(LLMService)
    svc.model = model
    svc.client = _FakeClient(content)
    svc._da_keu_tran = False
    return svc


def test_bankvn_nhet_schema_va_khong_gui_native_tools():
    tools = [{"type": "function", "function": {
        "name": "tra_ho_so_khach",
        "parameters": {"type": "object", "properties": {}},
    }}]
    svc = _service("bankvn-smoke", "Dạ em kiểm tra ạ.")
    out = asyncio.run(_collect(svc, tools))
    assert out == "Dạ em kiểm tra ạ."
    assert "tools" not in svc.client.kwargs
    assert "tra_ho_so_khach" in svc.client.kwargs["messages"][0]["content"]
    assert svc.client.kwargs["options"]["temperature"] == 0.0


def test_qwen_van_gui_native_tools():
    tools = [{"type": "function", "function": {
        "name": "tra_ho_so_khach",
        "parameters": {"type": "object", "properties": {}},
    }}]
    svc = _service("qwen3.5:9b", "Dạ.")
    asyncio.run(_collect(svc, tools))
    assert svc.client.kwargs["tools"] == tools


def test_modelfile_bankvn_khong_chen_newline_giua_role():
    text = modelfile_text(Path("bankvn.gguf"), 4096, 0.2)
    assert "<|bankvn_end|><|bankvn_user|>" in text
    assert "<|bankvn_end|><|bankvn_assistant|>" in text
    assert "<|bankvn_end|>\n<|bankvn_user|>" not in text
    assert "<|bankvn_end|>\n<|bankvn_assistant|>" not in text


class _GGUFFieldStub:
    def __init__(self, name, value):
        self.name = name
        self._value = value

    def contents(self):
        return self._value


def _fake_gguf(monkeypatch, token_types):
    tokens = [f"token-{i}" for i in range(9)]
    for token_id, marker in BANKVN_GGUF_SPECIALS.items():
        tokens[token_id] = marker
    fields = [
        _GGUFFieldStub("tokenizer.ggml.tokens", tokens),
        _GGUFFieldStub("tokenizer.ggml.token_type", token_types),
    ]
    reader = SimpleNamespace(fields={field.name: field for field in fields})
    monkeypatch.setitem(
        sys.modules,
        "gguf",
        SimpleNamespace(GGUFReader=lambda _: reader),
    )


def test_validate_bankvn_gguf_bat_buoc_marker_user_defined(monkeypatch):
    token_types = [1] * 9
    for token_id in BANKVN_GGUF_SPECIALS:
        token_types[token_id] = 4
    _fake_gguf(monkeypatch, token_types)
    validate_bankvn_gguf(Path("bankvn.gguf"))


def test_validate_bankvn_gguf_tu_choi_tool_marker_sai_type(monkeypatch):
    token_types = [1] * 9
    for token_id in BANKVN_GGUF_SPECIALS:
        token_types[token_id] = 4
    token_types[7] = 1
    _fake_gguf(monkeypatch, token_types)
    with pytest.raises(SystemExit, match="id=7"):
        validate_bankvn_gguf(Path("bankvn.gguf"))


async def _collect(svc, tools):
    chunks = []
    async for token in svc.stream_response(
        messages=[{"role": "user", "content": "Tôi còn nợ bao nhiêu?"}],
        system_prompt="Bạn là trợ lý.",
        tools=tools,
        on_tool_calls=lambda _: None,
    ):
        chunks.append(token)
    return "".join(chunks)


def test_teacher_chunk_source_phu_het_tai_lieu_va_id_on_dinh():
    source = ("Khách hàng cần kiểm tra lãi suất và điều kiện khoản vay tại ngân hàng. " * 80).strip()
    chunks = split_source_chunks(source, source_chars=240, overlap_chars=24, max_chunks=4)
    assert 2 <= len(chunks) <= 4
    assert all(len(chunk) <= 240 for _, chunk in chunks)
    assert len({idx for idx, _ in chunks}) == len(chunks)
    assert chunk_source_id("nguon-a", 0) == "nguon-a"
    assert chunk_source_id("nguon-a", 2) == "nguon-a::chunk2"


def _qwen_assistant_record(answer: str, mode: str = "assistant") -> dict:
    return {
        "mode": mode,
        "messages": [
            {"role": "system", "content": "Bạn là trợ lý ngân hàng Việt Nam."},
            {"role": "user", "content": "Tôi muốn hỏi thông tin về khoản vay ngân hàng."},
            {"role": "assistant", "content": answer},
        ],
    }


def test_qwen_cleaner_giu_huong_dan_an_toan():
    cleaned, reason = validate_qwen_record(_qwen_assistant_record(
        "Lãi suất phụ thuộc vào sản phẩm và hồ sơ. Bạn nên kiểm tra trên ứng dụng "
        "hoặc liên hệ tổng đài để nhận thông tin cập nhật."
    ))
    assert reason == "ok"
    assert cleaned["mode"] == "assistant"
    assert "Không tự bịa" in cleaned["messages"][0]["content"]


@pytest.mark.parametrize("answer,reason", [
    ("Lãi suất hiện tại là 10% mỗi năm.", "answer_has_digits"),
    ("Bạn hãy gửi mã OTP để tôi kiểm tra giúp.", "requests_secret"),
    ("Phí trả nợ trước hạn được miễn hoàn toàn.", "volatile_fact_without_safety_cue"),
    ("Dư nợ hiện tại của bạn là khoản cần thanh toán.", "claims_personal_data"),
])
def test_qwen_cleaner_loai_du_lieu_nguy_hiem(answer, reason):
    cleaned, actual = validate_qwen_record(_qwen_assistant_record(answer))
    assert cleaned is None
    assert actual == reason


def test_qwen_cleaner_loai_router_du_khong_co_tool_call():
    cleaned, reason = validate_qwen_record(_qwen_assistant_record(
        "Tôi sẽ kiểm tra thông tin cho bạn.", mode="router"
    ))
    assert cleaned is None
    assert reason == "not_assistant_mode"


def test_qwen_gate_khong_cho_candidate_kem_base():
    baseline = {
        "usable_rate": 1.0, "semantic_rate": 1.0, "safe_rate": 1.0,
        "stop_rate": 1.0, "degenerate_rate": 0.0,
    }
    candidate = {**baseline, "semantic_rate": 0.9, "failures": []}
    passed, failures = compare_with_baseline(candidate, baseline)
    assert not passed
    assert any("semantic_rate" in failure for failure in failures)
