"""Báo cáo cuộc gọi: chốt kết quả, chấm chất lượng, gắn nhãn, truy vấn có lọc.

Gom ba mục của Điều 6 vào một chỗ vì chúng đọc/ghi cùng một bảng:
    F14  chất lượng (suy ra tự động) + nhãn (người dùng bấm)
    F13  tóm tắt ý chính (do services/summarizer.py sinh, lưu ở đây)
    F15  trang báo cáo với đủ bộ lọc

RANH GIỚI VỚI models/db.py: db.py sở hữu các cột mà phiên đang chạy tự biết
(tên khách, số lượt, thời điểm). Mọi thứ quyết định SAU cuộc gọi - kết quả,
chất lượng, nhãn, đường dẫn bản ghi, tóm tắt - thuộc về file này. Chia như vậy
để một lần ghi muộn của pipeline không xoá mất thứ người dùng vừa đặt.
"""

import asyncio
import json
import logging
import time

from backend.models import db

logger = logging.getLogger(__name__)

# Kết quả một cuộc gọi, theo góc nhìn "có kết nối được không".
OUTCOMES = ("done", "no_answer", "busy", "voicemail", "failed")

# Chất lượng, theo góc nhìn "khách có tương tác không" - đúng các mức hợp đồng
# liệt kê: "có phản hồi, ko phản hồi, dập máy".
QUALITIES = (
    "co_phan_hoi",      # khách nói từ 2 lượt trở lên
    "it_phan_hoi",      # khách nói đúng 1 lượt
    "khong_phan_hoi",   # bắt máy nhưng không nói câu nào
    "dap_may",          # bắt máy rồi cúp ngay, dưới 10 giây, không nói gì
    "hop_thu_thoai",    # vào hộp thư thoại
    "khong_nghe_may",   # không ai bắt máy / máy bận / bấm số hỏng
)

NHAN_HIEN_THI = {
    "co_phan_hoi": "Có phản hồi",
    "it_phan_hoi": "Ít phản hồi",
    "khong_phan_hoi": "Không phản hồi",
    "dap_may": "Dập máy",
    "hop_thu_thoai": "Hộp thư thoại",
    "khong_nghe_may": "Không nghe máy",
}

_NGUONG_DAP_MAY_S = 10.0

# Các cột người dùng/hậu xử lý được phép sửa. Danh sách trắng: tên cột đi thẳng
# vào câu SQL nên không bao giờ được lấy từ dữ liệu người dùng gửi lên.
_SUA_DUOC = (
    "outcome", "quality", "label", "gender", "summary", "summary_json",
    "suggested_label", "summarized_at", "recording_path", "recording_size",
    "transferred_to", "transfer_reason",
)


def derive_quality(outcome: str, so_luot_khach: int, giay: float) -> str:
    """Chấm chất lượng từ những gì đo được. Không hỏi người dùng.

    Bắt người vận hành tự chấm vài nghìn cuộc thì họ sẽ không chấm, và cột lọc
    theo chất lượng của hợp đồng thành ra rỗng.
    """
    if outcome == "voicemail":
        return "hop_thu_thoai"
    if outcome in ("no_answer", "busy", "failed"):
        return "khong_nghe_may"
    if so_luot_khach >= 2:
        return "co_phan_hoi"
    if so_luot_khach == 1:
        return "it_phan_hoi"
    # Bắt máy nhưng không nói gì. Cúp trong 10 giây là dập máy; lâu hơn thì có
    # thể họ đang nghe mà không đáp - hai hành vi khác nhau, đừng gộp.
    return "dap_may" if giay < _NGUONG_DAP_MAY_S else "khong_phan_hoi"


# --- chốt một phiên -----------------------------------------------------------

def _finalize_sync(session_id: str, fields: dict) -> bool:
    conn = db.connection()
    if conn is None:
        return False
    data = {k: v for k, v in fields.items() if k in _SUA_DUOC and v is not None}
    if not data:
        return False
    assignments = ", ".join(f"{k} = ?" for k in data)
    with db.write_lock, conn:
        cur = conn.execute(
            f"UPDATE call_sessions SET {assignments} WHERE session_id = ?",
            (*data.values(), session_id),
        )
    return cur.rowcount > 0


async def update_session(session_id: str, **fields) -> bool:
    """Ghi các cột hậu-cuộc-gọi. Bỏ qua mọi khoá lạ."""
    return await asyncio.to_thread(_finalize_sync, session_id, fields)


