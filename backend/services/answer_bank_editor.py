"""Operator-authoritative edits and additive, source-grounded generation."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from backend.config import settings
from backend.models import db
from backend.services import answer_bank_learning as learning
from backend.services import knowledge_qa_service as qa

logger = logging.getLogger(__name__)


class EditorError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


async def _document(group: str, stem: str):
    docs, logs = learning.prepare_sources()
    if any(log.startswith("Đã tắt các đáp án") for log in logs):
        # Quarantine must reach the call snapshot before model work can await.
        await qa.nap_lai_duong_goi(build_voice=False)
    doc = next((d for d in docs if d.group == group and d.stem == stem), None)
    if doc is None:
        raise EditorError("Không có tài liệu nguồn hợp lệ trong knowledge", 404)
    return doc


def _state():
    from backend.main import app_state
    return learning.bo_hoc_tra_loi._state or app_state


def start_voice_retry(state=None):
    """Retry persisted voices after saves and restart, even with auto disabled.

    This isolated worker prepares WAVs only. It never rebuilds source answers
    and does not inherit the automatic builder's cancel flag.
    """
    if not settings.tieng_san_bat:
        return
    loop = asyncio.get_running_loop()
    task = getattr(loop, "_answer_bank_editor_voice_task", None)
    if task is None or task.done():
        task = loop.create_task(_retry_voices(state or _state()), name="answer-bank-editor-voice")
        setattr(loop, "_answer_bank_editor_voice_task", task)


async def _retry_voices(state):
    worker = learning.AnswerBankLearning()
    worker._state = state
    token = qa._manual_bank_worker.set(worker)
    try:
        while True:
            try:
                if getattr(state, "_answer_bank_publish_retry", False):
                    await qa.nap_lai_duong_goi(build_voice=False)
                    state._answer_bank_publish_retry = False
                await worker._refresh_stale_voices(retry_failed=True)
                qa.nap_lai_provenance_voice(state)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Chưa dựng được voice đã lưu; sẽ thử lại")
            await asyncio.sleep(max(10.0, float(settings.answer_bank_scan_interval_s)))
    finally:
        qa._manual_bank_worker.reset(token)


async def _publish(ids: list[str]) -> dict:
    try:
        await qa.nap_lai_duong_goi(build_voice=False)
        _state()._answer_bank_publish_retry = False
        start_voice_retry()
        if not settings.tieng_san_bat:
            return {"status": "disabled"}
        conn = learning._conn()
        active = conn.execute(
            "SELECT id,tra_loi FROM hoi_dap WHERE bat=1 AND id IN (" +
            ",".join("?" for _ in ids) + ")", ids).fetchall() if ids else []
        if ids and not active:
            return {"status": "disabled"}
        return {"status": "ready" if all(learning.voice_is_ready(r[0], r[1])
                                          for r in active) else "queued"}
    except Exception as exc:
        # A committed edit must be reported as saved. Fail closed if embedding
        # failed, and let the voice-only retry republish the bank later.
        state = _state()
        state._answer_bank_publish_retry = True
        state.hoi_dap, state.hoi_dap_vector, state.hoi_dap_provenance = (
            {k: v for k, v in (getattr(state, "hoi_dap", {}) or {}).items() if k not in ids},
            {k: v for k, v in (getattr(state, "hoi_dap_vector", {}) or {}).items() if k not in ids},
            {k: v for k, v in (getattr(state, "hoi_dap_provenance", {}) or {}).items() if k not in ids})
        try:
            start_voice_retry(state)
        except Exception:
            logger.exception("Không thể xếp lịch dựng voice")
        return {"status": "error", "error": f"Đã lưu; chưa cập nhật voice: {exc}"}


async def save(group: str, stem: str, questions: list[str], answer: str, enabled: bool,
               *, answer_id: str | None = None, expected_updated_at: float | None = None) -> dict:
    if not isinstance(questions, list) or any(
            not isinstance(q, str) or not q.strip() for q in questions):
        raise EditorError("Câu hỏi mẫu phải là chuỗi không rỗng")
    if not isinstance(answer, str) or not answer.strip():
        raise EditorError("Câu trả lời không được rỗng")
    questions, answer = [q.strip() for q in questions], answer.strip()
    doc = await _document(group, stem)
    async with learning.source_operation_lock(doc):
        conn = learning._conn()
        with db.write_lock, conn:
            if not learning._source_is_current(doc):
                raise EditorError("Tài liệu đã đổi; hãy tải lại trước khi lưu", 409)
            old = None
            if answer_id:
                owner = conn.execute("SELECT source_path FROM answer_bank_entries "
                                     "WHERE hoi_dap_id=?", (answer_id,)).fetchone()
                if not owner and not qa._legacy_source_is_unique(conn, group, stem):
                    raise EditorError("Không xác định được tài liệu sở hữu đáp án cũ; "
                                      "hãy thêm đáp án mới cho đúng tài liệu", 404)
                legacy = not owner and answer_id in {r["id"] for r in qa.danh_sach(group, stem)}
                if (owner and owner[0] != doc.rel) or (not owner and not legacy):
                    raise EditorError("Không có đáp án thuộc tài liệu này", 404)
                old = conn.execute("SELECT cau_hoi,tra_loi,bat,updated_at FROM hoi_dap WHERE id=?",
                                   (answer_id,)).fetchone()
                if old is None:
                    raise EditorError("Đáp án đã bị xóa", 404)
                if expected_updated_at is None or old[3] != expected_updated_at:
                    raise EditorError("Đáp án đã được sửa ở nơi khác; hãy tải lại", 409)
                # Legacy IDs retain their question-based runtime contract.
                # Never commit a row that would invalidate the whole reload.
                if not questions and not answer_id.startswith("ab_"):
                    raise EditorError("Đáp án cũ cần câu hỏi mẫu; hãy thêm đáp án mới nếu chỉ lưu nội dung trả lời")
            else:
                answer_id = "ab_manual_" + uuid.uuid4().hex
            now = max(time.time(), float(old[3] or 0) + 0.000001) if old else time.time()
            changed_voice = old is None or old[1] != answer
            if old:
                conn.execute("UPDATE hoi_dap SET cau_hoi=?,tra_loi=?,bat=?,updated_at=? WHERE id=?",
                             (json.dumps(questions, ensure_ascii=False), answer, int(enabled), now, answer_id))
            else:
                conn.execute("INSERT INTO hoi_dap "
                             "(id,cau_dem,cau_hoi,tra_loi,san_pham,bat,created_at,updated_at) "
                             "VALUES (?,'',?,?,?,?,?,?)", (answer_id, json.dumps(questions, ensure_ascii=False),
                                                          answer, stem if group == "products" else "",
                                                          int(enabled), now, now))
            entry = conn.execute("SELECT source_hash FROM answer_bank_entries WHERE hoi_dap_id=?",
                                 (answer_id,)).fetchone()
            changed_voice = changed_voice or not entry or entry[0] != doc.fingerprint
            conn.execute("INSERT INTO answer_bank_entries "
                         "(hoi_dap_id,source_path,source_hash,origin,evidence,created_at) "
                         "VALUES (?,?,?,'manual','',?) ON CONFLICT(hoi_dap_id) DO UPDATE SET "
                         "source_path=excluded.source_path,source_hash=excluded.source_hash,origin='manual',evidence=''",
                         (answer_id, doc.rel, doc.fingerprint, now))
            if changed_voice:
                conn.execute("UPDATE answer_bank_entries SET voice_ready=0,voice_fingerprint='',voice_attempts=0 "
                             "WHERE hoi_dap_id=?", (answer_id,))
        voice = await _publish([answer_id])
        rows = qa.danh_sach(group, stem)
        return {"ok": True, "item": next(r for r in rows if r["id"] == answer_id),
                "items": rows, "so_dong": len(rows), "voice": voice}


async def append(group: str, stem: str, count: int) -> dict:
    if not 1 <= count <= 300:
        raise EditorError("Số đáp án cần tạo phải từ 1 đến 300")
    doc = await _document(group, stem)
    worker = learning.AnswerBankLearning()
    worker._state = _state()
    token = qa._manual_bank_worker.set(worker)
    try:
        async with learning.source_operation_lock(doc):
            if not learning._source_is_current(doc):
                raise EditorError("Tài liệu đã đổi; hãy tải lại", 409)
            existing = qa.danh_sach(group, stem)
            items, reasons = await learning.generate_document(
                doc, count, learning._config()["variants_per_answer"], existing_items=existing)
            # Recheck all existing rows at activation, including disabled rows.
            seen_a = {qa._khong_dau(r["tra_loi"]) for r in existing}
            fresh = []
            for item in items:
                answer_key = qa._khong_dau(item["tra_loi"])
                if answer_key in seen_a:
                    reasons["trùng đáp án đã có"] = reasons.get("trùng đáp án đã có", 0) + 1
                    continue
                fresh.append(item)
                seen_a.add(answer_key)
            ids = learning._store_items(doc, fresh, "auto", replace=False)
            voice = await _publish(ids)
            rows = qa.danh_sach(group, stem)
            result = {"ok": True, "items": rows, "so_dong": len(rows), "added": len(ids),
                      "requested": count, "voice": voice, "loai": reasons}
            if not ids:
                result["message"] = "Tài liệu chưa cung cấp thêm đáp án mới đủ căn cứ; các đáp án đã có được giữ nguyên."
            return result
    finally:
        qa._manual_bank_worker.reset(token)
