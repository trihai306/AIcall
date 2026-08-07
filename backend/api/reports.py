"""API trang Báo cáo (Điều 6, mục Báo cáo).

Gom đủ những gì hợp đồng liệt kê vào một chỗ: lọc trạng thái, lọc chất lượng,
lọc thời lượng, gắn nhãn, nghe ghi âm, đọc bản ghi text và tóm tắt ý chính.

Khác tab "Phiên gọi" sẵn có: tab đó là màn hình gỡ lỗi kỹ thuật (độ trễ từng
chặng, phiên đang sống). Đây là màn hình cho người bán hàng.
"""

import csv
import io
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import settings
from backend.models import db, reports_db
from backend.services import recorder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["reports"])


class GanNhan(BaseModel):
    session_ids: list[str]
    label: str = ""          # rỗng = gỡ nhãn


class NhanRequest(BaseModel):
    label_id: str
    name: str
    color: str = "#888888"
    sort_order: int = 0


def _bo_loc(
    from_ts: float | None, to_ts: float | None, campaign_id: str, scenario_id: str,
    outcome: str, quality: str, label: str, gender: str, direction: str,
    min_duration: float | None, max_duration: float | None,
    field1: str, field2: str, field3: str, co_ghi_am: bool, q: str,
    gom_phien_thu: bool = False,
) -> dict:
    return {
        "from_ts": from_ts, "to_ts": to_ts,
        "campaign_id": campaign_id, "scenario_id": scenario_id,
        "outcome": outcome, "quality": quality, "label": label,
        "gender": gender, "direction": direction,
        "min_duration": min_duration, "max_duration": max_duration,
        "field1": field1, "field2": field2, "field3": field3,
        "co_ghi_am": co_ghi_am, "q": q,
        # Xem `_LA_CUOC_GOI_THAT` trong reports_db: mặc định loại phiên thử trên
        # trang Hội thoại ra khỏi báo cáo, vì chúng không phải cuộc gọi.
        "gom_phien_thu": gom_phien_thu,
    }


@router.get("/calls")
async def list_calls(
    from_ts: float | None = None,
    to_ts: float | None = None,
    campaign_id: str = "",
    scenario_id: str = "",
    outcome: str = "",
    quality: str = "",
    label: str = "",
    gender: str = "",
    direction: str = "",
    min_duration: float | None = None,
    max_duration: float | None = None,
    field1: str = "",
    field2: str = "",
    field3: str = "",
    co_ghi_am: bool = False,
    gom_phien_thu: bool = False,
    q: str = "",
    page: int = 1,
    limit: int = 50,
):
    """Danh sách cuộc gọi theo bộ lọc. `q` tìm cả trong nội dung hội thoại."""
    filters = _bo_loc(from_ts, to_ts, campaign_id, scenario_id, outcome, quality,
                      label, gender, direction, min_duration, max_duration,
                      field1, field2, field3, co_ghi_am, q, gom_phien_thu)
    result = await reports_db.list_calls(filters, page=page, limit=limit)
    return {
        **result,
        "page": page,
        "limit": limit,
        "has_more": page * limit < result["total"],
        "outcomes": reports_db.OUTCOMES,
        "qualities": reports_db.QUALITIES,
        "quality_labels": reports_db.NHAN_HIEN_THI,
    }


@router.get("/summary")
async def summary(
    from_ts: float | None = None,
    to_ts: float | None = None,
    campaign_id: str = "",
    scenario_id: str = "",
    outcome: str = "",
    quality: str = "",
    label: str = "",
    gender: str = "",
    direction: str = "",
    min_duration: float | None = None,
    max_duration: float | None = None,
    field1: str = "",
    field2: str = "",
    field3: str = "",
    co_ghi_am: bool = False,
    gom_phien_thu: bool = False,
    q: str = "",
):
    """Số tổng hợp cho ĐÚNG bộ lọc đang áp — không phải cho toàn bộ dữ liệu."""
    filters = _bo_loc(from_ts, to_ts, campaign_id, scenario_id, outcome, quality,
                      label, gender, direction, min_duration, max_duration,
                      field1, field2, field3, co_ghi_am, q, gom_phien_thu)
    return await reports_db.summary(filters)


