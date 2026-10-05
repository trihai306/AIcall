"""Sinh ngân hàng hỏi-đáp + tiếng sẵn từ tài liệu tri thức.

Qwen làm việc nặng lúc chuẩn bị dữ liệu, không làm việc đó khi khách đang chờ:
đọc tài liệu, nghĩ câu khách có thể hỏi, viết câu trả lời bám nguồn. Sau khi
lọc, các cặp được đưa vào bảng ``hoi_dap`` mà đường gọi hiện tại đã biết cách
tra vector, đọc nguyên văn và phát WAV dựng sẵn.

Các dòng mới dùng provenance với đường dẫn và hash tài liệu chính xác. Dòng
legacy vẫn hiển thị để giữ lịch sử câu nhân viên, nhưng không được tin cậy trên
đường gọi nếu thiếu provenance.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
import unicodedata
from contextvars import ContextVar
from typing import TYPE_CHECKING

from backend.core.dataset_rules import kiem_tra_tra_loi
from backend.services.rag_service import cat_manh

if TYPE_CHECKING:
    from backend.services.answer_bank_learning import AnswerBankLearning


_NHAN = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:\d+[.)]\s*)?(KH|TV)\s*[:：]\s*(.+?)\s*$",
    re.IGNORECASE,
)
_SO = re.compile(r"(?<!\w)\d[\d.,]*%?")
_manual_bank_worker: ContextVar["AnswerBankLearning | None"] = ContextVar(
    "manual_answer_bank_worker", default=None)


def _khong_dau(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _slug(text: str) -> str:
    return _khong_dau(text).replace(" ", "_")[:42] or "tai_lieu"


def tien_to(nhom: str, ten: str, loai: str = "auto") -> str:
    """Tiền tố id cho đúng một tài liệu và một nguồn câu hỏi.

    ``auto`` là các câu Qwen tự nghĩ từ tài liệu. ``nhan_vien`` là các câu
    nhân viên đã gặp ngoài thực tế. Tách hai nhóm để bổ sung câu thực tế không
    vô tình xóa ngân hàng tự sinh, đồng thời vẫn có thể sinh lại từng nhóm khi
    tài liệu thay đổi.
    """
    dau = "staff" if loai == "nhan_vien" else "auto"
    return f"{dau}_{_slug(nhom)}_{_slug(ten)}_"


def tach_cau_hoi_nhan_vien(text: str) -> list[str]:
    """Mỗi dòng là một câu; bỏ dòng trùng nhưng giữ nguyên thứ tự."""
    ra: list[str] = []
    da_co: set[str] = set()
    for dong in (text or "").splitlines():
        cau = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", dong).strip()
        khoa = _khong_dau(cau)
        if not khoa or khoa in da_co:
            continue
        da_co.add(khoa)
        ra.append(cau)
    return ra


def doc_cap(text: str) -> list[tuple[str, str]]:
    """Đọc định dạng hai dòng ``KH:`` / ``TV:`` mà model được yêu cầu trả."""
    ra: list[tuple[str, str]] = []
    hoi: str | None = None
    for dong in (text or "").splitlines():
        m = _NHAN.match(dong)
        if not m:
            continue
        vai, noi_dung = m.group(1).upper(), m.group(2).strip()
        if vai == "KH":
            hoi = noi_dung or None
        elif hoi and noi_dung:
            ra.append((hoi, noi_dung))
            hoi = None
    return ra


def _so_chuan(s: str) -> str:
    return s.rstrip(".,").replace(",", ".")


def so_bam_nguon(tra_loi: str, nguon: str) -> tuple[bool, list[str]]:
    """Không cho câu tự sinh thêm con số không có trong đoạn nguồn."""
    co = {_so_chuan(x) for x in _SO.findall(nguon or "")}
    thieu = sorted({_so_chuan(x) for x in _SO.findall(tra_loi or "")} - co)
    return not thieu, thieu


def loc_cap(hoi: str, tra_loi: str, nguon: str) -> tuple[bool, str]:
    if not _khong_dau(hoi):
        return False, "thiếu câu hỏi"
    if not (tra_loi or "").strip():
        return False, "thiếu câu trả lời"
    loi, _ = kiem_tra_tra_loi(tra_loi)
    if loi:
        return False, "; ".join(loi)
    hop_so, thieu = so_bam_nguon(tra_loi, nguon)
    if not hop_so:
        return False, "có số không nằm trong nguồn: " + ", ".join(thieu)
    return True, ""


def _prompt_tu_dong(nguon: str, so_cap: int) -> str:
    return f"""Bạn đang chuẩn bị trước thư viện hội thoại cho nhân viên gọi điện.
