import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import knowledge
from backend.models import db
from backend.services import answer_bank_editor as editor
from backend.services import answer_bank_learning as learning
from backend.services import knowledge_qa_service as qa

_REAL_RUNTIME_RELOAD = qa.nap_lai_duong_goi


@pytest.fixture
def bank(monkeypatch, tmp_path):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("CREATE TABLE hoi_dap (id TEXT PRIMARY KEY,cau_dem TEXT,cau_hoi TEXT NOT NULL,"
                 "tra_loi TEXT NOT NULL,san_pham TEXT,bat INTEGER NOT NULL DEFAULT 1,"
                 "created_at REAL,updated_at REAL)")
    monkeypatch.setattr(db, "connection", lambda: conn)
    monkeypatch.setattr(learning, "_prepared_conn", None)
    root = tmp_path / "knowledge"
    folder = root / "products"
    folder.mkdir(parents=True)
    path = folder / "vay.md"
    path.write_text("Thu nhập tối thiểu là 10 triệu đồng. Cần giấy tờ định danh.", encoding="utf-8")
    (folder / "the.md").write_text("Phí thẻ theo biểu phí.", encoding="utf-8")
    monkeypatch.setattr(learning, "_knowledge_root", lambda: root.resolve())
    monkeypatch.setattr(knowledge, "GOC", root)
    monkeypatch.setattr(learning.settings, "tieng_san_bat", False)
    published = []

    async def reload(*, build_voice=True):
        assert not build_voice
        published.append(True)
        return {}

    monkeypatch.setattr(qa, "nap_lai_duong_goi", reload)
    docs, _ = learning.prepare_sources()
    doc = next(d for d in docs if d.stem == "vay")
    app = FastAPI()
    app.include_router(knowledge.router)
    return conn, doc, path, TestClient(app), published


def _body(**kw):
    return {"nhom": "products", "ten": "vay", "cau_hoi": ["Cần giấy gì?"],
            "tra_loi": " Nội dung do nhân viên tự duyệt,\n  giữ khoảng cách. ", "bat": True, **kw}


def test_manual_save_and_edit_verbatim_no_model(bank, monkeypatch):
    conn, doc, path, client, published = bank

    async def forbidden(*args, **kwargs):
        raise AssertionError("Manual text must never be checked by Qwen")

    monkeypatch.setattr(learning, "generate_document", forbidden)
    monkeypatch.setattr(learning, "_verify_items", forbidden)
    added = client.post("/api/knowledge/hoi-dap", json=_body()).json()
    row = added["item"]
    assert row["id"].startswith("ab_manual_")
    assert row["nguon"] == "nhap_tay" and row["san_pham"] == "vay"
    assert row["tra_loi"] == "Nội dung do nhân viên tự duyệt,\n  giữ khoảng cách."
    assert learning.row_is_current(row["id"])
    edit = client.patch("/api/knowledge/hoi-dap/" + row["id"], json=_body(
        expected_updated_at=row["updated_at"], tra_loi="Nội dung mới", bat=False)).json()
    assert edit["ok"] and edit["voice"]["status"] == "disabled"
    assert not edit["item"]["bat"] and edit["item"]["tra_loi"] == "Nội dung mới"
    assert not learning.row_is_current(row["id"])
    entry = conn.execute("SELECT source_path,source_hash,origin FROM answer_bank_entries").fetchone()
    assert entry == (doc.rel, doc.fingerprint, "manual")
    assert len(published) == 2


def test_conflict_and_wrong_source_are_not_mutated(bank):
    conn, doc, path, client, _ = bank
    row = client.post("/api/knowledge/hoi-dap", json=_body()).json()["item"]
    url = "/api/knowledge/hoi-dap/" + row["id"]
    assert client.patch(url, json=_body(expected_updated_at=row["updated_at"] - 1)).status_code == 409
    assert client.patch(url, json=_body(ten="the", expected_updated_at=row["updated_at"])).status_code == 404
    assert client.patch("/api/knowledge/hoi-dap/missing", json=_body(expected_updated_at=0)).status_code == 404
    assert conn.execute("SELECT tra_loi,updated_at FROM hoi_dap").fetchone() == (row["tra_loi"], row["updated_at"])


@pytest.mark.parametrize("bad", [{"cau_hoi": [" "]}, {"cau_hoi": [12]},
                                  {"cau_hoi": "hỏi"}, {"tra_loi": "  "}])
