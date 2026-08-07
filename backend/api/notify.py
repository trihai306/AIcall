"""API kênh thông báo (Điều 6: "Gửi báo cáo qua zalo hoặc telegram").

Chốt Telegram, bỏ Zalo — xem đầu services/notify_service.py để biết lý do.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services import notify_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notify", tags=["notify"])


class KenhRequest(BaseModel):
    channel_id: str = ""              # rỗng = tạo mới
    kind: str = "telegram"
    name: str = "Telegram"
    token: str = ""                   # để trống hoặc "***" khi sửa mà không đổi token
    chat_id: str = ""
    events: list[str] = ["call_success", "daily_summary", "campaign_done"]
    enabled: bool = True


class GuiThuRequest(BaseModel):
    channel_id: str = ""
    text: str = "Tin nhắn thử từ hệ thống gọi tự động."


@router.get("/channels")
async def list_channels():
    """Danh sách kênh. Token luôn bị che thành *** trước khi trả ra."""
    return {
        "channels": await notify_service.list_channels(),
        "events": notify_service.SU_KIEN,
        "huong_dan": {
            "telegram": (
                "1) Nhắn @BotFather trên Telegram, gõ /newbot để tạo bot và lấy token. "
                "2) Nhắn một câu bất kỳ cho bot vừa tạo. "
                "3) Mở https://api.telegram.org/bot<TOKEN>/getUpdates để lấy chat_id."
            )
        },
    }


@router.post("/channels")
async def upsert_channel(req: KenhRequest):
    if req.kind != "telegram":
        return {"error": "Hiện chỉ hỗ trợ Telegram"}
    kenh = await notify_service.upsert_channel(
        req.channel_id,
        kind=req.kind,
        name=req.name.strip() or "Telegram",
        config={"token": req.token.strip(), "chat_id": req.chat_id.strip()},
        events=req.events,
        enabled=req.enabled,
    )
    if kenh is None:
        return {"error": "Không lưu được kênh — database chưa sẵn sàng"}
    return {"channel": kenh}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str):
    if not await notify_service.delete_channel(channel_id):
        return {"error": "Kênh không tồn tại"}
    return {"deleted": channel_id}


@router.post("/test")
async def send_test(req: GuiThuRequest):
    """Gửi thử một tin. Báo lại đúng lỗi Telegram trả về nếu hỏng."""
    kenh = await notify_service.list_channels(che_token=False)
    if req.channel_id:
        kenh = [k for k in kenh if k["channel_id"] == req.channel_id]
    if not kenh:
        return {"error": "Chưa có kênh nào — thêm kênh Telegram trước"}

    import json as _json

    ket_qua = []
    for k in kenh:
        try:
            config = _json.loads(k.get("config") or "{}")
        except ValueError:
            config = {}
        ok, loi = await notify_service._gui_telegram(config, req.text)
        ket_qua.append({"channel_id": k["channel_id"], "name": k["name"],
                        "ok": ok, "loi": loi})
    return {"ket_qua": ket_qua}


@router.post("/daily-summary")
async def send_daily_summary(campaign_id: str = ""):
    """Gửi ngay bản tổng hợp hôm nay, không đợi tới giờ hẹn."""
    return await notify_service.bao_tong_hop_ngay(campaign_id)