Đọc CHÍNH XÁC đoạn tài liệu dưới đây và tạo {so_cap} câu khách hàng thực tế có
thể hỏi, kèm câu trả lời ngắn để có thể thu voice sẵn.

TÀI LIỆU NGUỒN:
\"\"\"
{nguon}
\"\"\"

Quy tắc cho TV:
- Chỉ dùng dữ kiện có trong tài liệu nguồn; tuyệt đối không tự thêm dữ kiện.
- Nếu có số, giữ đúng chữ số như nguồn, không đổi sang một con số khác.
- 1-2 câu, tối đa 35 từ, tự nhiên khi nói điện thoại.
- Mở đầu bằng "Dạ", xưng "em", gọi khách là "anh chị", kết câu có "ạ".
- Không markdown, không gạch đầu dòng, không câu đệm riêng trước câu trả lời.
- Các câu KH phải khác ý hoặc khác cách hỏi có ích, tránh câu trùng nghĩa máy móc.

Chỉ trả đúng các cặp hai dòng, không giải thích:
KH: <câu khách hỏi>
TV: <câu trả lời>"""


def _prompt_cau_nhan_vien(nguon: str, cau_hoi: list[str]) -> str:
    ds = "\n".join(f"{i}. {c}" for i, c in enumerate(cau_hoi, 1))
    return f"""Bạn đang chuẩn bị thư viện trả lời có voice sẵn cho cuộc gọi.
Dựa CHỈ vào tài liệu nguồn, trả lời từng câu nhân viên đã ghi nhận bên dưới.

TÀI LIỆU NGUỒN:
\"\"\"
{nguon}
\"\"\"

CÂU HỎI NHÂN VIÊN GHI NHẬN:
{ds}

Quy tắc cho TV:
- Không có căn cứ trong nguồn thì nói ngắn rằng tài liệu hiện chưa có thông tin;
  không đoán và không tự thêm số.
- Nếu có số, giữ đúng chữ số như nguồn.
- 1-2 câu, tối đa 35 từ; mở đầu "Dạ", xưng "em", gọi "anh chị", kết có "ạ".
- Không markdown, không gạch đầu dòng, không câu đệm riêng.
- Giữ nguyên ý của câu KH; tạo đúng một câu trả lời cho mỗi câu hỏi.

