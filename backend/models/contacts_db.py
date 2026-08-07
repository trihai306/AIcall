"""SQLite repository for the outbound call list: contacts, campaigns, attempts.

Rows live in the same file as the call history - see backend/models/db.py for
the schema and the no-migration policy. Reads and writes run in a worker thread
so the voice pipeline never blocks on disk I/O.
"""

import asyncio
import re
import time
import uuid

from backend.models import db

CONTACT_STATUSES = (
    "pending",    # chưa gọi, hoặc đang chờ tới lượt gọi lại
    "calling",    # đang gọi
    "done",       # đã gọi xong
    "no_answer",  # không nghe máy
    "busy",       # máy bận
    "voicemail",  # vào hộp thư thoại
    "refused",    # từ chối
    "invalid",    # số không hợp lệ
    "dnc",        # yêu cầu không gọi lại
)

# Kết quả một lần gọi có thể xin gọi lại. Khác CONTACT_STATUSES ở chỗ đây là
# kết quả của MỘT lần bấm số, còn kia là trạng thái cuối cùng của số đó.
RETRYABLE = ("no_answer", "busy", "voicemail")

CAMPAIGN_STATUSES = ("draft", "running", "paused", "done")

# Mọi thứ sửa được của một chiến dịch. Phải khớp với `_ADDED_COLUMNS["campaigns"]`
# trong models/db.py - thêm cột ở đó mà quên ở đây thì cột mới không lưu được.
CAMPAIGN_FIELDS = (
    "name", "product", "status", "note",
    "scenario_id", "voice_name", "device_ids", "concurrency",
    "field1_label", "field2_label", "field3_label",
    "retry_no_answer", "retry_busy", "retry_voicemail", "retry_max", "retry_delay_min",
    "start_date", "end_date", "call_windows", "timezone",
    "on_voicemail", "detect_gender", "record_calls",
    "started_at", "paused_at",
)

EDITABLE_FIELDS = (
    "phone", "name", "product", "campaign_id", "status", "note",
    "field1", "field2", "field3", "next_retry_at", "retry_reason",
)

_DIGITS = re.compile(r"[^\d+]")


def normalize_phone(raw: str) -> str:
    """Strip formatting and put Vietnamese numbers in a single 0xxxxxxxxx shape.

    `+84 912 345 678`, `0084-912345678` and `0912.345.678` are the same lead;
    without this the UNIQUE index on `phone` would happily store all three.
    """
    p = _DIGITS.sub("", (raw or "").strip())
    if p.startswith("+84"):
        p = "0" + p[3:]
    elif p.startswith("0084"):
        p = "0" + p[4:]
    elif p.startswith("84") and len(p) >= 11:
        p = "0" + p[2:]
    return p.lstrip("+")


def _row(r) -> dict:
    return dict(r)


# --- contacts: reads ---------------------------------------------------------