@router.get("/export")
async def export_calls(
    from_ts: float | None = None,
    to_ts: float | None = None,
    campaign_id: str = "",
    scenario_id: str = "",
    outcome: str = "",
    quality: str = "",
    label: str = "",
    gender: str = "",
    direction: str = "",
    min_duration: float | None = None,
    max_duration: float | None = None,
    field1: str = "",
    field2: str = "",
    field3: str = "",
    co_ghi_am: bool = False,
    gom_phien_thu: bool = False,
    q: str = "",
):
    """Xuất CSV đúng tập đang lọc (không phải chỉ trang đang xem)."""
    filters = _bo_loc(from_ts, to_ts, campaign_id, scenario_id, outcome, quality,
                      label, gender, direction, min_duration, max_duration,
                      field1, field2, field3, co_ghi_am, q, gom_phien_thu)
    result = await reports_db.list_calls(filters, page=1, limit=100_000)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "thoi_gian", "ten_khach", "so_dien_thoai", "chien_dich", "huong",
        "thoi_luong_giay", "so_luot", "ket_qua", "chat_luong", "nhan",
        "gioi_tinh", "co_ghi_am", "chuyen_tiep", "tom_tat",
        "field1", "field2", "field3",
    ])
    for c in result["calls"]:
        w.writerow([
            time.strftime("%d/%m/%Y %H:%M", time.localtime(c["created_at"])),
            c.get("customer_name", ""), c.get("phone", ""),
            c.get("campaign_name") or "", c.get("direction", ""),
            c.get("duration_seconds", 0), c.get("turn_count", 0),
            c.get("outcome", ""), c.get("quality_label") or c.get("quality", ""),
            c.get("label", ""), c.get("gender", ""),
            "có" if c.get("co_ghi_am") else "", c.get("transferred_to", ""),
            (c.get("summary") or "").replace("\n", " "),
            c.get("field1", ""), c.get("field2", ""), c.get("field3", ""),
        ])

    # utf-8-sig để Excel trên Windows hiện đúng tiếng Việt.
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="bao_cao_cuoc_goi.csv"'},
    )


# --- một cuộc gọi -------------------------------------------------------------

@router.get("/calls/{session_id}")
async def call_detail(session_id: str):
    """Chi tiết: toàn văn hội thoại, tóm tắt, số đo độ trễ, bản ghi."""
    phien = await db.get_session(session_id)
    if phien is None:
        return {"error": "Cuộc gọi không tồn tại"}
    phien["quality_label"] = reports_db.NHAN_HIEN_THI.get(phien.get("quality") or "", "")
    phien["co_ghi_am"] = bool(phien.get("recording_path"))
    return {"call": phien}


@router.get("/calls/{session_id}/recording")
async def get_recording(session_id: str):
    """Phát / tải file ghi âm. Kênh trái là khách, kênh phải là bot."""
    phien = await db.get_session(session_id)
    if phien is None:
        return {"error": "Cuộc gọi không tồn tại"}

    duong_dan = phien.get("recording_path") or ""
    if not duong_dan:
        return {"error": "Cuộc gọi này không có bản ghi"}

    tep = Path(duong_dan)
    # Chỉ cho đọc file NẰM TRONG thư mục ghi âm. Đường dẫn tuy do hệ thống ghi
    # ra, nhưng đây là chỗ duy nhất một giá trị trong CSDL biến thành đường dẫn
    # file trả về cho trình duyệt — kiểm ở đây là rẻ nhất.
    goc = settings.recordings_dir.resolve()
    try:
        tep.resolve().relative_to(goc)
    except ValueError:
        logger.warning(f"Đường dẫn bản ghi nằm ngoài thư mục cho phép: {duong_dan}")
        return {"error": "Đường dẫn bản ghi không hợp lệ"}
    if not tep.exists():
        return {"error": "File ghi âm đã bị xoá khỏi ổ đĩa"}

    kieu = "audio/ogg" if tep.suffix == ".opus" else "audio/wav"
    return FileResponse(str(tep), media_type=kieu, filename=tep.name)


