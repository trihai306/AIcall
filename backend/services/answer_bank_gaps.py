"""Ba sổ nhỏ để kho trả lời LỚN DẦN theo cuộc gọi thật, bớt dần phần mô hình sinh.

1. `answer_bank_choices` - lựa chọn Qwen đã làm cho một câu hỏi. Trước đây chỉ
   nhớ trong tiến trình (`answer_bank_selector._da_chon`) nên mỗi lần khởi động
   lại backend là mọi cách hỏi lại chậm thêm một lần 300-400ms. Ghi xuống đây
   thì mỗi cách hỏi chỉ phải qua Qwen ĐÚNG MỘT LẦN.
2. `answer_bank_misses` - câu khách hỏi mà kho không có, mô hình phải tự viết.
   Gộp theo tập từ mang nghĩa, đếm số lần gặp: đây là danh sách việc cần soạn.
3. `answer_bank_route_stats` - mỗi ngày bao nhiêu lượt đi đường nào (kho / luật
   / mô hình sinh). Không có con số này thì không biết kho đã đủ dày hay chưa.

KHÔNG import torch và không đụng tới bộ học: tệp này chỉ là sqlite, gọi được từ
đường nóng của cuộc gọi (sau khi tiếng đã ra) lẫn từ test không có GPU. Mọi hàm
ghi đều nuốt lỗi - một cái sổ thống kê không được phép làm hỏng lượt trả lời.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Mapping

from backend.models import db

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS answer_bank_choices (
 key TEXT PRIMARY KEY, product TEXT NOT NULL DEFAULT '', bank_name TEXT NOT NULL DEFAULT '',
 words TEXT NOT NULL, question TEXT NOT NULL, answer_id TEXT NOT NULL,
 answer_hash TEXT NOT NULL, hits INTEGER NOT NULL DEFAULT 1,
 created_at REAL NOT NULL, last_used REAL NOT NULL);
CREATE TABLE IF NOT EXISTS answer_bank_misses (
 key TEXT PRIMARY KEY, question TEXT NOT NULL, product TEXT NOT NULL DEFAULT '',
 model_answer TEXT NOT NULL DEFAULT '', mode TEXT NOT NULL DEFAULT 'generated',
 count INTEGER NOT NULL DEFAULT 1, first_seen REAL NOT NULL, last_seen REAL NOT NULL,
 status TEXT NOT NULL DEFAULT 'open', answer_id TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_answer_bank_misses_status ON answer_bank_misses(status, count);
CREATE TABLE IF NOT EXISTS answer_bank_pending (
 hoi_dap_id TEXT PRIMARY KEY, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS answer_bank_groups (
 hoi_dap_id TEXT PRIMARY KEY, nhom TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS answer_bank_route_stats (
 day TEXT NOT NULL, mode TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(day, mode));
"""

# Đường mà MÔ HÌNH phải tự viết câu trả lời - thứ ta muốn bớt dần.
CHE_DO_SINH = frozenset({"generated", "speculative"})
_GIU_TOI_DA = 3000  # số câu chưa có đáp án giữ lại; quá thì bỏ câu cũ gặp ít nhất

_prepared_conn = None


def _conn():
    global _prepared_conn
    conn = db.connection()
    if conn is None:
        return None
    if _prepared_conn is not conn:
        with db.write_lock, conn:
            conn.executescript(_SCHEMA)
        _prepared_conn = conn
    return conn


def _hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _khoa(product: str, bank_name: str, words) -> tuple[str, str]:
    words_json = json.dumps(sorted(words), ensure_ascii=False)
    return _hash(f"{product}\n{bank_name}\n{words_json}"), words_json


def _rieng_tu(question: str) -> bool:
    """Câu có tên, số điện thoại, số tiền riêng... thì không ghi xuống đĩa."""
    try:
        from backend.services.answer_bank_learning import sanitize_history
    except Exception:
        return True
    return sanitize_history(question) != question


# ── 1. Lựa chọn đã nhớ ────────────────────────────────────────────────────