def _list_contacts_sync(
    campaign_id: str | None,
    status: str | None,
    search: str | None,
    page: int,
    limit: int,
    fields: dict | None = None,
) -> dict:
    conn = db.connection()
    if conn is None:
        return {"contacts": [], "total": 0}

    where, params = [], []
    if campaign_id:
        where.append("campaign_id = ?")
        params.append(campaign_id)
    if status:
        where.append("status = ?")
        params.append(status)
    if search:
        where.append("(phone LIKE ? OR name LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    # Lọc theo trường tuỳ biến. Tên cột lấy từ hằng số chứ không từ đầu vào -
    # chuỗi do người dùng gửi không bao giờ được ghép thẳng vào câu SQL.
    for col in ("field1", "field2", "field3"):
        value = (fields or {}).get(col)
        if value:
            where.append(f"{col} = ?")
            params.append(value)
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    offset = max(0, (page - 1) * limit)
    with db.write_lock:
        (total,) = conn.execute(
            f"SELECT COUNT(*) FROM contacts {clause}", params
        ).fetchone()
        rows = conn.execute(
            f"SELECT * FROM contacts {clause} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
    return {"contacts": [_row(r) for r in rows], "total": total}


async def list_contacts(
    campaign_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 50,
    fields: dict | None = None,
) -> dict:
    """A page of contacts plus the total matching the same filters.

    `fields` filters on the operator-defined columns, e.g.
    {"field1": "Chi nhánh Hà Nội"}.
    """
    return await asyncio.to_thread(
        _list_contacts_sync, campaign_id, status, search, page, limit, fields
    )


def _get_contact_sync(contact_id: str) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None
    with db.write_lock:
        row = conn.execute(
            "SELECT * FROM contacts WHERE contact_id = ?", (contact_id,)
        ).fetchone()
    return _row(row) if row else None


async def get_contact(contact_id: str) -> dict | None:
    return await asyncio.to_thread(_get_contact_sync, contact_id)


def _stats_sync(campaign_id: str | None) -> dict:
    conn = db.connection()
    if conn is None:
        return {"total": 0, "by_status": {}}

    clause, params = ("WHERE campaign_id = ?", [campaign_id]) if campaign_id else ("", [])
    with db.write_lock:
        rows = conn.execute(
            f"SELECT status, COUNT(*) AS n FROM contacts {clause} GROUP BY status",
            params,
        ).fetchall()
    by_status = {r["status"]: r["n"] for r in rows}
    return {"total": sum(by_status.values()), "by_status": by_status}


async def contact_stats(campaign_id: str | None = None) -> dict:
    """Lead counts per status, for the progress bar on the contacts page."""
    return await asyncio.to_thread(_stats_sync, campaign_id)


def _next_pending_sync(campaign_id: str | None) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None
    clause, params = ("AND campaign_id = ?", [campaign_id]) if campaign_id else ("", [])
    with db.write_lock:
        row = conn.execute(
            f"SELECT * FROM contacts WHERE status = 'pending' {clause} "
            "ORDER BY created_at LIMIT 1",
            params,
        ).fetchone()
    return _row(row) if row else None


async def next_pending(campaign_id: str | None = None) -> dict | None:
    """Oldest not-yet-called contact - what the 'gọi tiếp' button dials."""
    return await asyncio.to_thread(_next_pending_sync, campaign_id)


# --- contacts: writes --------------------------------------------------------

def _create_contact_sync(fields: dict) -> dict | str:
    conn = db.connection()
    if conn is None:
        return "database chưa sẵn sàng"

    phone = normalize_phone(fields.get("phone", ""))
    if not phone:
        return "Số điện thoại trống"

    with db.write_lock, conn:
        exists = conn.execute(
            "SELECT contact_id FROM contacts WHERE phone = ?", (phone,)
        ).fetchone()
        if exists:
            return f"Số {phone} đã có trong danh bạ"

        contact_id = f"ct_{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO contacts "
            "(contact_id, phone, name, product, campaign_id, status, note, "
            " field1, field2, field3, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                contact_id,
                phone,
                fields.get("name", ""),
                fields.get("product", ""),
                fields.get("campaign_id") or None,
                fields.get("status", "pending"),
                fields.get("note", ""),
                fields.get("field1", ""),
                fields.get("field2", ""),
                fields.get("field3", ""),
                time.time(),
            ),
        )
    return _get_contact_sync(contact_id)


async def create_contact(**fields) -> dict | str:
    """Insert one contact. Returns the row, or an error message string."""
    return await asyncio.to_thread(_create_contact_sync, fields)


