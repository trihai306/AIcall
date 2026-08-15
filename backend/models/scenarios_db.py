"""SQLite repository for call scenarios (kịch bản).

A scenario is everything about a call that changes when you point the system at
a different industry: who the bot says it works for, what it opens with, the
extra rules and worked examples fed to the LLM, which slice of the knowledge
base it may quote, and when it should hand over to a human.

What a scenario may NOT change lives in `services/llm_service.py` as
`CORE_RULES` - those encode fixes for real failures (the bot inventing interest
rates, listing six documents down a phone line, echoing an STT typo back at the
customer) and a new industry does not make them stop applying.

Rows live in the same SQLite file as everything else; see `models/db.py`.
"""

import asyncio
import json
import time
import uuid

from backend.models import db

DIRECTIONS = ("outbound", "inbound", "both")

# Điều kiện chuyển tiếp sang người thật. Xem services/transfer_service.py.
TRANSFER_TRIGGERS = (
    "khach_yeu_cau",   # khách nói thẳng "cho tôi gặp người thật"
    "ngoai_pham_vi",   # bot trả lời "ngoài phạm vi" quá 2 lượt liên tiếp
    "khong_tim_thay",  # RAG không có mảnh nào liên quan 2 lượt liên tiếp
    "het_luot",        # vượt max_turns
)

EDITABLE_FIELDS = (
    "name", "industry", "org_name", "agent_name", "opening_line", "rules",
    "examples", "knowledge_tag", "max_turns", "transfer_number", "transfer_on",
    "transfer_message", "direction", "note",
)

_DEFAULT_TRANSFER_MESSAGE = "Dạ em xin phép nối máy cho chuyên viên ạ"


def _row(r) -> dict:
    """Turn a row into a dict, expanding the two JSON columns.

    `examples` and `transfer_on` are stored as JSON text because SQLite has no
    list type. Callers get real lists; a row written by hand with malformed
    JSON degrades to empty rather than taking the whole page down.
    """
    d = dict(r)
    for key, fallback in (("examples", []), ("transfer_on", [])):
        raw = d.get(key) or ""
        try:
            value = json.loads(raw) if raw else fallback
        except (ValueError, TypeError):
            value = fallback
        d[key] = value if isinstance(value, list) else fallback
    d["is_default"] = bool(d.get("is_default"))
    return d


# --- reads -------------------------------------------------------------------

def _list_sync(direction: str | None) -> list[dict]:
    conn = db.connection()
    if conn is None:
        return []
    clause, params = ("", [])
    if direction:
        # 'both' answers to either side, so an inbound query must match it too.
        clause = "WHERE direction = ? OR direction = 'both'"
        params = [direction]
    with db.write_lock:
        rows = conn.execute(
            f"SELECT * FROM scenarios {clause} ORDER BY is_default DESC, created_at DESC",
            params,
        ).fetchall()
    return [_row(r) for r in rows]


async def list_scenarios(direction: str | None = None) -> list[dict]:
    return await asyncio.to_thread(_list_sync, direction)


def _get_sync(scenario_id: str) -> dict | None:
    conn = db.connection()
    if conn is None or not scenario_id:
        return None
    with db.write_lock:
        row = conn.execute(
            "SELECT * FROM scenarios WHERE scenario_id = ?", (scenario_id,)
        ).fetchone()
    return _row(row) if row else None


async def get_scenario(scenario_id: str) -> dict | None:
    return await asyncio.to_thread(_get_sync, scenario_id)


def _get_default_sync(direction: str) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None
    with db.write_lock:
        row = conn.execute(
            "SELECT * FROM scenarios WHERE is_default = 1 "
            "AND (direction = ? OR direction = 'both') LIMIT 1",
            (direction,),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM scenarios WHERE direction = ? OR direction = 'both' "
                "ORDER BY created_at LIMIT 1",
                (direction,),
            ).fetchone()
    return _row(row) if row else None


async def get_default(direction: str = "outbound") -> dict | None:
    """The scenario to use when a campaign or device names none."""
    return await asyncio.to_thread(_get_default_sync, direction)


