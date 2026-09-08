"""Tiếng nền (TV, người khác) nhỏ hơn hẳn mức khách ĐÃ BIẾT thì không được mở lượt
mới và không được cắt lời AI.

Cuộc 022eb3e5 (06-09-2026, TV mở): khách nói ở đỉnh 6383-6713; TV 800-1800 vẫn
(1) cắt lời AI lúc 21:38:33 (760ms tiếng, chữ rỗng) và (2) thành một lượt 13s
"trời đẹp thiệt... thích hợp để leo" mà AI đáp lại.

Đo trên 9 cuộc thật (`scripts/do_dinh_tung_luot.py`): lượt khách thật thấp nhất
bằng 0,39× mức to nhất trước đó của chính họ; TV chỉ 0,14-0,27×. Hai ngưỡng:
cắt lời ≥ 0,30× (bỏ sót một lần cắt lời là nhẹ), mở lượt ≥ 0,20× (bỏ sót lượt
khách là nặng - lấy thêm biên). Mốc mức khách suy giảm theo thời gian để khách
nói nhỏ đi hay đổi tay cầm máy vẫn được nghe.
"""
import asyncio

import numpy as np

import backend.services.phone_call_service as pcs
from backend.pipeline.session_manager import CallSession
from backend.services.phone_call_service import FRAME_BYTES_LEN, PhoneCallBridge, RATE_LEN


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


def _giong(n, muc):
    mau = FRAME_BYTES_LEN // 2
    ra = []
    for k in range(n):
        t = (np.arange(mau) + k * mau) / RATE_LEN
        x = sum(np.sin(2 * np.pi * f * t) for f in (400, 900, 1800, 2600))
        ra.append((x / float(np.sqrt(np.mean(x ** 2))) * muc).astype(np.int16).tobytes())
    return ra


IM = [b"\x00" * FRAME_BYTES_LEN]


def _bridge(khung, ai_dang_noi=False):
    pipeline = PipelineGia()
    bridge = PhoneCallBridge(pipeline=pipeline, session=CallSession(customer_name="K"))
    if ai_dang_noi:
        for f in _giong(150, 3000):        # 3s tiếng AI xếp hàng
            bridge._out.put_nowait(f)
        bridge._so_manh.them("dạ hạn mức bên em", 150)
    bridge.reader, bridge.running = ReaderGia(khung, bridge), True
    return bridge


def test_tieng_nen_20_phan_tram_muc_khach_khong_mo_luot(monkeypatch):
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    # khách nói 2s ở 6000 -> im 2s -> TV 3s ở 1000 (trên 700, nhưng 17% mức khách)
    khung = IM * 75 + _giong(100, 6000) + IM * 100 + _giong(150, 1000) + IM * 75
    b = _bridge(khung)
    asyncio.run(asyncio.wait_for(b._read_loop(), timeout=20))
    assert b.pipeline.so_luot == 1, f"{b.pipeline.so_luot} lượt - tiếng TV đã mở thêm lượt"


def test_khach_noi_nho_hon_40_phan_tram_van_duoc_nghe(monkeypatch):
    # 0,39x là lượt thật thấp nhất đo được - phải qua.
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    khung = IM * 75 + _giong(100, 6000) + IM * 100 + _giong(100, 2400) + IM * 75
    b = _bridge(khung)
    asyncio.run(asyncio.wait_for(b._read_loop(), timeout=20))
    assert b.pipeline.so_luot == 2


def test_tieng_nen_khong_cat_loi_ai_du_dai_qua_700ms(monkeypatch):
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    # khách nói 2s ở 6000 (AI im) -> im -> AI nói, TV 1500 (25% mức khách) suốt 2s
    khung = IM * 75 + _giong(100, 6000) + IM * 100
    b = _bridge(khung + _giong(100, 1500) + IM * 75)
    # AI bắt đầu nói đúng lúc TV kêu: nạp hàng đợi khi khách đã nói xong
    goc = b.reader.readexactly
    async def doc(n):
        if len(b.reader._khung) == 100 + 75:
            for f in _giong(150, 3000):
                b._out.put_nowait(f)
            b._so_manh.them("dạ hạn mức bên em", 150)
        return await goc(n)
    b.reader.readexactly = doc
    asyncio.run(asyncio.wait_for(b._read_loop(), timeout=20))
    assert b._so_lan_cat_loi == 0, "TV 25% mức khách đã cắt lời AI"
    assert b._out.qsize() == 150


def test_khach_noi_de_van_cat_loi(monkeypatch):
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    khung = IM * 75 + _giong(100, 6000) + IM * 100
    b = _bridge(khung + _giong(100, 5000) + IM * 75)
    goc = b.reader.readexactly
    async def doc(n):
        if len(b.reader._khung) == 100 + 75:
            for f in _giong(150, 3000):
                b._out.put_nowait(f)
            b._so_manh.them("dạ hạn mức bên em", 150)
        return await goc(n)
    b.reader.readexactly = doc
    asyncio.run(asyncio.wait_for(b._read_loop(), timeout=20))
    assert b._so_lan_cat_loi == 1
