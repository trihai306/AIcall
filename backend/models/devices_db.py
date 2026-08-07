"""SQLite repository for the calling devices the system dials through.

A "device" is whatever bridges the app to the phone network: a handset paired
through a phone-gateway app, an ADB handset, a USB GSM modem, a SIP
trunk, or a plain sound card. Rows live in the same file as the call history -
see backend/models/db.py for the schema and the no-migration policy.

Every write goes through `asyncio.to_thread` so the voice pipeline never waits
on disk I/O.
"""

import asyncio
import time
import uuid

from backend.models import db

# Fields the UI is allowed to write. Everything else (status, last_seen,
# is_default) is owned by the backend.
EDITABLE_FIELDS = (
    "name", "kind", "address", "dial_url", "phone_number", "note",
    # Bot nhận cuộc gọi đến - xem services/inbound_service.py
    "inbound_enabled", "inbound_scenario_id", "inbound_delay_s",
)

KINDS = ("adb", "phone_link", "usb_modem", "sip", "audio")


def _row(r) -> dict:
    d = dict(r)
    d["is_default"] = bool(d["is_default"])
    return d


# --- reads -------------------------------------------------------------------

def _list_sync() -> list[dict]:
    conn = db.connection()
    if conn is None:
        return []
    with db.write_lock:
        rows = conn.execute(
            "SELECT * FROM devices ORDER BY is_default DESC, created_at"
        ).fetchall()
    return [_row(r) for r in rows]


async def list_devices() -> list[dict]:
    """All devices, the default one first."""
    return await asyncio.to_thread(_list_sync)


def _get_sync(device_id: str) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None
    with db.write_lock:
        row = conn.execute(
            "SELECT * FROM devices WHERE device_id = ?", (device_id,)
        ).fetchone()
    return _row(row) if row else None


async def get_device(device_id: str) -> dict | None:
    return await asyncio.to_thread(_get_sync, device_id)


def _get_default_sync() -> dict | None:
    conn = db.connection()
    if conn is None:
        return None
    with db.write_lock:
        row = conn.execute(
            "SELECT * FROM devices WHERE is_default = 1 LIMIT 1"
        ).fetchone()
        # No explicit default: fall back to the first device that reported in.
        if row is None:
            row = conn.execute(
                "SELECT * FROM devices ORDER BY created_at LIMIT 1"
            ).fetchone()
    return _row(row) if row else None


async def get_default_device() -> dict | None:
    """The device outbound calls go through when the caller doesn't pick one."""
    return await asyncio.to_thread(_get_default_sync)


# --- writes ------------------------------------------------------------------

def _create_sync(fields: dict) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None

    device_id = f"dev_{uuid.uuid4().hex[:8]}"
    now = time.time()
    with db.write_lock, conn:
        # First device added becomes the default, otherwise there is nothing to
        # dial through until the user remembers to pick one.
        (count,) = conn.execute("SELECT COUNT(*) FROM devices").fetchone()
        conn.execute(
            "INSERT INTO devices "
            "(device_id, name, kind, address, dial_url, phone_number, note, "
            " is_default, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                device_id,
                fields.get("name", ""),
                fields.get("kind", "phone_link"),
                fields.get("address", ""),
                fields.get("dial_url", ""),
                fields.get("phone_number", ""),
                fields.get("note", ""),
                1 if count == 0 else 0,
                now,
            ),
        )
    return _get_sync(device_id)


async def create_device(**fields) -> dict | None:
    return await asyncio.to_thread(_create_sync, fields)


def _update_sync(device_id: str, fields: dict) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None

    updates = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS and v is not None}
    if updates:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        with db.write_lock, conn:
            conn.execute(
                f"UPDATE devices SET {assignments} WHERE device_id = ?",
                (*updates.values(), device_id),
            )
    return _get_sync(device_id)


async def update_device(device_id: str, **fields) -> dict | None:
    return await asyncio.to_thread(_update_sync, device_id, fields)


def _delete_sync(device_id: str) -> bool:
    conn = db.connection()
    if conn is None:
        return False
    with db.write_lock, conn:
        cur = conn.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
        deleted = cur.rowcount > 0
        # Deleting the default leaves the fleet headless - promote the oldest
        # remaining device so calls keep working.
        if deleted:
            has_default = conn.execute(
                "SELECT 1 FROM devices WHERE is_default = 1 LIMIT 1"
            ).fetchone()
            if not has_default:
                conn.execute(
                    "UPDATE devices SET is_default = 1 WHERE device_id = "
                    "(SELECT device_id FROM devices ORDER BY created_at LIMIT 1)"
                )
    return deleted


async def delete_device(device_id: str) -> bool:
    return await asyncio.to_thread(_delete_sync, device_id)


def _set_default_sync(device_id: str) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None
    with db.write_lock, conn:
        conn.execute("UPDATE devices SET is_default = 0")
        conn.execute(
            "UPDATE devices SET is_default = 1 WHERE device_id = ?", (device_id,)
        )
    return _get_sync(device_id)


async def set_default(device_id: str) -> dict | None:
    return await asyncio.to_thread(_set_default_sync, device_id)


def _mark_status_sync(device_id: str, status: str, error: str) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None
    with db.write_lock, conn:
        conn.execute(
            "UPDATE devices SET status = ?, last_error = ?, "
            "last_seen = CASE WHEN ? = 'online' THEN ? ELSE last_seen END "
            "WHERE device_id = ?",
            (status, error, status, time.time(), device_id),
        )
    return _get_sync(device_id)


async def mark_status(device_id: str, status: str, error: str = "") -> dict | None:
    """Record the result of a connection check. `last_seen` only moves on success."""
    return await asyncio.to_thread(_mark_status_sync, device_id, status, error)
