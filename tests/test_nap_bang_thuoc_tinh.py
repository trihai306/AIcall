"""Bảng thuộc tính phải được GIEO trước khi đọc, không thì lưới chết lặng lẽ.

Lỗi thật, phát hiện 09-09-2026 khi thử tư vấn qua trang Nhắn tin trên máy chạy
thật: AI trả lời "thu nhập 15 triệu thì vay tối đa khoảng 300 triệu" - con số
300 không có trong tài liệu nào - mà `metrics` KHÔNG có `chan_thuoc_tinh`, và
`logs/backend.log` không có một dòng "THUỘC TÍNH LỆCH" nào.

Gọi thẳng `chan_thuoc_tinh_sai` trên đúng câu đó thì nó CHẶN đúng. Tức lưới
không hỏng - nó chưa từng chạy.

Nguyên nhân: `StreamingPipeline.__init__` gọi `doc_bang_sync(conn)`, hàm này chỉ
ĐỌC. Hàm gieo `gieo_mac_dinh_sync` chỉ được gọi trong vỏ async `luat_kiem_db.
doc_bang()`, mà vỏ đó chỉ chạy khi có người mở trang quản lý luật kiểm. Không ai
mở thì bảng `thuoc_tinh_kiem` rỗng 0 dòng, `doc_bang_sync` trả `{}`, và
`chan_thuoc_tinh_sai` thoát ngay ở `if not kho`.

Đây đúng thứ mà chú thích tại chỗ nạp muốn tránh ("mất lưới lặng lẽ nguy hiểm
hơn nhiều so với dùng bảng cũ") - nhưng bảng RỖNG không phải ngoại lệ nên nó
không rơi vào nhánh `except`.
"""
import asyncio

import pytest

from backend.models import db
from backend.pipeline.streaming_pipeline import _nap_bang_thuoc_tinh
from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH


@pytest.fixture()
def _db_moi(tmp_path):
    asyncio.run(db.init_db(str(tmp_path / "t.db")))
    yield
    asyncio.run(db.close_db())


def test_db_moi_tinh_thi_van_co_bang(_db_moi):
    """DB chưa ai gieo -> vẫn phải ra bảng đầy đủ, không được trả rỗng."""
    bang = _nap_bang_thuoc_tinh()
    assert bang, "bảng rỗng -> lưới thuộc tính chết lặng lẽ"
    assert "lãi suất" in bang and "hạn mức" in bang


def test_gieo_xong_thi_bang_nam_trong_DB(_db_moi):
    """Gieo phải GHI vào DB, để trang quản lý mở ra là thấy ngay."""
    _nap_bang_thuoc_tinh()
    c = db.connection()
    n = c.execute("SELECT COUNT(*) FROM thuoc_tinh_kiem").fetchone()[0]
    assert n >= len(THUOC_TINH_MAC_DINH), f"chỉ có {n} dòng trong DB"


def test_DB_chua_mo_thi_dung_bang_goc():
    """Không có DB thì rơi về bảng trong code, KHÔNG tắt lưới."""
    asyncio.run(db.close_db())
    bang = _nap_bang_thuoc_tinh()
    assert bang == THUOC_TINH_MAC_DINH


def test_TAT_HET_thuoc_tinh_thi_TON_TRONG(_db_moi):
    """Người vận hành tắt hết thì lưới im - đó là quyền của họ, không gieo đè.

    Phân biệt được với ca "chưa gieo" nhờ đếm SỐ DÒNG: có dòng mà không dòng nào
    bật nghĩa là đã có người quyết định, còn 0 dòng nghĩa là chưa ai gieo.
    """
    _nap_bang_thuoc_tinh()
    c = db.connection()
    c.execute("UPDATE thuoc_tinh_kiem SET bat=0")
    c.commit()
    assert _nap_bang_thuoc_tinh() == {}