Chỉ trả đúng các cặp hai dòng theo cùng thứ tự, không giải thích:
KH: <câu khách hỏi>
TV: <câu trả lời>"""


def _chu_trong(text: str) -> set[str]:
    return {x for x in _khong_dau(text).split() if len(x) >= 3}


def _chon_manh(cau_hoi: list[str], manh: list[str], gioi_han: int = 8) -> list[str]:
    """Chọn các mảnh gần danh sách câu nhân viên để prompt không phình vô hạn."""
    if len(manh) <= gioi_han:
        return manh
    tu = set().union(*(_chu_trong(c) for c in cau_hoi)) if cau_hoi else set()
    cham = []
    for i, m in enumerate(manh):
        diem = len(tu & _chu_trong(m))
        cham.append((diem, -i, m))
    cham.sort(reverse=True)
    chon = [m for diem, _, m in cham[:gioi_han] if diem > 0]
    return chon or manh[:gioi_han]


def _chon_manh_phu_deu(manh: list[str], so_cau: int) -> list[str]:
    if len(manh) <= so_cau or so_cau <= 1:
        return manh
    vi_tri = {round(i * (len(manh) - 1) / (so_cau - 1)) for i in range(so_cau)}
    return [manh[i] for i in sorted(vi_tri)]


async def _goi_qwen(prompt: str, so_cap: int) -> str:
    from backend.main import app_state

    r = await app_state.llm.client.chat(
        model=app_state.llm.model,
        messages=[{"role": "user", "content": prompt}],
        think=False,
        options={"num_predict": max(420, so_cap * 130 + 180), "temperature": 0.45},
    )
    if isinstance(r, dict):
        return ((r.get("message") or {}).get("content") or "").strip()
    return (getattr(getattr(r, "message", None), "content", "") or "").strip()


def _gom_cap(cap: list[tuple[str, str, str]], gioi_han: int) -> tuple[list[dict], dict[str, int]]:
    """Lọc, khử trùng rồi gom các câu có cùng câu trả lời vào một voice."""
    theo_dap: dict[str, dict] = {}
    ly_do: dict[str, int] = {}
    cau_da_co: set[str] = set()
    for hoi, dap, nguon in cap:
        ok, vi_sao = loc_cap(hoi, dap, nguon)
        if not ok:
            ly_do[vi_sao] = ly_do.get(vi_sao, 0) + 1
            continue
        khoa_hoi = _khong_dau(hoi)
        if khoa_hoi in cau_da_co:
            ly_do["trùng câu hỏi"] = ly_do.get("trùng câu hỏi", 0) + 1
            continue
        cau_da_co.add(khoa_hoi)
        khoa_dap = re.sub(r"\s+", " ", dap.strip())
        item = theo_dap.setdefault(khoa_dap, {"cau_hoi": [], "tra_loi": khoa_dap})
        item["cau_hoi"].append(hoi.strip())
        if sum(len(x["cau_hoi"]) for x in theo_dap.values()) >= gioi_han:
            break
    return list(theo_dap.values()), ly_do


async def sinh_cap(noi_dung: str, so_cau: int = 12,
                   cau_hoi_nhan_vien: list[str] | None = None) -> tuple[list[dict], dict[str, int]]:
    """Qwen -> các dòng `{cau_hoi, tra_loi}` đã qua kiểm tra nguồn."""
    manh = [m for m in cat_manh(noi_dung or "") if m.strip()]
    if not manh:
        return [], {"tài liệu rỗng": 1}

    cau_nv = [c.strip() for c in (cau_hoi_nhan_vien or []) if c.strip()]
    cap_tho: list[tuple[str, str, str]] = []
    if cau_nv:
        nguon = "\n\n---\n\n".join(_chon_manh(cau_nv, manh))
        out = await _goi_qwen(_prompt_cau_nhan_vien(nguon, cau_nv), len(cau_nv))
        # Giữ câu hỏi nhân viên nếu model chỉ diễn đạt lại nhẹ; ghép theo thứ tự.
        doc = doc_cap(out)
        for i, (_, dap) in enumerate(doc[:len(cau_nv)]):
            cap_tho.append((cau_nv[i], dap, nguon))
        gioi_han = len(cau_nv)
    else:
        so_cau = max(1, min(int(so_cau or 12), 60))
        chon = _chon_manh_phu_deu(manh, so_cau)
        moi_manh = max(1, math.ceil(so_cau / max(1, len(chon))))
        for nguon in chon:
            out = await _goi_qwen(_prompt_tu_dong(nguon, moi_manh), moi_manh)
            cap_tho.extend((hoi, dap, nguon) for hoi, dap in doc_cap(out))
            if len(cap_tho) >= so_cau * 2:
                break
        gioi_han = so_cau
    return _gom_cap(cap_tho, gioi_han)


def _id_dong(prefix: str, item: dict) -> str:
    vat = json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return prefix + hashlib.sha1(vat).hexdigest()[:12]


def _rows_to_items(rows, nguon: str | None = None) -> list[dict]:
    ra = []
    for r in rows:
        try:
            hoi = json.loads(r[1] or "[]")
        except json.JSONDecodeError:
            hoi = []
        if not isinstance(hoi, list):
            hoi = []
        ra.append({"id": r[0], "cau_hoi": hoi, "tra_loi": r[2] or "",
                   "san_pham": r[3] or "", "bat": bool(r[4]), "updated_at": r[5],
                   "nguon": nguon or {"staff": "nhan_vien", "memory": "lich_su",
                                       "manual": "nhap_tay"}.get(r[6], "tu_dong")})
    return ra


def _doc_rows(conn, prefix: str, nguon: str = "tu_dong") -> list[dict]:
    rows = conn.execute(
        "SELECT id, cau_hoi, tra_loi, san_pham, bat, updated_at FROM hoi_dap "
        "WHERE id GLOB ? ORDER BY updated_at DESC, id",
        (prefix + "*",),
    ).fetchall()
    return _rows_to_items(rows, nguon)


def _provenance_rows(conn, nhom: str, ten: str) -> list[dict]:
    # Exact source identity avoids truncated/normalized slug collisions. The
    # tables may not exist in compatibility-only installations yet.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='answer_bank_entries'").fetchone() is None:
        return []
    rows = conn.execute(
        "SELECT h.id,h.cau_hoi,h.tra_loi,h.san_pham,h.bat,h.updated_at,e.origin "
        "FROM hoi_dap h JOIN answer_bank_entries e ON e.hoi_dap_id=h.id "
        "JOIN answer_bank_sources s ON s.source_path=e.source_path "
        "WHERE s.source_group=? AND s.source_stem=? ORDER BY h.updated_at DESC,h.id",
        (nhom, ten),
    ).fetchall()
    return _rows_to_items(rows)


def _legacy_source_is_unique(conn, nhom: str, ten: str) -> bool:
    """A truncated legacy ID cannot establish ownership between two sources."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='answer_bank_sources'").fetchone():
        return True  # Pre-provenance installations retain legacy compatibility.
    prefix = tien_to(nhom, ten)
    sources = conn.execute("SELECT source_group,source_stem FROM answer_bank_sources "
                           "WHERE status != 'missing'").fetchall()
    return sum(tien_to(r[0], r[1]) == prefix for r in sources) <= 1


