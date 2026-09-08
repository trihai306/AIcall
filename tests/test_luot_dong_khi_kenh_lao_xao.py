"""Kênh khách lạo xạo thì lượt vẫn phải đóng - đừng bắt khách chờ tới trần 15s.

Cuộc gọi thật `decf104f` (06-09-2026): khách nói xong lúc 19:05:19 nhưng lượt
mãi 19:05:33 mới đóng - đúng `MAX_TURN_MS=15000`. Đo trên chính bản ghi đó
(`scripts/do_khoang_im.py`): từ giây 11,7 tới 30,1, tức suốt 18,4 giây, kênh
khách KHÔNG có lấy một khoảng im 1000ms nào - dài nhất 900ms. Mà
`PHONE_SILENCE_END_MS=1000`, nên `silence_ms` bị đặt lại hoài và lượt không thể
đóng bằng đường im lặng.

Thủ phạm là ngưỡng TẮT: quét lại trên bản ghi (`scripts/quet_nguong.py`) cho
khoảng im dài nhất trong vùng đó theo từng ngưỡng —
    400 (cũ) -> 920ms   -> KẸT
    500      -> 1240ms  -> đóng được
Người dùng báo đúng triệu chứng: "đang nói nó im không trả lời".
"""
import asyncio

import numpy as np

import backend.services.phone_call_service as pcs

from backend.pipeline.session_manager import CallSession
from backend.services.phone_call_service import (
    FRAME_BYTES_LEN, PhoneCallBridge, RATE_LEN,
)


class ReaderGia:
    def __init__(self, khung, bridge=None):
        self._khung = list(khung)
        self.bridge = bridge

    async def readexactly(self, n: int) -> bytes:
        # PHẢI nhường điều khiển: `_handle_turn` chạy trong task nền, mà vòng
        # thu chỉ await đúng chỗ này. Không nhường thì vòng thu đọc tuốt tới hết
        # khung rồi task mới chạy - và test đo ra "lượt đóng lúc hết khung" với
        # mọi ngưỡng, tức đo nhầm chính thứ đang muốn đo.
        await asyncio.sleep(0)
        if not self._khung:
            if self.bridge is not None:
                self.bridge.running = False
            raise asyncio.IncompleteReadError(b"", n)
        return self._khung.pop(0)


class PipelineGia:
    """Ghi lại lượt đóng vào LÚC NÀO, không chỉ có đóng hay không.

    Chỉ đếm số lượt là không đủ: chuỗi thử nào kết bằng một quãng im đủ dài thì
    lượt cũng đóng, kể cả khi ngưỡng sai - test sẽ xanh mà chẳng chứng minh gì.
    """

    def __init__(self):
        self.so_luot = 0
        self.khung_con_lai = None   # còn bao nhiêu khung chưa đọc lúc lượt đóng

    def gan_reader(self, reader):
        self._reader = reader

    async def speculate(self, session, ngay: bool = False):
        pass

    async def process_turn(self, *a, **k):
        self.so_luot += 1
        if self.khung_con_lai is None:
            self.khung_con_lai = len(self._reader._khung)


def _khung(n: int, muc: int) -> list[bytes]:
    """muc=0 là im tuyệt đối; còn lại là tiếng có phổ giọng, RMS ĐÚNG bằng `muc`.

    Phải chuẩn theo RMS chứ không chia bừa cho số sóng: vòng thu so `muc` với
    ngưỡng bằng chính RMS, nên chia sai thì khung "mức 450" hoá ra RMS 159 và
    test đo nhầm một dải khác hẳn dải đang muốn thử.
    """
    if muc == 0:
        return [b"\x00" * FRAME_BYTES_LEN] * n
    mau = FRAME_BYTES_LEN // 2
    ra = []
    for k in range(n):
        t = (np.arange(mau) + k * mau) / RATE_LEN
        x = sum(np.sin(2 * np.pi * f * t) for f in (400, 900, 1800, 2600))
        x = x / float(np.sqrt(np.mean(x ** 2))) * muc
        ra.append(x.astype(np.int16).tobytes())
    return ra


def test_tieng_lao_xao_duoi_nguong_khong_giu_luot_mo_mai(monkeypatch):
    # Ép đúng cấu hình của cuộc gọi thật. Không ép thì test đo theo .env của máy
    # đang chạy: ở 750ms, khoảng im 900ms dưới đây tự nó đã đủ đóng lượt, và
    # test xanh với CẢ ngưỡng cũ lẫn mới - tức chẳng chứng minh gì.
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    # 75 khung im để đo nền, khách nói 1 giây, rồi kênh lạo xạo: cứ 900ms im lại
    # có 100ms tiếng mức ~450 - đúng dải đã giết cuộc gọi thật.
    khung = _khung(75, 0) + _khung(50, 3000)
    for _ in range(10):                       # 10 giây lạo xạo
        khung += _khung(45, 0) + _khung(5, 450)
    khung += _khung(75, 0)                    # rồi mới im hẳn 1,5 giây

    session = CallSession(customer_name="Khách")
    pipeline = PipelineGia()
    bridge = PhoneCallBridge(pipeline=pipeline, session=session)
    reader = ReaderGia(khung, bridge)
    pipeline.gan_reader(reader)
    bridge.reader = reader
    bridge.running = True
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=10))

    assert pipeline.so_luot >= 1, "lượt không bao giờ đóng"
    # Lượt phải đóng TRONG lúc kênh còn lạo xạo, chứ không phải đợi tới quãng im
    # cuối cùng. Còn > 100 khung (2 giây) chưa đọc nghĩa là nó đóng sớm; đợi tới
    # cuối thì con số này tụt về gần 0.
    assert pipeline.khung_con_lai > 100, (
        f"lượt chỉ đóng khi kênh im hẳn (còn {pipeline.khung_con_lai} khung) - "
        "khách phải ngồi nghe im lặng suốt lúc kênh lạo xạo")