def _import_sync(rows: list[dict], campaign_id: str | None) -> dict:
    conn = db.connection()
    if conn is None:
        return {"added": 0, "updated": 0, "skipped": 0}

    added = updated = skipped = 0
    now = time.time()
    with db.write_lock, conn:
        for r in rows:
            phone = normalize_phone(r.get("phone", ""))
            if not phone:
                skipped += 1
                continue

            existing = conn.execute(
                "SELECT contact_id FROM contacts WHERE phone = ?", (phone,)
            ).fetchone()
            if existing:
                # Re-importing a list must not reset the call outcome, only fill
                # in the descriptive fields the new file carries.
                conn.execute(
                    "UPDATE contacts SET "
                    "name = COALESCE(NULLIF(?, ''), name), "
                    "product = COALESCE(NULLIF(?, ''), product), "
                    "note = COALESCE(NULLIF(?, ''), note), "
                    "field1 = COALESCE(NULLIF(?, ''), field1), "
                    "field2 = COALESCE(NULLIF(?, ''), field2), "
                    "field3 = COALESCE(NULLIF(?, ''), field3), "
                    "campaign_id = COALESCE(?, campaign_id) "
                    "WHERE contact_id = ?",
                    (
                        r.get("name", ""),
                        r.get("product", ""),
                        r.get("note", ""),
                        r.get("field1", ""),
                        r.get("field2", ""),
                        r.get("field3", ""),
                        campaign_id,
                        existing["contact_id"],
                    ),
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO contacts "
                    "(contact_id, phone, name, product, campaign_id, status, note, "
                    " field1, field2, field3, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)",
                    (
                        f"ct_{uuid.uuid4().hex[:8]}",
                        phone,
                        r.get("name", ""),
                        r.get("product", ""),
                        campaign_id,
                        r.get("note", ""),
                        r.get("field1", ""),
                        r.get("field2", ""),
                        r.get("field3", ""),
                        now,
                    ),
                )
                added += 1
    return {"added": added, "updated": updated, "skipped": skipped}


async def import_contacts(rows: list[dict], campaign_id: str | None = None) -> dict:
    """Bulk upsert by phone number. Existing leads keep their call status."""
    return await asyncio.to_thread(_import_sync, rows, campaign_id)


def _update_contact_sync(contact_id: str, fields: dict) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None

    updates = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS and v is not None}
    if "phone" in updates:
        updates["phone"] = normalize_phone(updates["phone"])
    if "campaign_id" in updates:
        updates["campaign_id"] = updates["campaign_id"] or None

    if updates:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        with db.write_lock, conn:
            conn.execute(
                f"UPDATE contacts SET {assignments} WHERE contact_id = ?",
                (*updates.values(), contact_id),
            )
    return _get_contact_sync(contact_id)


async def update_contact(contact_id: str, **fields) -> dict | None:
    return await asyncio.to_thread(_update_contact_sync, contact_id, fields)


def _delete_contact_sync(contact_id: str) -> bool:
    conn = db.connection()
    if conn is None:
        return False
    with db.write_lock, conn:
        cur = conn.execute("DELETE FROM contacts WHERE contact_id = ?", (contact_id,))
    return cur.rowcount > 0


async def delete_contact(contact_id: str) -> bool:
    return await asyncio.to_thread(_delete_contact_sync, contact_id)


def _delete_many_sync(contact_ids: list[str]) -> int:
    conn = db.connection()
    if conn is None or not contact_ids:
        return 0
    placeholders = ",".join("?" * len(contact_ids))
    with db.write_lock, conn:
        cur = conn.execute(
            f"DELETE FROM contacts WHERE contact_id IN ({placeholders})", contact_ids
        )
    return cur.rowcount


async def delete_contacts(contact_ids: list[str]) -> int:
    return await asyncio.to_thread(_delete_many_sync, contact_ids)


# --- call attempts -----------------------------------------------------------

def _record_attempt_sync(
    contact_id: str,
    device_id: str | None,
    session_id: str | None,
    status: str,
    detail: str,
    contact_status: str | None,
) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None

    now = time.time()
    with db.write_lock, conn:
        row = conn.execute(
            "SELECT phone FROM contacts WHERE contact_id = ?", (contact_id,)
        ).fetchone()
        if row is None:
            return None

        conn.execute(
            "INSERT INTO call_attempts "
            "(contact_id, phone, device_id, session_id, status, detail, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (contact_id, row["phone"], device_id, session_id, status, detail, now),
        )
        conn.execute(
            "UPDATE contacts SET attempts = attempts + 1, last_called_at = ?, "
            "last_session_id = COALESCE(?, last_session_id), "
            "status = COALESCE(?, status) WHERE contact_id = ?",
            (now, session_id, contact_status, contact_id),
        )
    return _get_contact_sync(contact_id)


