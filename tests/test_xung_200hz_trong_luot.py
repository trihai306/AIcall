"""Xung đơn âm ~200Hz TRONG lượt không được giữ lượt mở, cũng không được thổi
phồng thời lượng tiếng dùng để quyết định cắt lời.

Bản ghi `decf104f` (06-09-2026): giữa hai câu khách có 153 khung vượt ngưỡng, tất
cả ≥85% năng lượng dưới 300Hz, tần đỉnh trung vị 200Hz, từng xung 40-200ms cách
nhau 300-900ms (khớp tần khung TDMA GSM 217Hz). `la_gio` bắt đúng loại này nhưng
chỉ chạy lúc MỞ lượt; trong lượt chỉ xét RMS nên mỗi xung đặt lại `silence_ms`.
Đo (`scripts/do_gio_trong_luot.py`): khoảng im dài nhất trong vùng kẹt là 1240ms
nếu chỉ dùng RMS, 2100ms nếu bỏ khung gió - và trong tiếng nói thật, chuỗi khung
"gió" liên tiếp dài nhất chỉ 40-120ms nên không thể tự đếm đủ 1000ms.
"""
import asyncio

import numpy as np

import backend.services.phone_call_service as pcs
from backend.pipeline.session_manager import CallSession
from backend.services.phone_call_service import (
    FRAME_BYTES_LEN, PhoneCallBridge, RATE_LEN,
)


class ReaderGia:
    def __init__(self, khung, bridge):
        self._khung = list(khung)
        self.bridge = bridge

    async def readexactly(self, n: int) -> bytes:
        await asyncio.sleep(0)          # nhường cho task xử lý lượt chạy
        if not self._khung:
            self.bridge.running = False
            raise asyncio.IncompleteReadError(b"", n)
        return self._khung.pop(0)


class PipelineGia:
    def __init__(self, reader=None):
        self.so_luot, self.khung_con_lai, self._reader = 0, None, reader

    async def speculate(self, session, ngay: bool = False):
        pass

    async def process_turn(self, *a, **k):
        self.so_luot += 1
        if self.khung_con_lai is None and self._reader is not None:
            self.khung_con_lai = len(self._reader._khung)


def _im(n):
    return [b"\x00" * FRAME_BYTES_LEN] * n


def _giong(n, muc):
    """Tiếng nói: phổ trải 400-2600Hz, RMS đúng bằng `muc`."""
    mau = FRAME_BYTES_LEN // 2
    ra = []
    for k in range(n):
        t = (np.arange(mau) + k * mau) / RATE_LEN
        x = sum(np.sin(2 * np.pi * f * t) for f in (400, 900, 1800, 2600))
        x = x / float(np.sqrt(np.mean(x ** 2))) * muc
        ra.append(x.astype(np.int16).tobytes())
    return ra


def _xung_200hz(n, muc):
    """Xung đơn âm 200Hz như đo được trên kênh thật, RMS đúng bằng `muc`."""
    mau = FRAME_BYTES_LEN // 2
    ra = []
    for k in range(n):
        t = (np.arange(mau) + k * mau) / RATE_LEN
        x = np.sin(2 * np.pi * 200 * t)
        x = x / float(np.sqrt(np.mean(x ** 2))) * muc
        ra.append(x.astype(np.int16).tobytes())
    return ra


def test_xung_200hz_to_hon_nguong_tat_khong_giu_luot_mo(monkeypatch):
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    # Khách nói 1 giây, rồi kênh chỉ còn xung 200Hz mức 1500 (gấp 3 ngưỡng tắt
    # 500 - nâng ngưỡng RMS không cứu được) cứ 900ms một xung 100ms, suốt 10 giây.
    khung = _im(75) + _giong(50, 3000)
    for _ in range(10):
        khung += _im(45) + _xung_200hz(5, 1500)
    khung += _im(75)

    session = CallSession(customer_name="Khách")
    bridge = PhoneCallBridge(pipeline=PipelineGia(), session=session)
    reader = ReaderGia(khung, bridge)
    bridge.pipeline._reader = reader
    bridge.reader, bridge.running = reader, True
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=10))

    assert bridge.pipeline.so_luot >= 1
    assert bridge.pipeline.khung_con_lai > 100, (
        f"lượt chỉ đóng khi kênh im hẳn (còn {bridge.pipeline.khung_con_lai} khung)"
        " - xung 200Hz vẫn đang đặt lại bộ đếm im lặng")


def test_xung_200hz_khong_thoi_phong_thoi_luong_de_cat_loi(monkeypatch):
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    # AI đang nói (100 khung xếp hàng). Khách "dạ" 300ms - chưa tới 700ms - rồi
    # chỉ còn xung 200Hz. Không có lưới thì tieng_ms = speech_ms - silence_ms bị
    # xung đặt lại silence_ms nên phồng lên quá 700ms và AI bị cắt oan.
    khung = _im(75) + _giong(15, 3000)
    for _ in range(4):
        khung += _im(20) + _xung_200hz(5, 1500)
    khung += _im(75)

    session = CallSession(customer_name="Khách")
    bridge = PhoneCallBridge(pipeline=PipelineGia(), session=session)
    reader = ReaderGia(khung, bridge)
    bridge.reader, bridge.running = reader, True
    for f in _giong(100, 3000):
        bridge._out.put_nowait(f)
    bridge._so_manh.them("dạ hạn mức bên em", 100)
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=10))

    assert bridge._out.qsize() == 100, (
        "tiếng 'dạ' 300ms cộng xung 200Hz không được tính thành 700ms tiếng và cắt lời AI")


def test_tieng_dap_ngan_co_duoi_dai_thap_van_thanh_luot(monkeypatch):
    """Lưới gió trong lượt KHÔNG được làm chặt thêm MIN_TURN_MS.

    Bản ghi `2fe53f0c` (14-08), giây 21,5: một tiếng đáp 180ms (9 khung, dải
    thấp 0,05-0,30) kết bằng 2 khung đuôi dải thấp 0,83 - cách "ừ"/"dạ" kết
    thúc. Chạy lại vòng thu thật (`scripts/chay_lai_vad.py`): luật cũ ra một
    lượt, luật gió coi 2 khung đuôi là im nên phần tiếng đếm được chỉ còn 100ms
    < 130 và lượt BIẾN MẤT. `MIN_TURN_MS=130` đã được hạ hai lần chính vì những
    tiếng đáp một âm tiết như thế (xem chú thích tại chỗ khai báo).
    """
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    khung = _im(75) + _giong(9, 4000) + _xung_200hz(2, 800) + _im(75)

    session = CallSession(customer_name="Khách")
    bridge = PhoneCallBridge(pipeline=PipelineGia(), session=session)
    reader = ReaderGia(khung, bridge)
    bridge.reader, bridge.running = reader, True
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=10))

    assert bridge.pipeline.so_luot == 1, (
        "tiếng đáp 180ms có đuôi dải thấp phải thành lượt như trước khi có lưới gió")
