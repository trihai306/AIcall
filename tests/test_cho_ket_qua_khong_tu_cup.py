"""Vòng theo dõi cuộc gọi KHÔNG được tự cúp máy ngay sau khi bấm số.

Lỗi thật, bắt được 14-08-2026 trên cuộc gọi thật tới 0396130621:

    08:42:12  ADB dialled 0396130621
    08:42:13  đã đóng cầu tiếng (0 lượt)
    08:42:13  cuộc gọi tay kết thúc: busy

Đúng MỘT giây. Không ai bấm nút kết quả cả - chính `cho_ket_qua` trả về 'busy'
rồi `_theo_doi_cuoc_goi_tay` gọi `dialer_service.hangup`.

Cơ chế: `dialer_service` bắn intent quay số rồi trả về ngay, còn tổng đài của
máy mất một lúc mới rời trạng thái rảnh. Lần đọc ĐẦU TIÊN của
`precise_call_state` vẫn ra 0 = rảnh, và nhánh "rảnh mà chưa tới 8 giây" coi đó
là máy bận.

Người dùng thấy đúng triệu chứng "bấm gọi được mà không nghe thấy gì": AI chỉ
chào SAU khi nối máy (`chao_khi_bat_may` chờ mã 1), mà cuộc gọi đã bị chính hệ
thống cúp trước khi kịp đổ chuông.
"""
import asyncio

import pytest

from backend.services import campaign_runner as cr


class _Phien:
    phone = "0396130621"
    la_hop_thu_thoai = False


def _chay(day_trang_thai, dung=None):
    """Chạy `cho_ket_qua` với một dãy trạng thái giả, trả kết quả."""
    day = list(day_trang_thai)

    async def _gia(serial):
        return day.pop(0) if day else (0, "rảnh")

    async def _main():
        goc = cr.adb_service.precise_call_state if hasattr(cr, "adb_service") else None
        from backend.services import adb_service
        that = adb_service.precise_call_state
        adb_service.precise_call_state = _gia
        try:
            return await cr.cho_ket_qua({"kind": "adb", "address": "x"},
                                        _Phien(), None, dung or asyncio.Event())
        finally:
            adb_service.precise_call_state = that

    return asyncio.run(_main())


def test_khong_ket_luan_busy_khi_may_chua_kip_len(monkeypatch):
    """Ca đã hỏng: đọc đầu tiên ra 'rảnh' vì máy chưa chuyển trạng thái.

    Sau đó cuộc gọi lên (đổ chuông rồi nhấc máy) thì phải theo tới cùng, chứ
    không được chốt 'busy' ở lần đọc đầu.
    """
    monkeypatch.setattr(cr, "_NHIP_THAM", 0.0)
    ket = _chay([(0, "rảnh"), (0, "rảnh"), (3, "đổ chuông"),
                 (1, "đã nhấc máy"), (1, "đã nhấc máy"), (0, "rảnh")])
    assert ket == "done", "tự chốt busy ngay sau khi bấm số - đúng lỗi 14-08"


def test_van_bao_busy_khi_dut_SAU_khi_da_do_chuong(monkeypatch):
    """Giữ nguyên hành vi đúng: lên rồi tắt sớm thì vẫn là máy bận."""
    monkeypatch.setattr(cr, "_NHIP_THAM", 0.0)
    assert _chay([(3, "đổ chuông"), (0, "rảnh")]) == "busy"


def test_quay_so_hong_thi_van_chot_chu_khong_treo(monkeypatch):
    """Không lên được thật (số sai, mất sóng) thì phải chốt, đừng giữ máy mãi."""
    monkeypatch.setattr(cr, "_NHIP_THAM", 0.0)
    monkeypatch.setattr(cr, "_CHO_LEN_S", 0.0)
    assert _chay([(0, "rảnh")]) == "no_answer"


def test_cho_len_ngan_hon_cho_bat_may():
    """Chờ lên phải ngắn hơn chờ bắt máy, không thì số hỏng giữ máy quá lâu."""
    assert 0 < cr._CHO_LEN_S < cr._CHO_BAT_MAY_S
