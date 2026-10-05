"""Q&A sinh từ tài liệu phải giữ riêng bộ tự động và câu nhân viên bổ sung."""

import asyncio
import sqlite3

import pytest

from backend.models import db
from backend.services import knowledge_qa_service as qa
from backend.services import answer_bank_learning as learning


def _db_tam(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE hoi_dap ("
        "id TEXT PRIMARY KEY, cau_dem TEXT, cau_hoi TEXT NOT NULL, "
        "tra_loi TEXT NOT NULL, san_pham TEXT, bat INTEGER NOT NULL DEFAULT 1, "
        "created_at REAL, updated_at REAL)"
    )
    monkeypatch.setattr(db, "connection", lambda: conn)
    return conn


def test_cau_nhan_vien_bo_sung_khong_xoa_bo_qwen(monkeypatch):
    _db_tam(monkeypatch)
    qa.luu("products", "vay_tin_chap", [{
        "cau_hoi": ["Lãi suất bao nhiêu?"],
        "tra_loi": "Dạ lãi suất theo tài liệu là 10% một năm ạ.",
    }])

    qa.luu("products", "vay_tin_chap", [{
        "cau_hoi": ["Khách hỏi tất toán trước hạn thì sao?"],
        "tra_loi": "Dạ phí tất toán thực hiện theo biểu phí trong tài liệu ạ.",
    }], loai="nhan_vien", gop_cu=True)

    rows = qa.danh_sach("products", "vay_tin_chap")
    assert {r["nguon"] for r in rows} == {"tu_dong", "nhan_vien"}
    assert len(rows) == 2


def test_nhap_them_cau_nhan_vien_giu_cau_da_hoc(monkeypatch):
    _db_tam(monkeypatch)
    qa.luu("faq", "goi_cuoc", [{
        "cau_hoi": ["Có mất phí không?"], "tra_loi": "Dạ có phí theo tài liệu ạ."
    }], loai="nhan_vien", gop_cu=True)
    qa.luu("faq", "goi_cuoc", [{
        "cau_hoi": ["Bao giờ thu phí?"], "tra_loi": "Dạ thời điểm thu phí theo tài liệu ạ."
    }], loai="nhan_vien", gop_cu=True)

    cau = qa.cau_hoi_nhan_vien_da_luu("faq", "goi_cuoc")
    assert cau == ["Có mất phí không?", "Bao giờ thu phí?"]


def test_tat_bo_cu_van_giu_cau_nhan_vien_de_sinh_lai(monkeypatch):
    _db_tam(monkeypatch)
    qa.luu("faq", "phi", [{
        "cau_hoi": ["Phí bao nhiêu?"], "tra_loi": "Dạ theo biểu phí ạ."
    }], loai="nhan_vien")

    assert qa._tat_cua_tai_lieu("faq", "phi") == 1
    assert qa.danh_sach("faq", "phi")[0]["bat"] is False
    assert qa.cau_hoi_nhan_vien_da_luu("faq", "phi") == ["Phí bao nhiêu?"]


def _source(monkeypatch, tmp_path, *, stem="the_tin_dung", group="products"):
    conn = _db_tam(monkeypatch)
    root = tmp_path / "knowledge"
    folder = root / group
    folder.mkdir(parents=True)
    path = folder / f"{stem}.md"
    path.write_text("Phí thường niên theo biểu phí. Hạn mức theo tài liệu.", encoding="utf-8")
    monkeypatch.setattr(learning, "_knowledge_root", lambda: root.resolve())
    monkeypatch.setattr(learning, "_prepared_conn", None)
    docs, _ = learning.prepare_sources()

    async def runtime(*, build_voice=True):
        return {"so_dong": conn.execute("SELECT COUNT(*) FROM hoi_dap WHERE bat=1").fetchone()[0],
                "voice": None}

    async def voice(_ids):
        pass

    monkeypatch.setattr(qa, "nap_lai_duong_goi", runtime)
    monkeypatch.setattr(learning.AnswerBankLearning, "_voice_rows", lambda self, ids: voice(ids))
    return conn, root, docs[0]


def _item(question, doc):
    return {"cau_hoi": [question], "tra_loi": "Dạ phí thường niên theo biểu phí ạ.",
            "evidence": doc.text.split(" Hạn")[0]}


def test_tao_va_luu_cau_nhan_vien_khong_de_bo_tu_dong(monkeypatch, tmp_path):
    conn, _, doc = _source(monkeypatch, tmp_path)
    auto_id = learning._replace_document(doc, [_item("Hạn mức bao nhiêu?", doc)], [])[0]
    learning._store_items(doc, [_item("Có mất phí không?", doc)], "staff", replace=False)
    built_voice_ids = []

    async def generated(actual, count, variants, fixed_questions=None):
        assert actual == doc
        assert set(fixed_questions) == {"Có mất phí không?", "Có phí thường niên không?"}
        return [_item(q, doc) for q in fixed_questions], {"hop_le": 2}

    async def voice(ids):
        built_voice_ids.extend(ids)

    monkeypatch.setattr(learning, "generate_document", generated)
    monkeypatch.setattr(learning.AnswerBankLearning, "_voice_rows", lambda self, ids: voice(ids))
    kq = asyncio.run(qa.tao_va_luu(
        doc.group, doc.stem, doc.text, 1, ["Có phí thường niên không?"],
    ))
    assert kq["ok"] is True
    assert {r["nguon"] for r in kq["items"]} == {"tu_dong", "nhan_vien"}
    assert conn.execute("SELECT bat FROM hoi_dap WHERE id=?", (auto_id,)).fetchone()[0] == 1
    assert set(qa.cau_hoi_nhan_vien_da_luu(doc.group, doc.stem)) == {
        "Có mất phí không?", "Có phí thường niên không?"}
    assert len(built_voice_ids) == 2
    for row in kq["items"]:
        assert learning.row_is_current(row["id"])
        assert row["id"].startswith(("ab_auto_", "ab_staff_"))
    assert {r[0] for r in conn.execute("SELECT origin FROM answer_bank_entries")} == {"auto", "staff"}


def test_listing_and_delete_use_exact_provenance_identity(monkeypatch, tmp_path):
    stem = "san_pham_co_ten_rat_dai_de_kiem_tra_va_cham_"
    conn, root, doc = _source(monkeypatch, tmp_path, stem=stem + "mot")
    second_path = root / "products" / f"{stem}hai.md"
    second_path.write_text(doc.text, encoding="utf-8")
    docs, _ = learning.prepare_sources()
    other = next(d for d in docs if d.stem == stem + "hai")
    ids = []
    for origin in ("auto", "staff", "memory"):
        ids.extend(learning._store_items(doc, [_item(origin + "?", doc)], origin, replace=False))
    other_id = learning._store_items(other, [_item("Khác?", other)], "auto", replace=False)[0]
    assert {r["id"] for r in qa.danh_sach(doc.group, doc.stem)} == set(ids)
    assert {r["nguon"] for r in qa.danh_sach(doc.group, doc.stem)} == {
        "tu_dong", "nhan_vien", "lich_su"}
    assert qa._tat_cua_tai_lieu(doc.group, doc.stem) == 3
    assert conn.execute("SELECT bat FROM hoi_dap WHERE id=?", (other_id,)).fetchone()[0] == 1
    assert qa.cau_hoi_nhan_vien_da_luu(doc.group, doc.stem) == ["staff?"]
    assert qa._xoa_rows_cua_tai_lieu(doc.group, doc.stem) == 3
    assert conn.execute("SELECT COUNT(*) FROM answer_bank_entries").fetchone()[0] == 1
    assert qa.danh_sach(other.group, other.stem)[0]["id"] == other_id


def test_manual_generation_keeps_staff_history_after_source_edit(monkeypatch, tmp_path):
    _, _, doc = _source(monkeypatch, tmp_path)
    learning._replace_document(doc, [_item("Auto?", doc)], [_item("Phí?", doc)])
    doc.path.write_text("Phí thường niên theo biểu phí mới.", encoding="utf-8")
    calls = []

    async def generated(actual, count, variants, fixed_questions=None):
        calls.append(fixed_questions)
        question = fixed_questions[0] if fixed_questions else "Auto mới?"
        return [_item(question, actual)], {}

    monkeypatch.setattr(learning, "generate_document", generated)
    result = asyncio.run(qa.tao_va_luu(doc.group, doc.stem, doc.path.read_text(encoding="utf-8"), 120))
    assert result["ok"]
    assert calls == [None, ["Phí?"]]
    assert qa.cau_hoi_nhan_vien_da_luu(doc.group, doc.stem) == ["Phí?"]
    assert all(learning.row_is_current(row["id"]) for row in result["items"])


def test_manual_generation_rejects_changed_source_before_commit(monkeypatch, tmp_path):
    conn, _, doc = _source(monkeypatch, tmp_path)
    old_id = learning._replace_document(doc, [_item("Auto?", doc)], [])[0]

    async def generated(actual, count, variants, fixed_questions=None):
        doc.path.write_text("Nội dung mới.", encoding="utf-8")
        return [_item("Mới?", actual)], {}

    monkeypatch.setattr(learning, "generate_document", generated)
    with pytest.raises(RuntimeError, match="Tài liệu đổi"):
        asyncio.run(qa.tao_va_luu(doc.group, doc.stem, doc.text, 1))
    assert conn.execute("SELECT id FROM hoi_dap").fetchall() == [(old_id,)]
    assert learning.row_is_current(old_id) is False


def test_partial_staff_reply_does_not_erase_prior_questions(monkeypatch, tmp_path):
    conn, _, doc = _source(monkeypatch, tmp_path)
    old_id = learning._store_items(doc, [_item("Cũ?", doc)], "staff", replace=False)[0]

    async def generated(actual, count, variants, fixed_questions=None):
        return [_item("Mới?", actual)], {}

    monkeypatch.setattr(learning, "generate_document", generated)
    result = asyncio.run(qa.tao_va_luu(doc.group, doc.stem, doc.text, 1, ["Mới?"]))
    assert "error" in result
    assert conn.execute("SELECT id FROM hoi_dap").fetchall() == [(old_id,)]
    assert qa.cau_hoi_nhan_vien_da_luu(doc.group, doc.stem) == ["Cũ?"]


def test_explicit_manual_generation_ignores_cancelled_disabled_automation(monkeypatch, tmp_path):
    conn, _, doc = _source(monkeypatch, tmp_path)
    conn.execute("UPDATE answer_bank_config SET enabled=0,variants_per_answer=1")
    cancelled = asyncio.Event()
    cancelled.set()
    monkeypatch.setattr(learning.bo_hoc_tra_loi, "_cancel", cancelled)
    from backend.core import service_priority
    monkeypatch.setattr(service_priority, "background_ai_busy_reason", lambda: "")

    async def chat(prompt, predict=1800):
        # Suspend so _guarded actually evaluates the cancellation flag.
        await asyncio.sleep(0.01)
        if "Kiểm tra từng item" in prompt:
            return '[{"index":0,"grounded":true}]'
        return ('[{"questions":["Có phí thường niên không?"],'
                '"answer":"Dạ phí thường niên theo biểu phí ạ.",'
                '"evidence":"Phí thường niên theo biểu phí."}]')

    monkeypatch.setattr(learning, "_chat", chat)
    result = asyncio.run(qa.tao_va_luu(doc.group, doc.stem, doc.text, 1))
    assert result.get("ok"), result
    assert learning.row_is_current(result["items"][0]["id"])
    assert learning.bo_hoc_tra_loi._cancel.is_set()
    assert qa._manual_bank_worker.get() is None


def test_two_concurrent_manual_additions_preserve_both_staff_questions(monkeypatch, tmp_path):
    _, _, doc = _source(monkeypatch, tmp_path)
    learning._replace_document(doc, [_item("Auto?", doc)], [_item("Gốc?", doc)])

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def generated(actual, count, variants, fixed_questions=None):
            calls.append(list(fixed_questions))
            if len(calls) == 1:
                entered.set()
                await release.wait()
            return [_item(q, actual) for q in fixed_questions], {}

        monkeypatch.setattr(learning, "generate_document", generated)
        first = asyncio.create_task(qa.tao_va_luu(doc.group, doc.stem, doc.text, 1, ["Một?"]))
        await asyncio.wait_for(entered.wait(), 1)
        second = asyncio.create_task(qa.tao_va_luu(doc.group, doc.stem, doc.text, 1, ["Hai?"]))
        await asyncio.sleep(0)
        assert len(calls) == 1
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), 2)
        assert all(result.get("ok") for result in results)
        assert set(calls[1]) == {"Gốc?", "Một?", "Hai?"}

    asyncio.run(scenario())
    assert set(qa.cau_hoi_nhan_vien_da_luu(doc.group, doc.stem)) == {"Gốc?", "Một?", "Hai?"}


