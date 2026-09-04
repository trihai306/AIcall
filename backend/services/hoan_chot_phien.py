"""Hoãn chốt phiên một nhịp sau khi trình duyệt ngắt kết nối.

VÌ SAO CÓ TỆP NÀY. Ngắt WebSocket -> `chot_phien` -> `sessions.remove(id)`.
Đúng cho cuộc gọi thật: khách cúp máy là hết cuộc, phải chốt ngay để trang Báo
cáo có số. Nhưng trên web thì TẢI LẠI TRANG cũng ngắt WebSocket, mà đó không
phải hết cuộc.

Đo 2026-09-04: F5 xong, trình duyệt gửi lại đúng `/ws/call/7e590a03` (có trong
log), server không còn phiên đó nên cấp mã mới `bd5a15cc` và khung chat trống.
Bot cũng quên sạch - đúng thứ người dùng báo.

Nên chờ một nhịp rồi hãy chốt. Nối lại kịp thì huỷ hẹn; không thì chốt như cũ,
chỉ muộn hơn vài chục giây.

KHÔNG áp cho cuộc gọi điện thoại: bên đó cúp máy là hết thật, chốt muộn làm
trang Báo cáo hiện sai trạng thái suốt quãng chờ.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# Bao lâu thì coi như người dùng đã bỏ đi thật.
#
# Đủ dài cho: tải lại trang (~2-4s), mất mạng chớp nhoáng, máy ngủ vài giây.
# Không dài hơn mức cần: suốt quãng này phiên còn nằm trong bộ nhớ và chưa hiện
# ở trang Báo cáo, nên đặt vài phút là người dùng tưởng mất cuộc.
GIAY_CHO_MAC_DINH = 90.0


class HoanChot:
    """Giữ các hẹn chốt phiên đang chờ, theo mã phiên."""

    def __init__(self, giay: float = GIAY_CHO_MAC_DINH, chot=None):
        self.giay = giay
        self.chot = chot
        self._hen: dict[str, asyncio.Task] = {}

    def hen(self, session_id: str) -> None:
        """Hẹn chốt phiên sau `giay`. Hẹn lại cùng phiên thì thay hẹn cũ."""
        cu = self._hen.pop(session_id, None)
        if cu is not None and not cu.done():
            cu.cancel()
        self._hen[session_id] = asyncio.ensure_future(self._cho_roi_chot(session_id))

    def huy(self, session_id: str) -> bool:
        """Huỷ hẹn vì phiên vừa được nối lại. True nếu thật sự có hẹn để huỷ."""
        t = self._hen.pop(session_id, None)
        if t is None:
            return False
        if not t.done():
            t.cancel()
        return True

    def dang_cho(self) -> int:
        return len(self._hen)

    async def _cho_roi_chot(self, session_id: str) -> None:
        try:
            await asyncio.sleep(self.giay)
        except asyncio.CancelledError:
            return
        # Bỏ khỏi sổ TRƯỚC khi chốt: chốt có thể ném lỗi, mà để lại hẹn đã chạy
        # xong thì lần ngắt sau `hen()` đi huỷ một task đã chết và tưởng là đã
        # thay được hẹn.
        self._hen.pop(session_id, None)
        try:
            ra = self.chot(session_id) if self.chot else None
            if asyncio.iscoroutine(ra):
                await ra
        except Exception as e:
            # Task này không ai await. Không bắt lỗi ở đây thì Python chỉ ghi
            # "Task exception was never retrieved" lúc thu gom rác - chìm nghỉm,
            # và phiên vĩnh viễn không được chốt mà không ai biết.
            logger.error("Chốt phiên %s hỏng: %s", session_id, e)
