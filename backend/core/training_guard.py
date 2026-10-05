"""Keep GPU training away from live phone service on a single GPU."""

from __future__ import annotations


def busy_reason(voice_calls: list[dict], campaigns: list[dict],
                inbound_devices: list[dict]) -> str:
    if any(call.get("running") for call in voice_calls):
        return "Đang có cuộc gọi dùng AI; chờ cuộc gọi kết thúc rồi train."
    if any(c.get("trang_thai") == "dang_chay" for c in campaigns):
        return "Chiến dịch gọi điện đang chạy; GPU phải ưu tiên khách."
    if any(d.get("dang_nghe") for d in inbound_devices):
        return "Máy đang tự nhận cuộc gọi đến; không thể lấy GPU khỏi dịch vụ khách."
    return ""


def live_service_busy_reason() -> str:
    from backend.core.service_priority import (
        customer_turns_active, customer_cooldown_remaining,
    )
    if customer_turns_active():
        return "Khách đang trao đổi trên web; chờ hết lượt rồi train."
    if customer_cooldown_remaining() > 0:
        return "Khách vừa tương tác; chờ hai phút yên lặng rồi train."

    from backend.services.phone_call_service import phone_calls
    from backend.services.campaign_runner import campaigns
    from backend.services.inbound_service import goi_vao

    return busy_reason(phone_calls.status(), campaigns.all_progress(),
                       goi_vao.trang_thai())