def ghi_lua_chon(product: str, bank_name: str, words, question: str,
                 answer_id: str, answer: str) -> None:
    """Ghi lựa chọn Qwen vừa làm. `product`/`bank_name` ĐÃ chuẩn hoá bởi bộ chọn."""
    try:
        conn = _conn()
        if conn is None or not words or not answer_id or _rieng_tu(question):
            return
        key, words_json = _khoa(product, bank_name, words)
        now = time.time()
        with db.write_lock, conn:
            conn.execute(
                "INSERT INTO answer_bank_choices "
                "(key,product,bank_name,words,question,answer_id,answer_hash,hits,created_at,last_used) "
                "VALUES (?,?,?,?,?,?,?,1,?,?) ON CONFLICT(key) DO UPDATE SET "
                "answer_id=excluded.answer_id,answer_hash=excluded.answer_hash,"
                "question=excluded.question,hits=hits+1,last_used=excluded.last_used",
                (key, product, bank_name, words_json, question.strip()[:300],
                 answer_id, _hash(answer), now, now))
    except Exception:
        logger.exception("Không ghi được lựa chọn đáp án đã nhớ")


def nap_lua_chon(bank: Mapping[str, Mapping[str, Any]]) -> dict[tuple, tuple[str, str]]:
    """Các lựa chọn còn HIỆU LỰC với kho đang dùng, theo đúng dạng `_da_chon`.

    Còn hiệu lực = dòng vẫn có trong kho và chữ đáp án chưa đổi kể từ lúc Qwen
    chọn. Đáp án bị sửa hay tắt thì lựa chọn cũ không được sống lại.
    """
    try:
        conn = _conn()
        if conn is None:
            return {}
        rows = conn.execute(
            "SELECT product,bank_name,words,answer_id,answer_hash FROM answer_bank_choices").fetchall()
    except Exception:
        logger.exception("Không nạp được lựa chọn đáp án đã nhớ")
        return {}
    ra: dict[tuple, tuple[str, str]] = {}
    for product, bank_name, words_json, answer_id, answer_hash in rows:
        answer = str((bank.get(answer_id) or {}).get("tra_loi") or "")
        if not answer or _hash(answer) != answer_hash:
            continue
        try:
            words = frozenset(json.loads(words_json))
        except (ValueError, TypeError):
            continue
        ra[(product, bank_name, words)] = (answer_id, answer)
    return ra


def danh_sach_lua_chon(limit: int = 200) -> list[dict]:
    conn = _conn()
    if conn is None:
        return []
    rows = conn.execute(
        "SELECT c.key,c.question,c.product,c.answer_id,c.hits,c.last_used,h.tra_loi,h.bat,c.answer_hash "
        "FROM answer_bank_choices c LEFT JOIN hoi_dap h ON h.id=c.answer_id "
        "ORDER BY c.last_used DESC LIMIT ?", (max(1, min(int(limit), 1000)),)).fetchall()
    return [{"key": r[0], "cau_hoi": r[1], "san_pham": r[2], "answer_id": r[3], "so_lan": r[4],
             "lan_cuoi": r[5], "tra_loi": r[6] or "",
             "con_hieu_luc": bool(r[6]) and bool(r[7]) and _hash(r[6]) == r[8]} for r in rows]


def xoa_lua_chon(key: str) -> bool:
    conn = _conn()
    if conn is None:
        return False
    with db.write_lock, conn:
        deleted = conn.execute("DELETE FROM answer_bank_choices WHERE key=?", (key,)).rowcount
    if deleted:
        # Bộ chọn đang giữ bản trong RAM: buộc nó nạp lại từ đĩa.
        from backend.services import answer_bank_selector
        answer_bank_selector.quen_lua_chon()
    return bool(deleted)


# ── 2 + 3. Câu chưa có đáp án và thống kê đường trả lời ───────────────────

