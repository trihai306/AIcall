"""Bộ khử vọng phải được NỐI đúng hai đầu của cầu tiếng:
  - `_write_loop` đưa khung ĐÃ ghi xuống máy vào làm tham chiếu;
  - `_read_loop` cho khung micro đi qua bộ khử TRƯỚC khi VAD/STT thấy nó.
Bản ghi cuộc gọi vẫn nhận khung micro THÔ (quyết định 06-09-2026: giữ bằng
chứng để đo lại và thử thuật toán mới sau này).
"""
import asyncio

import numpy as np

from backend.pipeline.session_manager import CallSession
from backend.services.phone_call_service import (
    FRAME_BYTES_LEN, FRAME_BYTES_XUONG, PhoneCallBridge, RATE_LEN,
)


class ReaderGia:
    def __init__(self, khung, bridge):
        self._khung, self.bridge = list(khung), bridge

    async def readexactly(self, n):
        await asyncio.sleep(0)
        if not self._khung:
            self.bridge.running = False
            raise asyncio.IncompleteReadError(b"", n)
        return self._khung.pop(0)


class PipelineGia:
    def __init__(self):
        self.so_luot = 0

    async def speculate(self, *a, **k):
        pass

    async def process_turn(self, *a, **k):
        self.so_luot += 1


class KhuVongXoaSach:
    """Bộ khử giả: coi mọi thứ là vọng, trả về im lặng. Nếu vòng thu dùng nó
    thì không lượt nào mở được dù micro rất to."""
    dang_thuc = True
    la_vong = False

    def __init__(self):
        self.tham_chieu = []

    def them_tham_chieu(self, x):
        self.tham_chieu.append(np.asarray(x))

    def xu_ly(self, m):
        return np.zeros_like(m)


def _giong(n, muc=3000):
    mau = FRAME_BYTES_LEN // 2
    ra = []
    for k in range(n):
        t = (np.arange(mau) + k * mau) / RATE_LEN
        x = sum(np.sin(2 * np.pi * f * t) for f in (400, 900, 1800, 2600))
        ra.append((x / float(np.sqrt(np.mean(x ** 2))) * muc).astype(np.int16).tobytes())
    return ra


def _bridge_co_khu_vong(khu_vong, pipeline=None):
    """Cầu tiếng với bộ khử BẬT (cờ `phone_khu_vong` mặc định tắt cho tới khi
    nghiệm thu offline đạt - test dây thì phải bật tay)."""
    bridge = PhoneCallBridge(pipeline=pipeline or PipelineGia(),
                             session=CallSession(customer_name="Khách"))
    bridge.khu_vong, bridge.khu_vong_bat = khu_vong, True
    return bridge


def test_vong_thu_cho_khung_mic_qua_bo_khu_truoc_khi_vad():
    bridge = _bridge_co_khu_vong(KhuVongXoaSach())
    khung = [b"\x00" * FRAME_BYTES_LEN] * 75 + _giong(50) + [b"\x00" * FRAME_BYTES_LEN] * 75
    bridge.reader, bridge.running = ReaderGia(khung, bridge), True
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=10))
    assert bridge.pipeline.so_luot == 0, (
        "micro to mà bộ khử trả im lặng thì VAD không được thấy tiếng - "
        "tức khung chưa đi qua bộ khử")


def test_vong_ghi_dua_khung_da_phat_vao_tham_chieu():
    bridge = _bridge_co_khu_vong(KhuVongXoaSach())

    class WriterGia:
        def __init__(self):
            self.n = 0

        def write(self, b):
            self.n += 1
            if self.n >= 20:
                bridge.running = False

        async def drain(self):
            pass

    bridge.writer, bridge.running = WriterGia(), True
    for _ in range(20):
        bridge._out.put_nowait(b"\x01" * FRAME_BYTES_XUONG)
    try:
        asyncio.run(asyncio.wait_for(bridge._write_loop(), timeout=5))
    except asyncio.TimeoutError:
        pass
    assert len(bridge.khu_vong.tham_chieu) == 20, "mỗi khung ghi xuống máy phải thành một khung tham chiếu"
    assert all(len(x) == FRAME_BYTES_LEN // 2 for x in bridge.khu_vong.tham_chieu), (
        "tham chiếu phải ở tần số kênh LÊN (8kHz) để căn được với micro")


class KhuVongDanhDauVong:
    """Bộ khử giả: trả khung NGUYÊN VẸN nhưng bảo VAD rằng đó là vọng.
    Nếu VAD tôn trọng cờ thì không lượt nào mở dù micro rất to."""
    dang_thuc = True
    la_vong = True

    def them_tham_chieu(self, x):
        pass

    def xu_ly(self, m):
        return m


def test_khung_bi_danh_dau_vong_khong_mo_luot():
    bridge = _bridge_co_khu_vong(KhuVongDanhDauVong())
    khung = [b"\x00" * FRAME_BYTES_LEN] * 75 + _giong(50) + [b"\x00" * FRAME_BYTES_LEN] * 75
    bridge.reader, bridge.running = ReaderGia(khung, bridge), True
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=10))
    assert bridge.pipeline.so_luot == 0, "khung vọng không được mở lượt"


def test_khung_vong_khong_giu_luot_mo(monkeypatch):
    """Khách nói 1 giây rồi chỉ còn vọng AI: lượt phải đóng đúng sau 1s im, chứ
    không bị vọng kéo dài. Đây là cơ chế đẻ ra chữ rác trong CSDL cuộc 1c1c3b16:
    khách nói ngắn, đuôi lượt toàn tiếng AI vọng, STT phiên âm cả đuôi."""
    import backend.services.phone_call_service as pcs
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)

    class KhuVongVongSauGiay2:
        dang_thuc = True
        la_vong = False
        def __init__(self): self.i = 0
        def them_tham_chieu(self, x): pass
        def xu_ly(self, m):
            self.i += 1
            self.la_vong = self.i > 75 + 50      # từ sau giây nói của khách: toàn vọng
            return m

    pipeline = PipelineGia()
    bridge = _bridge_co_khu_vong(KhuVongVongSauGiay2(), pipeline)
    khung = [b"\x00" * FRAME_BYTES_LEN] * 75 + _giong(50) + _giong(200, 1500) + [b"\x00" * FRAME_BYTES_LEN] * 75
    reader = ReaderGia(khung, bridge)
    bridge.reader, bridge.running = reader, True

    con_lai = []
    async def process_turn(*a, **k):
        con_lai.append(len(reader._khung))
    pipeline.process_turn = process_turn
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=10))
    assert con_lai, "phải có lượt cho 1 giây khách nói"
    assert con_lai[0] > 150, (
        f"lượt đóng khi còn {con_lai[0]} khung - tức bị 4 giây vọng kéo dài")


def test_mac_dinh_tat_thi_khong_dung_vao_khung():
    """Cờ tắt (mặc định) thì khung đi thẳng, bộ khử không được gọi - đường thật
    phải y hệt trước khi có bộ khử cho tới khi nghiệm thu đạt."""
    bridge = PhoneCallBridge(pipeline=PipelineGia(), session=CallSession(customer_name="Khách"))
    bridge.khu_vong = KhuVongXoaSach()          # nếu bị gọi thì không lượt nào mở
    assert bridge.khu_vong_bat is False
    khung = [b"\x00" * FRAME_BYTES_LEN] * 75 + _giong(50) + [b"\x00" * FRAME_BYTES_LEN] * 75
    bridge.reader, bridge.running = ReaderGia(khung, bridge), True
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=10))
    assert bridge.pipeline.so_luot == 1
