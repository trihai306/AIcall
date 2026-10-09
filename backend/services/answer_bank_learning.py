"""Incrementally prepare a large, grounded Q&A and voice bank in the background.

Knowledge files are the only authority.  Ended-call user turns may contribute a
general question intent, but their old assistant answers and private values are
never supplied to the builder.  Every activated answer carries an exact quote
from the current source document and a source fingerprint.
"""
from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import logging
import re
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable

from backend.config import settings
from backend.models import db
from backend.services import knowledge_qa_service as qa
from backend.services.rag_service import cat_manh

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS answer_bank_config (
 id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 1,
 questions_per_document INTEGER NOT NULL DEFAULT 120,
 variants_per_answer INTEGER NOT NULL DEFAULT 4, learn_history INTEGER NOT NULL DEFAULT 1,
 updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS answer_bank_sources (
 source_path TEXT PRIMARY KEY, source_group TEXT NOT NULL, source_stem TEXT NOT NULL,
 content_hash TEXT NOT NULL, config_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 answers_count INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT NOT NULL DEFAULT '', built_at REAL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS answer_bank_entries (
 hoi_dap_id TEXT PRIMARY KEY, source_path TEXT NOT NULL, source_hash TEXT NOT NULL,
 origin TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '', voice_ready INTEGER NOT NULL DEFAULT 0,
 voice_fingerprint TEXT NOT NULL DEFAULT '', voice_attempts INTEGER NOT NULL DEFAULT 0,
 created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_answer_bank_entries_source ON answer_bank_entries(source_path, origin);
CREATE TABLE IF NOT EXISTS answer_bank_history (
 session_id TEXT NOT NULL, turn_index INTEGER NOT NULL, source_path TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', processed_at REAL NOT NULL,
 PRIMARY KEY(session_id, turn_index));
CREATE TABLE IF NOT EXISTS answer_bank_staging (
 source_path TEXT NOT NULL, source_hash TEXT NOT NULL, stage_key TEXT NOT NULL,
 batch_index INTEGER NOT NULL, items TEXT NOT NULL, updated_at REAL NOT NULL,
 PRIMARY KEY(source_path,stage_key,batch_index));
CREATE TABLE IF NOT EXISTS answer_bank_job (
 id INTEGER PRIMARY KEY CHECK(id=1), job_id TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'idle', phase TEXT NOT NULL DEFAULT '',
 current_document TEXT NOT NULL DEFAULT '', documents_done INTEGER NOT NULL DEFAULT 0,
 documents_total INTEGER NOT NULL DEFAULT 0, answers_added INTEGER NOT NULL DEFAULT 0,
 voice_done INTEGER NOT NULL DEFAULT 0, voice_total INTEGER NOT NULL DEFAULT 0,
 logs TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '', last_run REAL,
 updated_at REAL NOT NULL);
"""


@dataclass(frozen=True)
class Document:
    path: Path
    rel: str
    group: str
    stem: str
    text: str
    fingerprint: str


class PausedForCustomer(Exception):
    pass


class BuildCancelled(Exception):
    pass


def _voice_variants(answer_id: str, text: str) -> dict[str, str]:
    from backend.pipeline.noi_cau_dem import loi_sau_dem

    key = f"hd_{answer_id}"
    variants = {key: text}
    continuation = loi_sau_dem("Dạ", text)
    if continuation != text:
        variants[key + "_noi_dem"] = continuation
    return variants


def _voice_files_ready(tts, answer_id: str, text: str, voice: str) -> bool:
    from backend.services.tieng_san import kho_tieng_san

    return all(kho_tieng_san._duong_dan(
        voice, key, tts._van_tay_filler(spoken, voice)).is_file()
        for key, spoken in _voice_variants(answer_id, text).items())


_prepared_conn = None
_BUILDER_VERSION = 2  # Answer coverage with optional question examples.


def _conn():
    global _prepared_conn
    conn = db.connection()
    if conn is None:
        raise RuntimeError("Cơ sở dữ liệu chưa sẵn sàng")
    if _prepared_conn is not conn:
        now = time.time()
        with db.write_lock, conn:
            conn.executescript(_SCHEMA)
            columns = {r[1] for r in conn.execute("PRAGMA table_info(answer_bank_entries)")}
            if "voice_fingerprint" not in columns:
                conn.execute("ALTER TABLE answer_bank_entries ADD COLUMN voice_fingerprint TEXT NOT NULL DEFAULT ''")
            if "voice_attempts" not in columns:
                conn.execute("ALTER TABLE answer_bank_entries ADD COLUMN voice_attempts INTEGER NOT NULL DEFAULT 0")
            conn.execute(
                "INSERT OR IGNORE INTO answer_bank_config VALUES (1,?,?,?,?,?)",
                (int(settings.answer_bank_enabled), settings.answer_bank_questions_per_document,
                 settings.answer_bank_variants_per_answer, int(settings.answer_bank_learn_history), now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO answer_bank_job "
                "(id,status,logs,updated_at) VALUES (1,'idle','[]',?)", (now,),
            )
        _prepared_conn = conn
    return conn


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _config(conn=None) -> dict[str, Any]:
    conn = conn or _conn()
    row = conn.execute(
        "SELECT enabled,questions_per_document,variants_per_answer,learn_history "
        "FROM answer_bank_config WHERE id=1"
    ).fetchone()
    return {"enabled": bool(row[0]), "questions_per_document": int(row[1]),
            "variants_per_answer": int(row[2]), "learn_history": bool(row[3])}


def _config_hash(cfg: dict[str, Any], model: str = "") -> str:
    return _hash(json.dumps({"questions_per_document": cfg["questions_per_document"],
                             "variants_per_answer": cfg["variants_per_answer"],
                             "model": model, "builder_version": _BUILDER_VERSION}, sort_keys=True))


def _knowledge_root() -> Path:
    return (settings.project_dir / "knowledge").resolve()


def _documents() -> tuple[list[Document], list[str]]:
    root = _knowledge_root()
    docs: list[Document] = []
    logs: list[str] = []
    seen_stems: dict[tuple[str, str], str] = {}
    if not root.exists():
        return docs, logs
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt"} or not path.is_file():
            continue
        if path.is_symlink():
            logs.append(f"Bỏ liên kết tượng trưng: {path.name}")
            continue
        resolved = path.resolve()
        try:
            rel = resolved.relative_to(root).as_posix()
        except ValueError:
            logs.append(f"Bỏ đường dẫn ra ngoài knowledge: {path}")
            continue
        group = Path(rel).parent.as_posix()
        stem_key = (group, qa._khong_dau(path.stem))
        if stem_key in seen_stems:
            logs.append(f"Bỏ tài liệu trùng tên '{path.stem}': {rel} (đã có {seen_stems[stem_key]})")
            continue
        seen_stems[stem_key] = rel
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            logs.append(f"Bỏ tài liệu rỗng: {rel}")
            continue
        docs.append(Document(resolved, rel, group, path.stem, text, _hash(text)))
    return docs, logs


def source_operation_lock(doc: Document) -> asyncio.Lock:
    """Serialize one source's staff snapshot through answer activation.

    Locks belong to the running loop, so independent application/test loops do
    not reuse loop-bound locks. Different source files have independent locks.
    """
    loop = asyncio.get_running_loop()
    locks = getattr(loop, "_answer_bank_source_locks", None)
    if locks is None:
        locks = {}
        setattr(loop, "_answer_bank_source_locks", locks)
    identity = str(doc.path)
    if identity not in locks:
        locks[identity] = asyncio.Lock()
    return locks[identity]


def _entry_prefixes(doc: Document) -> tuple[str, str, str]:
    return tuple(_bank_prefix(doc, origin) for origin in ("auto", "staff", "memory"))


def _bank_prefix(doc: Document, origin: str) -> str:
    kind = {"auto": "auto", "staff": "staff", "memory": "mem"}[origin]
    identity = hashlib.sha1(doc.rel.encode("utf-8")).hexdigest()[:10]
    return f"ab_{kind}_{qa._slug(doc.group)[:20]}_{qa._slug(doc.stem)[:24]}_{identity}_"


def _disable_generated(conn, rel: str, group: str, stem: str) -> int:
    """Disable auto/staff/memory facts, leaving arbitrary hand-authored rows alone."""
    exact = conn.execute(
        "UPDATE hoi_dap SET bat=0,updated_at=? WHERE bat != 0 AND id IN "
        "(SELECT hoi_dap_id FROM answer_bank_entries WHERE source_path=?)",
        (time.time(), rel),
    )
    prefixes = (qa.tien_to(group, stem), qa.tien_to(group, stem, "nhan_vien"),
                f"mem_{qa._slug(group)}_{qa._slug(stem)}_")
    cur = conn.execute(
        "UPDATE hoi_dap SET bat=0, updated_at=? WHERE bat != 0 AND "
        "(id GLOB ? OR id GLOB ? OR id GLOB ?) AND id NOT IN "
        "(SELECT hoi_dap_id FROM answer_bank_entries)",
        (time.time(), *(p + "*" for p in prefixes)),
    )
    # Provenance is retained so diagnostics can explain why a row is stale.
    return int(exact.rowcount or 0) + int(cur.rowcount or 0)


def prepare_sources(*, full_rebuild: bool = False) -> tuple[list[Document], list[str]]:
    """Fingerprint files and deactivate stale generated rows before vector load."""
    conn = _conn()
    docs, logs = _documents()
    by_rel = {d.rel: d for d in docs}
    cfg = _config(conn)
    model = ""
    try:
        from backend.main import app_state
        model = getattr(getattr(app_state, "llm", None), "model", "") or ""
    except Exception:
        model = settings.ollama_model
    cfg_hash = _config_hash(cfg, model)
    now = time.time()
    changed = False
    with db.write_lock, conn:
        old = conn.execute(
            "SELECT source_path,source_group,source_stem,content_hash,config_hash,status "
            "FROM answer_bank_sources"
        ).fetchall()
        for row in old:
            rel, group, stem = str(row[0]), str(row[1]), str(row[2])
            doc = by_rel.get(rel)
            if doc is None:
                n = _disable_generated(conn, rel, group, stem)
                conn.execute("DELETE FROM answer_bank_staging WHERE source_path=?", (rel,))
                conn.execute("UPDATE answer_bank_sources SET status='missing',last_error=?,updated_at=? "
                             "WHERE source_path=?", ("Tài liệu đã bị xóa", now, rel))
                changed = changed or bool(n)
            elif row[5] == "missing" or row[3] != doc.fingerprint:
                n = _disable_generated(conn, rel, group, stem)
                conn.execute("DELETE FROM hoi_dap WHERE id IN (SELECT hoi_dap_id FROM "
                             "answer_bank_entries WHERE source_path=? AND origin IN ('auto','memory'))",
                             (rel,))
                conn.execute("DELETE FROM answer_bank_entries WHERE source_path=? "
                             "AND origin IN ('auto','memory')", (rel,))
                conn.execute("DELETE FROM answer_bank_staging WHERE source_path=?", (rel,))
                conn.execute("DELETE FROM answer_bank_history WHERE source_path=? "
                             "AND status IN ('learned','failed')", (rel,))
                conn.execute("UPDATE answer_bank_sources SET content_hash=?,config_hash=?,status='pending',"
                             "answers_count=0,attempts=0,last_error='',updated_at=? WHERE source_path=?",
                             (doc.fingerprint, cfg_hash, now, rel))
                changed = changed or bool(n)
            elif full_rebuild or row[4] != cfg_hash:
                # Generation policy changed while the authoritative document
                # did not. Keep the verified old bank serving until its larger
                # replacement is complete and atomically activated.
                conn.execute("DELETE FROM answer_bank_staging WHERE source_path=?", (rel,))
                conn.execute("UPDATE answer_bank_sources SET config_hash=?,status='pending',"
                             "attempts=0,last_error='',updated_at=? WHERE source_path=?",
                             (cfg_hash, now, rel))
        existing = {str(r[0]) for r in old}
        for doc in docs:
            if doc.rel not in existing:
                # Legacy generated rows have no fingerprint, so they cannot be
                # trusted merely because their stem matches this new metadata.
                n = _disable_generated(conn, doc.rel, doc.group, doc.stem)
                changed = changed or bool(n)
                conn.execute(
                    "INSERT INTO answer_bank_sources "
                    "(source_path,source_group,source_stem,content_hash,config_hash,status,updated_at) "
                    "VALUES (?,?,?,?,?,'pending',?)",
                    (doc.rel, doc.group, doc.stem, doc.fingerprint, cfg_hash, now),
                )
    if changed:
        logs.append("Đã tắt các đáp án sinh từ phiên bản tài liệu cũ.")
    return docs, logs


def provenance_for_ids(ids: list[str] | tuple[str, ...]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    conn = _conn()
    rows = []
    values = tuple(ids)
    for start in range(0, len(values), 500):
        batch = values[start:start + 500]
        marks = ",".join("?" for _ in batch)
        rows.extend(conn.execute(
            f"SELECT hoi_dap_id,source_path,source_hash,origin,evidence,voice_ready "
            f"FROM answer_bank_entries WHERE hoi_dap_id IN ({marks})", batch
        ).fetchall())
    return _provenance_rows(rows)


def _provenance_rows(rows, *, lock_held: bool = False) -> dict[str, dict[str, Any]]:
    # Resolve the installation authority once while building the snapshot,
    # matching the outbound scenario selected for a fresh call. Generic
    # knowledge must follow that organisation instead of an old env fallback.
    installation_bank = settings.bank_name
    conn = db.connection()
    if conn is not None:
        with nullcontext() if lock_held else db.write_lock:
            has_scenarios = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='scenarios'"
            ).fetchone()
            if has_scenarios:
                scenario = conn.execute(
                    "SELECT org_name FROM scenarios WHERE direction IN ('outbound','both') "
                    "ORDER BY is_default DESC,created_at LIMIT 1"
                ).fetchone()
                if scenario and str(scenario[0] or "").strip():
                    installation_bank = str(scenario[0]).strip()
    generic = {"products", "faq", "policies", "policy", "chinh sach", "quy dinh",
               "global", "common", "shared"}
    result = {}
    for row in rows:
        source = str(row[1]).replace("\\", "/").lstrip("/")
        top = source.split("/", 1)[0] if "/" in source else ""
        bank_scope = installation_bank if not top or qa._khong_dau(top) in generic else top
        result[str(row[0])] = {"source_path": row[1], "source_hash": row[2],
                               "origin": row[3], "evidence": row[4],
                               "voice_ready": bool(row[5]), "scope": top,
                               "bank": "shinhan" if top == "shinhan" else "",
                               "bank_scope": bank_scope}
    return result


def active_provenance(conn=None, *, lock_held: bool = False) -> dict[str, dict[str, Any]]:
    """One query for the runtime snapshot; avoids per-turn SQLite lookups."""
    conn = conn if conn is not None else _conn()
    rows = conn.execute(
        "SELECT e.hoi_dap_id,e.source_path,e.source_hash,e.origin,e.evidence,e.voice_ready "
        "FROM answer_bank_entries e JOIN hoi_dap h ON h.id=e.hoi_dap_id WHERE h.bat=1"
    ).fetchall()
    return _provenance_rows(rows, lock_held=lock_held)


def row_is_current(answer_id: str, *, snapshot=None) -> bool:
    """Whether a runtime row is still safe after an awaited selector call.

    Hand-authored rows without generated prefixes are governed only by ``bat``.
    Generated rows require provenance plus a matching current file hash. Any DB,
    path, or metadata error fails closed.
    """
    try:
        conn = _conn()
        row = conn.execute("SELECT bat,cau_hoi,tra_loi,san_pham,cau_dem,updated_at "
                           "FROM hoi_dap WHERE id=?", (answer_id,)).fetchone()
        if row is None or not bool(row[0]):
            return False
        if snapshot is not None:
            from backend.pipeline.bo_thi_cuoi import bo_thi_cuoi
            if (json.loads(row[1] or "[]") != list(snapshot.get("cau_hoi") or [])
                    or (row[2] or "") != (snapshot.get("tra_loi") or "")
                    or (row[3] or "") != (snapshot.get("san_pham") or "")
                    or bo_thi_cuoi(row[4] or "") != (snapshot.get("cau_dem") or "")
                    or ("updated_at" in snapshot and row[5] != snapshot["updated_at"])):
                return False
        entry = conn.execute(
            "SELECT e.source_path,e.source_hash,s.status,s.content_hash "
            "FROM answer_bank_entries e LEFT JOIN answer_bank_sources s "
            "ON s.source_path=e.source_path WHERE e.hoi_dap_id=?", (answer_id,),
        ).fetchone()
        generated = answer_id.startswith(("auto_", "staff_", "mem_", "ab_auto_",
                                          "ab_staff_", "ab_mem_", "ab_manual_"))
        if entry is None:
            return not generated
        if entry[2] not in {"done", "pending", "error"} or entry[1] != entry[3]:
            return False
        root = _knowledge_root()
        path = (root / entry[0]).resolve(strict=True)
        path.relative_to(root)
        return _hash(path.read_text(encoding="utf-8", errors="replace")) == entry[1]
    except Exception:
        return False


row_is_current.supports_snapshot = True


def voice_is_ready(answer_id: str, text: str, state=None) -> bool:
    """Readiness is current provenance plus both actual voice variants."""
    try:
        if state is None:
            from backend.main import app_state
            state = app_state
        row = _conn().execute(
            "SELECT voice_ready,voice_fingerprint FROM answer_bank_entries WHERE hoi_dap_id=?",
            (answer_id,),
        ).fetchone()
        voice = state.tts.default_voice_name()
        return bool(row and row[0] and row_is_current(answer_id)
                    and row[1] == state.tts._van_tay_filler(text, voice)
                    and _voice_files_ready(state.tts, answer_id, text, voice))
    except Exception:
        return False


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    starts = [p for p in (text.find("["), text.find("{")) if p >= 0]
    if not starts:
        raise ValueError("Qwen không trả JSON")
    start = min(starts)
    end = max(text.rfind("]"), text.rfind("}"))
    try:
        if end < start:
            raise ValueError("JSON chưa hoàn chỉnh")
        return json.loads(text[start:end + 1])
    except ValueError:
        salvaged = _salvage_array(text[start:])
        if salvaged:
            return salvaged
        raise


def _salvage_array(text: str) -> list:
    """Các object TRỌN VẸN ở đầu một mảng JSON bị cắt hoặc hỏng giữa chừng.

    Qwen chạm num_predict thì cụt ngang object cuối ("Expecting ',' delimiter"
    ở ký tự 4.127 với `nghiep_vu_co_ban_va_loi_thoai.md`, 02-10-2026). Bỏ cả
    lô vì một object cụt là mất trắng các đáp án đã sinh đúng trước nó.
    """
    if not text.startswith("["):
        return []
    decoder = json.JSONDecoder()
    items: list = []
    pos = 1
    while True:
        while pos < len(text) and text[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(text) or text[pos] != "{":
            return items
        try:
            obj, pos = decoder.raw_decode(text, pos)
        except ValueError:
            return items
        items.append(obj)


def _evidence_in_source(evidence: str, source: str) -> bool:
    return len(_normal(evidence)) >= 8 and _normal(evidence).casefold() in _normal(source).casefold()


def _qualitative_contradiction(answer: str, evidence: str) -> bool:
    """Reject common polarity flips even before the independent Qwen verdict."""
    a, e = qa._khong_dau(answer), qa._khong_dau(evidence)
    if "khong can" in a and re.search(r"(?:^| )can(?: |$)", e) and "khong can" not in e:
        return True
    if any(x in a for x in ("mien phi", "khong mat phi", "khong co phi")):
        if re.search(r"(?:^| )phi(?: |$)", e) and not any(
                x in e for x in ("mien phi", "khong mat phi", "khong co phi")):
            return True
    if "khong co dieu kien" in a and "dieu kien" in e and "khong co dieu kien" not in e:
        return True
    return False


# Không bắt "không cung cấp": câu "anh/chị có thể không cung cấp thông tin nếu
# chưa sẵn sàng" là lời thoại hợp lệ của tài liệu nghiệp vụ.
# "Tài liệu chỉ nêu X, không có thông tin về Y" vẫn kèm được một câu trích có
# thật nên lọt cả hai lưới; trên máy Win 02-10-2026 có 324 đáp án như vậy được
# bật. Kho trả lời trước chỉ chứa câu trả lời; câu chưa có căn cứ để LLM xử lý.
_REFUSAL = re.compile(
    r"(?i)(?:không|chưa) (?:có|nêu|đề cập|ghi)[^.]{0,25}"
    r"(?:thông tin|cụ thể|rõ|quy định|căn cứ)|tài liệu (?:chỉ|không|chưa)|em xin lỗi")


# "anh chị thực hiện" làm TỪ ĐỆM: "anh chị thực hiện sau khi phê duyệt trong vòng
# 24 giờ", "anh chị thực hiện miễn phí thường niên". Lời dặn cũ của prompt khiến
# Qwen chép cụm này vào 300/2.481 đáp án (06-10-2026). "thực hiện giao dịch /
# thanh toán / thủ tục..." là cách nói đúng, không bắt.
_FILLER_THUC_HIEN = re.compile(
    r"(?i)(?:anh/?\s?chị|khách|mình) thực hiện "
    r"(?!giao dịch|thanh toán|thủ tục|đăng ký|các bước|theo hướng dẫn|việc|yêu cầu|khoản|lệnh)")


def _lac_chu_de(item: dict, question: str) -> bool:
    from backend.services.answer_bank_selector import _thieu_chu_de
    return _thieu_chu_de(item, question)


def _validate_item(raw: dict, source: str, variants: int) -> tuple[dict | None, str]:
    answer = _normal(str(raw.get("answer") or raw.get("tra_loi") or ""))
    # Qwen hay viết "...đối tác. ạ": TTS đọc "ạ" thành một câu rời.
    answer = re.sub(r"\s*[.,]\s*ạ\.?$", " ạ.", answer)
    evidence = _normal(str(raw.get("evidence") or raw.get("nguon") or ""))
    questions = raw.get("questions") or raw.get("cau_hoi") or []
    if not isinstance(questions, list) or any(not isinstance(q, str) for q in questions):
        return None, "câu hỏi mẫu phải là danh sách chuỗi"
    questions = [_normal(q) for q in questions if _normal(q)]
    if not answer:
        return None, "thiếu câu trả lời"
    if not _evidence_in_source(evidence, source):
        return None, "trích dẫn không tồn tại nguyên văn trong nguồn"
    if _qualitative_contradiction(answer, evidence):
        return None, "câu trả lời đảo nghĩa của bằng chứng"
    if _REFUSAL.search(answer):
        return None, "câu trả lời là từ chối, không có căn cứ trong nguồn"
    if _FILLER_THUC_HIEN.search(answer):
        return None, "câu trả lời chèn cụm đệm 'anh chị thực hiện'"
    # loc_cap uses its first argument only as a nonempty identity check;
    # answer style and numeric grounding remain independent of examples.
    ok, why = qa.loc_cap(answer, answer, source)
    if not ok:
        return None, why
    unique: list[str] = []
    seen: set[str] = set()
    for q in questions:
        key = qa._khong_dau(q)
        if key and key not in seen:
            seen.add(key)
            unique.append(q)
    return {"cau_hoi": unique[:variants], "tra_loi": answer, "evidence": evidence}, ""


_EXCLUSION_BUDGET_CHARS = 3500


def _generation_prompt(source: str, count: int, variants: int,
                       fixed_questions: list[str] | None = None,
                       exclusions: list[dict] | None = None) -> str:
    fixed = ""
    if fixed_questions:
        # Câu hỏi cho trước kéo Qwen chép nguyên đoạn nguồn: với tài liệu lời
        # thoại, 9/20 đáp án dài 37-48 từ và bị trần 35 từ loại (07-10-2026).
        fixed = ("\nCÂU HỎI PHẢI TRẢ LỜI (giữ request_index tương ứng). Mỗi answer TÓM GỌN "
                 "nhiều nhất 28 từ: chỉ lấy ý trả lời thẳng vào câu hỏi, KHÔNG chép cả đoạn "
                 "lời thoại trong tài liệu; đếm lại số từ trước khi trả:\n" +
                 "\n".join(f"{i}: {q}" for i, q in enumerate(fixed_questions)))
    excluded = ""
    if exclusions:
        # Ngân sách theo KÝ TỰ, giữ đáp án gần nhất. Trần cũ 16.000 ký tự (~5.000
        # token) cộng mảnh nguồn có thể vượt num_ctx 4096, khi đó Ollama cắt đầu
        # prompt và mất cả lời dặn trả JSON. Trùng chữ vẫn được khử ở accept().
        answers: list[str] = []
        used = 0
        for item in reversed(exclusions):
            answer = _normal(str(item.get("tra_loi", "")))
            if not answer or used + len(answer) > _EXCLUSION_BUDGET_CHARS:
                break
            answers.append(answer)
            used += len(answer)
        excluded = ("\nĐÃ CÓ TRONG KHO (chỉ để tránh lặp, KHÔNG phải nguồn dữ kiện; "
                    "tạo nội dung trả lời mới, không lặp ý hay diễn đạt lại đáp án đã có):\n" +
                    json.dumps(answers[::-1], ensure_ascii=False))
    return f"""Bạn đang chuẩn bị thư viện trả lời trước cho cuộc gọi tiếng Việt.
Chỉ được dùng dữ kiện trong TÀI LIỆU. Tạo tối đa {count} đáp án khác ý để phủ
các dữ kiện, điều kiện và hướng dẫn thực hiện hữu ích trong tài liệu. Ưu tiên
nội dung đáp án; khách có thể hỏi theo nhiều cách và Qwen sẽ chọn theo ý/ngữ cảnh.
questions là câu hỏi mẫu TÙY CHỌN: từ 0 đến {variants} câu, có thể để [].
Không cố tạo đủ số lượng, không chia một ý thành nhiều đáp án trùng nghĩa.
Nếu câu hỏi bắt buộc không có căn cứ thì bỏ qua. Trả lời 1-2 câu, tối đa 35 từ, mở đầu Dạ, xưng em, gọi anh chị,
kết thúc ạ. Không thêm hoặc đổi bất kỳ con số nào.
Mọi cách hỏi phải giữ cùng sản phẩm và nghiệp vụ; không đổi câu hỏi về thẻ
thành khoản vay. Giữ đủ các bước và điều kiện cần để trả lời trọn ý. Nếu tài
liệu hướng dẫn khách tự làm một việc thì chủ ngữ là anh chị kèm ĐỘNG TỪ CỤ THỂ
(anh chị mở ứng dụng, anh chị cần nộp, anh chị được vay...), không nói em làm.
Không chèn cụm "anh chị thực hiện" làm từ đệm trước một động từ hay một dữ kiện.

Mỗi item bắt buộc có evidence là một câu/trích đoạn CHÉP NGUYÊN VĂN từ tài liệu
và trực tiếp chứng minh answer. Chỉ trả JSON array:
[{{"request_index":0,"questions":[],"answer":"...","evidence":"trích nguyên văn"}}]
{fixed}
{excluded}

TÀI LIỆU:
<<<NGUỒN
{source}
NGUỒN>>>"""


async def _chat(prompt: str, predict: int = 1800) -> str:
    from backend.main import app_state
    args = dict(model=app_state.llm.model,
                messages=[{"role": "user", "content": prompt}], think=False,
                keep_alive=-1,
                options={"num_predict": min(max(500, predict), 4096),
                         "temperature": 0.35, "num_ctx": settings.llm_num_ctx})
    try:
        response = await app_state.llm.client.chat(**args, stream=True)
    except TypeError:  # lightweight test doubles / older ollama client
        response = await app_state.llm.client.chat(**args)
    if hasattr(response, "__aiter__"):
        pieces: list[str] = []
        try:
            async for chunk in response:
                if isinstance(chunk, dict):
                    pieces.append(str((chunk.get("message") or {}).get("content") or ""))
                else:
                    pieces.append(str(getattr(getattr(chunk, "message", None), "content", "") or ""))
        finally:
            close = getattr(response, "aclose", None)
            if close:
                await close()
        return _normal("".join(pieces))
    if isinstance(response, dict):
        return _normal(((response.get("message") or {}).get("content") or ""))
    return _normal(getattr(getattr(response, "message", None), "content", "") or "")


async def _chat_json(prompt: str, predict: int) -> Any:
    """Gọi Qwen và đọc JSON; hỏng JSON thì gọi lại MỘT lần.

    Lỗi JSON lẻ tẻ (thiếu dấu phẩy, ngoặc kép trong câu tiếng Việt) từng làm
    `nghiep_vu_co_ban_va_loi_thoai.md` lỗi đủ 3 lần rồi bị bỏ hẳn. Nhiệt độ
    0,35 nên lần gọi sau thường ra chuỗi khác.
    """
    for attempt in range(2):
        text = await _guarded(_chat(prompt, predict), settings.answer_bank_llm_timeout_s)
        try:
            return _extract_json(text)
        except ValueError:  # json.JSONDecodeError là ValueError
            if attempt:
                raise
            logger.info("Thư viện tự động: Qwen trả JSON hỏng, gọi lại một lần")


async def _guarded(coro: Awaitable[Any], timeout: float, *, cancellable: bool = True) -> Any:
    """Bound one GPU call and preempt it promptly when customer work appears."""
    from backend.core.service_priority import background_ai_busy_reason, background_gpu_lock
    gate = background_gpu_lock()
    await gate.acquire()
    reason_before = background_ai_busy_reason()
    if reason_before:
        gate.release()
        if hasattr(coro, "close"):
            coro.close()
        raise PausedForCustomer(reason_before)
    task = asyncio.create_task(coro)
    deadline = time.monotonic() + timeout
    try:
        while not task.done():
            worker = qa._manual_bank_worker.get() or globals().get("bo_hoc_tra_loi")
            cancelled = bool(worker and worker._cancel.is_set())
            if cancelled:
                if cancellable:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                else:
                    await asyncio.wait_for(asyncio.shield(task), max(0.1, deadline - time.monotonic()))
                raise BuildCancelled
            reason = background_ai_busy_reason()
            if reason:
                if cancellable:
                    # _chat uses a streaming response; cancellation closes the
                    # HTTP stream in its finally block instead of merely
                    # abandoning an unbounded server request.
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    raise PausedForCustomer(reason)
                # Native F5 work may already be executing in its single worker
                # thread and cannot be interrupted safely. Let exactly this
                # bounded call finish, then pause before starting another one.
                result = await asyncio.wait_for(asyncio.shield(task), max(0.1, deadline - time.monotonic()))
                raise PausedForCustomer(reason) from None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise TimeoutError(f"Tác vụ nền quá {timeout:.0f} giây")
            await asyncio.wait({task}, timeout=min(0.5, remaining))
        return task.result()
    except BaseException:
        if not task.done():
            task.cancel()
        raise
    finally:
        if gate.locked():
            gate.release()


async def _verify_items(items: list[dict], source: str) -> list[dict]:
    """Independent semantic verdict; exact quote alone is not sufficient."""
    if not items:
        return []
    payload = [{"index": i, "required_question": x.get("_required", ""),
                "questions": x["cau_hoi"], "answer": x["tra_loi"],
                "evidence": x["evidence"]} for i, x in enumerate(items)]
    prompt = """Kiểm tra từng item chỉ theo TÀI LIỆU. grounded=true chỉ khi evidence
là trích dẫn liên quan và answer được tài liệu/evidence suy ra trực tiếp, không
đảo nghĩa, không thêm điều kiện hay khẳng định định tính. Giữ đủ các điều kiện,
giới hạn và các bước cần thiết; không biến trường hợp có điều kiện thành cam kết
vô điều kiện. questions có thể rỗng và không phải lý do để loại đáp án. Nếu required_question
có giá trị thì answer bắt buộc phải trả lời đúng ý đó; không được thay bằng FAQ
khác. Mọi cách hỏi phải cùng ý và answer phải trả lời được. Khi nghi ngờ chọn false. Chỉ JSON array:
[{"index":0,"grounded":true}]
ITEMS:
""" + json.dumps(payload, ensure_ascii=False) + "\nTÀI LIỆU:\n" + source
    raw = await _chat_json(prompt, min(1800, len(items) * 90 + 300))
    accepted = set()
    for verdict in raw if isinstance(raw, list) else []:
        if isinstance(verdict, dict) and verdict.get("grounded") is True:
            try:
                accepted.add(int(verdict.get("index")))
            except (TypeError, ValueError):
                pass
    result = []
    for i, item in enumerate(items):
        if i in accepted:
            item.pop("_required", None)
            item.pop("_request_index", None)
            result.append(item)
    return result


def _staged_batch(doc: Document, stage_key: str, batch_index: int) -> list[dict] | None:
    if not stage_key:
        return None
    row = _conn().execute(
        "SELECT items,source_hash FROM answer_bank_staging "
        "WHERE source_path=? AND stage_key=? AND batch_index=?",
        (doc.rel, stage_key, batch_index),
    ).fetchone()
    if row is None or row[1] != doc.fingerprint:
        return None
    try:
        value = json.loads(row[0])
        return value if isinstance(value, list) else None
    except json.JSONDecodeError:
        return None


def _save_staged_batch(doc: Document, stage_key: str, batch_index: int,
                       items: list[dict]) -> None:
    if not stage_key or not items:
        return
    conn = _conn()
    with db.write_lock, conn:
        if not _source_is_current(doc):
            raise RuntimeError("Tài liệu đổi trong lúc lưu checkpoint")
        conn.execute(
            "INSERT OR REPLACE INTO answer_bank_staging "
            "(source_path,source_hash,stage_key,batch_index,items,updated_at) VALUES (?,?,?,?,?,?)",
            (doc.rel, doc.fingerprint, stage_key, batch_index,
             json.dumps(items, ensure_ascii=False), time.time()),
        )


async def generate_document(doc: Document, count: int, variants: int,
                            fixed_questions: list[str] | None = None,
                            stage_key: str = "",
                            existing_items: list[dict] | None = None) -> tuple[list[dict], dict[str, int]]:
    """Cover every source chunk through bounded batches, then deduplicate."""
    chunks = [c for c in cat_manh(doc.text) if c.strip()] or [doc.text]
    target = len(fixed_questions or []) or count
    target = max(1, min(int(target), 300))
    variants = max(1, min(int(variants), 8))
    reasons: dict[str, int] = {}
    out: list[dict] = []
    seen_a = {qa._khong_dau(item.get("tra_loi", "")) for item in existing_items or []}
    fixed = list(fixed_questions or [])
    if stage_key:
        # A checkpoint is usable only for this answer-generation policy and
        # request, even when called without a preceding prepare_sources scan.
        stage_key += ":" + _hash(json.dumps({
            "builder_version": _BUILDER_VERSION, "target": target, "variants": variants,
            "fixed": fixed, "existing": existing_items or [],
        }, sort_keys=True, ensure_ascii=False))[:20]

    def accept(items: list[dict]) -> None:
        for item in items:
            if _REFUSAL.search(item.get("tra_loi", "")):
                # Bản lưu tạm của lần dựng trước có thể chưa qua luật mới.
                reasons["câu trả lời là từ chối, không có căn cứ trong nguồn"] = (
                    reasons.get("câu trả lời là từ chối, không có căn cứ trong nguồn", 0) + 1)
                continue
            if _FILLER_THUC_HIEN.search(item.get("tra_loi", "")):
                reasons["câu trả lời chèn cụm đệm 'anh chị thực hiện'"] = (
                    reasons.get("câu trả lời chèn cụm đệm 'anh chị thực hiện'", 0) + 1)
                continue
            kept = [q for q in item["cau_hoi"] if not _lac_chu_de(item, q)]
            if len(kept) < len(item["cau_hoi"]):
                reasons["câu hỏi mẫu lệch chủ đề đáp án"] = (
                    reasons.get("câu hỏi mẫu lệch chủ đề đáp án", 0)
                    + len(item["cau_hoi"]) - len(kept))
                if fixed and not kept:
                    continue  # câu bắt buộc mà đáp án lạc đề thì không lưu
                item["cau_hoi"] = kept
            key = qa._khong_dau(item["tra_loi"])
            if key in seen_a:
                if fixed:
                    # Several independently verified staff questions can
                    # share one prepared answer; preserve their coverage.
                    prior = next((x for x in out if qa._khong_dau(x["tra_loi"]) == key), None)
                    if prior is not None:
                        known = {qa._khong_dau(q) for q in prior["cau_hoi"]}
                        prior["cau_hoi"].extend(q for q in item["cau_hoi"]
                                                if qa._khong_dau(q) not in known)
                reasons["trùng đáp án đã có"] = reasons.get("trùng đáp án đã có", 0) + 1
                continue
            seen_a.add(key)
            out.append(item)
    if fixed:
        # Questions are mapped to the full authoritative document in bounded
        # groups; exact evidence still keeps each accepted answer grounded.
        work = [(doc.text, fixed[i:i + 8]) for i in range(0, len(fixed), 8)]
    else:
        chosen = qa._chon_manh_phu_deu(chunks, target)
        base, extra = divmod(target, len(chosen))
        work = []
        for index, chunk in enumerate(chosen):
            allocated = base + (1 if index < extra else 0)
            while allocated > 0:
                ask = min(8, allocated)
                work.append((chunk, [], ask))
                allocated -= ask
    if fixed:
        work = [(source, questions, len(questions)) for source, questions in work]
    for batch_index, (source, questions, requested) in enumerate(work):
        ask = min(8, requested)
        staged = _staged_batch(doc, stage_key, batch_index)
        if staged is not None:
            accept(staged)
            continue
        raw = await _chat_json(
            _generation_prompt(source, ask, variants, questions or None,
                               (existing_items or []) + out),
            ask * (variants * 60 + 160) + 300)
        if isinstance(raw, dict):
            raw = raw.get("items") or []
        batch: list[dict] = []
        requested_seen: set[int] = set()
        for candidate in raw if isinstance(raw, list) else []:
            if not isinstance(candidate, dict):
                continue
            item, why = _validate_item(candidate, source, variants)
            if item is None:
                reasons[why] = reasons.get(why, 0) + 1
                continue
            answer_key = qa._khong_dau(item["tra_loi"])
            if answer_key in seen_a and not questions:
                reasons["trùng đáp án đã có"] = reasons.get("trùng đáp án đã có", 0) + 1
                continue
            if questions:
                try:
                    request_index = int(candidate.get("request_index"))
                    if not 0 <= request_index < len(questions):
                        raise IndexError(request_index)
                    required = questions[request_index]
                except (TypeError, ValueError, IndexError):
                    reasons["thiếu request_index của câu bắt buộc"] = (
                        reasons.get("thiếu request_index của câu bắt buộc", 0) + 1)
                    continue
                if request_index in requested_seen:
                    continue
                requested_seen.add(request_index)
                item["cau_hoi"] = [required] + [q for q in item["cau_hoi"]
                                                     if qa._khong_dau(q) != qa._khong_dau(required)]
                item["cau_hoi"] = item["cau_hoi"][:variants]
                item["_required"] = required
                item["_request_index"] = request_index
            batch.append(item)
        verified = await _verify_items(batch, source)
        rejected = len(batch) - len(verified)
        if rejected:
            reasons["Qwen xác minh ngữ nghĩa không đạt"] = (
                reasons.get("Qwen xác minh ngữ nghĩa không đạt", 0) + rejected)
        _save_staged_batch(doc, stage_key, batch_index, verified)
        accept(verified)
        await asyncio.sleep(0)
    return out[:target], reasons


_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?84|0)\s*(?:[ .-]?\d){8,10}(?!\d)")
_ACCOUNT = re.compile(r"(?i)\b(?:stk|số tài khoản|tài khoản|cccd|cmnd|mã khách hàng)"
                      r"\s*[:#-]?\s*[A-Z0-9][A-Z0-9 .-]{3,40}")
_MONEY = re.compile(r"(?i)(?<!\w)\d[\d., ]{2,}\s*(?:đ|đồng|vnd|triệu|tr|tỷ)\b")
_NAME = re.compile(r"(?i)\b(?:tôi|em|anh|chị)\s+(?:tên là|là)\s+[A-ZÀ-Ỹ][\wÀ-ỹ]*(?:\s+[A-ZÀ-Ỹ][\wÀ-ỹ]*){0,3}")
_DOB = re.compile(r"(?i)\b(?:ngày sinh|sinh ngày|dob)\s*[:#-]?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_ADDRESS = re.compile(r"(?i)\b(?:địa chỉ|ở tại|nhà ở|nhà tôi ở|tôi ở|đang ở)"
                      r"\s*[:#-]?\s*[^,.;]{2,80}")
_EMPLOYER = re.compile(r"(?i)\b(?:công ty|nơi làm việc|đơn vị công tác)\s*[:#-]?\s*[^,.;]{2,80}")
_LONG_ID = re.compile(r"(?<!\d)\d{6,}(?!\d)")
_SPACED_ID = re.compile(r"(?<!\d)(?:\d[ .-]?){6,}(?!\d)")
_PERSONAL_NUMBER = re.compile(r"(?i)\b(?:số của tôi|mã của tôi)\s*[:#-]?\s*(?:\d[ .-]?){4,}")


def sanitize_history(text: str, private_values: list[str] | tuple[str, ...] = ()) -> str:
    result = _normal(text)[:800]
    for value in private_values:
        value = _normal(value)
        if len(value) >= 2:
            result = re.sub(re.escape(value), "[thông tin riêng]", result, flags=re.I)
    result = _EMAIL.sub("[email]", result)
    result = _PHONE.sub("[số điện thoại]", result)
    result = _ACCOUNT.sub("[mã riêng]", result)
    result = _MONEY.sub("[số tiền riêng]", result)
    result = _NAME.sub("[tên khách]", result)
    result = _DOB.sub("[ngày sinh]", result)
    result = _ADDRESS.sub("[địa chỉ]", result)
    result = _EMPLOYER.sub("[nơi làm việc]", result)
    result = _PERSONAL_NUMBER.sub("[mã riêng]", result)
    result = _SPACED_ID.sub("[mã riêng]", result)
    result = _LONG_ID.sub("[mã riêng]", result)
    return result


def _history_candidates(limit: int = 200) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT t.session_id,t.turn_index,t.content,s.product,s.customer_name,s.phone "
            "FROM conversation_turns t JOIN call_sessions s ON s.session_id=t.session_id "
            "LEFT JOIN answer_bank_history h ON h.session_id=t.session_id AND h.turn_index=t.turn_index "
            "WHERE s.status='ended' AND t.role='user' AND h.session_id IS NULL "
            "ORDER BY t.recorded_at LIMIT ?", (max(1, min(limit, 500)),),
        ).fetchall()
    except Exception:
        return []
    return [{"session_id": r[0], "turn_index": int(r[1]),
             "text": sanitize_history(r[2], (r[4] or "", r[5] or "")),
             "product": _normal(r[3] or "")} for r in rows]


_PROFILE_SKIP = re.compile(r"(?i)^(?:nguồn|sha-?256|phạm vi|https?://)")
# Ý định kiểu mô tả ("câu hỏi chung về vay tín chấp", "hỏi về hạn mức") không
# phải lời khách: nó thành câu hỏi mẫu của kho và không khớp câu khách thật nói.
_META_INTENT = re.compile(r"(?i)^\s*(?:câu hỏi|hỏi về|hỏi thông tin|khách (?:hàng )?hỏi|ý định)\b")


def _doc_profile(doc: Document, limit: int = 420) -> str:
    """Tên, các mục và câu mở đầu của tài liệu cho bước chọn nguồn.

    Chỉ đưa đường dẫn thì Qwen chọn theo TÊN FILE: đo trên máy Win 02-10-2026,
    `shinhan_consumer_credit_terms_2025.md` (948 byte, chỉ nói ứng tiền mặt
    bằng thẻ) nhận 873 câu hỏi vay tín chấp vì tên có "consumer_credit".
    """
    title, heads, body = "", [], []
    for line in doc.text.splitlines():
        line = _normal(line)
        if not line or _PROFILE_SKIP.match(line):
            continue
        if line.startswith("#"):
            text = line.lstrip("#").strip()
            if not title and not line.startswith("##"):
                title = text
            elif text:
                heads.append(text)
        elif sum(len(x) for x in body) < 200:
            body.append(line)
    parts = [title or doc.stem]
    if heads:
        parts.append("mục: " + ", ".join(heads)[:220])
    if body:
        parts.append("nội dung: " + " ".join(body)[:200])
    return " | ".join(parts)[:limit]


def _product_conflict(intent: str, product: str, doc: Document) -> bool:
    """Câu hỏi nêu một sản phẩm mà tài liệu không hề nhắc tới -> gán sai nguồn."""
    from backend.services.rag_service import RAGService
    code = (RAGService._san_pham_trong_cau(intent, None)
            or RAGService._san_pham_trong_cau(product, None))
    if not code:
        return False
    words = dict(RAGService._TU_KHOA_SP).get(code, ())
    text = qa._khong_dau(doc.text)
    return not any(qa._khong_dau(w) in text for w in words)


def _row_for(item: dict, rows: list[dict], used: set[int]) -> int | None:
    """Lượt USER mà item nói tới, khớp theo lời Qwen chép lại chứ không theo index.

    Đo 02-10-2026 trên lô 8 lượt thật: Qwen hay lệch một hàng (ý định của lượt
    i+1 gán cho lượt i, "lãi suất vay tín chấp" thành "bảo hiểm nhân thọ").
    Không khớp chắc chắn thì bỏ, để lượt đó được quét lại lần sau.
    """
    echo = qa._khong_dau(str(item.get("user") or ""))
    if not echo:
        return None
    best, best_ratio = None, 0.0
    for i, row in enumerate(rows):
        if i in used:
            continue
        ratio = difflib.SequenceMatcher(None, echo, qa._khong_dau(row["text"])).ratio()
        if ratio > best_ratio:
            best, best_ratio = i, ratio
    return best if best_ratio >= 0.8 else None


async def _map_history(rows: list[dict], docs: list[Document]) -> list[dict]:
    if not rows or not docs:
        return []
    sources = "\n".join(f"- {d.rel}: {_doc_profile(d)}" for d in docs)
    turns = "\n".join(f"{i}: product={r['product']!r}; user={r['text']}" for i, r in enumerate(rows))
    prompt = f"""Rút ý định câu hỏi từ các lượt USER đã khử riêng tư. Tuyệt đối
không suy ra tên, số liên lạc, tài khoản hay số tiền cá nhân.
intent là MỘT câu hỏi viết lại gọn như chính khách sẽ hỏi, giữ đúng sản phẩm
(câu không nêu sản phẩm thì lấy theo product), ví dụ "lãi suất vay tín chấp
bao nhiêu". Không viết kiểu mô tả như "câu hỏi chung về ..." hay "hỏi về ...".
Chọn source theo NỘI DUNG mô tả bên cạnh, không theo tên file; chỉ chọn khi tài
liệu đó trực tiếp nói về đúng sản phẩm và ý được hỏi, nếu không chắc dùng source="".
Không trả lời câu hỏi. Chỉ JSON array:
[{{"index":0,"user":"<chép NGUYÊN VĂN lượt USER đó>","intent":"<câu hỏi của khách>","source":"<đường dẫn trong SOURCES hoặc rỗng>"}}]
SOURCES:
{sources}
USER TURNS:
{turns}"""
    raw = await _chat_json(prompt, 1800)
    by_rel = {d.rel: d for d in docs}
    allowed = set(by_rel)
    mapped = []
    used: set[int] = set()
    for item in raw if isinstance(raw, list) else []:
        try:
            idx = _row_for(item, rows, used)
            source = str(item.get("source") or "")
            intent = sanitize_history(str(item.get("intent") or ""))
        except (ValueError, TypeError, AttributeError):
            continue
        if idx is None:
            continue
        used.add(idx)
        row = rows[idx]
        if not intent:
            continue
        if source not in allowed or _META_INTENT.match(intent):
            source = ""
        elif _product_conflict(intent, row.get("product", ""), by_rel[source]):
            logger.info("Thư viện tự động: bỏ gán '%s' -> %s vì tài liệu không nói về sản phẩm này",
                        intent, source)
            source = ""
        mapped.append({**row, "intent": intent, "source": source})
    return mapped


def _id_for(doc: Document, item: dict, origin: str) -> str:
    prefix = _bank_prefix(doc, origin)
    payload = json.dumps({"q": item["cau_hoi"], "a": item["tra_loi"]},
                         ensure_ascii=False, sort_keys=True)
    return prefix + hashlib.sha1(payload.encode()).hexdigest()[:12]


def _source_is_current(doc: Document) -> bool:
    try:
        root = _knowledge_root()
        resolved = doc.path.resolve(strict=True)
        resolved.relative_to(root)
        return resolved == doc.path and _hash(resolved.read_text(encoding="utf-8", errors="replace")) == doc.fingerprint
    except (OSError, ValueError):
        return False


def _protected_rows(conn, doc: Document) -> list:
    """Operator choices survive replacement, including disabled current rows."""
    return conn.execute(
        "SELECT h.id,h.cau_hoi,h.tra_loi FROM hoi_dap h JOIN answer_bank_entries e "
        "ON e.hoi_dap_id=h.id WHERE e.source_path=? AND "
        "(e.origin='manual' OR (h.bat=0 AND e.source_hash=?))",
        (doc.rel, doc.fingerprint),
    ).fetchall()


def _filter_protected(conn, doc: Document, rows: list[tuple]) -> list[tuple]:
    protected = _protected_rows(conn, doc)
    protected_ids = {r[0] for r in protected}
    questions = {qa._khong_dau(q) for r in protected for q in json.loads(r[1] or "[]")}
    answers = {qa._khong_dau(r[2]) for r in protected}
    result = []
    for row_id, item, origin in rows:
        # An exact ID owned by another source must never be overwritten either.
        owner = conn.execute("SELECT source_path,origin FROM answer_bank_entries "
                             "WHERE hoi_dap_id=?", (row_id,)).fetchone()
        if (row_id in protected_ids or (owner and (owner[0] != doc.rel or owner[1] == 'manual'))
                or qa._khong_dau(item["tra_loi"]) in answers
                or any(qa._khong_dau(q) in questions for q in item["cau_hoi"])):
            continue
        result.append((row_id, item, origin))
    return result


def _store_items(doc: Document, items: list[dict], origin: str, *, replace: bool) -> list[str]:
    conn = _conn()
    now = time.time()
    ids: list[str] = []
    # Only for quarantining IDs written by the pre-provenance implementation.
    # New IDs use _bank_prefix() through _id_for() and cannot collide on slugs.
    legacy_prefix = (qa.tien_to(doc.group, doc.stem) if origin == "auto" else
                     qa.tien_to(doc.group, doc.stem, "nhan_vien") if origin == "staff" else
                     f"mem_{qa._slug(doc.group)}_{qa._slug(doc.stem)}_")
    stored_origin = origin
    san_pham = doc.stem if doc.group == "products" else ""
    with db.write_lock, conn:
        if not _source_is_current(doc):
            raise RuntimeError("Tài liệu đổi hoặc ra ngoài knowledge trước lúc lưu")
        rows = _filter_protected(conn, doc, [(_id_for(doc, item, origin), item, origin)
                                             for item in items])
        protected_ids = {r[0] for r in _protected_rows(conn, doc)}
        if replace:
            old_ids = [r[0] for r in conn.execute(
                "SELECT hoi_dap_id FROM answer_bank_entries WHERE source_path=? AND origin=?",
                (doc.rel, stored_origin),).fetchall() if r[0] not in protected_ids]
            if old_ids:
                conn.executemany("DELETE FROM hoi_dap WHERE id=?", [(x,) for x in old_ids])
                conn.executemany("DELETE FROM answer_bank_entries WHERE hoi_dap_id=?",
                                 [(x,) for x in old_ids])
            # Covers rows created by the older service before provenance existed.
            conn.execute("DELETE FROM hoi_dap WHERE id GLOB ? AND id NOT IN "
                         "(SELECT hoi_dap_id FROM answer_bank_entries)", (legacy_prefix + "*",))
        for row_id, item, _ in rows:
            ids.append(row_id)
            conn.execute(
                "INSERT OR REPLACE INTO hoi_dap "
                "(id,cau_dem,cau_hoi,tra_loi,san_pham,bat,created_at,updated_at) "
                "VALUES (?,?,?,?,?,1,?,?)",
                (row_id, "", json.dumps(item["cau_hoi"], ensure_ascii=False),
                 item["tra_loi"], san_pham, now, now),
            )
            conn.execute(
                "INSERT OR REPLACE INTO answer_bank_entries "
                "(hoi_dap_id,source_path,source_hash,origin,evidence,voice_ready,voice_fingerprint,voice_attempts,created_at) "
                "VALUES (?,?,?,?,?,0,'',0,?)",
                (row_id, doc.rel, doc.fingerprint, stored_origin, item.get("evidence", ""), now),
            )
    return ids


def _replace_document(doc: Document, auto_items: list[dict], staff_items: list[dict]) -> list[str]:
    """Activate one complete source version in one SQLite transaction."""
    conn = _conn()
    now = time.time()
    prefixes = (qa.tien_to(doc.group, doc.stem), qa.tien_to(doc.group, doc.stem, "nhan_vien"))
    san_pham = doc.stem if doc.group == "products" else ""
    rows: list[tuple[str, dict, str]] = []
    for item in auto_items:
        rows.append((_id_for(doc, item, "auto"), item, "auto"))
    for item in staff_items:
        # Staff questions are operator observations, but the answer is still
        # regenerated from the current source and shares the source invariant.
        rows.append((_id_for(doc, item, "staff"), item, "staff"))
    with db.write_lock, conn:
        if not _source_is_current(doc):
            raise RuntimeError("Tài liệu đổi hoặc ra ngoài knowledge trước lúc kích hoạt")
        rows = _filter_protected(conn, doc, rows)
        protected_ids = {r[0] for r in _protected_rows(conn, doc)}
        old_ids = [r[0] for r in conn.execute(
            "SELECT hoi_dap_id FROM answer_bank_entries WHERE source_path=? "
            "AND origin IN ('auto','staff')",
            (doc.rel,),).fetchall() if r[0] not in protected_ids]
        if old_ids:
            conn.executemany("DELETE FROM hoi_dap WHERE id=?", [(x,) for x in old_ids])
            conn.executemany("DELETE FROM answer_bank_entries WHERE hoi_dap_id=?",
                             [(x,) for x in old_ids])
        # Remove legacy auto/staff IDs which predate answer_bank_entries.
        conn.execute("DELETE FROM hoi_dap WHERE (id GLOB ? OR id GLOB ?) AND id NOT IN "
                     "(SELECT hoi_dap_id FROM answer_bank_entries)",
                     (prefixes[0] + "*", prefixes[1] + "*"))
        for row_id, item, stored_origin in rows:
            conn.execute(
                "INSERT INTO hoi_dap "
                "(id,cau_dem,cau_hoi,tra_loi,san_pham,bat,created_at,updated_at) "
                "VALUES (?,?,?,?,?,1,?,?)",
                (row_id, "", json.dumps(item["cau_hoi"], ensure_ascii=False),
                 item["tra_loi"], san_pham, now, now),
            )
            conn.execute(
                "INSERT INTO answer_bank_entries "
                "(hoi_dap_id,source_path,source_hash,origin,evidence,voice_ready,voice_fingerprint,voice_attempts,created_at) "
                "VALUES (?,?,?,?,?,0,'',0,?)",
                (row_id, doc.rel, doc.fingerprint, stored_origin, item.get("evidence", ""), now),
            )
        conn.execute(
            "UPDATE answer_bank_sources SET status='done',answers_count=?,attempts=0,last_error='',"
            "built_at=?,updated_at=? WHERE source_path=? AND content_hash=?",
            (len(rows), now, now, doc.rel, doc.fingerprint),
        )
        conn.execute("DELETE FROM answer_bank_staging WHERE source_path=?", (doc.rel,))
    return [r[0] for r in rows]


def _mark_history(rows: list[dict], status: str, source: str = "", error: str = "") -> None:
    conn = _conn()
    now = time.time()
    with db.write_lock, conn:
        conn.executemany(
            "INSERT OR REPLACE INTO answer_bank_history "
            "(session_id,turn_index,source_path,status,error,processed_at) VALUES (?,?,?,?,?,?)",
            [(r["session_id"], r["turn_index"], source or r.get("source", ""),
              status, error, now) for r in rows],
        )


def _question_key(question: str) -> frozenset[str]:
    """Tập từ mang nghĩa của câu hỏi - cùng phép so mà bộ chọn dùng để đọc thẳng."""
    from backend.services.answer_bank_selector import khoa_cau_hoi
    return khoa_cau_hoi(question)


# Mỗi câu hỏi giữ vài cách nói để bộ chọn luân phiên; quá số này thì thôi.
# Không giới hạn thì kho phình: đo 05-10-2026 có ~100 dòng cho một câu hỏi.
_VARIANTS_PER_QUESTION = 4


def _known_question_keys(doc: Document) -> dict:
    """Câu hỏi (tập từ) -> số đáp án đang bật của tài liệu này có câu hỏi đó."""
    rows = _conn().execute(
        "SELECT h.cau_hoi FROM answer_bank_entries e JOIN hoi_dap h ON h.id=e.hoi_dap_id "
        "WHERE e.source_path=? AND h.bat=1", (doc.rel,)).fetchall()
    keys: dict = {}
    for row in rows:
        try:
            questions = json.loads(row[0] or "[]")
        except json.JSONDecodeError:
            continue
        for key in {_question_key(q) for q in questions if isinstance(q, str)}:
            if key:
                keys[key] = keys.get(key, 0) + 1
    return keys


def _staff_questions(doc: Document) -> list[str]:
    result = qa.cau_hoi_nhan_vien_da_luu(doc.group, doc.stem)
    seen = {qa._khong_dau(q) for q in result}
    conn = _conn()
    rows = conn.execute(
        "SELECT h.cau_hoi FROM answer_bank_entries e JOIN hoi_dap h ON h.id=e.hoi_dap_id "
        "WHERE e.source_path=? AND e.origin='staff'", (doc.rel,),
    ).fetchall()
    for row in rows:
        try:
            questions = json.loads(row[0] or "[]")
        except json.JSONDecodeError:
            questions = []
        for question in questions:
            key = qa._khong_dau(question)
            if key and key not in seen:
                seen.add(key)
                result.append(question)
    return result


class AnswerBankLearning:
    def __init__(self):
        self._state = None
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._cancel = asyncio.Event()
        self._full_rebuild = False
        self._manual_requested = False

    def khoi_dong(self, state) -> None:
        self._state = state
        prepare_sources()
        from backend.services.answer_bank_editor import start_voice_retry
        start_voice_retry(state)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="answer-bank-learning")
        if _config()["enabled"]:
            self._wake.set()

    async def dung(self) -> None:
        self._cancel.set()
        self._wake.set()
        task, self._task = self._task, None
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def configure(self, *, enabled: bool, questions_per_document: int,
                  variants_per_answer: int, learn_history: bool) -> dict:
        q = max(12, min(int(questions_per_document), 300))
        v = max(1, min(int(variants_per_answer), 8))
        conn = _conn()
        with db.write_lock, conn:
            conn.execute(
                "UPDATE answer_bank_config SET enabled=?,questions_per_document=?,"
                "variants_per_answer=?,learn_history=?,updated_at=? WHERE id=1",
                (int(enabled), q, v, int(learn_history), time.time()),
            )
        if enabled:
            self.request_build()
        else:
            self._cancel.set()
            self._set_job(status="cancelled", phase="", error="Đã tắt theo cấu hình")
        return self.trang_thai()

    def request_build(self, full_rebuild: bool = False) -> dict:
        self._full_rebuild = self._full_rebuild or bool(full_rebuild)
        self._manual_requested = True
        self._cancel.clear()
        self._wake.set()
        return self.trang_thai()

    def cancel(self) -> dict:
        self._cancel.set()
        self._wake.set()
        self._set_job(status="cancelled", phase="", error="Đã hủy theo yêu cầu")
        return self.trang_thai()

    def document_changed(self, _path: Path | None = None) -> dict:
        prepare_sources()
        if _config()["enabled"]:
            self._cancel.clear()
            self._wake.set()
        return self.trang_thai()

    def _job(self) -> dict:
        conn = _conn()
        row = conn.execute("SELECT * FROM answer_bank_job WHERE id=1").fetchone()
        keys = [d[0] for d in conn.execute("SELECT * FROM answer_bank_job WHERE 0").description]
        data = dict(zip(keys, row))
        data["id"] = data.pop("job_id", "")
        try:
            data["logs"] = json.loads(data.get("logs") or "[]")
        except json.JSONDecodeError:
            data["logs"] = []
        data.pop("updated_at", None)
        data.pop("last_run", None)
        return data

    def _set_job(self, **changes) -> None:
        if not changes:
            return
        conn = _conn()
        allowed = {"job_id", "status", "phase", "current_document", "documents_done",
                   "documents_total", "answers_added", "voice_done", "voice_total",
                   "logs", "error", "last_run"}
        values = {k: v for k, v in changes.items() if k in allowed}
        if "logs" in values and not isinstance(values["logs"], str):
            values["logs"] = json.dumps(values["logs"][-80:], ensure_ascii=False)
        values["updated_at"] = time.time()
        sql = ",".join(f"{k}=?" for k in values)
        with db.write_lock, conn:
            conn.execute(f"UPDATE answer_bank_job SET {sql} WHERE id=1", tuple(values.values()))

    def _log(self, message: str) -> None:
        job = self._job()
        logs = list(job.get("logs") or [])
        logs.append(_normal(message))
        self._set_job(logs=logs)
        logger.info("Thư viện tự động: %s", message)

    _TIENG_NHO_GIAY = 60.0

    def _dem_tieng_da_nho(self, mac_dinh: int) -> int:
        """Số đáp án đã có đủ tệp tiếng - số đã nhớ, tự làm mới ở luồng nền."""
        import threading
        import time as _time
        nho = getattr(self, "_tieng_nho", None)
        dang = getattr(self, "_tieng_dang_dem", False)
        if (nho is None or _time.monotonic() - nho[0] > self._TIENG_NHO_GIAY) and not dang:
            self._tieng_dang_dem = True

            def _dem():
                try:
                    from backend.services.tieng_san import kho_tieng_san  # noqa: F401
                    tts = self._state.tts
                    voice = tts.default_voice_name()
                    # Kết nối DÙNG CHUNG của ứng dụng: chỉ đọc, KHÔNG đóng.
                    rows = _conn().execute(
                        "SELECT h.id,h.tra_loi,e.voice_ready,e.voice_fingerprint "
                        "FROM answer_bank_entries e JOIN hoi_dap h "
                        "ON h.id=e.hoi_dap_id WHERE h.bat=1").fetchall()
                    n = 0
                    for row in rows:
                        if (bool(row[2]) and row[3] == tts._van_tay_filler(row[1], voice)
                                and _voice_files_ready(tts, row[0], row[1], voice)):
                            n += 1
                    self._tieng_nho = (_time.monotonic(), n)
                except Exception:
                    pass
                finally:
                    self._tieng_dang_dem = False

            threading.Thread(target=_dem, daemon=True).start()
        nho = getattr(self, "_tieng_nho", None)
        return nho[1] if nho is not None else mac_dinh

    def trang_thai(self) -> dict:
        conn = _conn()
        cfg = _config(conn)
        stats = conn.execute(
            "SELECT COUNT(*),COALESCE(SUM(json_array_length(h.cau_hoi)),0),"
            "COALESCE(SUM(CASE WHEN e.origin='memory' THEN json_array_length(h.cau_hoi) ELSE 0 END),0),"
            "COALESCE(SUM(e.voice_ready),0) FROM answer_bank_entries e "
            "JOIN hoi_dap h ON h.id=e.hoi_dap_id WHERE h.bat=1"
        ).fetchone()
        ready = int(stats[3])
        if self._state is not None:
            # ĐẾM TỆP TIẾNG Ở LUỒNG RIÊNG, trả số đã nhớ. Bản cũ soát tệp của
            # TỪNG đáp án ngay trong lời gọi này: 5.494 đáp án mất 1,3 giây, mà
            # hàm chạy trên vòng sự kiện và trang Tri thức AI gọi nó mỗi 2,5
            # giây. Hễ ai mở trang đó là mọi cuộc gọi đang chạy bị đứng 1,3
            # giây một lần - khách nghe AI "đang nói tự nhiên dứt" (bộ canh
            # vòng sự kiện bắt được ngăn xếp này 08-10-2026).
            ready = self._dem_tieng_da_nho(ready)
        job = self._job()
        last = conn.execute("SELECT last_run FROM answer_bank_job WHERE id=1").fetchone()[0]
        return {"enabled": cfg["enabled"],
                "model": getattr(getattr(self._state, "llm", None), "model", settings.ollama_model),
                "config": {k: cfg[k] for k in ("questions_per_document", "variants_per_answer", "learn_history")},
                "stats": {"answers": int(stats[0]), "questions": int(stats[1]),
                          "memory_questions": int(stats[2]), "voice_ready": ready,
                          "voice_total": int(stats[0])},
                "job": job, "last_run": last}

    async def _wait_idle(self) -> None:
        last_reason = ""
        while True:
            if self._cancel.is_set():
                raise BuildCancelled
            from backend.core.service_priority import background_ai_busy_reason
            reason = background_ai_busy_reason()
            if not reason:
                return
            if reason != last_reason:
                self._set_job(status="paused", phase="waiting", error="")
                self._log(reason)
                last_reason = reason
            await asyncio.sleep(1)

    async def _voice_rows(self, ids: list[str]) -> None:
        if not ids or not settings.tieng_san_bat or self._state is None:
            return
        if not getattr(self._state.tts, "_is_loaded", False):
            self._log("F5 chưa sẵn sàng; giữ trạng thái voice chưa dựng để thử lại.")
            return
        conn = _conn()
        rows = conn.execute(
            f"SELECT id,tra_loi FROM hoi_dap WHERE id IN ({','.join('?' for _ in ids)})", ids
        ).fetchall()
        from backend.services.tieng_san import kho_tieng_san
        voice = self._state.tts.default_voice_name()
        self._set_job(voice_total=len(rows))
        done = 0
        for row in rows:
            await self._wait_idle()
            if not row_is_current(row[0]):
                continue
            fingerprint = self._state.tts._van_tay_filler(row[1], voice)
            try:
                wav = True
                for key, spoken in _voice_variants(row[0], row[1]).items():
                    await self._wait_idle()
                    clip = await _guarded(
                        kho_tieng_san.dung_mot(self._state.tts, key, spoken, voice),
                        settings.answer_bank_tts_timeout_s, cancellable=False,
                    )
                    wav = wav and bool(clip)
            except (PausedForCustomer, BuildCancelled):
                raise
            except Exception as exc:
                wav = None
                self._log(f"Voice {row[0]} chưa dựng được: {exc}")
            # Edits can happen while F5 runs. Never mark an old snapshot ready.
            current = conn.execute("SELECT tra_loi FROM hoi_dap WHERE id=? AND bat=1",
                                   (row[0],)).fetchone()
            if not current or current[0] != row[1] or not row_is_current(row[0]):
                continue
            if wav:
                with db.write_lock, conn:
                    conn.execute("UPDATE answer_bank_entries SET voice_ready=1,voice_fingerprint=?,"
                                 "voice_attempts=0 WHERE hoi_dap_id=?", (fingerprint, row[0]))
                done += 1
            else:
                with db.write_lock, conn:
                    conn.execute("UPDATE answer_bank_entries SET voice_ready=0,voice_fingerprint=?,"
                                 "voice_attempts=voice_attempts+1 WHERE hoi_dap_id=?",
                                 (fingerprint, row[0]))
            self._set_job(voice_done=done)

    async def _refresh_stale_voices(self, *, retry_failed: bool = False) -> None:
        """Build only missing/current-fingerprint voices, at most three failures."""
        if self._state is None or not settings.tieng_san_bat:
            return
        conn = _conn()
        rows = conn.execute(
            "SELECT h.id,h.tra_loi,e.voice_fingerprint,e.voice_attempts,e.voice_ready "
            "FROM answer_bank_entries e JOIN hoi_dap h ON h.id=e.hoi_dap_id WHERE h.bat=1"
        ).fetchall()
        from backend.services.tieng_san import kho_tieng_san
        voice = self._state.tts.default_voice_name()
        pending: list[str] = []
        # Soát tệp tiếng của cả kho ở LUỒNG RIÊNG rồi mới vào khoá ghi: 5.500
        # đáp án là hơn một giây đọc đĩa, làm ngay trên vòng sự kiện thì cuộc
        # gọi đang chạy bị đứng tiếng (cùng lỗi với `_dem_tieng_da_nho`).
        tts = self._state.tts

        def _soat():
            ra = []
            for row in rows:
                current = tts._van_tay_filler(row[1], voice)
                ra.append((current, bool(row[4]) and row[2] == current
                           and _voice_files_ready(tts, row[0], row[1], voice)))
            return ra

        da_soat = await asyncio.to_thread(_soat)
        with db.write_lock, conn:
            for row, (current, san_sang) in zip(rows, da_soat):
                attempts = int(row[3] or 0)
                if san_sang:
                    continue
                if row[2] != current:
                    conn.execute("UPDATE answer_bank_entries SET voice_ready=0,voice_attempts=0 "
                                 "WHERE hoi_dap_id=?", (row[0],))
                    attempts = 0
                if attempts < 3 or retry_failed:
                    pending.append(row[0])
        if pending:
            await self._voice_rows(pending)

    async def _build_document(self, doc: Document, cfg: dict) -> list[str]:
        async with source_operation_lock(doc):
            return await self._build_document_locked(doc, cfg)

    async def _build_document_locked(self, doc: Document, cfg: dict) -> list[str]:
        conn = _conn()
        if doc.stem.endswith("_ai_soan"):
            # Tài liệu GIỮ CHỖ cho đáp án giao tiếp do hai AI đối thoại soạn
            # (answer_bank_selfask). Nó không có nội dung nghiệp vụ; để bộ dựng
            # đọc là sinh ra đáp án rác kiểu "tài liệu này là nơi giữ...".
            with db.write_lock, conn:
                conn.execute("UPDATE answer_bank_sources SET status='done',last_error='',"
                             "built_at=?,updated_at=? WHERE source_path=?",
                             (time.time(), time.time(), doc.rel))
            return []
        # Preserve staff questions before replacing their source-grounded answers.
        staff_questions = _staff_questions(doc)
        items, reasons = await generate_document(
            doc, cfg["questions_per_document"], cfg["variants_per_answer"], stage_key="auto")
        # Never activate a partial/empty replacement and never commit a result
        # generated from a file that changed during the awaited model calls.
        if _hash(doc.path.read_text(encoding="utf-8", errors="replace")) != doc.fingerprint:
            raise RuntimeError("Tài liệu đổi trong lúc Qwen đang đọc; sẽ làm lại bản mới")
        if not items:
            raise RuntimeError("Không có đáp án đủ bằng chứng: " + json.dumps(reasons, ensure_ascii=False))
        staff_items: list[dict] = []
        if staff_questions:
            staff_items, _ = await generate_document(
                doc, len(staff_questions), cfg["variants_per_answer"], staff_questions,
                stage_key="staff:" + _hash(json.dumps(staff_questions, ensure_ascii=False)))
            if _hash(doc.path.read_text(encoding="utf-8", errors="replace")) != doc.fingerprint:
                raise RuntimeError("Tài liệu đổi trong lúc Qwen đang làm mới câu nhân viên")
            covered = {qa._khong_dau(q) for item in staff_items for q in item["cau_hoi"]}
            if any(qa._khong_dau(q) not in covered for q in staff_questions):
                raise RuntimeError("Không làm mới được đầy đủ câu hỏi nhân viên từ nguồn mới")
        # One last hash check covers the interval after staff generation. Only
        # now do we replace all auto+staff rows atomically.
        if _hash(doc.path.read_text(encoding="utf-8", errors="replace")) != doc.fingerprint:
            raise RuntimeError("Tài liệu đổi trước lúc kích hoạt; sẽ làm lại bản mới")
        return _replace_document(doc, items, staff_items)

    async def _learn_history(self, docs: list[Document], cfg: dict) -> list[str]:
        rows = _history_candidates()
        if not rows:
            return []
        by_rel = {d.rel: d for d in docs}
        ids: list[str] = []
        da_co: dict[str, dict] = {}
        for start in range(0, len(rows), 8):
            batch = rows[start:start + 8]
            mapped = await _map_history(batch, docs)
            seen = {(m["session_id"], m["turn_index"]) for m in mapped}
            # Lượt Qwen bỏ sót hoặc chép lại không khớp: đánh dấu luôn, nếu để
            # trống nó đứng mãi ở đầu hàng (ORDER BY recorded_at) và chặn cả bộ học.
            missing = [r for r in batch if (r["session_id"], r["turn_index"]) not in seen]
            if missing:
                _mark_history(missing, "ignored", error="Không khớp được lượt khách trong kết quả Qwen")
            for item in mapped:
                if not item["source"]:
                    _mark_history([item], "ignored",
                                  error="Không xác định chắc chắn tài liệu phù hợp")
                    continue
                doc = by_rel[item["source"]]
                # Kho đã ĐỦ cách nói cho câu hỏi này thì thôi (bộ chọn luân phiên
                # giữa chúng). Trước đây mỗi lượt khách hỏi lại sinh thêm một
                # cách diễn đạt không giới hạn.
                key = _question_key(item["intent"])
                known = da_co.setdefault(doc.rel, _known_question_keys(doc))
                if key and known.get(key, 0) >= _VARIANTS_PER_QUESTION:
                    _mark_history([item], "learned", error="Kho đã đủ cách nói cho câu hỏi này")
                    continue
                stage_key = f"memory:{item['session_id']}:{item['turn_index']}"
                generated, reasons = await generate_document(
                    doc, 1, cfg["variants_per_answer"], [item["intent"]], stage_key=stage_key)
                if not generated:
                    _mark_history([item], "failed", error=json.dumps(reasons, ensure_ascii=False))
                    continue
                ids.extend(_store_items(doc, generated, "memory", replace=False))
                for g in generated:
                    for q in g["cau_hoi"]:
                        known[_question_key(q)] = known.get(_question_key(q), 0) + 1
                _mark_history([item], "learned")
                conn = _conn()
                with db.write_lock, conn:
                    conn.execute("DELETE FROM answer_bank_staging WHERE source_path=? AND stage_key=?",
                                 (doc.rel, stage_key))
        return ids

    async def _run_once(self, full: bool, *, force: bool = False) -> None:
        cfg = _config()
        if not cfg["enabled"] and not force:
            self._set_job(status="idle", phase="", error="")
            return
        docs, scan_logs = prepare_sources(full_rebuild=full)
        if any(log.startswith("Đã tắt các đáp án") for log in scan_logs):
            # Publish quarantine before the first awaited Qwen/F5 operation.
            await qa.nap_lai_duong_goi(build_voice=False)
        conn = _conn()
        pending = []
        for doc in docs:
            row = conn.execute("SELECT status,attempts FROM answer_bank_sources WHERE source_path=?",
                               (doc.rel,)).fetchone()
            # Retry unchanged transient failures twice; after that only an
            # explicit/full request, config/source change, or restart retries.
            if (full or row[0] == "pending" or
                    (row[0] == "error" and (force or int(row[1]) < 3))):
                pending.append(doc)
        job_id = f"answer_bank_{int(time.time() * 1000)}"
        self._set_job(job_id=job_id, status="running", phase="scan", current_document="",
                      documents_done=0, documents_total=len(pending), answers_added=0,
                      voice_done=0, voice_total=0, logs=scan_logs, error="", last_run=time.time())
        added = 0
        failures: list[str] = []
        for index, doc in enumerate(pending):
            await self._wait_idle()
            self._set_job(status="running", phase="answers", current_document=doc.rel,
                          documents_done=index, answers_added=added, error="")
            try:
                ids = await self._build_document(doc, cfg)
                added += len(ids)
                # Compute a complete new map before publishing both references.
                await qa.nap_lai_duong_goi(build_voice=False)
                self._set_job(phase="voice", answers_added=added)
                await self._voice_rows(ids)
                self._log(f"{doc.rel}: thêm {len(ids)} đáp án đã đối chiếu nguồn.")
            except PausedForCustomer:
                raise
            except BuildCancelled:
                raise
            except Exception as exc:
                with db.write_lock, conn:
                    conn.execute("UPDATE answer_bank_sources SET status='error',attempts=attempts+1,"
                                 "last_error=?,updated_at=? WHERE source_path=?",
                                 (str(exc), time.time(), doc.rel))
                self._log(f"{doc.rel}: lỗi {exc}")
                failures.append(f"{doc.rel}: {exc}")
            self._set_job(documents_done=index + 1)
        if cfg["learn_history"]:
            await self._wait_idle()
            self._set_job(status="running", phase="history", current_document="")
            memory_ids = await self._learn_history(docs, cfg)
            if memory_ids:
                added += len(memory_ids)
                await qa.nap_lai_duong_goi(build_voice=False)
                self._set_job(phase="voice", answers_added=added)
                await self._voice_rows(memory_ids)
                self._log(f"Đã học {len(memory_ids)} ý hỏi chung từ lịch sử đã khử riêng tư.")
        await self._refresh_stale_voices()
        unresolved = conn.execute(
            "SELECT source_path,last_error FROM answer_bank_sources "
            "WHERE status IN ('error','missing') ORDER BY source_path"
        ).fetchall()
        for row in unresolved:
            message = f"{row[0]}: {row[1] or 'chưa thể cập nhật'}"
            if message not in failures:
                failures.append(message)
        voice_error = ""
        if settings.tieng_san_bat:
            stats = self.trang_thai()["stats"]
            if stats["voice_ready"] < stats["voice_total"]:
                voice_error = (f"Voice sẵn mới có {stats['voice_ready']}/{stats['voice_total']}; "
                               "F5 chưa sẵn sàng hoặc có câu dựng lỗi.")
        errors = failures + ([voice_error] if voice_error else [])
        self._set_job(status="error" if errors else "done", phase="", current_document="",
                      answers_added=added, error="; ".join(errors)[:2000], last_run=time.time())

    async def _loop(self) -> None:
        interval = max(10.0, float(settings.answer_bank_scan_interval_s))
        while True:
            try:
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()
                manual, self._manual_requested = self._manual_requested, False
                if not _config()["enabled"] and not manual:
                    continue
                full, self._full_rebuild = self._full_rebuild, False
                await self._run_once(full, force=manual)
            except asyncio.CancelledError:
                raise
            except BuildCancelled:
                self._set_job(status="cancelled", phase="", current_document="",
                              error="Đã hủy theo yêu cầu", last_run=time.time())
                self._cancel.clear()
            except PausedForCustomer as exc:
                # A manual build must keep resuming even with automatic
                # preparation disabled. The source checkpoints already keep
                # completed work, so only restore the request, not full rebuild.
                self._manual_requested = self._manual_requested or manual
                self._set_job(status="paused", phase="waiting", error="")
                self._log(str(exc))
                # The next bounded scan resumes from persisted source checkpoints.
            except Exception as exc:
                logger.exception("Bộ học thư viện trả lời bị lỗi")
                self._set_job(status="error", error=str(exc), phase="", last_run=time.time())


bo_hoc_tra_loi = AnswerBankLearning()