def danh_sach(nhom: str, ten: str) -> list[dict]:
    from backend.models import db

    conn = db.connection()
    if conn is None:
        return []
    rows = (_doc_rows(conn, tien_to(nhom, ten), "tu_dong")
            + _doc_rows(conn, tien_to(nhom, ten, "nhan_vien"), "nhan_vien")
            )
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='answer_bank_entries'").fetchone():
        # Once an ID has provenance, its exact source alone owns it. Legacy
        # truncated/normalized slug prefixes can match unrelated documents.
        attributed = {r[0] for r in conn.execute("SELECT hoi_dap_id FROM answer_bank_entries")}
        rows = [row for row in rows if row["id"] not in attributed]
    if not _legacy_source_is_unique(conn, nhom, ten):
        rows = []
    rows += _provenance_rows(conn, nhom, ten)
    items = list({row["id"]: row for row in rows}.values())
    from backend.services.answer_bank_learning import voice_is_ready
    for item in items:
        item["voice_ready"] = voice_is_ready(item["id"], item["tra_loi"])
    return items


def cau_hoi_nhan_vien_da_luu(nhom: str, ten: str) -> list[str]:
    """Keep observed staff questions, including rows disabled after source edits."""
    ra: list[str] = []
    da_co: set[str] = set()
    for row in danh_sach(nhom, ten):
        if row["nguon"] != "nhan_vien":
            continue
        for cau in row.get("cau_hoi") or []:
            khoa = _khong_dau(cau)
            if khoa and khoa not in da_co:
                da_co.add(khoa)
                ra.append(cau)
    return ra


def _gop_items_cu(rows: list[dict], items: list[dict]) -> list[dict]:
    """Gộp câu nhân viên mới vào kho cũ; câu nhập lại dùng câu trả lời mới."""
    theo_hoi: dict[str, tuple[str, str]] = {}
    for row in rows:
        dap = (row.get("tra_loi") or "").strip()
        for cau in row.get("cau_hoi") or []:
            khoa = _khong_dau(cau)
            if khoa and dap:
                theo_hoi[khoa] = (cau.strip(), dap)
    for item in items:
        dap = (item.get("tra_loi") or "").strip()
        for cau in item.get("cau_hoi") or []:
            khoa = _khong_dau(cau)
            if khoa and dap:
                theo_hoi[khoa] = (cau.strip(), dap)

    theo_dap: dict[str, dict] = {}
    for cau, dap in theo_hoi.values():
        row = theo_dap.setdefault(dap, {"cau_hoi": [], "tra_loi": dap})
        row["cau_hoi"].append(cau)
    return list(theo_dap.values())