async def record_attempt(
    contact_id: str,
    device_id: str | None = None,
    session_id: str | None = None,
    status: str = "dialed",
    detail: str = "",
    contact_status: str | None = None,
) -> dict | None:
    """Log one dial and bump the contact's counters. Returns the updated contact."""
    return await asyncio.to_thread(
        _record_attempt_sync, contact_id, device_id, session_id, status, detail, contact_status
    )


def _list_attempts_sync(contact_id: str, limit: int) -> list[dict]:
    conn = db.connection()
    if conn is None:
        return []
    with db.write_lock:
        rows = conn.execute(
            "SELECT * FROM call_attempts WHERE contact_id = ? "
            "ORDER BY started_at DESC LIMIT ?",
            (contact_id, limit),
        ).fetchall()
    return [_row(r) for r in rows]


async def list_attempts(contact_id: str, limit: int = 20) -> list[dict]:
    """Call history of a single number, newest first."""
    return await asyncio.to_thread(_list_attempts_sync, contact_id, limit)


# --- campaigns ---------------------------------------------------------------

def _list_campaigns_sync() -> list[dict]:
    conn = db.connection()
    if conn is None:
        return []
    with db.write_lock:
        rows = conn.execute(
            "SELECT c.*, "
            "  (SELECT COUNT(*) FROM contacts ct WHERE ct.campaign_id = c.campaign_id) AS total, "
            "  (SELECT COUNT(*) FROM contacts ct WHERE ct.campaign_id = c.campaign_id "
            "   AND ct.status = 'pending') AS pending "
            "FROM campaigns c ORDER BY c.created_at DESC"
        ).fetchall()
    return [_row(r) for r in rows]


async def list_campaigns() -> list[dict]:
    """Campaigns with their lead counts."""
    return await asyncio.to_thread(_list_campaigns_sync)


