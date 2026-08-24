"""Quản lý kho câu đệm từ giao diện.

Câu đệm là thứ khách nghe ĐẦU TIÊN mỗi lượt: phát song song trong lúc LLM còn
đang nghĩ, để chỗ trống giữa hai người nói không thành quãng im. Kho nằm trong
SQLite, trước đây sửa phải vào thẳng DB - nên suốt dự án nó đứng nguyên ở 20
tình huống × ĐÚNG MỘT mẩu mở đầu, và khách hỏi cùng chủ đề hai lần thì nghe y
hệt nhau.

`filler_store.nap_tu_db` đã ném lỗi cho dữ liệu sai, nhưng nó ném lúc KHỞI ĐỘNG
BACKEND: người vận hành gõ thiếu dấu phẩy lúc 3 giờ chiều thì tới lần restart
sau mới biết, lúc đó không ai nhớ đã sửa gì. Nên `kiem_tinh_huong` ở đây soi
đúng những luật ấy ngay lúc lưu.

SỬA XONG PHẢI LÀM HAI VIỆC, thiếu một là hỏng câm:
  `nap_lai()`     để đường chạy thấy dữ liệu mới
  nhúng lại ví dụ để tình huống mới được cosine chấm điểm - thiếu bước này thì
                  tình huống vừa thêm KHÔNG BAO GIỜ được chọn, mà không có gì báo
"""

import json
import logging
import re
import time

from fastapi import APIRouter, Body

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fillers", tags=["fillers"])

_ID_HOP_LE = re.compile(r"^[a-z0-9_]{2,40}$")


def kiem_tinh_huong(d: dict) -> list[str]:
    """Mọi lỗi của một tình huống, gộp một lần.

    Trả HẾT lỗi chứ không dừng ở lỗi đầu: sửa một lỗi rồi lưu lại mới thấy lỗi
    kế tiếp là kiểu hành người dùng.
    """
    loi: list[str] = []

    ma = (d.get("id") or "").strip()
    if not _ID_HOP_LE.match(ma):
        loi.append("Mã tình huống chỉ dùng chữ thường, số và gạch dưới "
                   "(2-40 ký tự) — nó là khoá chính và đi vào tên tệp clip")
    if not (d.get("ten") or "").strip():
        loi.append("Thiếu tên tình huống")

    vi_du = [v for v in (d.get("vi_du") or []) if (v or "").strip()]
    if len(vi_du) < 2:
        loi.append(f"Cần ít nhất 2 ví dụ, đang có {len(vi_du)} — một ví dụ thì "
                   "điểm cosine dựa vào đúng một cách nói")

    mo_dau = [m for m in (d.get("mo_dau") or []) if (m or "").strip()]
    if not mo_dau:
        loi.append("Cần ít nhất 1 mẩu mở đầu")
    for m in mo_dau:
        if not m.rstrip().endswith(","):
            loi.append(f"Mẩu mở đầu phải kết bằng dấu phẩy: {m!r} — thiếu phẩy "
                       "thì F5 hạ giọng kết câu ngay giữa lượt, khách nghe như "
                       "AI đã nói xong trong khi câu trả lời thật chưa tới")

    speed = d.get("speed")
    if speed not in (None, "") and not (0.5 <= float(speed) <= 1.5):
        loi.append("Tốc đọc phải trong khoảng 0.5 - 1.5")
    return loi


def kiem_cau_duoi(d: dict) -> list[str]:
    loi: list[str] = []
    if not _ID_HOP_LE.match((d.get("id") or "").strip()):
        loi.append("Mã câu đuôi chỉ dùng chữ thường, số và gạch dưới (2-40 ký tự)")
    if not (d.get("text") or "").strip():
        loi.append("Câu đuôi không được rỗng")
    return loi


def dem_clip(so_mau_tong: int, so_duoi: int) -> int:
    """Số clip phải dựng sẵn cho MỘT giọng.

    Mẩu mở đầu và câu đuôi được ghép sẵn thành một clip liền chứ không phát nối
    hai clip rời - nối hai lần sinh F5 khác nhau thì lệch tông ngay giữa câu.
    Cái giá là số clip nhân theo TÍCH, nên con số này phải hiện ra trước khi ai
    đó bấm Dựng tiếng rồi ngồi đợi hai mươi phút.
    """
    return so_mau_tong * so_duoi + so_duoi