def luu(nhom: str, ten: str, items: list[dict], *, loai: str = "auto",
        gop_cu: bool = False) -> list[dict]:
    """Lưu atomically đúng một nhóm Q&A của tài liệu.

    Nhóm tự sinh được thay hoàn toàn khi tài liệu đổi. Nhóm nhân viên mặc định
    được gộp để mỗi lần nhân viên nhập thêm câu hỏi không xóa các câu đã học.
    """
    from backend.models import db

    conn = db.connection()
    if conn is None:
        raise RuntimeError("Cơ sở dữ liệu chưa sẵn sàng")
    prefix = tien_to(nhom, ten, loai)
    san_pham = ten if nhom == "products" else ""
    if gop_cu:
        items = _gop_items_cu(_doc_rows(conn, prefix, loai), items)
    now = time.time()
    with conn:
        conn.execute("DELETE FROM hoi_dap WHERE id GLOB ?", (prefix + "*",))
        for item in items:
            ma = _id_dong(prefix, item)
            conn.execute(
                "INSERT INTO hoi_dap "
                "(id,cau_dem,cau_hoi,tra_loi,san_pham,bat,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (ma, "", json.dumps(item["cau_hoi"], ensure_ascii=False),
                 item["tra_loi"], san_pham, 1, now, now),
            )
    return _doc_rows(conn, prefix, "nhan_vien" if loai == "nhan_vien" else "tu_dong")


def _tat_cua_tai_lieu(nhom: str, ten: str) -> int:
    """Disable exactly the displayed source rows while preserving staff history."""
    from backend.models import db

    conn = db.connection()
    if conn is None:
        return 0
    ids = [row["id"] for row in danh_sach(nhom, ten)]
    with db.write_lock, conn:
        conn.executemany("UPDATE hoi_dap SET bat=0,updated_at=? WHERE id=?",
                         [(time.time(), row_id) for row_id in ids])
    return len(ids)


def _xoa_rows_cua_tai_lieu(nhom: str, ten: str) -> int:
    from backend.models import db

    conn = db.connection()
    if conn is None:
        return 0
    ids = [row["id"] for row in danh_sach(nhom, ten)]
    has_provenance = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                 "AND name='answer_bank_entries'").fetchone()
    with db.write_lock, conn:
        conn.executemany("DELETE FROM hoi_dap WHERE id=?", [(row_id,) for row_id in ids])
        if has_provenance:
            conn.executemany("DELETE FROM answer_bank_entries WHERE hoi_dap_id=?",
                             [(row_id,) for row_id in ids])
    return len(ids)