def test_empty_input_rejected_without_save(bank, bad):
    conn, _, _, client, _ = bank
    assert client.post("/api/knowledge/hoi-dap", json=_body(**bad)).status_code in {400, 422}
    assert conn.execute("SELECT COUNT(*) FROM hoi_dap").fetchone()[0] == 0


def test_manual_answer_without_examples_create_edit_and_rebuild_protection(bank, monkeypatch):
    conn, doc, _, client, _ = bank

    async def forbidden(*args, **kwargs):
        raise AssertionError("Manual answers must never be rewritten by Qwen")

    monkeypatch.setattr(learning, "_chat", forbidden)
    body = _body(tra_loi=" Dạ lời nhân viên duyệt,\n  giữ nguyên ạ. ")
    body.pop("cau_hoi")
    saved = client.post("/api/knowledge/hoi-dap", json=body).json()["item"]
    assert saved["cau_hoi"] == [] and saved["tra_loi"] == body["tra_loi"].strip()
    edited = client.patch("/api/knowledge/hoi-dap/" + saved["id"], json={
        **body, "expected_updated_at": saved["updated_at"], "bat": False,
    }).json()["item"]
    assert edited["cau_hoi"] == [] and not edited["bat"]
    duplicate = {"cau_hoi": ["Hỏi mẫu mới?"], "tra_loi": edited["tra_loi"], "evidence": doc.text}
    assert learning._replace_document(doc, [duplicate], []) == []
    assert learning._store_items(doc, [duplicate], "auto", replace=False) == []
    assert qa.danh_sach("products", "vay") == [edited]
    assert conn.execute("SELECT origin FROM answer_bank_entries").fetchone()[0] == "manual"


@pytest.mark.parametrize("promoted", [False, True])
def test_legacy_edit_without_examples_fails_before_mutating_or_promoting(bank, promoted):
    conn, doc, _, client, _ = bank
    legacy_id = qa.tien_to("products", "vay", "auto") + "legacy"
    conn.execute("INSERT INTO hoi_dap VALUES (?, '', ?, 'Đáp án cũ', 'vay', 1, 0, 7)",
                 (legacy_id, '["Câu hỏi cũ?"]'))
    if promoted:
        conn.execute("INSERT INTO answer_bank_entries "
                     "(hoi_dap_id,source_path,source_hash,origin,created_at) VALUES (?,?,?,'manual',0)",
                     (legacy_id, doc.rel, doc.fingerprint))
    before = conn.execute("SELECT * FROM hoi_dap WHERE id=?", (legacy_id,)).fetchone()
    provenance_before = conn.execute("SELECT * FROM answer_bank_entries WHERE hoi_dap_id=?",
                                    (legacy_id,)).fetchone()
    response = client.patch("/api/knowledge/hoi-dap/" + legacy_id, json=_body(
        cau_hoi=[], tra_loi="Đáp án mới", expected_updated_at=7))
    assert response.status_code == 400 and "cần câu hỏi mẫu" in response.json()["detail"]
    assert conn.execute("SELECT * FROM hoi_dap WHERE id=?", (legacy_id,)).fetchone() == before
    assert conn.execute("SELECT * FROM answer_bank_entries WHERE hoi_dap_id=?",
                        (legacy_id,)).fetchone() == provenance_before