def ghi_luot(question: str, product: str, route: Mapping[str, Any], answer: str = "") -> None:
    """Ghi một lượt đã trả lời xong: cộng thống kê, và sổ câu chưa có đáp án.

    Gọi SAU khi tiếng đã ra. Lượt mô hình sinh -> thêm/cộng dồn vào sổ. Lượt đọc
    từ kho -> câu cùng ý đang nằm trong sổ được đánh dấu đã có đáp án.
    """
    try:
        conn = _conn()
        mode = str((route or {}).get("mode") or "")
        if conn is None or not mode:
            return
        from backend.services.answer_bank_selector import _norm, khoa_cau_hoi
        now = time.time()
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        words = khoa_cau_hoi(question)
        key = _khoa(_norm(product), "", words)[0] if len(words) >= 2 else ""
        with db.write_lock, conn:
            conn.execute(
                "INSERT INTO answer_bank_route_stats (day,mode,n) VALUES (?,?,1) "
                "ON CONFLICT(day,mode) DO UPDATE SET n=n+1", (day, mode))
            if not key:
                return
            if mode == "answer_bank":
                conn.execute(
                    "UPDATE answer_bank_misses SET status='answered',answer_id=? "
                    "WHERE key=? AND status='open'", (str(route.get("answer_id") or ""), key))
                return
            # Chế độ "chỉ chọn trong kho": kho không có thì AI hẹn liên hệ sau -
            # vẫn là một câu kho còn THIẾU, phải vào sổ như lượt mô hình sinh.
            thieu = mode in CHE_DO_SINH or str(route.get("reason") or "").startswith("kho_khong_co")
            if not thieu or _rieng_tu(question):
                return
            if mode not in CHE_DO_SINH:
                answer = ""  # câu hẹn lại không phải bản nháp đáp án
            conn.execute(
                "INSERT INTO answer_bank_misses "
                "(key,question,product,model_answer,mode,count,first_seen,last_seen) "
                "VALUES (?,?,?,?,?,1,?,?) ON CONFLICT(key) DO UPDATE SET "
                "count=count+1,last_seen=excluded.last_seen,model_answer=excluded.model_answer,"
                "mode=excluded.mode,"
                # Câu đã có đáp án mà vẫn rơi về mô hình thì mở lại: đáp án đó
                # không còn được chọn (bị tắt, bị sửa, hoặc bị cổng an toàn loại).
                "status=CASE WHEN status='answered' THEN 'open' ELSE status END",
                (key, question.strip()[:300], (product or "").strip(), (answer or "").strip()[:1200],
                 mode, now, now))
            total = conn.execute("SELECT COUNT(*) FROM answer_bank_misses").fetchone()[0]
            if total > _GIU_TOI_DA:
                conn.execute(
                    "DELETE FROM answer_bank_misses WHERE key IN (SELECT key FROM answer_bank_misses "
                    "WHERE status!='open' OR count=1 ORDER BY last_seen LIMIT ?)",
                    (total - _GIU_TOI_DA + 200,))
    except Exception:
        logger.exception("Không ghi được sổ câu chưa có đáp án")


def ghi_thieu_tu_hoi(question: str, product: str) -> None:
    """Câu Qwen tự hỏi mà tài liệu không trả lời được: cần người soạn đáp án.

    Không cộng dồn số lần gặp - đó là số lần KHÁCH THẬT hỏi - và không đụng tới
    dòng đã có (kể cả dòng đã bỏ qua).
    """
    try:
        conn = _conn()
        if conn is None or _rieng_tu(question):
            return
        from backend.services.answer_bank_selector import _norm, khoa_cau_hoi
        words = khoa_cau_hoi(question)
        if len(words) < 2:
            return
        now = time.time()
        with db.write_lock, conn:
            conn.execute(
                "INSERT OR IGNORE INTO answer_bank_misses "
                "(key,question,product,model_answer,mode,count,first_seen,last_seen) "
                "VALUES (?,?,?,'','tu_hoi',0,?,?)",
                (_khoa(_norm(product), "", words)[0], question.strip()[:300],
                 (product or "").strip(), now, now))
    except Exception:
        logger.exception("Không ghi được câu tự hỏi chưa có đáp án")


def danh_sach_thieu(status: str = "open", limit: int = 200) -> list[dict]:
    conn = _conn()
    if conn is None:
        return []
    rows = conn.execute(
        "SELECT key,question,product,model_answer,mode,count,first_seen,last_seen,status,answer_id "
        "FROM answer_bank_misses WHERE status=? ORDER BY count DESC,last_seen DESC LIMIT ?",
        (status, max(1, min(int(limit), 1000)))).fetchall()
    return [{"key": r[0], "cau_hoi": r[1], "san_pham": r[2], "cau_mo_hinh": r[3], "che_do": r[4],
             "so_lan": r[5], "lan_dau": r[6], "lan_cuoi": r[7], "trang_thai": r[8],
             "answer_id": r[9]} for r in rows]


def dat_trang_thai(key: str, status: str, answer_id: str = "") -> bool:
    if status not in {"open", "ignored", "answered"}:
        raise ValueError("Trạng thái không hợp lệ")
    conn = _conn()
    if conn is None:
        return False
    with db.write_lock, conn:
        return bool(conn.execute(
            "UPDATE answer_bank_misses SET status=?,answer_id=? WHERE key=?",
            (status, answer_id, key)).rowcount)


def lay_thieu(key: str) -> dict | None:
    conn = _conn()
    if conn is None:
        return None
    r = conn.execute("SELECT key,question,product,model_answer,status FROM answer_bank_misses "
                     "WHERE key=?", (key,)).fetchone()
    return ({"key": r[0], "cau_hoi": r[1], "san_pham": r[2], "cau_mo_hinh": r[3],
             "trang_thai": r[4]} if r else None)