@router.post("/calls/{session_id}/summarize")
async def summarize_call(session_id: str):
    """Tóm tắt lại một cuộc gọi (chạy ngay, không qua hàng đợi)."""
    from backend.main import app_state
    from backend.services.summarizer import tom_tat_phien

    ket_qua = await tom_tat_phien(session_id, app_state.llm)
    if ket_qua is None:
        return {"error": "Không tóm tắt được — bản ghi quá ngắn hoặc LLM không sẵn sàng"}
    return {"summary": ket_qua}


@router.post("/summarize-pending")
async def summarize_pending(limit: int = 50):
    """Chạy bù tóm tắt cho các cuộc gọi cũ chưa có."""
    from backend.main import app_state
    from backend.services.summarizer import chay_bu

    return await chay_bu(app_state.llm, limit)


@router.get("/summarizer/status")
async def summarizer_status():
    from backend.services.summarizer import bo_tom_tat

    return bo_tom_tat.trang_thai()


# --- nhãn ---------------------------------------------------------------------

@router.get("/labels")
async def list_labels():
    return {"labels": await reports_db.list_labels()}


@router.post("/labels")
async def upsert_label(req: NhanRequest):
    label_id = req.label_id.strip()
    if not label_id:
        return {"error": "Thiếu mã nhãn"}
    return {"label": await reports_db.upsert_label(
        label_id, req.name.strip() or label_id, req.color, req.sort_order
    )}


@router.delete("/labels/{label_id}")
async def delete_label(label_id: str):
    """Xoá nhãn. Các cuộc gọi đang mang nhãn này sẽ được gỡ nhãn."""
    if not await reports_db.delete_label(label_id):
        return {"error": "Nhãn không tồn tại"}
    return {"deleted": label_id}


@router.post("/label")
async def set_label(req: GanNhan):
    """Gắn (hoặc gỡ) nhãn cho nhiều cuộc gọi một lúc."""
    if not req.session_ids:
        return {"error": "Chưa chọn cuộc gọi nào"}
    if req.label:
        hop_le = {l["label_id"] for l in await reports_db.list_labels()}
        if req.label not in hop_le:
            return {"error": f"Nhãn '{req.label}' không tồn tại"}
    return {"updated": await reports_db.set_label(req.session_ids, req.label)}


# --- dung lượng ghi âm --------------------------------------------------------

@router.get("/recordings/stats")
async def recording_stats():
    thong_ke = await __import__("asyncio").to_thread(
        recorder.thong_ke, settings.recordings_dir
    )
    return {
        **thong_ke,
        "dung_luong_mb": round(thong_ke["dung_luong"] / 1024 / 1024, 1),
        "giu_ngay": settings.recordings_giu_ngay,
    }


@router.post("/recordings/cleanup")
async def cleanup_recordings(older_than_days: int | None = None):
    """Xoá bản ghi cũ. Không truyền tham số thì dùng hạn lưu trữ trong .env."""
    import asyncio as _asyncio

    giu = settings.recordings_giu_ngay if older_than_days is None else older_than_days
    if giu <= 0:
        return {"error": "Số ngày giữ phải lớn hơn 0 — truyền 0 nghĩa là giữ mãi"}
    ket_qua = await _asyncio.to_thread(
        recorder.don_file_cu, settings.recordings_dir, giu
    )
    logger.info(f"Dọn ghi âm cũ hơn {giu} ngày: {ket_qua}")
    return {**ket_qua, "giai_phong_mb": round(ket_qua["giai_phong"] / 1024 / 1024, 1)}
