"""Hoãn chốt phiên một nhịp sau khi trình duyệt ngắt kết nối.

VÌ SAO. Ngắt WebSocket -> `chot_phien` -> `sessions.remove(id)`. Đúng cho cuộc
gọi thật: khách cúp máy là hết cuộc. Nhưng trên web, TẢI LẠI TRANG cũng ngắt
WebSocket - và đó không phải hết cuộc. Đo được 2026-09-04: F5 xong thì trình
duyệt gửi lại đúng `/ws/call/7e590a03`, server không còn phiên đó nên cấp mã
mới và khung chat trống trơn.

Nên chờ một nhịp trước khi chốt. Nối lại kịp thì huỷ hẹn; không nối lại thì
chốt như cũ, chỉ muộn hơn vài chục giây.
"""
import asyncio

from backend.services.hoan_chot_phien import HoanChot


def chay(coro):
    """Chạy coroutine trong test đồng bộ.

    Dự án không có `pytest-asyncio` và cố ý không thêm gói mới, nên gói vào
    `asyncio.run` thay vì kéo thêm một phụ thuộc cho sáu test.
    """
    return asyncio.run(coro)


def test_khong_ai_noi_lai_thi_van_chot():
    async def _t():
        da_chot = []
        h = HoanChot(giay=0.05, chot=lambda s: da_chot.append(s))
        h.hen("abc")
        await asyncio.sleep(0.2)
        assert da_chot == ["abc"]
    chay(_t())


def test_noi_lai_kip_thi_KHONG_chot():
    async def _t():
        da_chot = []
        h = HoanChot(giay=0.3, chot=lambda s: da_chot.append(s))
        h.hen("abc")
        assert h.huy("abc") is True
        await asyncio.sleep(0.45)
        assert da_chot == []
    chay(_t())


def test_huy_phien_khong_co_hen_thi_bao_khong_co():
    async def _t():
        h = HoanChot(giay=0.05, chot=lambda s: None)
        assert h.huy("chua-tung-co") is False
    chay(_t())


def test_hen_lai_cung_phien_thi_khong_chot_hai_lan():
    async def _t():
        da_chot = []
        h = HoanChot(giay=0.05, chot=lambda s: da_chot.append(s))
        h.hen("abc")
        h.hen("abc")
        await asyncio.sleep(0.25)
        assert da_chot == ["abc"]
    chay(_t())


def test_chot_hong_thi_khong_lam_do_ca_tien_trinh():
    async def _t():
        def no(_):
            raise RuntimeError("hỏng")
        h = HoanChot(giay=0.05, chot=no)
        h.hen("abc")
        await asyncio.sleep(0.2)
        assert h.dang_cho() == 0
    chay(_t())


def test_chot_xong_thi_khong_giu_hen_nua():
    async def _t():
        h = HoanChot(giay=0.05, chot=lambda s: None)
        h.hen("abc")
        await asyncio.sleep(0.2)
        assert h.dang_cho() == 0
    chay(_t())