async def resolve(scenario_id: str = "", direction: str = "outbound") -> dict:
    """Scenario by id, falling back to the default, falling back to {}.

    Returns a dict either way so callers never have to null-check before
    reading a field - an empty dict makes the helpers below fall back to the
    values in .env, which is exactly the pre-scenario behaviour.
    """
    if scenario_id:
        found = await get_scenario(scenario_id)
        if found:
            return found
    return await get_default(direction) or {}


# --- tên xưng hô: MỘT chỗ duy nhất -------------------------------------------
#
# Ba đường cùng phải xưng tên tổ chức: prompt cho LLM, bảng lượt thường gặp, và
# câu mở đầu cuộc gọi ra. Trước đây mỗi đường tự đọc lấy - đường LLM đọc kịch
# bản còn hai đường kia đọc thẳng `.env`, nên đổi tên trong kịch bản xong thì
# trong CÙNG một cuộc gọi, câu chào sẵn nói một tên còn câu mô hình sinh nói tên
# khác. Gom về đây để không thể lệch nữa.
#
# `.env` chỉ còn là lưới cuối cho phiên chưa kịp gắn kịch bản; nguồn thật là
# CSDL. Xem `core/startup.ensure_default` - nó chỉ gieo mầm khi bảng còn trống.

def ten_to_chuc(scenario: dict | None) -> str:
    from backend.config import settings
    return (scenario or {}).get("org_name") or settings.bank_name


def ten_nhan_vien(scenario: dict | None) -> str:
    from backend.config import settings
    return (scenario or {}).get("agent_name") or settings.agent_name


# --- writes ------------------------------------------------------------------

def _clean(fields: dict) -> dict:
    """Keep only editable keys, and JSON-encode the two list columns."""
    out = {}
    for key, value in fields.items():
        if key not in EDITABLE_FIELDS or value is None:
            continue
        if key in ("examples", "transfer_on"):
            out[key] = json.dumps(value if isinstance(value, list) else [], ensure_ascii=False)
        elif key == "max_turns":
            # 0 or a negative number would end every call before it starts.
            out[key] = max(1, int(value))
        else:
            out[key] = value
    return out


def _create_sync(fields: dict) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None

    data = _clean(fields)
    data.setdefault("name", "Kịch bản mới")
    data.setdefault("transfer_message", _DEFAULT_TRANSFER_MESSAGE)
    if data.get("direction") not in DIRECTIONS:
        data["direction"] = "outbound"

    scenario_id = f"sc_{uuid.uuid4().hex[:8]}"
    columns = ["scenario_id", *data.keys(), "created_at"]
    values = [scenario_id, *data.values(), time.time()]

    with db.write_lock, conn:
        conn.execute(
            f"INSERT INTO scenarios ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})",
            values,
        )
    return _get_sync(scenario_id)


async def create_scenario(**fields) -> dict | None:
    return await asyncio.to_thread(_create_sync, fields)


def _update_sync(scenario_id: str, fields: dict) -> dict | None:
    conn = db.connection()
    if conn is None:
        return None

    data = _clean(fields)
    if data.get("direction") and data["direction"] not in DIRECTIONS:
        data.pop("direction")

    if data:
        assignments = ", ".join(f"{k} = ?" for k in data)
        with db.write_lock, conn:
            conn.execute(
                f"UPDATE scenarios SET {assignments} WHERE scenario_id = ?",
                (*data.values(), scenario_id),
            )
    return _get_sync(scenario_id)


async def update_scenario(scenario_id: str, **fields) -> dict | None:
    return await asyncio.to_thread(_update_sync, scenario_id, fields)


def _set_default_sync(scenario_id: str) -> bool:
    conn = db.connection()
    if conn is None:
        return False
    with db.write_lock, conn:
        row = conn.execute(
            "SELECT direction FROM scenarios WHERE scenario_id = ?", (scenario_id,)
        ).fetchone()
        if row is None:
            return False
        # Default is per direction: an inbound scenario becoming default must
        # not unset the outbound one the campaigns are relying on.
        conn.execute(
            "UPDATE scenarios SET is_default = 0 WHERE direction = ?", (row["direction"],)
        )
        conn.execute(
            "UPDATE scenarios SET is_default = 1 WHERE scenario_id = ?", (scenario_id,)
        )
    return True