async def finalize_session(session) -> dict:
    """Chốt một phiên vừa kết thúc: kết quả, chất lượng, bản ghi.

    Gọi sau `db.save_session(..., ended=True)`. Phần tóm tắt KHÔNG làm ở đây -
    nó cần LLM, mà LLM lúc đó đang phục vụ cuộc gọi khác; xem
    services/summarizer.py.
    """
    so_luot_khach = sum(1 for t in session.history if t.get("role") == "user")
    giay = time.time() - session.created_at
    outcome = session.outcome or ("done" if so_luot_khach else "no_answer")
    quality = derive_quality(outcome, so_luot_khach, giay)

    await update_session(
        session.session_id,
        outcome=outcome,
        quality=quality,
        gender=session.gender or None,
        recording_path=session.recording_path or None,
        recording_size=session.recording_size or None,
        transferred_to=session.transferred_to or None,
        transfer_reason=session.transfer_reason or None,
    )
    return {"outcome": outcome, "quality": quality, "so_luot_khach": so_luot_khach}


async def save_summary(session_id: str, tom_tat: str, chi_tiet: dict) -> bool:
    """Lưu bản tóm tắt do LLM sinh. `chi_tiet` là JSON có cấu trúc."""
    return await update_session(
        session_id,
        summary=tom_tat,
        summary_json=json.dumps(chi_tiet, ensure_ascii=False),
        suggested_label=chi_tiet.get("nhan_de_xuat", ""),
        summarized_at=time.time(),
    )


# --- nhãn ---------------------------------------------------------------------

def _labels_sync() -> list[dict]:
    conn = db.connection()
    if conn is None:
        return []
    with db.write_lock:
        rows = conn.execute("SELECT * FROM labels ORDER BY sort_order, name").fetchall()
    return [dict(r) for r in rows]


async def list_labels() -> list[dict]:
    return await asyncio.to_thread(_labels_sync)


def _upsert_label_sync(label_id: str, name: str, color: str, sort_order: int) -> dict:
    conn = db.connection()
    if conn is None:
        return {}
    with db.write_lock, conn:
        conn.execute(
            "INSERT INTO labels (label_id, name, color, sort_order) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(label_id) DO UPDATE SET "
            "name = excluded.name, color = excluded.color, sort_order = excluded.sort_order",
            (label_id, name, color, sort_order),
        )
        row = conn.execute("SELECT * FROM labels WHERE label_id = ?", (label_id,)).fetchone()
    return dict(row) if row else {}


async def upsert_label(label_id: str, name: str, color: str = "#888888",
                       sort_order: int = 0) -> dict:
    return await asyncio.to_thread(_upsert_label_sync, label_id, name, color, sort_order)


def _delete_label_sync(label_id: str) -> bool:
    conn = db.connection()
    if conn is None:
        return False
    with db.write_lock, conn:
        cur = conn.execute("DELETE FROM labels WHERE label_id = ?", (label_id,))
        # Phiên đang mang nhãn này thì gỡ nhãn ra, đừng để trỏ vào nhãn đã xoá:
        # bộ lọc trong báo cáo sẽ không bao giờ tìm thấy chúng nữa.
        if cur.rowcount:
            conn.execute(
                "UPDATE call_sessions SET label = '' WHERE label = ?", (label_id,)
            )
    return cur.rowcount > 0


async def delete_label(label_id: str) -> bool:
    return await asyncio.to_thread(_delete_label_sync, label_id)


def _set_label_sync(session_ids: list[str], label: str) -> int:
    conn = db.connection()
    if conn is None or not session_ids:
        return 0
    marks = ",".join("?" * len(session_ids))
    with db.write_lock, conn:
        cur = conn.execute(
            f"UPDATE call_sessions SET label = ? WHERE session_id IN ({marks})",
            (label, *session_ids),
        )
    return cur.rowcount


async def set_label(session_ids: list[str], label: str) -> int:
    """Gắn nhãn cho nhiều phiên một lúc. Chuỗi rỗng = gỡ nhãn."""
    return await asyncio.to_thread(_set_label_sync, session_ids, label)


# --- truy vấn báo cáo ---------------------------------------------------------

# Các cột lọc được. Ánh xạ tên tham số -> biểu thức SQL, để tên cột không bao
# giờ đến từ chuỗi người dùng gửi lên.
_LOC_BANG_NHAU = {
    "campaign_id": "s.campaign_id",
    "scenario_id": "s.scenario_id",
    "outcome": "s.outcome",
    "quality": "s.quality",
    "label": "s.label",
    "gender": "s.gender",
    "direction": "s.direction",
}
_LOC_TRUONG_TUY_BIEN = {"field1": "c.field1", "field2": "c.field2", "field3": "c.field3"}