def test_append_accepts_distinct_answers_without_examples(bank, monkeypatch):
    _, doc, _, client, _ = bank
    manual = client.post("/api/knowledge/hoi-dap", json=_body(cau_hoi=[])).json()["item"]
    generated = [
        {"cau_hoi": [], "tra_loi": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.", "evidence": doc.text},
        {"cau_hoi": [], "tra_loi": "Dạ anh chị cần giấy tờ định danh ạ.", "evidence": doc.text},
    ]

    async def generate(*args, **kwargs):
        assert kwargs["existing_items"] == [manual]
        return generated, {}

    monkeypatch.setattr(learning, "generate_document", generate)
    result = client.post("/api/knowledge/tao-them-hoi-dap", json={
        "nhom": "products", "ten": "vay", "so_cau": 2,
    }).json()
    assert result["added"] == 2 and result["so_dong"] == 3
    assert all(row["cau_hoi"] == [] for row in result["items"])
    assert next(row for row in result["items"] if row["id"] == manual["id"]) == manual


def test_edit_generated_protects_id_questions_and_disabled_through_rebuild(bank):
    conn, doc, path, client, _ = bank
    item = {"cau_hoi": ["Cần giấy gì?"], "tra_loi": "Đáp án tự sinh cũ", "evidence": "Cần giấy tờ định danh."}
    original = learning._replace_document(doc, [item], [])[0]
    version = conn.execute("SELECT updated_at FROM hoi_dap WHERE id=?", (original,)).fetchone()[0]
    client.patch("/api/knowledge/hoi-dap/" + original,
                 json=_body(expected_updated_at=version, tra_loi="Nhân viên đã sửa", bat=False)).raise_for_status()
    learning.prepare_sources(full_rebuild=True)
    assert learning._replace_document(doc, [item, {**item, "tra_loi": "Trùng ý với ID mới"}], []) == []
    assert learning._store_items(doc, [item], "auto", replace=True) == []
    assert conn.execute("SELECT tra_loi,bat FROM hoi_dap WHERE id=?", (original,)).fetchone() == ("Nhân viên đã sửa", 0)
    assert conn.execute("SELECT origin FROM answer_bank_entries").fetchone()[0] == "manual"


def test_source_change_quarantines_manual_and_missing_provenance_fails_closed(bank):
    conn, doc, path, client, _ = bank
    row = client.post("/api/knowledge/hoi-dap", json=_body()).json()["item"]
    conn.execute("DELETE FROM answer_bank_entries WHERE hoi_dap_id=?", (row["id"],))
    assert not learning.row_is_current(row["id"])
    row = client.post("/api/knowledge/hoi-dap", json=_body()).json()["item"]
    path.write_text("Nguồn mới.", encoding="utf-8")
    learning.prepare_sources()
    assert not learning.row_is_current(row["id"])
    assert conn.execute("SELECT bat FROM hoi_dap WHERE id=?", (row["id"],)).fetchone()[0] == 0
    assert conn.execute("SELECT origin FROM answer_bank_entries WHERE hoi_dap_id=?", (row["id"],)).fetchone()[0] == "manual"


def test_append_deduplicates_answers_and_preserves_all_existing(bank, monkeypatch):
    conn, doc, path, client, _ = bank
    old = client.post("/api/knowledge/hoi-dap", json=_body(tra_loi="Đáp án nhân viên")).json()["item"]
    calls = []

    async def generate(doc, count, variants, **kwargs):
        calls.append((count, kwargs["existing_items"]))
        return [
            {"cau_hoi": old["cau_hoi"], "tra_loi": "Ý cũ", "evidence": doc.text},
            {"cau_hoi": ["Hỏi khác"], "tra_loi": "Đáp án nhân viên!", "evidence": doc.text},
            {"cau_hoi": ["Thu nhập?"], "tra_loi": "Thu nhập tối thiểu 10 triệu đồng", "evidence": doc.text},
            {"cau_hoi": ["Thu nhập!"], "tra_loi": "Một đáp án khác", "evidence": doc.text}], {}

    monkeypatch.setattr(learning, "generate_document", generate)
    result = client.post("/api/knowledge/tao-them-hoi-dap", json={"nhom": "products", "ten": "vay", "so_cau": 300}).json()
    assert result["ok"] and result["requested"] == 300 and result["added"] == 2
    assert result["so_dong"] == 3 and len(calls[0][1]) == 1
    assert next(r for r in result["items"] if r["id"] == old["id"]) == old
    repeated = client.post("/api/knowledge/tao-them-hoi-dap", json={"nhom": "products", "ten": "vay", "so_cau": 300}).json()
    assert repeated["added"] == 0 and repeated["message"]
    assert client.post("/api/knowledge/tao-them-hoi-dap", json={"nhom": "products", "ten": "vay", "so_cau": 301}).status_code == 422


def test_voice_invalidation_and_unchanged_text_preserves_fingerprint(bank):
    conn, doc, path, client, _ = bank
    row = client.post("/api/knowledge/hoi-dap", json=_body(tra_loi="Câu cũ")).json()["item"]
    conn.execute("UPDATE answer_bank_entries SET voice_ready=1,voice_fingerprint='old',voice_attempts=2")
    row = client.patch("/api/knowledge/hoi-dap/" + row["id"], json=_body(
        expected_updated_at=row["updated_at"], tra_loi="Câu cũ")).json()["item"]
    assert conn.execute("SELECT voice_ready,voice_fingerprint FROM answer_bank_entries").fetchone() == (1, "old")
    client.patch("/api/knowledge/hoi-dap/" + row["id"], json=_body(
        expected_updated_at=row["updated_at"], tra_loi="Câu mới")).raise_for_status()
    assert conn.execute("SELECT voice_ready,voice_fingerprint,voice_attempts FROM answer_bank_entries").fetchone() == (0, "", 0)


def test_actual_voice_readiness_requires_both_variants(bank, monkeypatch, tmp_path):
    conn, doc, path, client, _ = bank
    from backend.services.tieng_san import kho_tieng_san
    row = client.post("/api/knowledge/hoi-dap", json=_body(tra_loi="Dạ anh chị chuẩn bị giấy tờ ạ.")).json()["item"]
    tts = SimpleNamespace(default_voice_name=lambda: "test", _van_tay_filler=lambda text, voice: learning._hash(text))
    state = SimpleNamespace(tts=tts)
    monkeypatch.setattr(kho_tieng_san, "thu_muc", tmp_path / "wav")
    conn.execute("UPDATE answer_bank_entries SET voice_ready=1,voice_fingerprint=?", (learning._hash(row["tra_loi"]),))
    assert not learning.voice_is_ready(row["id"], row["tra_loi"], state)
    for key, spoken in learning._voice_variants(row["id"], row["tra_loi"]).items():
        wav = kho_tieng_san._duong_dan("test", key, learning._hash(spoken))
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(b"wav")
    assert learning.voice_is_ready(row["id"], row["tra_loi"], state)
    assert not learning.voice_is_ready(row["id"], "Đáp án mới", state)


def test_saved_success_when_voice_publication_fails(bank, monkeypatch):
    conn, doc, path, client, _ = bank
    state = SimpleNamespace(hoi_dap={}, hoi_dap_vector={}, hoi_dap_provenance={})
    monkeypatch.setattr(editor, "_state", lambda: state)

    async def broken(*args, **kwargs):
        raise RuntimeError("Embedding đang lỗi")

    monkeypatch.setattr(qa, "nap_lai_duong_goi", broken)
    result = client.post("/api/knowledge/hoi-dap", json=_body()).json()
    assert result["ok"] and result["voice"]["status"] == "error"
    assert conn.execute("SELECT COUNT(*) FROM hoi_dap").fetchone()[0] == 1


def test_voice_only_queue_is_isolated_and_retries_when_auto_disabled(bank, monkeypatch):
    conn, doc, path, client, _ = bank
    conn.execute("UPDATE answer_bank_config SET enabled=0")
    calls = []
    global_worker = learning.bo_hoc_tra_loi
    global_worker._cancel.set()

    async def voices(worker, **kwargs):
        assert kwargs == {"retry_failed": True}
        assert qa._manual_bank_worker.get() is worker and not worker._cancel.is_set()
        calls.append(True)

    async def no_sleep(*args):
        raise asyncio.CancelledError

    monkeypatch.setattr(learning.AnswerBankLearning, "_refresh_stale_voices", voices)
    monkeypatch.setattr(editor.asyncio, "sleep", no_sleep)
    try:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(editor._retry_voices(SimpleNamespace(
                hoi_dap={}, hoi_dap_vector={}, hoi_dap_provenance={})))
        assert calls == [True]
        assert global_worker._cancel.is_set()
    finally:
        global_worker._cancel.clear()


def test_selector_rejects_same_id_answer_edited_during_qwen_await(bank):
    import numpy as np
    from backend.services.answer_bank_selector import choose
    from backend.services.bang_hoi_dap import doc_dong

    conn, doc, path, client, _ = bank
    saved = client.post("/api/knowledge/hoi-dap", json=_body(
        cau_hoi=["thu nhập tối thiểu là bao nhiêu"], tra_loi="Thu nhập cũ")).json()["item"]
    captured = {r["id"]: r for r in doc_dong(conn)}

    class LLM:
        async def generate_simple(self, *args, **kwargs):
            result = await editor.save("products", "vay", saved["cau_hoi"], "Thu nhập mới", True,
                                       answer_id=saved["id"], expected_updated_at=saved["updated_at"])
            assert result["ok"]
            return '{"choice":"C1"}'

    async def select():
        return await choose(
            rag=SimpleNamespace(embed=lambda texts: np.array([[1.0, 0.0]], dtype=np.float32)),
            llm=LLM(), bank=captured,
            vector_bank={saved["id"]: np.array([[0.86, 0.510294]], dtype=np.float32)},
            # Câu KHÁC chữ với câu mẫu: trùng câu mẫu thì bộ chọn đọc thẳng,
            # không qua Qwen nên không có quãng chờ nào để sửa chen vào.
            question="lương cỡ nào thì đủ điều kiện", product="vay",
            bank_name=learning.settings.bank_name, provenance=learning.active_provenance(),
            is_current=learning.row_is_current)

    assert learning.row_is_current(saved["id"], snapshot=captured[saved["id"]])
    assert asyncio.run(select()) is None
    assert learning.row_is_current(saved["id"])
    assert not learning.row_is_current(saved["id"], snapshot=captured[saved["id"]])


def test_promoted_legacy_row_exact_source_beats_colliding_slug(bank):
    conn, doc, path, client, _ = bank
    # Two valid exact stems share the truncated legacy prefix.
    base = "san_pham_co_ten_rat_dai_de_kiem_tra_va_cham_"
    first, second = base + "mot", base + "hai"
    path.rename(path.parent / (first + ".md"))
    learning.prepare_sources()
    assert qa.tien_to("products", first) == qa.tien_to("products", second)
    legacy_id = qa.tien_to("products", first) + "legacy"
    conn.execute("INSERT INTO hoi_dap VALUES (?,'',?,?,?,1,0,1)",
                 (legacy_id, '["Cần giấy gì?"]', "Câu cũ", first))
    edited = client.patch("/api/knowledge/hoi-dap/" + legacy_id,
                          json=_body(ten=first, expected_updated_at=1, tra_loi="Nhân viên sửa")).json()
    assert edited["item"]["nguon"] == "nhap_tay"
    (path.parent / (second + ".md")).write_text("Nguồn khác.", encoding="utf-8")
    docs, _ = learning.prepare_sources()
    assert {d.stem for d in docs} >= {first, second}
    assert qa.danh_sach("products", second) == []
    assert qa._tat_cua_tai_lieu("products", second) == 0
    assert qa._xoa_rows_cua_tai_lieu("products", second) == 0
    assert learning.row_is_current(legacy_id)
    assert qa.danh_sach("products", first)[0]["nguon"] == "nhap_tay"


def test_unowned_legacy_collision_cannot_be_claimed_disabled_or_deleted(bank):
    conn, doc, path, client, _ = bank
    base = "san_pham_co_ten_rat_dai_de_kiem_tra_va_cham_"
    first, second = base + "mot", base + "hai"
    path.rename(path.parent / (first + ".md"))
    (path.parent / (second + ".md")).write_text("Nguồn khác.", encoding="utf-8")
    learning.prepare_sources()
    legacy_id = qa.tien_to("products", first) + "unknown"
    conn.execute("INSERT INTO hoi_dap VALUES (?,'',?,?,?,1,0,1)",
                 (legacy_id, '["Hỏi cũ?"]', "Đáp án cũ", ""))
    for stem in (first, second):
        response = client.patch("/api/knowledge/hoi-dap/" + legacy_id,
                                json=_body(ten=stem, expected_updated_at=1))
        assert response.status_code == 404 and "hãy thêm đáp án mới" in response.json()["detail"]
        assert qa.danh_sach("products", stem) == []
        assert qa._tat_cua_tai_lieu("products", stem) == 0
        assert qa._xoa_rows_cua_tai_lieu("products", stem) == 0
    assert conn.execute("SELECT tra_loi,bat,updated_at FROM hoi_dap WHERE id=?", (legacy_id,)).fetchone() == ("Đáp án cũ", 1, 1)
    assert conn.execute("SELECT COUNT(*) FROM answer_bank_entries").fetchone()[0] == 0


def test_additive_generator_excludes_existing_and_keeps_numeric_semantic_checks(bank, monkeypatch):
    _, doc, _, _, _ = bank
    existing = [{"cau_hoi": ["Điều kiện là gì?"], "tra_loi": "Dạ cần giấy tờ định danh ạ."}]
    prompts = []

    async def chat(prompt, predict=1800):
        prompts.append(prompt)
        if "Kiểm tra từng item" in prompt:
            return '[{"index":0,"grounded":true},{"index":1,"grounded":true}]'
        return json.dumps([
            {"questions": existing[0]["cau_hoi"], "answer": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.",
             "evidence": "Thu nhập tối thiểu là 10 triệu đồng."},
            {"questions": ["Cần định danh?"], "answer": existing[0]["tra_loi"],
             "evidence": "Cần giấy tờ định danh."},
            {"questions": [], "answer": "Dạ thu nhập tối thiểu là 10 triệu đồng ạ.",
             "evidence": "Thu nhập tối thiểu là 10 triệu đồng."},
            {"questions": ["Thu nhập tối thiểu khác?"], "answer": "Dạ thu nhập tối thiểu là 999 triệu đồng ạ.",
             "evidence": "Thu nhập tối thiểu là 10 triệu đồng."}], ensure_ascii=False)

    async def direct(coro, *args, **kwargs):
        return await coro

    monkeypatch.setattr(learning, "_chat", chat)
    monkeypatch.setattr(learning, "_guarded", direct)
    rows, reasons = asyncio.run(learning.generate_document(doc, 1, 1, existing_items=existing))
    assert len(rows) == 1 and "10 triệu" in rows[0]["tra_loi"]
    assert reasons["trùng đáp án đã có"] == 2
    assert sum(reasons.values()) == 3
    assert "ĐÃ CÓ TRONG KHO" in prompts[0] and existing[0]["tra_loi"] in prompts[0]
    assert "Kiểm tra từng item" in prompts[1]


def test_generation_uses_actual_runtime_selected_model(monkeypatch):
    from backend.main import app_state
    calls = []

    async def chat(**kwargs):
        calls.append(kwargs)
        return {"message": {"content": "[]"}}

    monkeypatch.setattr(app_state, "llm", SimpleNamespace(
        model="operator-selected-qwen", client=SimpleNamespace(chat=chat)))
    assert asyncio.run(learning._chat("prompt")) == "[]"
    assert calls[0]["model"] == "operator-selected-qwen"


def test_runtime_reuses_vectors_and_encodes_only_changed_retrieval_texts(bank, monkeypatch):
    import numpy as np
    from backend.main import app_state
    from backend.services.bang_hoi_dap import doc_dong, retrieval_texts, RETRIEVAL_LAYOUT_VERSION

    conn, _, _, client, _ = bank
    first = client.post("/api/knowledge/hoi-dap", json=_body()).json()["item"]
    second = client.post("/api/knowledge/hoi-dap", json=_body(cau_hoi=["Thu nhập?"])).json()["item"]
    rows = {r["id"]: r for r in doc_dong(conn)}
    old_vectors = {r["id"]: np.ones((len(retrieval_texts(r)), 3), dtype=np.float32) for r in rows.values()}
    calls = []

    def embed(texts):
        calls.append(list(texts))
        return np.ones((len(texts), 3), dtype=np.float32)

    rag = SimpleNamespace(embed=embed)
    monkeypatch.setattr(app_state, "rag", rag)
    monkeypatch.setattr(app_state, "hoi_dap", rows)
    monkeypatch.setattr(app_state, "hoi_dap_vector", old_vectors)
    monkeypatch.setattr(app_state, "hoi_dap_provenance", learning.active_provenance())
    monkeypatch.setattr(app_state, "_hoi_dap_vector_rag", rag, raising=False)
    monkeypatch.setattr(app_state, "_hoi_dap_vector_layout", RETRIEVAL_LAYOUT_VERSION, raising=False)
    monkeypatch.setattr(learning.settings, "embedding_device", "cpu")
    asyncio.run(_REAL_RUNTIME_RELOAD(build_voice=False))
    assert calls == []
    assert app_state.hoi_dap_vector[first["id"]] is old_vectors[first["id"]]
    conn.execute("UPDATE hoi_dap SET tra_loi='Đáp án đã sửa' WHERE id=?", (first["id"],))
    asyncio.run(_REAL_RUNTIME_RELOAD(build_voice=False))
    assert calls == [["Đáp án đã sửa"]]
    assert app_state.hoi_dap[first["id"]]["tra_loi"] == "Đáp án đã sửa"
    np.testing.assert_array_equal(app_state.hoi_dap_vector[first["id"]][0], old_vectors[first["id"]][0])
    conn.execute("UPDATE hoi_dap SET cau_hoi=? WHERE id=?", ('["Câu hỏi mới?"]', first["id"]))
    asyncio.run(_REAL_RUNTIME_RELOAD(build_voice=False))
    assert calls == [["Đáp án đã sửa"], ["Câu hỏi mới?"]]
    assert app_state.hoi_dap_vector[second["id"]] is old_vectors[second["id"]]


def test_cpu_embedding_keeps_loop_responsive_and_publishes_latest_db_snapshot(bank, monkeypatch):
    import threading
    import numpy as np
    from backend.main import app_state
    from backend.services.bang_hoi_dap import doc_dong

    conn, _, _, client, _ = bank
    saved = client.post("/api/knowledge/hoi-dap", json=_body()).json()["item"]
    started, release = threading.Event(), threading.Event()
    calls = []
    main_thread = threading.get_ident()

    def embed(texts):
        assert threading.get_ident() != main_thread
        calls.append(list(texts))
        if len(calls) == 1:
            started.set()
            assert release.wait(3)
        return np.ones((len(texts), 3), dtype=np.float32)

    rag = SimpleNamespace(embed=embed)
    monkeypatch.setattr(app_state, "rag", rag)
    monkeypatch.setattr(app_state, "hoi_dap", {})
    monkeypatch.setattr(app_state, "hoi_dap_vector", {})
    monkeypatch.setattr(app_state, "hoi_dap_provenance", {})
    monkeypatch.setattr(app_state, "_hoi_dap_vector_rag", rag, raising=False)
    monkeypatch.setattr(learning.settings, "embedding_device", "cpu")

    async def run():
        task = asyncio.create_task(_REAL_RUNTIME_RELOAD(build_voice=False))
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set() and not task.done()
        # A real save can commit while another document is encoding. The old
        # question vector must not be paired with this newer DB row at publish.
        conn.execute("UPDATE hoi_dap SET cau_hoi=?,tra_loi=? WHERE id=?",
                     ('["Câu hỏi mới nhất?"]', "Đáp án mới nhất", saved["id"]))
        release.set()
        await task

    try:
        asyncio.run(run())
    finally:
        release.set()
    assert calls == [saved["cau_hoi"] + [saved["tra_loi"]], ["Câu hỏi mới nhất?", "Đáp án mới nhất"]]
    assert app_state.hoi_dap[saved["id"]]["tra_loi"] == "Đáp án mới nhất"
    assert app_state.hoi_dap[saved["id"]]["cau_hoi"] == ["Câu hỏi mới nhất?"]


@pytest.mark.parametrize("invalidation", ["layout", "rag"])
def test_runtime_rebuilds_incompatible_cache_and_indexes_answer_only(bank, monkeypatch, invalidation):
    import numpy as np
    from backend.main import app_state
    from backend.core.startup import _nhung_bang_hoi_dap
    from backend.services.bang_hoi_dap import doc_dong, RETRIEVAL_LAYOUT_VERSION

    conn, _, _, client, _ = bank
    saved = client.post("/api/knowledge/hoi-dap", json=_body()).json()["item"]
    conn.execute("UPDATE hoi_dap SET cau_hoi='[]' WHERE id=?", (saved["id"],))
    conn.execute("INSERT INTO hoi_dap VALUES ('legacy','', '[\"Legacy example\"]', 'Legacy answer','',1,0,1)")
    rows = {row["id"]: row for row in doc_dong(conn)}
    calls = []

    def embed(texts):
        calls.append(list(texts))
        return np.ones((len(texts), 3), dtype=np.float32)

    rag = SimpleNamespace(embed=embed)
    monkeypatch.setattr(app_state, "rag", rag)
    monkeypatch.setattr(app_state, "hoi_dap", rows)
    monkeypatch.setattr(app_state, "hoi_dap_vector", {})
    monkeypatch.setattr(app_state, "hoi_dap_provenance", {})
    monkeypatch.setattr(app_state, "_hoi_dap_vector_rag", None, raising=False)
    monkeypatch.setattr(app_state, "_hoi_dap_vector_layout", None, raising=False)
    monkeypatch.setattr(learning.settings, "embedding_device", "cpu")
    asyncio.run(_nhung_bang_hoi_dap(app_state, list(rows.values())))
    startup_matrices = app_state.hoi_dap_vector
    calls.clear()
    asyncio.run(_REAL_RUNTIME_RELOAD(build_voice=False))
    assert calls == []
    assert all(app_state.hoi_dap_vector[key] is matrix for key, matrix in startup_matrices.items())
    if invalidation == "layout":
        app_state._hoi_dap_vector_layout = RETRIEVAL_LAYOUT_VERSION - 1
    else:
        app_state.rag = SimpleNamespace(embed=embed)
    asyncio.run(_REAL_RUNTIME_RELOAD(build_voice=False))
    assert calls == [[saved["tra_loi"], "Legacy example"]]
    assert app_state.hoi_dap_vector[saved["id"]].shape == (1, 3)
    assert app_state._hoi_dap_vector_rag is app_state.rag
    assert app_state._hoi_dap_vector_layout == RETRIEVAL_LAYOUT_VERSION


def test_cancelled_reload_holds_lock_until_native_cpu_encode_finishes(bank, monkeypatch):
    import threading
    import numpy as np
    from backend.main import app_state

    _, _, _, client, _ = bank
    client.post("/api/knowledge/hoi-dap", json=_body())
    started, release = threading.Event(), threading.Event()
    calls = []

    def embed(texts):
        calls.append(list(texts))
        started.set()
        assert release.wait(3)
        return np.ones((len(texts), 3), dtype=np.float32)

    monkeypatch.setattr(app_state, "rag", SimpleNamespace(embed=embed))
    monkeypatch.setattr(app_state, "hoi_dap", {})
    monkeypatch.setattr(app_state, "hoi_dap_vector", {})
    monkeypatch.setattr(app_state, "hoi_dap_provenance", {})
    monkeypatch.setattr(learning.settings, "embedding_device", "cpu")

    async def run():
        first = asyncio.create_task(_REAL_RUNTIME_RELOAD(build_voice=False))
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()
        first.cancel()
        second = asyncio.create_task(_REAL_RUNTIME_RELOAD(build_voice=False))
        await asyncio.sleep(0.01)
        first.cancel()
        await asyncio.sleep(0.03)
        assert len(calls) == 1 and not first.done() and not second.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        await second
        assert len(calls) == 2

    try:
        asyncio.run(run())
    finally:
        release.set()


def test_idle_voice_retry_never_rebuilds_runtime_vectors(bank, monkeypatch):
    calls = []
    state = SimpleNamespace(hoi_dap={}, hoi_dap_vector={}, hoi_dap_provenance={})
    old_bank, old_vectors, old_provenance = state.hoi_dap, state.hoi_dap_vector, state.hoi_dap_provenance

    async def publication(*args, **kwargs):
        raise AssertionError("An idle voice worker must not rebuild the runtime bank")

    async def voices(*args, **kwargs):
        calls.append(True)

    async def stop(*args):
        raise asyncio.CancelledError

    monkeypatch.setattr(qa, "nap_lai_duong_goi", publication)
    monkeypatch.setattr(learning.AnswerBankLearning, "_refresh_stale_voices", voices)
    monkeypatch.setattr(editor.asyncio, "sleep", stop)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(editor._retry_voices(state))
    assert calls == [True]
    assert (state.hoi_dap is old_bank and state.hoi_dap_vector is old_vectors
            and state.hoi_dap_provenance is old_provenance)


def test_voice_metadata_refresh_reuses_bank_and_vectors(bank):
    conn, _, _, client, _ = bank
    row = client.post("/api/knowledge/hoi-dap", json=_body()).json()["item"]
    state = SimpleNamespace(hoi_dap={row["id"]: row}, hoi_dap_vector={row["id"]: object()},
                            hoi_dap_provenance=learning.active_provenance())
    bank_ref, vectors_ref = state.hoi_dap, state.hoi_dap_vector
    conn.execute("UPDATE answer_bank_entries SET voice_ready=1 WHERE hoi_dap_id=?", (row["id"],))
    assert qa.nap_lai_provenance_voice(state)
    assert state.hoi_dap is bank_ref and state.hoi_dap_vector is vectors_ref
    assert state.hoi_dap_provenance[row["id"]]["voice_ready"]
    assert not qa.nap_lai_provenance_voice(state)


def test_voice_metadata_refresh_skips_bank_with_committed_unpublished_edit(bank):
    conn, _, _, client, _ = bank
    row = client.post("/api/knowledge/hoi-dap", json=_body()).json()["item"]
    state = SimpleNamespace(hoi_dap={row["id"]: row}, hoi_dap_vector={row["id"]: object()},
                            hoi_dap_provenance=learning.active_provenance())
    previous = state.hoi_dap_provenance
    conn.execute("UPDATE hoi_dap SET tra_loi='Đáp án đã đổi' WHERE id=?", (row["id"],))
    conn.execute("UPDATE answer_bank_entries SET voice_ready=1 WHERE hoi_dap_id=?", (row["id"],))
    assert not qa.nap_lai_provenance_voice(state)
    assert state.hoi_dap_provenance is previous


def test_voice_retry_recovers_failed_runtime_publication_without_auto_rebuild(bank, monkeypatch):
    calls = []
    state = SimpleNamespace(hoi_dap={}, hoi_dap_vector={}, hoi_dap_provenance={},
                            _answer_bank_publish_retry=True)

    async def publication(*args, **kwargs):
        calls.append("publish")

    async def voices(*args, **kwargs):
        calls.append("voice")

    async def stop(*args):
        raise asyncio.CancelledError

    monkeypatch.setattr(qa, "nap_lai_duong_goi", publication)
    monkeypatch.setattr(learning.AnswerBankLearning, "_refresh_stale_voices", voices)
    monkeypatch.setattr(editor.asyncio, "sleep", stop)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(editor._retry_voices(state))
    assert calls == ["publish", "voice"] and not state._answer_bank_publish_retry