@pytest.mark.parametrize("background_first", [False, True])
def test_background_and_manual_generation_preserve_added_staff(monkeypatch, tmp_path, background_first):
    _, _, doc = _source(monkeypatch, tmp_path)
    learning._replace_document(doc, [_item("Auto?", doc)], [_item("Gốc?", doc)])

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def generated(actual, count, variants, fixed_questions=None, stage_key=""):
            calls.append(list(fixed_questions) if fixed_questions else None)
            if len(calls) == 1:
                entered.set()
                await release.wait()
            return [_item(q, actual) for q in (fixed_questions or ["Auto mới?"])], {}

        monkeypatch.setattr(learning, "generate_document", generated)
        worker = learning.AnswerBankLearning()

        def manual():
            return qa.tao_va_luu(doc.group, doc.stem, doc.text, 1, ["Bổ sung?"])

        def background():
            return worker._build_document(doc, learning._config())

        first = asyncio.create_task(background() if background_first else manual())
        await asyncio.wait_for(entered.wait(), 1)
        second = asyncio.create_task(manual() if background_first else background())
        await asyncio.sleep(0)
        assert len(calls) == 1
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), 2)
        manual_result = results[1 if background_first else 0]
        assert manual_result["ok"]
        if not background_first:
            assert set(calls[-1]) == {"Gốc?", "Bổ sung?"}

    asyncio.run(scenario())
    assert set(qa.cau_hoi_nhan_vien_da_luu(doc.group, doc.stem)) == {"Gốc?", "Bổ sung?"}
    assert all(learning.row_is_current(row["id"]) for row in qa.danh_sach(doc.group, doc.stem))


@pytest.mark.parametrize("failure", [learning.PausedForCustomer, learning.BuildCancelled, asyncio.CancelledError])
def test_source_operation_lock_is_released_after_interruption(monkeypatch, tmp_path, failure):
    _, _, doc = _source(monkeypatch, tmp_path)

    async def scenario():
        calls = 0

        async def generated(actual, count, variants, fixed_questions=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise failure()
            return [_item(q, actual) for q in fixed_questions], {}

        monkeypatch.setattr(learning, "generate_document", generated)
        with pytest.raises(failure):
            await qa.tao_va_luu(doc.group, doc.stem, doc.text, 1, ["Đầu?"])
        assert learning.source_operation_lock(doc).locked() is False
        assert qa._manual_bank_worker.get() is None
        result = await asyncio.wait_for(
            qa.tao_va_luu(doc.group, doc.stem, doc.text, 1, ["Sau?"]), 1)
        assert result["ok"]

    asyncio.run(scenario())
    assert qa.cau_hoi_nhan_vien_da_luu(doc.group, doc.stem) == ["Sau?"]
