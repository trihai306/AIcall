import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from backend.models import db
from backend.services import answer_bank_learning as learning
from backend.services import knowledge_qa_service as qa


def _database(monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute(
        "CREATE TABLE hoi_dap (id TEXT PRIMARY KEY,cau_dem TEXT,cau_hoi TEXT NOT NULL,"
        "tra_loi TEXT NOT NULL,san_pham TEXT,bat INTEGER NOT NULL DEFAULT 1,"
        "created_at REAL,updated_at REAL)"
    )
    monkeypatch.setattr(db, "connection", lambda: conn)
    learning._prepared_conn = None
    learning._conn()
    return conn


def _root(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    root.mkdir()
    monkeypatch.setattr(learning, "_knowledge_root", lambda: root.resolve())
    return root


def test_first_scan_quarantines_legacy_but_preserves_manual(monkeypatch, tmp_path):
    conn = _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    product = root / "products"
    product.mkdir()
    path = product / "vay.md"
    path.write_text("Thu nhập tối thiểu là 10 triệu đồng.", encoding="utf-8")
    auto = qa.tien_to("products", "vay") + "old"
    staff = qa.tien_to("products", "vay", "nhan_vien") + "old"
    conn.executemany(
        "INSERT INTO hoi_dap VALUES (?,?,?,?,'',1,0,0)",
        [(auto, "", '["a"]', "cũ"), (staff, "", '["b"]', "cũ"),
         ("manual-row", "", '["c"]', "duyệt tay")],
    )

    docs, _ = learning.prepare_sources()
    assert len(docs) == 1
    assert conn.execute("SELECT bat FROM hoi_dap WHERE id=?", (auto,)).fetchone()[0] == 0
    assert conn.execute("SELECT bat FROM hoi_dap WHERE id=?", (staff,)).fetchone()[0] == 0
    assert conn.execute("SELECT bat FROM hoi_dap WHERE id='manual-row'").fetchone()[0] == 1

    item = {"cau_hoi": ["Cần thu nhập bao nhiêu?"],
            "tra_loi": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.",
            "evidence": "Thu nhập tối thiểu là 10 triệu đồng."}
    ids = learning._replace_document(docs[0], [item], [])
    assert learning.row_is_current(ids[0]) is True
    path.write_text("Thu nhập tối thiểu là 12 triệu đồng.", encoding="utf-8")
    learning.prepare_sources()
    assert learning.row_is_current(ids[0]) is False
    assert conn.execute("SELECT bat FROM hoi_dap WHERE id='manual-row'").fetchone()[0] == 1


def test_colliding_long_stems_get_distinct_source_ids(monkeypatch, tmp_path):
    conn = _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    folder = root / "products"
    folder.mkdir()
    stem = "san_pham_co_ten_rat_dai_de_kiem_tra_va_cham_"
    (folder / f"{stem}mot.md").write_text("Điều kiện một.", encoding="utf-8")
    (folder / f"{stem}hai.md").write_text("Điều kiện hai.", encoding="utf-8")
    docs, _ = learning.prepare_sources()
    assert len(docs) == 2
    assert learning._bank_prefix(docs[0], "auto") != learning._bank_prefix(docs[1], "auto")
    first_id = learning._replace_document(docs[0], [{
        "cau_hoi": ["Một?"], "tra_loi": "Dạ điều kiện một ạ.", "evidence": "Điều kiện một."
    }], [])[0]
    second_id = learning._replace_document(docs[1], [{
        "cau_hoi": ["Hai?"], "tra_loi": "Dạ điều kiện hai ạ.", "evidence": "Điều kiện hai."
    }], [])[0]
    assert first_id != second_id
    learning._replace_document(docs[0], [{
        "cau_hoi": ["Một mới?"], "tra_loi": "Dạ điều kiện một ạ.", "evidence": "Điều kiện một."
    }], [])
    assert conn.execute("SELECT COUNT(*) FROM hoi_dap WHERE id=?", (second_id,)).fetchone()[0] == 1


def test_privacy_and_history_query_only_ended_user(monkeypatch):
    conn = _database(monkeypatch)
    conn.executescript(
        "CREATE TABLE call_sessions(session_id TEXT PRIMARY KEY,status TEXT,product TEXT,"
        "customer_name TEXT,phone TEXT);"
        "CREATE TABLE conversation_turns(session_id TEXT,turn_index INTEGER,role TEXT,"
        "content TEXT,recorded_at REAL);"
    )
    conn.executemany("INSERT INTO call_sessions VALUES (?,?,?,?,?)", [
        ("ended", "ended", "vay", "Nguyễn Văn A", "0912345678"),
        ("active", "active", "vay", "B", "0987654321"),
    ])
    conn.executemany("INSERT INTO conversation_turns VALUES (?,?,?,?,?)", [
        ("ended", 0, "user", "Nhà tôi ở 12 Nguyễn Trãi, số tài khoản 1234 5678 9012", 1),
        ("ended", 1, "assistant", "Câu trả lời cũ không được học", 2),
        ("active", 0, "user", "Lượt chưa kết thúc", 3),
    ])
    rows = learning._history_candidates()
    assert len(rows) == 1
    assert rows[0]["session_id"] == "ended"
    assert "Nguyễn Trãi" not in rows[0]["text"]
    assert "1234" not in rows[0]["text"]


def test_qualitative_contradiction_is_rejected():
    source = "Khách hàng cần có thu nhập ít nhất 10 triệu đồng mỗi tháng."
    item, why = learning._validate_item({
        "questions": ["Có cần thu nhập không?"],
        "answer": "Dạ anh chị không cần chứng minh thu nhập ạ.",
        "evidence": source,
    }, source, 1)
    assert item is None
    assert "đảo nghĩa" in why


@pytest.mark.parametrize("examples", [None, [], ["Thu nhập bao nhiêu?"]])
def test_grounded_answer_accepts_zero_or_one_optional_example(examples):
    source = "Thu nhập tối thiểu là 10 triệu đồng."
    raw = {"answer": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.", "evidence": source}
    if examples is not None:
        raw["questions"] = examples
    item, why = learning._validate_item(raw, source, 4)
    assert not why and item["cau_hoi"] == (examples or [])


@pytest.mark.parametrize("override,reason", [
    ({"answer": "Dạ thu nhập tối thiểu là 999 triệu đồng ạ."}, "số"),
    ({"evidence": "Nguồn không chứa trích dẫn này."}, "trích dẫn"),
    ({"answer": "Dạ anh chị không cần chứng minh thu nhập ạ."}, "đảo nghĩa"),
    ({"questions": [17]}, "danh sách chuỗi"),
])
def test_answer_without_examples_keeps_evidence_numeric_and_polarity_gates(override, reason):
    source = "Anh chị cần thu nhập tối thiểu là 10 triệu đồng."
    raw = {"questions": [], "answer": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.",
           "evidence": source, **override}
    item, why = learning._validate_item(raw, source, 4)
    assert item is None and reason in why


def test_generation_deduplicates_answers_not_shared_or_missing_examples(monkeypatch, tmp_path):
    _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    source = "Thu nhập tối thiểu là 10 triệu đồng. Cần giấy tờ định danh."
    (root / "vay.md").write_text(source, encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    raw = [
        {"questions": [], "answer": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.", "evidence": source},
        {"questions": ["Điều kiện là gì?"], "answer": "Dạ anh chị cần giấy tờ định danh ạ.", "evidence": source},
        {"questions": ["Điều kiện là gì?"], "answer": "Dạ thu nhập tối thiểu là 10 triệu đồng và cần giấy tờ định danh ạ.", "evidence": source},
        {"questions": ["Thu nhập?"], "answer": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.", "evidence": source},
    ]

    async def chat(prompt, predict=1800):
        if "Kiểm tra từng item" in prompt:
            return json.dumps([{"index": i, "grounded": True} for i in range(4)])
        assert "TÙY CHỌN" in prompt and "Không cố tạo đủ số lượng" in prompt
        return json.dumps(raw, ensure_ascii=False)

    async def direct(coro, *args, **kwargs):
        return await coro

    monkeypatch.setattr(learning, "_chat", chat)
    monkeypatch.setattr(learning, "_guarded", direct)
    rows, reasons = asyncio.run(learning.generate_document(doc, 4, 4))
    assert len(rows) == 3 and rows[0]["cau_hoi"] == []
    assert rows[1]["cau_hoi"] == rows[2]["cau_hoi"] == ["Điều kiện là gì?"]
    assert reasons == {"trùng đáp án đã có": 1}


def test_fixed_questions_keep_coverage_and_semantic_gate_without_generated_examples(monkeypatch, tmp_path):
    _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    source = "Thu nhập tối thiểu là 10 triệu đồng."
    (root / "vay.md").write_text(source, encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    fixed = ["Thu nhập tối thiểu?", "Cần thu nhập bao nhiêu?", "Có cần giấy tờ gì?"]

    async def chat(prompt, predict=1800):
        if "Kiểm tra từng item" in prompt:
            payload = json.loads(prompt.split("ITEMS:\n", 1)[1].split("\nTÀI LIỆU:", 1)[0])
            assert [item["required_question"] for item in payload] == fixed
            return '[{"index":0,"grounded":true},{"index":1,"grounded":true},{"index":2,"grounded":false}]'
        return json.dumps([{"request_index": i, "questions": [],
                            "answer": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.",
                            "evidence": source} for i in range(3)], ensure_ascii=False)

    async def direct(coro, *args, **kwargs):
        return await coro

    monkeypatch.setattr(learning, "_chat", chat)
    monkeypatch.setattr(learning, "_guarded", direct)
    rows, reasons = asyncio.run(learning.generate_document(doc, 3, 4, fixed))
    assert len(rows) == 1 and rows[0]["cau_hoi"] == fixed[:2]
    assert reasons["Qwen xác minh ngữ nghĩa không đạt"] == 1


def test_semantic_verifier_rejects_unsupported_unconditional_answer_without_examples(monkeypatch):
    source = "Khoản vay chỉ áp dụng khi hồ sơ được ngân hàng phê duyệt."
    item = {"cau_hoi": [], "tra_loi": "Dạ anh chị được nhận khoản vay ngay ạ.", "evidence": source}

    async def chat(prompt, predict=1800):
        assert "vô điều kiện" in prompt and item["tra_loi"] in prompt and source in prompt
        assert '"questions": []' in prompt
        return '[{"index":0,"grounded":false}]'

    async def direct(coro, *args, **kwargs):
        return await coro

    monkeypatch.setattr(learning, "_chat", chat)
    monkeypatch.setattr(learning, "_guarded", direct)
    assert asyncio.run(learning._verify_items([item], source)) == []


def test_answer_policy_version_invalidates_ready_source_and_old_checkpoints(monkeypatch, tmp_path):
    conn = _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    source = "Thu nhập tối thiểu là 10 triệu đồng."
    (root / "vay.md").write_text(source, encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    item = {"cau_hoi": [], "tra_loi": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.", "evidence": source}
    ids = learning._store_items(doc, [item], "auto", replace=False)
    with monkeypatch.context() as old:
        old.setattr(learning, "_BUILDER_VERSION", 1)
        learning.prepare_sources()
        old_hash = conn.execute("SELECT config_hash FROM answer_bank_sources").fetchone()[0]
    conn.execute("UPDATE answer_bank_sources SET status='ready'")
    learning._save_staged_batch(doc, "auto", 0, [item])
    learning.prepare_sources()
    row = conn.execute("SELECT status,config_hash FROM answer_bank_sources").fetchone()
    assert row[0] == "pending" and row[1] != old_hash
    assert conn.execute("SELECT COUNT(*) FROM answer_bank_staging").fetchone()[0] == 0
    assert learning.row_is_current(ids[0])
    # Direct callers must not reuse a pre-policy key, either.
    learning._save_staged_batch(doc, "auto", 0, [item])
    calls = []

    async def chat(prompt, predict=1800):
        calls.append(prompt)
        return '[{"index":0,"grounded":true}]' if "Kiểm tra từng item" in prompt else json.dumps([item])

    async def direct(coro, *args, **kwargs):
        return await coro

    monkeypatch.setattr(learning, "_chat", chat)
    monkeypatch.setattr(learning, "_guarded", direct)
    rows, _ = asyncio.run(learning.generate_document(doc, 1, 4, stage_key="auto"))
    assert rows == [item] and len(calls) == 2


def test_generation_covers_each_chunk_and_semantic_verifier(monkeypatch, tmp_path):
    chunks = ["Điều kiện A áp dụng.", "Điều kiện B áp dụng.", "Điều kiện C áp dụng."]
    monkeypatch.setattr(learning, "cat_manh", lambda _text: chunks)
    prompts = []

    async def chat(prompt, predict=1800):
        prompts.append(prompt)
        if "Kiểm tra từng item" in prompt:
            return '[{"index":0,"grounded":true}]'
        source = next(chunk for chunk in chunks if chunk in prompt)
        return ('[{"questions":["Hỏi ' + source.split()[2] + '?"],"answer":"Dạ ' + source[:-1].lower() +
                ' ạ.","evidence":"' + source + '"}]')

    async def direct(coro, _timeout, **_kwargs):
        return await coro

    monkeypatch.setattr(learning, "_chat", chat)
    monkeypatch.setattr(learning, "_guarded", direct)
    doc = learning.Document(tmp_path / "x.md", "faq/x.md", "faq", "x",
                            "\n".join(chunks), learning._hash("\n".join(chunks)))
    result, _ = asyncio.run(learning.generate_document(doc, 3, 1))
    assert len(result) == 3
    generation_prompts = [p for p in prompts if "Kiểm tra từng item" not in p]
    assert all(any(chunk in prompt for prompt in generation_prompts) for chunk in chunks)


def test_config_hash_ignores_enable_and_history_toggle():
    base = {"enabled": True, "questions_per_document": 120,
            "variants_per_answer": 4, "learn_history": True}
    toggled = {**base, "enabled": False, "learn_history": False}
    assert learning._config_hash(base, "qwen3.5:9b") == learning._config_hash(toggled, "qwen3.5:9b")


def test_staged_batches_resume_without_repeating_qwen(monkeypatch, tmp_path):
    _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    folder = root / "faq"
    folder.mkdir()
    path = folder / "phi.md"
    text = "Phí A áp dụng.\nPhí B áp dụng."
    path.write_text(text, encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    monkeypatch.setattr(learning, "cat_manh", lambda _text: ["Phí A áp dụng.", "Phí B áp dụng."])
    calls = []

    async def chat(prompt, predict=1800):
        calls.append(prompt)
        if "Kiểm tra từng item" in prompt:
            return '[{"index":0,"grounded":true}]'
        source = "Phí A áp dụng." if "Phí A áp dụng." in prompt else "Phí B áp dụng."
        return ('[{"questions":["' + source.split()[1] + ' là gì?"],'
                '"answer":"Dạ có ' + source[:-1].lower() + ' ạ.","evidence":"' + source + '"}]')

    async def direct(coro, _timeout, **_kwargs):
        return await coro

    monkeypatch.setattr(learning, "_chat", chat)
    monkeypatch.setattr(learning, "_guarded", direct)
    first = asyncio.run(learning.generate_document(doc, 2, 1, stage_key="auto"))[0]
    first_calls = len(calls)
    second = asyncio.run(learning.generate_document(doc, 2, 1, stage_key="auto"))[0]
    assert first == second
    assert len(calls) == first_calls


def test_memory_activation_fails_closed_if_source_changes(monkeypatch, tmp_path):
    _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    folder = root / "faq"
    folder.mkdir()
    path = folder / "x.md"
    path.write_text("Điều kiện cũ.", encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    path.write_text("Điều kiện mới.", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Tài liệu đổi"):
        learning._store_items(doc, [{"cau_hoi": ["Hỏi?"], "tra_loi": "Dạ đáp ạ.",
                                     "evidence": "Điều kiện cũ."}], "memory", replace=False)


def test_config_growth_keeps_current_bank_until_atomic_replacement(monkeypatch, tmp_path):
    conn = _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    folder = root / "faq"
    folder.mkdir()
    (folder / "x.md").write_text("Phí hiện tại là 10 nghìn đồng.", encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    row_id = learning._replace_document(doc, [{
        "cau_hoi": ["Phí bao nhiêu?"], "tra_loi": "Dạ phí là 10 nghìn đồng ạ.",
        "evidence": "Phí hiện tại là 10 nghìn đồng.",
    }], [])[0]
    conn.execute("UPDATE answer_bank_config SET questions_per_document=200")
    learning.prepare_sources()
    assert conn.execute("SELECT bat FROM hoi_dap WHERE id=?", (row_id,)).fetchone()[0] == 1
    assert learning.row_is_current(row_id) is True
    assert conn.execute("SELECT status FROM answer_bank_sources").fetchone()[0] == "pending"


def test_all_document_failures_leave_job_error_and_manual_retry_is_allowed(monkeypatch, tmp_path):
    conn = _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    folder = root / "faq"
    folder.mkdir()
    (folder / "x.md").write_text("Nguồn.", encoding="utf-8")
    learning.prepare_sources()
    conn.execute("UPDATE answer_bank_config SET learn_history=0")
    worker = learning.AnswerBankLearning()

    async def no_wait():
        return None

    async def fail(_doc, _cfg):
        raise RuntimeError("model not found")

    monkeypatch.setattr(worker, "_wait_idle", no_wait)
    monkeypatch.setattr(worker, "_build_document", fail)
    asyncio.run(worker._run_once(False))
    assert worker.trang_thai()["job"]["status"] == "error"
    assert "model not found" in worker.trang_thai()["job"]["error"]
    conn.execute("UPDATE answer_bank_sources SET attempts=3,status='error'")
    # An explicit build (force=True) retries exhausted transient failures.
    asyncio.run(worker._run_once(False, force=True))
    assert "model not found" in worker.trang_thai()["job"]["error"]


def test_voice_refresh_skips_ready_current_file(monkeypatch, tmp_path):
    conn = _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    folder = root / "faq"
    folder.mkdir()
    (folder / "x.md").write_text("Nguồn.", encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    row_id = learning._replace_document(doc, [{
        "cau_hoi": ["Hỏi?"], "tra_loi": "Dạ nguồn ạ.", "evidence": "Nguồn."
    }], [])[0]
    conn.execute("UPDATE answer_bank_entries SET voice_ready=1,voice_fingerprint='fp' "
                 "WHERE hoi_dap_id=?", (row_id,))
    wav = tmp_path / "ready.wav"
    wav.write_bytes(b"RIFF")

    class TTS:
        _is_loaded = True

        @staticmethod
        def default_voice_name():
            return "voice"

        @staticmethod
        def _van_tay_filler(_text, _voice):
            return "fp"

    worker = learning.AnswerBankLearning()
    worker._state = type("State", (), {"tts": TTS()})()
    from backend.services.tieng_san import kho_tieng_san
    monkeypatch.setattr(kho_tieng_san, "_duong_dan", lambda *_args: wav)
    calls = []

    async def voice_rows(ids):
        calls.append(ids)

    monkeypatch.setattr(worker, "_voice_rows", voice_rows)
    asyncio.run(worker._refresh_stale_voices())
    assert calls == []


def test_manual_build_resumes_after_customer_pause_when_auto_disabled(monkeypatch):
    conn = _database(monkeypatch)
    conn.execute("UPDATE answer_bank_config SET enabled=0")
    worker = learning.AnswerBankLearning()
    calls = []

    async def run_once(full, *, force=False):
        calls.append((full, force))
        if len(calls) == 1:
            # Simulate the next scheduled scan without waiting ten seconds.
            worker._wake.set()
            raise learning.PausedForCustomer("Nhường tài nguyên cho khách")
        raise asyncio.CancelledError

    monkeypatch.setattr(worker, "_run_once", run_once)
    worker.request_build(full_rebuild=True)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(worker._loop())

    assert calls == [(True, True), (False, True)]


def test_partial_staff_rebuild_keeps_previous_questions(monkeypatch, tmp_path):
    _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    folder = root / "faq"
    folder.mkdir()
    (folder / "x.md").write_text("Điều kiện hiện tại đã được xác minh.", encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    first = {"cau_hoi": ["Điều kiện là gì?"], "tra_loi": "Dạ theo điều kiện ạ.",
             "evidence": doc.text}
    second = {**first, "cau_hoi": ["Cần giấy tờ nào?"]}
    learning._replace_document(doc, [], [first, second])
    before = learning._staff_questions(doc)

    async def partial(_doc, _count, _variants, fixed_questions=None, **_kwargs):
        return ([first], {})

    monkeypatch.setattr(learning, "generate_document", partial)
    with pytest.raises(RuntimeError, match="đầy đủ"):
        asyncio.run(learning.AnswerBankLearning()._build_document(doc, {
            "questions_per_document": 12, "variants_per_answer": 1,
        }))
    assert learning._staff_questions(doc) == before


def test_voice_builder_prepares_standalone_and_filler_continuation(monkeypatch, tmp_path):
    conn = _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    folder = root / "faq"
    folder.mkdir()
    (folder / "x.md").write_text("Điều kiện hiện tại đã được xác minh.", encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    text = "Dạ điều kiện hiện tại đã được xác minh ạ."
    row_id = learning._replace_document(doc, [{
        "cau_hoi": ["Điều kiện là gì?"], "tra_loi": text, "evidence": doc.text,
    }], [])[0]
    tts = type("TTS", (), {
        "_is_loaded": True,
        "default_voice_name": lambda self: "voice",
        "_van_tay_filler": lambda self, text, voice: learning._hash(text),
    })()
    worker = learning.AnswerBankLearning()
    worker._state = type("State", (), {"tts": tts})()
    calls = []
    from backend.services.tieng_san import kho_tieng_san

    async def build(_tts, key, spoken, voice):
        calls.append((key, spoken))
        return b"RIFF"

    async def guarded(coro, *_args, **_kwargs):
        return await coro

    async def idle():
        return None

    monkeypatch.setattr(kho_tieng_san, "dung_mot", build)
    monkeypatch.setattr(learning, "_guarded", guarded)
    monkeypatch.setattr(worker, "_wait_idle", idle)
    asyncio.run(worker._voice_rows([row_id]))

    assert calls == [(f"hd_{row_id}", text),
                     (f"hd_{row_id}_noi_dem", text.removeprefix("Dạ "))]
    assert conn.execute("SELECT voice_ready FROM answer_bank_entries WHERE hoi_dap_id=?",
                        (row_id,)).fetchone()[0] == 1


def test_voice_readiness_requires_continuation_file(monkeypatch, tmp_path):
    from backend.services.tieng_san import kho_tieng_san

    class TTS:
        @staticmethod
        def _van_tay_filler(text, _voice):
            return learning._hash(text)

    monkeypatch.setattr(kho_tieng_san, "_duong_dan",
                        lambda _voice, key, _fingerprint: tmp_path / (key + ".wav"))
    (tmp_path / "hd_row.wav").write_bytes(b"RIFF")
    assert not learning._voice_files_ready(TTS(), "row", "Dạ thông tin đúng ạ.", "voice")
    (tmp_path / "hd_row_noi_dem.wav").write_bytes(b"RIFF")
    assert learning._voice_files_ready(TTS(), "row", "Dạ thông tin đúng ạ.", "voice")


def test_generic_provenance_uses_default_scenario_bank_and_named_sources_stay_scoped(monkeypatch):
    conn = _database(monkeypatch)
    monkeypatch.setattr(learning.settings, "bank_name", "Ngân hàng ABC")
    conn.execute("CREATE TABLE scenarios (org_name TEXT,direction TEXT,is_default INTEGER,created_at REAL)")
    conn.executemany("INSERT INTO scenarios VALUES (?,?,?,?)", [
        ("Ngân hàng ABC", "outbound", 0, 1),
        ("Ngân hàng Quân đội", "both", 1, 2),
    ])
    sources = ["products/the.md", "faq/phi.md", "policies/a.md", "policy/a.md",
               "chinh_sach/a.md", "quy_dinh/a.md", "global/a.md", "common/a.md", "shared/a.md",
               "shinhan/the.md", "vietcombank/the.md"]
    conn.executemany(
        "INSERT INTO hoi_dap VALUES (?, '', '[\"Phí?\"]', 'Dạ theo biểu phí ạ.', '',1,0,0)",
        [(str(index),) for index, _ in enumerate(sources)],
    )
    conn.executemany(
        "INSERT INTO answer_bank_entries(hoi_dap_id,source_path,source_hash,origin,evidence,created_at) "
        "VALUES (?,?,'hash','auto','Bằng chứng.',0)",
        [(str(index), source) for index, source in enumerate(sources)],
    )
    snapshot = learning.active_provenance()
    assert all(snapshot[str(index)]["bank_scope"] == "Ngân hàng Quân đội" for index in range(9))
    assert snapshot["9"]["bank_scope"] == "shinhan"
    assert snapshot["10"]["bank_scope"] == "vietcombank"
    from backend.services.answer_bank_selector import _bank_scope_exclusions
    bank = {key: {"id": key} for key in snapshot}
    assert _bank_scope_exclusions("Phí?", "", "Ngân hàng Quân đội", bank, snapshot) == frozenset({"9", "10"})
    assert _bank_scope_exclusions("Phí?", "", "Shinhan Bank", bank, snapshot) == frozenset(set(bank) - {"9"})
    # This is a cached snapshot: changing the default does not mutate it.
    conn.execute("UPDATE scenarios SET org_name='Ngân hàng mới' WHERE is_default=1")
    assert snapshot["0"]["bank_scope"] == "Ngân hàng Quân đội"
    assert learning.active_provenance()["0"]["bank_scope"] == "Ngân hàng mới"


def test_generic_provenance_falls_back_only_when_scenario_missing_or_empty(monkeypatch):
    conn = _database(monkeypatch)
    monkeypatch.setattr(learning.settings, "bank_name", "Ngân hàng ABC")
    rows = [("auto", "faq/a.md", "hash", "auto", "Nguồn.", 1)]
    assert learning._provenance_rows(rows)["auto"]["bank_scope"] == "Ngân hàng ABC"
    conn.execute("CREATE TABLE scenarios (org_name TEXT,direction TEXT,is_default INTEGER,created_at REAL)")
    conn.execute("INSERT INTO scenarios VALUES ('', 'outbound',1,0)")
    assert learning._provenance_rows(rows)["auto"]["bank_scope"] == "Ngân hàng ABC"
    conn.execute("UPDATE scenarios SET org_name='Ngân hàng Quân đội',is_default=0")
    assert learning._provenance_rows(rows)["auto"]["bank_scope"] == "Ngân hàng Quân đội"


def _doc(rel: str, text: str) -> "learning.Document":
    return learning.Document(Path(rel), rel, str(Path(rel).parent), Path(rel).stem,
                             text, learning._hash(text))


def test_history_mapping_shows_content_and_rejects_wrong_product(monkeypatch):
    card = _doc("shinhan/consumer_credit_terms.md",
                "# Shinhan Bank — consumer_credit_terms_2025\n\nNguồn PDF chính thức: https://x\n"
                "SHA-256 PDF: abc\n\n## cash_advance_interest\n\n"
                "Giao dịch ứng trước tiền mặt bằng thẻ tín dụng không áp dụng thời gian miễn lãi.")
    loan = _doc("products/vay_tin_chap.md", "# Vay tín chấp\n\nLãi suất vay tín chấp từ 7.9%/năm.")
    profile = learning._doc_profile(card)
    assert "ứng trước tiền mặt bằng thẻ tín dụng" in profile
    assert "cash_advance_interest" in profile and "https" not in profile and "SHA" not in profile

    texts = ["lãi vay tín chấp nhiêu em", "cho hỏi lãi suất vay tín chấp", "vay tín chấp thế nào",
             "ứng tiền mặt thẻ có miễn lãi không", "lãi bao nhiêu"]
    rows = [{"session_id": "s", "turn_index": i, "text": texts[i],
             "product": "vay tín chấp" if i == 4 else ""} for i in range(5)]
    seen = {}

    async def fake_chat(prompt, predict=1800):
        seen["prompt"] = prompt
        return json.dumps([
            {"index": 0, "user": rows[0]["text"], "intent": "lãi suất vay tín chấp bao nhiêu", "source": card.rel},
            {"index": 1, "user": rows[1]["text"], "intent": "lãi suất vay tín chấp bao nhiêu", "source": loan.rel},
            {"index": 2, "user": rows[2]["text"], "intent": "câu hỏi chung về vay tín chấp", "source": loan.rel},
            {"index": 3, "user": rows[3]["text"], "intent": "ứng tiền mặt bằng thẻ tín dụng có miễn lãi không",
             "source": card.rel},
            {"index": 4, "user": rows[4]["text"], "intent": "lãi suất bao nhiêu", "source": card.rel},
        ], ensure_ascii=False)

    async def passthrough(coro, timeout, **_):
        return await coro

    monkeypatch.setattr(learning, "_chat", fake_chat)
    monkeypatch.setattr(learning, "_guarded", passthrough)
    mapped = asyncio.run(learning._map_history(rows, [card, loan]))
    assert "ứng trước tiền mặt" in seen["prompt"]
    assert "\"intent\":\"câu hỏi chung\"" not in seen["prompt"]
    assert [m["source"] for m in mapped] == ["", loan.rel, "", card.rel, ""]


@pytest.mark.parametrize("answer", [
    "Dạ, tài liệu chỉ nêu về giao dịch ứng trước tiền mặt, không có thông tin về lãi suất vay tín chấp ạ.",
    "Dạ, tài liệu hiện tại chưa đề cập cụ thể đến mức phí thường niên của thẻ ạ.",
    "Dạ, em xin lỗi nhưng tài liệu không cung cấp thông tin cụ thể về hạn mức ạ.",
])
def test_refusal_answer_is_not_stored_even_with_real_quote(answer):
    source = "Giao dịch ứng trước tiền mặt bằng thẻ tín dụng không áp dụng thời gian miễn lãi."
    item, why = learning._validate_item(
        {"questions": ["lãi suất vay tín chấp bao nhiêu"], "answer": answer,
         "evidence": source}, source, 4)
    assert item is None and "từ chối" in why


def test_plain_negative_fact_is_still_accepted():
    source = "Gửi tiết kiệm không yêu cầu chứng minh thu nhập."
    item, _ = learning._validate_item(
        {"questions": [], "answer": "Dạ, gửi tiết kiệm không yêu cầu chứng minh thu nhập ạ.",
         "evidence": source}, source, 4)
    assert item is not None



def test_history_mapping_follows_echoed_text_not_shifted_index(monkeypatch):
    loan = _doc("products/vay_tin_chap.md", "# Vay tín chấp\n\nLãi suất vay tín chấp từ 7.9%/năm.")
    rows = [{"session_id": "s", "turn_index": i, "text": t, "product": "vay tín chấp"}
            for i, t in enumerate(["chị hỏi chút mà lãi hơi cao nhỉ em",
                                   "lãi suất vay tín chấp bên em bao nhiêu một năm",
                                   "ngôn ngành năm mươi triệu"])]

    async def fake_chat(prompt, predict=1800):
        # Qwen lệch một hàng: ý định của lượt 1 gắn index 0; lượt 2 chép sai hẳn.
        return json.dumps([
            {"index": 0, "user": rows[1]["text"], "intent": "lãi suất vay tín chấp bao nhiêu một năm",
             "source": loan.rel},
            {"index": 1, "user": "bảo hiểm nhân thọ đóng bao nhiêu", "intent": "bảo hiểm nhân thọ",
             "source": ""},
        ], ensure_ascii=False)

    async def passthrough(coro, timeout, **_):
        return await coro

    monkeypatch.setattr(learning, "_chat", fake_chat)
    monkeypatch.setattr(learning, "_guarded", passthrough)
    mapped = asyncio.run(learning._map_history(rows, [loan]))
    assert [(m["turn_index"], m["source"]) for m in mapped] == [(1, loan.rel)]


def test_bad_json_is_retried_once(monkeypatch):
    replies = iter(['[{"a":1 "b":2}]', '[{"a":1}]'])

    async def fake_chat(prompt, predict=1800):
        return next(replies)

    async def passthrough(coro, timeout, **_):
        return await coro

    monkeypatch.setattr(learning, "_chat", fake_chat)
    monkeypatch.setattr(learning, "_guarded", passthrough)
    assert asyncio.run(learning._chat_json("p", 100)) == [{"a": 1}]


def test_exclusion_list_stays_within_context_budget():
    # 300 đáp án đã có từng đẩy prompt quá num_ctx 4096 (02-10-2026).
    many = [{"cau_hoi": ["CAUHOI_MAU_%d" % i],
             "tra_loi": "Dạ đây là một câu trả lời đã có trong kho, số %d, dài vừa phải ạ." % i}
            for i in range(300)]
    prompt = learning._generation_prompt("Nguồn ngắn.", 8, 1, None, many)
    assert len(prompt) < 6000
    assert "số 299" in prompt and "số 0," not in prompt  # giữ đáp án GẦN NHẤT
    assert "CAUHOI_MAU" not in prompt


def test_truncated_json_keeps_complete_items():
    cut = '[{"request_index":0,"answer":"Dạ A ạ.","evidence":"A"}, {"request_index":1,"answer":"Dạ B ạ.","evidence":"B"}, {"request_index":2,"answer":"Dạ C dang dở'
    assert learning._extract_json(cut) == [
        {"request_index": 0, "answer": "Dạ A ạ.", "evidence": "A"},
        {"request_index": 1, "answer": "Dạ B ạ.", "evidence": "B"}]
    with pytest.raises(ValueError):
        learning._extract_json('[{"answer": "cụt')


def test_legit_dont_provide_info_line_is_not_a_refusal():
    source = "Khách từ chối cung cấp thông tin: anh/chị có thể không cung cấp thông tin nếu chưa sẵn sàng."
    item, why = learning._validate_item(
        {"questions": ["tôi không muốn cung cấp thông tin"],
         "answer": "Dạ, anh/chị có thể không cung cấp thông tin nếu chưa sẵn sàng ạ.",
         "evidence": "anh/chị có thể không cung cấp thông tin nếu chưa sẵn sàng"}, source, 4)
    assert item is not None, why


def test_staged_items_are_rechecked_and_off_topic_questions_dropped(monkeypatch, tmp_path):
    _database(monkeypatch)
    root = _root(monkeypatch, tmp_path)
    (root / "shinhan").mkdir()
    path = root / "shinhan" / "credit.md"
    path.write_text("Ứng trước tiền mặt bằng thẻ tín dụng không áp dụng thời gian miễn lãi.", encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    staged = [
        {"cau_hoi": ["thẻ tín dụng miễn lãi bao nhiêu ngày", "ứng tiền mặt có miễn lãi không"],
         "tra_loi": "Dạ ứng trước tiền mặt bằng thẻ không được miễn lãi ạ.", "evidence": "x"},
        {"cau_hoi": ["lãi vay tín chấp"],
         "tra_loi": "Dạ tài liệu chỉ nêu ứng tiền mặt, không có thông tin lãi vay ạ.", "evidence": "x"},
    ]
    monkeypatch.setattr(learning, "_staged_batch", lambda *_a: staged)
    items, why = asyncio.run(learning.generate_document(doc, 8, 2, stage_key="auto"))
    assert [i["cau_hoi"] for i in items] == [["ứng tiền mặt có miễn lãi không"]]
    assert why["câu trả lời là từ chối, không có căn cứ trong nguồn"] == 1


def test_history_question_already_in_bank_is_not_generated_again(monkeypatch, tmp_path):
    conn = _database(monkeypatch)
    conn.execute("CREATE TABLE call_sessions (session_id TEXT, status TEXT, product TEXT, customer_name TEXT, phone TEXT)")
    conn.execute("CREATE TABLE conversation_turns (session_id TEXT, turn_index INTEGER, role TEXT, content TEXT, recorded_at REAL)")
    root = _root(monkeypatch, tmp_path)
    (root / "products").mkdir()
    (root / "products" / "vay.md").write_text("Lãi suất vay tín chấp từ 7.9%/năm.", encoding="utf-8")
    doc = learning.prepare_sources()[0][0]
    learning._store_items(doc, [{"cau_hoi": ["lãi suất vay tín chấp bao nhiêu"],
                                 "tra_loi": f"Dạ lãi suất vay tín chấp {cach} 7.9%/năm ạ.",
                                 "evidence": "Lãi suất vay tín chấp từ 7.9%/năm."}
                                for cach in ("từ", "là từ", "hiện từ", "bên em từ")],
                          "memory", replace=False)
    rows = [{"session_id": "s1", "turn_index": 0, "text": "lãi vay tín chấp nhiêu", "product": ""}]
    monkeypatch.setattr(learning, "_history_candidates", lambda: rows)

    async def mapped(batch, docs):
        return [{**batch[0], "intent": "lãi suất vay tín chấp là bao nhiêu", "source": doc.rel}]

    async def must_not_generate(*_a, **_k):
        raise AssertionError("câu hỏi đã đủ cách nói thì không sinh thêm đáp án")

    monkeypatch.setattr(learning, "_map_history", mapped)
    monkeypatch.setattr(learning, "generate_document", must_not_generate)
    worker = learning.AnswerBankLearning()
    assert asyncio.run(worker._learn_history([doc], {"variants_per_answer": 1})) == []
    assert conn.execute("SELECT status FROM answer_bank_history").fetchone()[0] == "learned"
    assert conn.execute("SELECT COUNT(*) FROM hoi_dap").fetchone()[0] == learning._VARIANTS_PER_QUESTION


@pytest.mark.parametrize("answer, ok", [
    ("Dạ, anh chị thực hiện sau khi phê duyệt trong vòng 24 giờ ạ.", False),
    ("Dạ, anh chị thực hiện mở thẻ sẽ được miễn phí năm đầu ạ.", False),
    ("Dạ, anh chị thực hiện giao dịch ứng trước tiền mặt sẽ không được miễn lãi ạ.", True),
    ("Dạ, anh chị mở thẻ sẽ được miễn phí năm đầu ạ.", True),
])
def test_filler_thuc_hien_is_rejected_but_real_usage_kept(answer, ok):
    source = "Giải ngân trong vòng 24 giờ. Mở thẻ miễn phí năm đầu. Giao dịch ứng trước tiền mặt không được miễn lãi."
    item, why = learning._validate_item({"questions": [], "answer": answer, "evidence": "Mở thẻ miễn phí năm đầu."}, source, 4)
    assert (item is not None) is ok, why
    if not ok:
        assert "thực hiện" in why
    assert 'Không chèn cụm "anh chị thực hiện"' in learning._generation_prompt("x", 1, 1)