def thong_ke(days: int = 7) -> dict:
    """Tỉ lệ lượt đọc từ kho / theo luật / mô hình sinh trong `days` ngày gần nhất."""
    conn = _conn()
    trong = {"ngay": [], "tong": {}, "so_luot": 0, "ty_le_kho": None, "ty_le_sinh": None,
             "ty_le_khong_sinh": None, "cau_thieu": 0, "lua_chon_da_nho": 0, "cho_duyet": 0}
    if conn is None:
        return trong
    days = max(1, min(int(days), 90))
    tu = time.strftime("%Y-%m-%d", time.localtime(time.time() - (days - 1) * 86400))
    rows = conn.execute("SELECT day,mode,n FROM answer_bank_route_stats WHERE day>=? ORDER BY day",
                        (tu,)).fetchall()
    theo_ngay: dict[str, dict[str, int]] = {}
    tong: dict[str, int] = {}
    for day, mode, n in rows:
        theo_ngay.setdefault(day, {})[mode] = n
        tong[mode] = tong.get(mode, 0) + n
    so_luot = sum(tong.values())
    sinh = sum(n for mode, n in tong.items() if mode in CHE_DO_SINH or mode == "kho_khong_co")
    kho = tong.get("answer_bank", 0)
    return {
        "ngay": [{"ngay": day, **modes} for day, modes in theo_ngay.items()],
        "tong": tong, "so_luot": so_luot,
        "ty_le_kho": round(kho / so_luot, 3) if so_luot else None,
        "ty_le_sinh": round(sinh / so_luot, 3) if so_luot else None,
        "ty_le_khong_sinh": round(1 - sinh / so_luot, 3) if so_luot else None,
        "cau_thieu": conn.execute(
            "SELECT COUNT(*) FROM answer_bank_misses WHERE status='open'").fetchone()[0],
        "lua_chon_da_nho": conn.execute("SELECT COUNT(*) FROM answer_bank_choices").fetchone()[0],
        "cho_duyet": so_cho_duyet(),
    }


# ── 4. Đáp án AI tự hỏi tự soạn, CHỜ DUYỆT ───────────────────────────────
#
# Đáp án Qwen soạn cho câu nó TỰ ĐẶT RA có căn cứ trong tài liệu, nhưng ghép
# cặp hỏi-đáp hay lệch: đo 07-10-2026, "có được miễn phí hồ sơ khi vay lần đầu
# không" nhận đáp án về phí TRẢ TRƯỚC HẠN - câu đúng tài liệu, sai câu hỏi. Ở
# chế độ chỉ chọn trong kho, câu hỏi mẫu sai là khách nghe nhầm đáp án nguyên
# văn. Nên các đáp án này vào kho ở trạng thái TẮT, người duyệt mới bật.

def cho_duyet(ids) -> None:
    conn = _conn()
    ids = list(ids)
    if conn is None or not ids:
        return
    now = time.time()
    with db.write_lock, conn:
        conn.executemany("UPDATE hoi_dap SET bat=0 WHERE id=?", [(i,) for i in ids])
        conn.executemany("INSERT OR IGNORE INTO answer_bank_pending VALUES (?,?)",
                         [(i, now) for i in ids])


def danh_sach_cho_duyet(limit: int = 300) -> list[dict]:
    conn = _conn()
    if conn is None:
        return []
    rows = conn.execute(
        "SELECT p.hoi_dap_id,h.cau_hoi,h.tra_loi,h.san_pham,e.source_path,e.evidence,p.created_at "
        "FROM answer_bank_pending p JOIN hoi_dap h ON h.id=p.hoi_dap_id "
        "LEFT JOIN answer_bank_entries e ON e.hoi_dap_id=p.hoi_dap_id "
        "WHERE h.bat=0 ORDER BY p.created_at DESC, p.hoi_dap_id LIMIT ?",
        (max(1, min(int(limit), 1000)),)).fetchall()
    ra = []
    for r in rows:
        try:
            cau_hoi = json.loads(r[1] or "[]")
        except ValueError:
            cau_hoi = []
        ra.append({"id": r[0], "cau_hoi": cau_hoi, "tra_loi": r[2], "san_pham": r[3],
                   "tai_lieu": r[4] or "", "can_cu": r[5] or "", "luc": r[6]})
    return ra


def so_cho_duyet() -> int:
    conn = _conn()
    if conn is None:
        return 0
    return conn.execute("SELECT COUNT(*) FROM answer_bank_pending p JOIN hoi_dap h "
                        "ON h.id=p.hoi_dap_id WHERE h.bat=0").fetchone()[0]


