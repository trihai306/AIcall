import logging
from fastapi import APIRouter
from pydantic import BaseModel

from backend.models import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["calls"])


class CreateSessionRequest(BaseModel):
    customer_name: str = "Khách hàng"
    product: str = "vay tín chấp"
    voice_name: str = "default"


class TextRequest(BaseModel):
    text: str
    session_id: str | None = None


@router.post("/sessions")
async def create_session(req: CreateSessionRequest):
    from backend.main import app_state
    session = app_state.sessions.create(
        customer_name=req.customer_name,
        product=req.product,
        voice_name=req.voice_name,
    )
    return {"session_id": session.session_id, "session": session.to_dict()}


@router.get("/sessions")
async def list_sessions():
    from backend.main import app_state
    return {"sessions": app_state.sessions.list_active()}


@router.get("/history")
async def list_history(page: int = 1, limit: int = 20, q: str = "", status: str = ""):
    """Past calls from SQLite, newest first, with search + status filter.

    q matches customer name, product or session id. Headers only - no transcript.
    """
    limit = max(1, min(limit, 100))
    sessions, total = await db.list_sessions(page=page, limit=limit, q=q, status=status)
    return {
        "sessions": sessions,
        "page": page,
        "limit": limit,
        "total": total,
        "has_more": page * limit < total,
    }


@router.get("/history/stats")
async def history_stats():
    """Aggregate numbers for the session-management dashboard."""
    return {"stats": await db.session_stats()}


@router.delete("/history/{session_id}")
async def delete_history(session_id: str):
    """Hard-delete a session (transcript + metrics) from the call history."""
    from backend.main import app_state
    app_state.sessions.remove(session_id)  # drop from memory too if still live
    deleted = await db.delete_session_record(session_id)
    if not deleted:
        return {"error": "Session not found"}
    return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    from backend.main import app_state
    session = app_state.sessions.get(session_id)
    if session:
        return {"session": session.to_dict()}

    # Not live in memory - look it up in the call history (e.g. after a restart).
    stored = await db.get_session(session_id)
    if stored:
        return {"session": stored}
    return {"error": "Session not found"}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    from backend.main import app_state
    session = app_state.sessions.get(session_id)
    if session:
        # Save the transcript before dropping the session from memory.
        try:
            await db.save_session(session, ended=True)
        except Exception as e:
            logger.warning(f"DB flush on delete failed: {e}")
    app_state.sessions.remove(session_id)
    return {"status": "deleted"}


@router.get("/voices")
async def list_voices():
    """CHÍNH LÀ endpoint phục vụ `/api/voices` — không phải `api/voices.py`.

    Router này mang prefix `/api` TRẦN và được `main.py` đăng ký TRƯỚC
    `voices.router` (prefix `/api/voices`), nên FastAPI khớp route ở đây và bản
    trong `api/voices.py` không bao giờ chạy. Đã mất thời gian vì chỗ này: sửa
    `api/voices.py`, khởi động lại, đọc lại file trên đĩa, soi cả module đã nạp —
    tất cả đều đúng mà kết quả trả về vẫn y như cũ.

    Sửa gì cho danh sách giọng thì sửa Ở ĐÂY, hoặc gộp hẳn hai chỗ lại.

    `mac_dinh` phải có: thiếu nó thì giao diện chọn đại phần tử đầu danh sách,
    mà câu đệm chỉ dựng sẵn cho giọng mặc định -> khách nghe im lặng trọn TTFA
    (đo 07-08: 1741/1067/1817ms, log `KHÔNG có filler cho giọng 'fosd_1'`).
    """
    from backend.main import app_state

    mac_dinh = app_state.tts.default_voice_name()
    ds = app_state.tts.list_voices()
    for v in ds:
        v["mac_dinh"] = (v.get("name") == mac_dinh)
    return {"voices": ds, "mac_dinh": mac_dinh}


@router.get("/health")
async def health_check():
    from backend.main import app_state
    stt_ok = await app_state.stt.health_check()
    llm_ok = await app_state.llm.health_check()
    return {
        "status": "ok" if stt_ok and llm_ok else "degraded",
        "system": getattr(app_state, "system_info", {}),
        "services": {
            "stt": "ok" if stt_ok else "unavailable",
            "llm": "ok" if llm_ok else "unavailable",
            "tts": "loaded" if app_state.tts._is_loaded else "not_loaded",
            "rag": f"{app_state.rag._collection.count() if app_state.rag._collection else 0} docs",
        },
    }