# Phiên thử trên trang Hội thoại KHÔNG phải cuộc gọi: mở trang, bấm micro, nói
# vài câu - không quay số, không có máy nào đổ chuông. Nhưng nó vẫn được ghi vào
# `call_sessions` với `direction` mặc định 'outbound', nên báo cáo đếm luôn vào
# số cuộc gọi.
#
# Hậu quả đo được trên máy thật: 167 "cuộc gọi" thì 152 là phiên thử trình duyệt
# (không số điện thoại, không chiến dịch, không danh bạ) - chỉ 15 cuộc gọi thật.
# "Nghe máy 9%" thật ra là 15/167, tức tỉ lệ BẢN GHI CÓ SỐ ĐIỆN THOẠI, chẳng liên
# quan gì tới việc khách có bắt máy hay không. "Thời lượng TB 0p56s" cũng bị 152
# phiên thử ngắn kéo tụt.
#
# Nhận dạng bằng DỮ LIỆU sẵn có thay vì thêm cột: cuộc gọi thật luôn có ít nhất
# một trong ba - số điện thoại, danh bạ, hoặc chiến dịch. Nhờ vậy 167 bản ghi cũ
# được phân loại đúng ngay, không phải chuyển đổi CSDL.
_LA_CUOC_GOI_THAT = (
    "(COALESCE(s.phone,'') <> '' OR COALESCE(s.contact_id,'') <> '' "
    " OR COALESCE(s.campaign_id,'') <> '')"
)