def _conn():
    from backend.models.db import connection
    return connection()


def _mang(s: str | None) -> list[str]:
    """Cột JSON trong DB có thể là NULL, chuỗi rỗng, hoặc JSON hỏng do sửa tay."""
    if not s:
        return []
    try:
        v = json.loads(s)
        return [str(x) for x in v] if isinstance(v, list) else []
    except json.JSONDecodeError:
        return []


def _nhung_lai_vi_du():
    """Nhúng lại ví dụ để cosine chấm điểm được tình huống vừa sửa.

    Tách hàm riêng để test thay được: nhúng thật cần model embedding, mà điều
    test cần biết chỉ là bước này CÓ chạy - thiếu nó thì tình huống mới không
    bao giờ được chọn và không có gì báo.
    """
    from backend.main import app_state
    from backend.services.filler_situation import chuan_hoa
    from backend.services.filler_store import lay_kho

    if app_state.rag is None:
        logger.warning("RAG chưa sẵn sàng, chưa nhúng lại ví dụ tình huống")
        return
    kho = lay_kho()
    app_state.kho_vector = {
        t.id: chuan_hoa(app_state.rag.embed(list(t.vi_du)))
        for t in kho.tinh_huong if t.vi_du
    }
    logger.info("Đã nhúng lại ví dụ của %d tình huống", len(app_state.kho_vector))


def _ap_dung():
    """Nạp lại kho + nhúng lại ví dụ. Lỗi ở đây không được nuốt im."""
    from backend.services.filler_store import nap_lai
    nap_lai()
    try:
        _nhung_lai_vi_du()
    except Exception as e:
        logger.warning("Không nhúng lại được ví dụ tình huống: %s", e)


# --- đọc -------------------------------------------------------------------------

@router.get("")
async def danh_sach():
    conn = _conn()
    if conn is None:
        return {"error": "DB chưa mở"}

    ths = [{
        "id": r[0], "ten": r[1], "vi_du": _mang(r[2]), "tu_khoa": _mang(r[3]),
        "mo_dau": _mang(r[4]), "speed": r[5], "bat": bool(r[6]),
    } for r in conn.execute("SELECT id, ten, vi_du, tu_khoa, mo_dau, speed, bat "
                            "FROM tinh_huong ORDER BY id")]
    duoi = [{"id": r[0], "text": r[1], "hop_cau_hoi": bool(r[2]), "bat": bool(r[3])}
            for r in conn.execute("SELECT id, text, hop_cau_hoi, bat FROM cau_duoi "
                                  "ORDER BY id")]

    # Thống kê tính trên mục ĐANG BẬT: đó mới là thứ đường chạy dùng và là thứ
    # phải dựng tiếng.
    mau_bat = sum(len(t["mo_dau"]) for t in ths if t["bat"])
    duoi_bat = sum(1 for d in duoi if d["bat"])
    return {
        "tinh_huong": ths,
        "cau_duoi": duoi,
        "nguong_diem": _nguong(),
        "thong_ke": {
            "so_tinh_huong": sum(1 for t in ths if t["bat"]),
            "so_mau": mau_bat,
            "so_duoi": duoi_bat,
            "so_clip": dem_clip(mau_bat, duoi_bat),
        },
    }


def _nguong() -> float:
    from backend.services.filler_situation import NGUONG_DIEM
    return NGUONG_DIEM


# --- ghi -------------------------------------------------------------------------