def cau_hoi_cho_duyet() -> list[str]:
    return [q for row in danh_sach_cho_duyet(1000) for q in row["cau_hoi"]]


def duyet(ids, chap_nhan: bool) -> list[str]:
    """Bật (chấp nhận) hoặc xoá hẳn (từ chối) các đáp án chờ duyệt. Trả id đã bật."""
    conn = _conn()
    ids = list(ids)
    if conn is None or not ids:
        return []
    now = time.time()
    with db.write_lock, conn:
        dang_cho = [i for i in ids if conn.execute(
            "SELECT 1 FROM answer_bank_pending WHERE hoi_dap_id=?", (i,)).fetchone()]
        if chap_nhan:
            conn.executemany("UPDATE hoi_dap SET bat=1,updated_at=? WHERE id=?",
                             [(now, i) for i in dang_cho])
        else:
            conn.executemany("DELETE FROM hoi_dap WHERE id=? AND bat=0", [(i,) for i in dang_cho])
            conn.executemany("DELETE FROM answer_bank_entries WHERE hoi_dap_id=? AND NOT EXISTS "
                             "(SELECT 1 FROM hoi_dap WHERE id=?)", [(i, i) for i in dang_cho])
        conn.executemany("DELETE FROM answer_bank_pending WHERE hoi_dap_id=?",
                         [(i,) for i in dang_cho])
    return dang_cho if chap_nhan else []


# ── 5. Nhóm tình huống của đáp án ────────────────────────────────────────
#
# Kho vài nghìn đáp án thì "khách đang ở tình huống nào" (bận, từ chối, nghi
# ngờ, muốn nghe tiếp...) là thứ người soạn cần để tìm và soát, và là thứ Qwen
# cần để phân biệt hai đáp án gần chữ nhau: "anh không cần" lúc mở đầu khác
# "anh không cần hỏi gì thêm" lúc kết thúc. Nhãn nằm ở bảng riêng vì `hoi_dap`
# là bảng dùng chung với dòng soạn tay đời cũ.

_nhom_cache: tuple[object, dict[str, str]] | None = None


def dat_nhom(answer_id: str, nhom: str) -> None:
    global _nhom_cache
    conn = _conn()
    if conn is None or not answer_id:
        return
    nhom = (nhom or "").strip()[:80]
    with db.write_lock, conn:
        if nhom:
            conn.execute("INSERT INTO answer_bank_groups VALUES (?,?) ON CONFLICT(hoi_dap_id) "
                         "DO UPDATE SET nhom=excluded.nhom", (answer_id, nhom))
        else:
            conn.execute("DELETE FROM answer_bank_groups WHERE hoi_dap_id=?", (answer_id,))
    _nhom_cache = None


def nhom_cua(answer_id: str) -> str:
    """Nhóm tình huống của một đáp án, "" nếu chưa gắn. Đọc từ bản nhớ đệm:
    hàm này nằm trên đường chọn đáp án của cuộc gọi."""
    global _nhom_cache
    conn = _conn()
    if conn is None:
        return ""
    if _nhom_cache is None or _nhom_cache[0] is not conn:
        try:
            _nhom_cache = (conn, dict(conn.execute(
                "SELECT hoi_dap_id,nhom FROM answer_bank_groups").fetchall()))
        except Exception:
            return ""
    return _nhom_cache[1].get(answer_id, "")


def theo_nhom() -> list[dict]:
    """Các đáp án đã gắn nhóm tình huống, gom theo nhóm (cả dòng đang tắt)."""
    conn = _conn()
    if conn is None:
        return []
    rows = conn.execute(
        "SELECT g.nhom,h.id,h.cau_hoi,h.tra_loi,h.bat FROM answer_bank_groups g "
        "JOIN hoi_dap h ON h.id=g.hoi_dap_id ORDER BY g.nhom,h.created_at,h.id").fetchall()
    ra: dict[str, dict] = {}
    for nhom, answer_id, cau_hoi, tra_loi, bat in rows:
        try:
            cach_hoi = json.loads(cau_hoi or "[]")
        except ValueError:
            cach_hoi = []
        muc = ra.setdefault(nhom, {"nhom": nhom, "so_dap_an": 0, "so_cach_hoi": 0, "items": []})
        muc["so_dap_an"] += 1
        muc["so_cach_hoi"] += len(cach_hoi)
        muc["items"].append({"id": answer_id, "cau_hoi": cach_hoi, "tra_loi": tra_loi,
                             "bat": bool(bat)})
    return list(ra.values())