def _get_campaign_sync(campaign_id: str) -> dict | None:
    conn = db.connection()
    if conn is None or not campaign_id:
        return None
    with db.write_lock:
        row = conn.execute(
            "SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
    return _row(row) if row else None


async def get_campaign(campaign_id: str) -> dict | None:
    return await asyncio.to_thread(_get_campaign_sync, campaign_id)


def _create_campaign_sync(fields: dict) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None
    campaign_id = f"cp_{uuid.uuid4().hex[:8]}"
    with db.write_lock, conn:
        conn.execute(
            "INSERT INTO campaigns (campaign_id, name, product, status, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                campaign_id,
                fields.get("name", "Chiến dịch mới"),
                fields.get("product", ""),
                fields.get("status", "draft"),
                fields.get("note", ""),
                time.time(),
            ),
        )
        row = conn.execute(
            "SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
    return _row(row) if row else None


async def create_campaign(**fields) -> dict | None:
    return await asyncio.to_thread(_create_campaign_sync, fields)


def _update_campaign_sync(campaign_id: str, fields: dict) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None

    updates = {k: v for k, v in fields.items() if k in CAMPAIGN_FIELDS and v is not None}
    with db.write_lock, conn:
        if updates:
            assignments = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE campaigns SET {assignments} WHERE campaign_id = ?",
                (*updates.values(), campaign_id),
            )
        row = conn.execute(
            "SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
    return _row(row) if row else None


async def update_campaign(campaign_id: str, **fields) -> dict | None:
    return await asyncio.to_thread(_update_campaign_sync, campaign_id, fields)


def _delete_campaign_sync(campaign_id: str) -> bool:
    conn = db.connection()
    if conn is None:
        return False
    # contacts.campaign_id is ON DELETE SET NULL: the leads survive, they just
    # go back to the unassigned pool.
    with db.write_lock, conn:
        cur = conn.execute(
            "DELETE FROM campaigns WHERE campaign_id = ?", (campaign_id,)
        )
    return cur.rowcount > 0


async def delete_campaign(campaign_id: str) -> bool:
    return await asyncio.to_thread(_delete_campaign_sync, campaign_id)


# --- nhập số từ chiến dịch khác ----------------------------------------------

def _import_from_campaign_sync(
    target_campaign_id: str,
    source_campaign_id: str,
    statuses: list[str],
    min_attempts: int,
    max_attempts: int,
    reset_status: bool,
) -> dict:
    conn = db.connection()
    if conn is None:
        return {"imported": 0, "skipped": 0, "error": "database chưa sẵn sàng"}
    if target_campaign_id == source_campaign_id:
        return {"imported": 0, "skipped": 0, "error": "Chiến dịch nguồn và đích trùng nhau"}

    valid = [s for s in statuses if s in CONTACT_STATUSES]
    if not valid:
        return {"imported": 0, "skipped": 0, "error": "Chưa chọn trạng thái nào để lấy"}

    placeholders = ",".join("?" * len(valid))
    with db.write_lock, conn:
        if conn.execute(
            "SELECT 1 FROM campaigns WHERE campaign_id = ?", (target_campaign_id,)
        ).fetchone() is None:
            return {"imported": 0, "skipped": 0, "error": "Chiến dịch đích không tồn tại"}

        rows = conn.execute(
            f"SELECT contact_id FROM contacts WHERE campaign_id = ? "
            f"AND status IN ({placeholders}) AND attempts >= ? AND attempts <= ?",
            (source_campaign_id, *valid, min_attempts, max_attempts),
        ).fetchall()
        if not rows:
            return {"imported": 0, "skipped": 0}

        ids = [r["contact_id"] for r in rows]
        marks = ",".join("?" * len(ids))
        # `contacts.phone` là UNIQUE nên một số chỉ thuộc MỘT chiến dịch tại một
        # thời điểm - đây là CHUYỂN chứ không phải nhân bản. Lịch sử ở
        # call_attempts vẫn giữ nguyên, tra lại được đầy đủ.
        if reset_status:
            conn.execute(
                f"UPDATE contacts SET campaign_id = ?, status = 'pending', "
                f"next_retry_at = NULL, retry_reason = '' WHERE contact_id IN ({marks})",
                (target_campaign_id, *ids),
            )
        else:
            conn.execute(
                f"UPDATE contacts SET campaign_id = ? WHERE contact_id IN ({marks})",
                (target_campaign_id, *ids),
            )
    return {"imported": len(ids), "skipped": 0}


async def import_from_campaign(
    target_campaign_id: str,
    source_campaign_id: str,
    statuses: list[str],
    min_attempts: int = 0,
    max_attempts: int = 99,
    reset_status: bool = True,
) -> dict:
    """Move numbers matching a filter from one campaign into another.

    The contract asks for "nhập từ chiến dịch khác (các số đã gọi nhưng bận,
    hoặc không nhấc máy...)", so the usual call passes
    statuses=["busy", "no_answer"].
    """
    return await asyncio.to_thread(
        _import_from_campaign_sync, target_campaign_id, source_campaign_id,
        statuses, min_attempts, max_attempts, reset_status,
    )


# --- chọn số kế tiếp cho bộ quay số tự động -----------------------------------

def _claim_next_sync(campaign_id: str | None) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None

    clause, params = ("AND campaign_id = ?", [campaign_id]) if campaign_id else ("", [])
    now = time.time()
    with db.write_lock, conn:
        # Số tới hạn gọi lại đi trước số chưa gọi lần nào: nó có mốc thời gian
        # phải tôn trọng, còn số mới thì gọi lúc nào cũng được.
        row = conn.execute(
            f"SELECT * FROM contacts WHERE status = 'pending' {clause} "
            "AND (next_retry_at IS NULL OR next_retry_at <= ?) "
            "ORDER BY (next_retry_at IS NULL), next_retry_at, created_at LIMIT 1",
            (*params, now),
        ).fetchone()
        if row is None:
            return None
        # Đánh dấu 'calling' NGAY trong cùng ổ khoá: chạy nhiều máy song song thì
        # hai luồng đọc cùng lúc sẽ cùng nhận một số và gọi khách hai lần.
        conn.execute(
            "UPDATE contacts SET status = 'calling' WHERE contact_id = ?",
            (row["contact_id"],),
        )
    return _get_contact_sync(row["contact_id"])


async def claim_next(campaign_id: str | None = None) -> dict | None:
    """Take the next number to dial and mark it 'calling' atomically.

    Returns None when the campaign has nothing due right now - which is not the
    same as being finished; a retry may fall due in ten minutes. Use
    `pending_summary` to tell those apart.
    """
    return await asyncio.to_thread(_claim_next_sync, campaign_id)


def _pending_summary_sync(campaign_id: str | None) -> dict:
    conn = db.connection()
    if conn is None:
        return {"san_sang": 0, "cho_goi_lai": 0, "moc_ke_tiep": None}

    clause, params = ("AND campaign_id = ?", [campaign_id]) if campaign_id else ("", [])
    now = time.time()
    with db.write_lock:
        ready = conn.execute(
            f"SELECT COUNT(*) FROM contacts WHERE status = 'pending' {clause} "
            "AND (next_retry_at IS NULL OR next_retry_at <= ?)",
            (*params, now),
        ).fetchone()[0]
        row = conn.execute(
            f"SELECT COUNT(*) AS n, MIN(next_retry_at) AS moc FROM contacts "
            f"WHERE status = 'pending' {clause} AND next_retry_at > ?",
            (*params, now),
        ).fetchone()
    return {"san_sang": ready, "cho_goi_lai": row["n"], "moc_ke_tiep": row["moc"]}


async def pending_summary(campaign_id: str | None = None) -> dict:
    """How many numbers are dialable now, how many are waiting on a retry clock."""
    return await asyncio.to_thread(_pending_summary_sync, campaign_id)


def _finish_attempt_sync(
    contact_id: str, ket_qua: str, campaign: dict, note: str
) -> dict | None:
    """Apply the retry policy after one dial and write the final state."""
    conn = db.connection()
    if conn is None:
        return None

    with db.write_lock, conn:
        row = conn.execute(
            "SELECT attempts FROM contacts WHERE contact_id = ?", (contact_id,)
        ).fetchone()
        if row is None:
            return None

        bat = {
            "no_answer": campaign.get("retry_no_answer", 1),
            "busy": campaign.get("retry_busy", 1),
            "voicemail": campaign.get("retry_voicemail", 0),
        }
        retry_max = int(campaign.get("retry_max", 3) or 3)
        delay_min = max(1, int(campaign.get("retry_delay_min", 30) or 30))

        con_luot = row["attempts"] < retry_max
        goi_lai = ket_qua in RETRYABLE and bool(bat.get(ket_qua)) and con_luot

        if goi_lai:
            # Quay lại 'pending' nhưng có mốc thời gian: bộ chọn số ở trên sẽ bỏ
            # qua nó cho tới khi tới hạn.
            conn.execute(
                "UPDATE contacts SET status = 'pending', next_retry_at = ?, "
                "retry_reason = ?, note = COALESCE(NULLIF(?, ''), note) "
                "WHERE contact_id = ?",
                (time.time() + delay_min * 60, ket_qua, note, contact_id),
            )
        else:
            conn.execute(
                "UPDATE contacts SET status = ?, next_retry_at = NULL, retry_reason = '', "
                "note = COALESCE(NULLIF(?, ''), note) WHERE contact_id = ?",
                (ket_qua if ket_qua in CONTACT_STATUSES else "done", note, contact_id),
            )
    return _get_contact_sync(contact_id)


async def finish_attempt(
    contact_id: str, ket_qua: str, campaign: dict | None = None, note: str = ""
) -> dict | None:
    """Close out one dial: either schedule a retry or write the final status.

    `ket_qua` is the outcome of THIS dial (done | no_answer | busy | voicemail |
    refused | invalid | dnc). `campaign` carries the retry policy; pass {} and
    nothing is ever retried.
    """
    return await asyncio.to_thread(
        _finish_attempt_sync, contact_id, ket_qua, campaign or {}, note
    )