@router.post("/tinh-huong")
async def luu_tinh_huong(than: dict = Body(...)):
    loi = kiem_tinh_huong(than)
    if loi:
        # Trả lỗi TRƯỚC khi ghi: ghi rồi mới báo là để lại dữ liệu làm backend
        # không khởi động nổi ở lần restart sau.
        return {"error": " · ".join(loi), "loi": loi}

    conn = _conn()
    if conn is None:
        return {"error": "DB chưa mở"}

    ma = than["id"].strip()
    gio = time.time()
    conn.execute(
        "INSERT INTO tinh_huong (id, ten, vi_du, tu_khoa, mo_dau, speed, bat, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET ten=excluded.ten, vi_du=excluded.vi_du, "
        "tu_khoa=excluded.tu_khoa, mo_dau=excluded.mo_dau, speed=excluded.speed, "
        "bat=excluded.bat, updated_at=excluded.updated_at",
        (ma, than["ten"].strip(),
         json.dumps([v.strip() for v in than["vi_du"] if v.strip()], ensure_ascii=False),
         json.dumps([v.strip() for v in (than.get("tu_khoa") or []) if v.strip()],
                    ensure_ascii=False),
         json.dumps([m.strip() for m in than["mo_dau"] if m.strip()], ensure_ascii=False),
         float(than["speed"]) if than.get("speed") not in (None, "") else None,
         1 if than.get("bat", True) else 0, gio, gio))
    conn.commit()
    _ap_dung()
    logger.info("Câu đệm: lưu tình huống %s", ma)
    return {"ok": True, "id": ma}


@router.delete("/tinh-huong/{ma}")
async def xoa_tinh_huong(ma: str):
    conn = _conn()
    if conn is None:
        return {"error": "DB chưa mở"}
    conn.execute("DELETE FROM tinh_huong WHERE id = ?", (ma,))
    conn.commit()
    _ap_dung()
    logger.info("Câu đệm: xoá tình huống %s", ma)
    return {"ok": True, "da_xoa": ma}


@router.post("/cau-duoi")
async def luu_cau_duoi(than: dict = Body(...)):
    loi = kiem_cau_duoi(than)
    if loi:
        return {"error": " · ".join(loi), "loi": loi}
    conn = _conn()
    if conn is None:
        return {"error": "DB chưa mở"}
    gio = time.time()
    conn.execute(
        "INSERT INTO cau_duoi (id, text, hop_cau_hoi, bat, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET text=excluded.text, "
        "hop_cau_hoi=excluded.hop_cau_hoi, bat=excluded.bat, "
        "updated_at=excluded.updated_at",
        (than["id"].strip(), than["text"].strip(),
         1 if than.get("hop_cau_hoi", True) else 0,
         1 if than.get("bat", True) else 0, gio, gio))
    conn.commit()
    _ap_dung()
    return {"ok": True, "id": than["id"].strip()}


@router.delete("/cau-duoi/{ma}")
async def xoa_cau_duoi(ma: str):
    conn = _conn()
    if conn is None:
        return {"error": "DB chưa mở"}
    con_lai = conn.execute("SELECT COUNT(*) FROM cau_duoi WHERE bat = 1 AND id != ?",
                           (ma,)).fetchone()[0]
    if con_lai == 0:
        # Rổ đuôi là đường xuống cấp cuối cùng: rỗng nó thì khách nghe im lặng
        # trọn quãng chờ, và backend không nạp nổi kho ở lần khởi động sau.
        return {"error": "Đây là câu đuôi cuối cùng đang bật. Xoá nó thì khách "
                         "nghe im lặng trọn quãng chờ mỗi lượt — thêm câu khác "
                         "trước đã."}
    conn.execute("DELETE FROM cau_duoi WHERE id = ?", (ma,))
    conn.commit()
    _ap_dung()
    return {"ok": True, "da_xoa": ma}


# --- thử -------------------------------------------------------------------------

def _trang_thai():
    """Tách ra để test thay được - chạm `app_state` thật là kéo cả model theo."""
    from backend.main import app_state
    return app_state