async def nap_lai_duong_goi(*, build_voice: bool = True) -> dict:
    """Cập nhật vector Q&A và dựng WAV ngay, không bắt người dùng restart app."""
    from backend.config import settings
    from backend.core.startup import _nhung_theo_nhom, _nhung_cpu
    from backend.main import app_state
    from backend.models import db
    from backend.services.bang_hoi_dap import doc_dong, retrieval_texts, RETRIEVAL_LAYOUT_VERSION
    import numpy as np

    loop = asyncio.get_running_loop()
    lock = getattr(loop, "_answer_bank_runtime_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(loop, "_answer_bank_runtime_lock", lock)
    async with lock:
        rag = app_state.rag
        # Startup's vectors already belong to this RAG instance. Later reloads
        # must not reuse vectors produced by a different embedding model.
        cache, matrices = {}, {}
        if (getattr(app_state, "_hoi_dap_vector_rag", None) is rag
                and getattr(app_state, "_hoi_dap_vector_layout", None) == RETRIEVAL_LAYOUT_VERSION):
            bank_old = getattr(app_state, "hoi_dap", {}) or {}
            vectors_old = getattr(app_state, "hoi_dap_vector", {}) or {}
            for row_id, row in bank_old.items():
                texts = retrieval_texts(row)
                matrix = vectors_old.get(row_id)
                if matrix is None or np.asarray(matrix).ndim != 2 or len(matrix) != len(texts):
                    continue
                matrices[texts] = matrix
                cache.update(zip(texts, matrix))
        while True:
            if app_state.rag is not rag:
                rag, cache, matrices = app_state.rag, {}, {}
            conn = db.connection()
            if conn is not None:
                from backend.services.answer_bank_learning import _conn
                _conn()  # Schema preparation must precede the non-reentrant DB lock.
            with db.write_lock:
                dong = doc_dong(conn) if conn is not None else []
                # Text cache preserves unchanged examples when only an answer
                # changes. Deduplicate shared text without conflating row layout.
                missing_texts = list(dict.fromkeys(
                    text for d in dong for text in retrieval_texts(d) if text not in cache))
                missing = [(text, (text,)) for text in missing_texts]
                if not missing:
                    bang_moi = {d["id"]: d for d in dong}
                    vector_moi = {}
                    for d in dong:
                        texts = retrieval_texts(d)
                        if not texts:
                            continue
                        if texts not in matrices:
                            matrices[texts] = np.stack([cache[text] for text in texts])
                        vector_moi[d["id"]] = matrices[texts]
                    try:
                        from backend.services.answer_bank_learning import active_provenance
                        provenance_moi = active_provenance(conn, lock_held=True) if conn else {}
                    except Exception:
                        provenance_moi = {}
                    # One publish, without await: rows, vectors and provenance
                    # correspond to the latest DB snapshot, never the pre-encode
                    # snapshot if another document was saved while CPU worked.
                    app_state.hoi_dap, app_state.hoi_dap_vector, app_state.hoi_dap_provenance = (
                        bang_moi, vector_moi, provenance_moi)
                    app_state._hoi_dap_vector_rag = rag
                    app_state._hoi_dap_vector_layout = RETRIEVAL_LAYOUT_VERSION
                    break
            if str(settings.embedding_device).lower() == "cpu":
                # RAG retrieval already performs read-only CPU encoding in a
                # worker thread. Encoding only changed retrieval texts keeps
                # health checks and editor requests responsive as well.
                encoded = await _nhung_cpu(rag, missing)
            else:
                from backend.core.service_priority import background_ai_busy_reason, background_gpu_lock
                async with background_gpu_lock():
                    reason = background_ai_busy_reason()
                    if reason:
                        raise RuntimeError(reason)
                    # Preserve the existing device behavior for non-CPU models
                    # and serialize with customer admission/background F5/Qwen.
                    encoded = _nhung_theo_nhom(rag, missing)
            cache.update({text: encoded[text][0] for text in missing_texts})
    voice = None
    if build_voice and settings.tieng_san_bat and dong:
        from backend.services.tieng_san import kho_tieng_san

        ten_giong = app_state.tts.default_voice_name()
        voice = await kho_tieng_san.dung_nhieu(
            app_state.tts,
            {f"hd_{d['id']}": d.get("tra_loi", "") for d in dong},
            ten_giong,
        )
        voice["giong"] = ten_giong
    return {"so_dong": len(dong), "voice": voice}


def nap_lai_provenance_voice(state) -> bool:
    """Voice completion changes metadata only; it never needs new embeddings."""
    from backend.models import db
    from backend.services.bang_hoi_dap import doc_dong
    from backend.services.answer_bank_learning import active_provenance, _conn
    conn = _conn()
    with db.write_lock:
        rows = doc_dong(conn) if conn is not None else []
        published = getattr(state, "hoi_dap", {}) or {}
        if ({row["id"] for row in rows} != set(published)
                or any(any(published[row["id"]].get(key, "" if key == "cau_dem" else None) != value
                           for key, value in row.items()) for row in rows)):
            # A committed edit can be waiting for CPU encoding. Its full
            # publication owns this newer version; voice must not pair fresh
            # provenance with an older question/answer/vector snapshot.
            return False
        provenance = active_provenance(conn, lock_held=True)
        previous = getattr(state, "hoi_dap_provenance", {}) or {}
        identity = lambda meta: {k: v for k, v in meta.items() if k != "voice_ready"}
        if (set(provenance) != set(previous)
                or any(identity(meta) != identity(previous[row_id])
                       for row_id, meta in provenance.items())
                or provenance == previous):
            return False
        state.hoi_dap, state.hoi_dap_vector, state.hoi_dap_provenance = (
            state.hoi_dap, state.hoi_dap_vector, provenance)
    return True


async def dong_bo_tu_tai_lieu(nhom: str, ten: str, noi_dung: str,
                              so_cau: int = 12) -> dict:
    """Rebuild current auto and preserved staff answers in one transaction."""
    result = await tao_va_luu(nhom, ten, noi_dung, so_cau)
    if result.get("error"):
        result["da_tat_cu"] = _tat_cua_tai_lieu(nhom, ten)
        result["runtime"] = await nap_lai_duong_goi(build_voice=False)
    return result


async def xoa_cua_tai_lieu(nhom: str, ten: str) -> dict:
    """Xóa tài liệu thì gỡ luôn mọi câu/voice tham chiếu khỏi đường gọi."""
    so_dong = _xoa_rows_cua_tai_lieu(nhom, ten)
    runtime = await nap_lai_duong_goi()
    return {"ok": True, "so_dong": so_dong, "runtime": runtime}


async def _nap_bank_da_luu(ids: list[str]) -> dict:
    from backend.services.answer_bank_learning import bo_hoc_tra_loi

    # Use the guarded F5 builder (the background GPU gate and customer-idle
    # checks), then republish voice readiness for the selector snapshot.
    await nap_lai_duong_goi(build_voice=False)
    worker = _manual_bank_worker.get() or bo_hoc_tra_loi
    await worker._voice_rows(ids)
    return await nap_lai_duong_goi(build_voice=False)


async def tao_va_luu(nhom: str, ten: str, noi_dung: str, so_cau: int = 12,
                     cau_hoi_nhan_vien: list[str] | None = None) -> dict:
    from backend.services import answer_bank_learning as learning

    # An explicit request has its own cancellation state. Disabling or cancelling
    # the automatic builder must not cancel this request or revive a running job.
    worker = learning.AnswerBankLearning()
    worker._state = learning.bo_hoc_tra_loi._state
    token = _manual_bank_worker.set(worker)
    try:
        return await _tao_va_luu_hien_tai(nhom, ten, noi_dung, so_cau, cau_hoi_nhan_vien)
    finally:
        _manual_bank_worker.reset(token)


async def _tao_va_luu_hien_tai(nhom: str, ten: str, noi_dung: str, so_cau: int = 12,
                     cau_hoi_nhan_vien: list[str] | None = None) -> dict:
    """The manual per-document action uses the same grounded bank as automation."""
    from backend.services import answer_bank_learning as learning

    docs, logs = learning.prepare_sources()
    # Source edits quarantine stale rows before any awaited model work.
    if any(log.startswith("Đã tắt các đáp án") for log in logs):
        await nap_lai_duong_goi(build_voice=False)
    doc = next((d for d in docs if d.group == nhom and d.stem == ten), None)
    if doc is None:
        return {"error": "Không có tài liệu nguồn hợp lệ trong knowledge"}
    if noi_dung != doc.text:
        return {"error": "Tài liệu đã đổi trước lúc tạo hỏi-đáp; hãy thử lại"}
    async with learning.source_operation_lock(doc):
        if not learning._source_is_current(doc):
            return {"error": "Tài liệu đã đổi trong lúc chờ tạo hỏi-đáp; hãy thử lại"}
        cfg = learning._config()
        existing_staff = cau_hoi_nhan_vien_da_luu(nhom, ten)
        staff_questions = tach_cau_hoi_nhan_vien("\n".join(
            existing_staff + list(cau_hoi_nhan_vien or [])))
        la_nhan_vien = bool(cau_hoi_nhan_vien)
        auto_items: list[dict] = []
        reasons: dict[str, int] = {}
        if not la_nhan_vien:
            auto_items, reasons = await learning.generate_document(
                doc, max(1, min(int(so_cau or 12), 300)), cfg["variants_per_answer"])
            if not auto_items:
                return {"error": "Qwen chưa tạo được câu hỏi-đáp hợp lệ từ tài liệu này",
                        "loai": reasons}
        staff_items: list[dict] = []
        if staff_questions:
            staff_items, staff_reasons = await learning.generate_document(
                doc, len(staff_questions), cfg["variants_per_answer"], staff_questions)
            for why, count in staff_reasons.items():
                reasons[why] = reasons.get(why, 0) + count
            covered = {_khong_dau(q) for item in staff_items for q in item["cau_hoi"]}
            # A partial reply must not erase previously observed staff intents.
            if any(_khong_dau(q) not in covered for q in staff_questions):
                return {"error": "Không làm mới được đầy đủ câu hỏi nhân viên từ nguồn hiện tại",
                        "loai": reasons}
        # Both stores perform a final on-disk hash/path check inside the transaction.
        if la_nhan_vien:
            ids = learning._store_items(doc, staff_items, "staff", replace=True)
        else:
            ids = learning._replace_document(doc, auto_items, staff_items)
        runtime = await _nap_bank_da_luu(ids)
        rows = danh_sach(nhom, ten)
        return {"ok": True, "items": rows, "so_dong": len(rows), "loai": reasons,
                "tu_dong": len(auto_items), "nhan_vien": len(staff_items), "runtime": runtime}