def _dung_dieu_kien(f: dict) -> tuple[str, list]:
    where, params = [], []

    # Mặc định chỉ tính cuộc gọi thật. Truyền `gom_phien_thu=True` để xem cả
    # phiên thử - chúng vẫn nằm nguyên trong CSDL, chỉ là không trộn vào số liệu.
    if not f.get("gom_phien_thu"):
        where.append(_LA_CUOC_GOI_THAT)

    for key, cot in _LOC_BANG_NHAU.items():
        value = f.get(key)
        if value:
            where.append(f"{cot} = ?")
            params.append(value)

    for key, cot in _LOC_TRUONG_TUY_BIEN.items():
        value = f.get(key)
        if value:
            where.append(f"{cot} = ?")
            params.append(value)

    if f.get("from_ts"):
        where.append("s.created_at >= ?")
        params.append(float(f["from_ts"]))
    if f.get("to_ts"):
        where.append("s.created_at <= ?")
        params.append(float(f["to_ts"]))

    # Thời lượng: phiên chưa kết thúc thì ended_at là NULL, lấy thời điểm hiện
    # tại thay vào để nó không biến mất khỏi mọi bộ lọc thời lượng.
    thoi_luong = "(COALESCE(s.ended_at, ?) - s.created_at)"
    if f.get("min_duration") is not None:
        where.append(f"{thoi_luong} >= ?")
        params += [time.time(), float(f["min_duration"])]
    if f.get("max_duration") is not None:
        where.append(f"{thoi_luong} <= ?")
        params += [time.time(), float(f["max_duration"])]

    if f.get("co_ghi_am"):
        where.append("s.recording_path != ''")

    q = (f.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        # Tìm cả trong nội dung hội thoại: "khách nào có nhắc tới lãi suất" là
        # câu hỏi thật của người bán hàng, mà tên khách thì không trả lời được.
        where.append(
            "(s.customer_name LIKE ? OR s.phone LIKE ? OR s.summary LIKE ? "
            " OR EXISTS (SELECT 1 FROM conversation_turns t "
            "            WHERE t.session_id = s.session_id AND t.content LIKE ?))"
        )
        params += [like, like, like, like]

    return (("WHERE " + " AND ".join(where)) if where else ""), params


_FROM = (
    "FROM call_sessions s "
    # LEFT JOIN: phiên gọi thử từ giao diện không có contact_id, và chúng vẫn
    # phải hiện trong báo cáo.
    "LEFT JOIN contacts c ON c.contact_id = s.contact_id "
    "LEFT JOIN campaigns cp ON cp.campaign_id = s.campaign_id "
)


def _list_sync(f: dict, page: int, limit: int) -> dict:
    conn = db.connection()
    if conn is None:
        return {"calls": [], "total": 0}

    clause, params = _dung_dieu_kien(f)
    offset = max(0, (page - 1) * limit)
    with db.write_lock:
        total = conn.execute(f"SELECT COUNT(*) {_FROM} {clause}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT s.*, cp.name AS campaign_name, "
            f"       c.field1, c.field2, c.field3, c.name AS contact_name "
            f"{_FROM} {clause} ORDER BY s.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()

    now = time.time()
    calls = []
    for r in rows:
        d = dict(r)
        d["duration_seconds"] = round((d.get("ended_at") or now) - d["created_at"], 1)
        d["quality_label"] = NHAN_HIEN_THI.get(d.get("quality") or "", "")
        d["co_ghi_am"] = bool(d.get("recording_path"))
        calls.append(d)
    return {"calls": calls, "total": total}


async def list_calls(filters: dict, page: int = 1, limit: int = 50) -> dict:
    """Một trang báo cáo cuộc gọi theo bộ lọc."""
    return await asyncio.to_thread(_list_sync, filters, page, limit)


def _summary_sync(f: dict) -> dict:
    conn = db.connection()
    if conn is None:
        return {}

    clause, params = _dung_dieu_kien(f)
    now = time.time()
    with db.write_lock:
        tong = conn.execute(
            f"SELECT COUNT(*) AS n, "
            f"       AVG(COALESCE(s.ended_at, {now}) - s.created_at) AS tb_giay, "
            f"       SUM(COALESCE(s.ended_at, {now}) - s.created_at) AS tong_giay, "
            f"       SUM(CASE WHEN s.outcome = 'done' THEN 1 ELSE 0 END) AS nghe_may, "
            f"       SUM(CASE WHEN s.recording_path != '' THEN 1 ELSE 0 END) AS co_ghi_am "
            f"{_FROM} {clause}",
            params,
        ).fetchone()
        theo_nhan = conn.execute(
            f"SELECT s.label AS k, COUNT(*) AS n {_FROM} {clause} GROUP BY s.label", params
        ).fetchall()
        theo_chat_luong = conn.execute(
            f"SELECT s.quality AS k, COUNT(*) AS n {_FROM} {clause} GROUP BY s.quality", params
        ).fetchall()
        theo_ket_qua = conn.execute(
            f"SELECT s.outcome AS k, COUNT(*) AS n {_FROM} {clause} GROUP BY s.outcome", params
        ).fetchall()
        theo_ngay = conn.execute(
            f"SELECT date(s.created_at, 'unixepoch', 'localtime') AS ngay, COUNT(*) AS n "
            f"{_FROM} {clause} GROUP BY ngay ORDER BY ngay DESC LIMIT 30",
            params,
        ).fetchall()

    n = tong["n"] or 0
    return {
        "tong_cuoc": n,
        "nghe_may": tong["nghe_may"] or 0,
        "ty_le_nghe_may": round((tong["nghe_may"] or 0) / n * 100, 1) if n else 0.0,
        "thoi_luong_tb": round(tong["tb_giay"] or 0, 1),
        "tong_thoi_luong": round(tong["tong_giay"] or 0, 1),
        "co_ghi_am": tong["co_ghi_am"] or 0,
        "theo_nhan": {(r["k"] or "chua_gan"): r["n"] for r in theo_nhan},
        "theo_chat_luong": {(r["k"] or "chua_cham"): r["n"] for r in theo_chat_luong},
        "theo_ket_qua": {(r["k"] or "chua_ro"): r["n"] for r in theo_ket_qua},
        "theo_ngay": [{"ngay": r["ngay"], "so_cuoc": r["n"]} for r in theo_ngay],
    }


async def summary(filters: dict) -> dict:
    """Các con số tổng hợp cho đúng bộ lọc đang áp."""
    return await asyncio.to_thread(_summary_sync, filters)


def _chua_tom_tat_sync(limit: int) -> list[str]:
    conn = db.connection()
    if conn is None:
        return []
    with db.write_lock:
        rows = conn.execute(
            "SELECT session_id FROM call_sessions "
            "WHERE status = 'ended' AND summary = '' AND turn_count > 0 "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [r["session_id"] for r in rows]


async def chua_tom_tat(limit: int = 50) -> list[str]:
    """Các phiên đã xong nhưng chưa có tóm tắt - dùng để chạy bù."""
    return await asyncio.to_thread(_chua_tom_tat_sync, limit)