@router.post("/thu")
async def thu(than: dict = Body(...)):
    """Gõ một câu khách nói, xem hệ thống chọn tình huống nào và mẩu nào sẽ phát.

    Đây là thứ khiến việc thêm tình huống kiểm được ngay thay vì đoán: cosine
    chấm trên phiên âm CỤT lúc chạy thật, nên một tình huống nghe rất hợp lý vẫn
    có thể không bao giờ đạt ngưỡng.
    """
    cau = (than.get("cau") or "").strip()
    if not cau:
        return {"error": "Nhập một câu khách hay nói rồi bấm Thử"}

    st = _trang_thai()
    if getattr(st, "rag", None) is None:
        return {"error": "Chưa nạp xong bộ nhúng — đợi backend sẵn sàng rồi thử lại"}
    kho_vec = getattr(st, "kho_vector", None) or {}
    if not kho_vec:
        # Im lặng trả "không khớp" ở đây sẽ khiến người dùng đi sửa ví dụ trong
        # khi lỗi nằm chỗ khác.
        return {"error": "Chưa nhúng ví dụ của tình huống nào. Lưu lại một tình "
                         "huống để nhúng lại, hoặc khởi động lại backend."}

    from backend.services.filler_situation import chon_tinh_huong, chuan_hoa
    from backend.services.filler_store import lay_kho

    q = chuan_hoa(st.rag.embed([cau]))[0]
    id_th, diem = chon_tinh_huong(q, kho_vec)

    ten, mo_dau = "", []
    for t in lay_kho().tinh_huong:
        if t.id == id_th:
            ten, mo_dau = t.ten, list(t.mo_dau)
            break

    return {
        "cau": cau,
        "id": id_th,
        "ten": ten,
        "diem": round(float(diem), 3),
        "nguong": _nguong(),
        "dat_nguong": id_th is not None,
        "mo_dau": mo_dau,
    }


# --- dựng tiếng ------------------------------------------------------------------
#
# Mẩu mở đầu và câu đuôi ghép sẵn thành clip liền, nên số clip là TÍCH: 30 tình
# huống × 4 mẩu × 42 đuôi ≈ 5.000 clip cho mỗi giọng, khoảng hai mươi phút GPU.
# Trả tiền một lần rồi các lượt sau đọc thẳng từ đĩa.

_viec = {"dang_chay": False, "bat_dau": 0.0, "so_clip": 0, "giong": "",
         "xong": 0, "loi": None, "ket_thuc": 0.0}


def _thu_muc_clip():
    from backend.services.filler_store import THU_MUC_FILLER
    return THU_MUC_FILLER


def _dem_clip_tren_dia(giong: str) -> int:
    tm = _thu_muc_clip() / giong
    return sum(1 for _ in tm.rglob("*.wav")) if tm.exists() else 0


def _chay_dung_tieng():
    """Bắt đầu dựng ở nền. Không chặn request: dựng mất hàng chục phút."""
    import asyncio as _a

    async def _lam():
        from backend.main import app_state
        from backend.services.filler_store import lay_kho
        try:
            await app_state.tts.dung_fillers(lay_kho())
            _viec["loi"] = None
        except Exception as e:
            logger.exception("Dựng tiếng câu đệm hỏng")
            _viec["loi"] = str(e)
        finally:
            _viec["dang_chay"] = False
            _viec["ket_thuc"] = time.time()

    _a.create_task(_lam())


@router.post("/dung-tieng")
async def dung_tieng():
    if _viec["dang_chay"]:
        return {"error": "Đang dựng rồi. Hai lượt dựng song song giành cùng GPU "
                         "với nhau và với cuộc gọi đang sống.",
                "trang_thai": _viec}

    d = await danh_sach()
    if "error" in d:
        return d
    so_clip = d["thong_ke"]["so_clip"]

    giong = ""
    try:
        from backend.main import app_state
        giong = app_state.tts._default_voice
    except Exception:
        pass

    _viec.update({"dang_chay": True, "bat_dau": time.time(), "so_clip": so_clip,
                  "giong": giong, "loi": None, "ket_thuc": 0.0,
                  "xong": _dem_clip_tren_dia(giong)})
    _chay_dung_tieng()
    logger.info("Câu đệm: bắt đầu dựng %d clip cho giọng %s", so_clip, giong)
    return {"ok": True, "so_clip": so_clip, "giong": giong}


@router.get("/dung-tieng")
async def trang_thai_dung():
    """Tiến độ đếm từ SỐ TỆP THẬT trên đĩa, không phải phần trăm ước lượng.

    `dung_fillers` không báo tiến độ ra ngoài, mà bịa một con số chạy đều là nói
    dối - người dùng đợi theo nó rồi tưởng treo khi nó đứng.
    """
    tren_dia = _dem_clip_tren_dia(_viec["giong"]) if _viec["giong"] else 0
    return {**_viec, "tren_dia": tren_dia,
            "giay": round((_viec["ket_thuc"] or time.time()) - _viec["bat_dau"])
                    if _viec["bat_dau"] else 0}