async def set_default(scenario_id: str) -> bool:
    return await asyncio.to_thread(_set_default_sync, scenario_id)


def _delete_sync(scenario_id: str) -> bool:
    conn = db.connection()
    if conn is None:
        return False
    with db.write_lock, conn:
        cur = conn.execute("DELETE FROM scenarios WHERE scenario_id = ?", (scenario_id,))
        if cur.rowcount:
            # campaigns.scenario_id is plain TEXT (see db._ADDED_COLUMNS on why
            # there is no REFERENCES), so the dangling id is cleared here.
            # Those campaigns fall back to the default scenario.
            conn.execute(
                "UPDATE campaigns SET scenario_id = '' WHERE scenario_id = ?", (scenario_id,)
            )
            conn.execute(
                "UPDATE devices SET inbound_scenario_id = '' WHERE inbound_scenario_id = ?",
                (scenario_id,),
            )
    return cur.rowcount > 0


async def delete_scenario(scenario_id: str) -> bool:
    return await asyncio.to_thread(_delete_sync, scenario_id)


# --- first run ----------------------------------------------------------------

def _seed_sync(org_name: str, agent_name: str) -> bool:
    """Create the banking scenario the system shipped with, once.

    Without this an upgraded install has no scenarios at all, every campaign
    resolves to {} and the bot silently loses the worked examples and the STT
    typo hints that used to be hard-coded in the prompt.
    """
    conn = db.connection()
    if conn is None:
        return False
    with db.write_lock, conn:
        if conn.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0]:
            return False
        conn.execute(
            "INSERT INTO scenarios (scenario_id, name, industry, org_name, agent_name, "
            "opening_line, rules, examples, max_turns, transfer_message, direction, "
            "is_default, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (
                "sc_nganhang",
                "Tư vấn vay ngân hàng",
                "ngân hàng",
                org_name,
                agent_name,
                f"Dạ em chào anh/chị, em là {agent_name} bên {org_name} ạ.",
                # Gợi ý sửa lỗi chép âm: đặc thù ngành, nên thuộc về kịch bản.
                # Luật chung "hãy đoán ý thật trước khi trả lời" nằm ở CORE_RULES.
                "Bản ghi hay sai các từ sau, hiểu theo nghĩa đúng: "
                '"lãnh xuất" là "lãi suất", "cẩn cước" là "căn cước", '
                '"tính chấp" là "tín chấp", "hạng mức" là "hạn mức".',
                json.dumps(
                    [
                        {
                            "khach": "Lãi suất vay bao nhiêu?",
                            "tu_van": "Dạ hiện bên em lãi suất từ (số trong THÔNG TIN THAM KHẢO) "
                                      "phần trăm một năm ạ. Anh/chị định vay khoảng bao nhiêu ạ?",
                        },
                        {
                            "khach": "Tôi bận lắm.",
                            "tu_van": "Dạ em xin lỗi đã làm phiền ạ. Em xin phép gọi lại lúc khác ạ.",
                        },
                        {
                            "khach": "Cần giấy tờ gì?",
                            "tu_van": "Dạ chỉ cần căn cước và sao kê lương ba tháng gần nhất ạ.",
                        },
                        {
                            "khach": "Mở thẻ tín dụng cần những giấy tờ gì?",
                            "tu_van": "Dạ anh/chị chuẩn bị căn cước và sao kê lương ba tháng ạ. "
                                      "Anh/chị đang làm ở đâu để em tư vấn hạn mức ạ?",
                        },
                    ],
                    ensure_ascii=False,
                ),
                20,
                _DEFAULT_TRANSFER_MESSAGE,
                "both",
                "Kịch bản mặc định, tạo tự động từ cấu hình trong .env",
                time.time(),
            ),
        )
    return True


async def ensure_default(org_name: str, agent_name: str) -> bool:
    """Seed the shipped scenario if the table is empty. Safe to call every boot."""
    return await asyncio.to_thread(_seed_sync, org_name, agent_name)
