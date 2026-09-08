"""Tiếng TV / người khác nói cạnh máy khách không được giữ lượt mở tới trần 15s.

Cuộc gọi 64b6f2ac (06-09-2026): khách nói 2,4s (đỉnh 3300-8200) rồi im, nhưng
TV trong phòng phát tiếng người ở mức 800-2500 - trên ngưỡng tắt cố định 500 -
suốt 15 giây, lượt chỉ đóng ở trần MAX_TURN_MS. Lưới gió và ngưỡng RMS cố định
đều vô dụng vì đó là tiếng người thật. Khác biệt vật lý đo được
(`scripts/do_muc_tv.py`): khách ở gần micro nên TO HƠN HẲN tiếng nền - ngưỡng
tắt = 15% đỉnh lượt (≈1234) đóng lượt sau 3,3s, đúng lúc khách dứt lời.
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
        self.luot = []          # (số khung còn lại lúc đóng, độ dài giây)

    async def speculate(self, *a, **k):
        pass

    async def process_turn(self, audio_bytes=b"", **k):
        self.luot.append((len(self._reader._khung), len(audio_bytes) / 2 / RATE_LEN))


def _giong(n, muc):
    """Phổ giọng (400-2600Hz) để không bị lưới gió, RMS đúng bằng `muc`."""
    mau = FRAME_BYTES_LEN // 2
    ra = []
    for k in range(n):
        t = (np.arange(mau) + k * mau) / RATE_LEN
        x = sum(np.sin(2 * np.pi * f * t) for f in (400, 900, 1800, 2600))
        ra.append((x / float(np.sqrt(np.mean(x ** 2))) * muc).astype(np.int16).tobytes())
    return ra


def _chay(khung):
    pipeline = PipelineGia()
    bridge = PhoneCallBridge(pipeline=pipeline, session=CallSession(customer_name="K"))
    reader = ReaderGia(khung, bridge)
    pipeline._reader = reader
    bridge.reader, bridge.running = reader, True
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=20))
    return pipeline.luot


def test_tieng_tv_sau_khi_khach_dut_loi_khong_giu_luot(monkeypatch):
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    im = [b"\x00" * FRAME_BYTES_LEN]
    # nền 1,5s -> khách nói 2s ở 8000 -> TV 10s ở 1000 (gấp đôi ngưỡng cố định
    # 500, nhưng chỉ 12,5% đỉnh - đúng tỉ lệ đo được: đỉnh 8227, TV 800-1500)
    # -> im hẳn
    khung = im * 75 + _giong(100, 8000) + _giong(500, 1000) + im * 75
    luot = _chay(khung)
    assert luot, "phải có lượt cho 2 giây khách nói"
    assert luot[0][1] < 5.0, (
        f"lượt đầu dài {luot[0][1]:.1f}s - tiếng TV 1000 (>500) vẫn giữ lượt mở; "
        "phải đóng ~1s sau khi khách dứt lời")


def test_khach_noi_nho_dan_o_cuoi_cau_khong_bi_cat_doi(monkeypatch):
    # Khách hạ giọng cuối câu còn 25% đỉnh: vẫn là một lượt, không được chẻ đôi.
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    im = [b"\x00" * FRAME_BYTES_LEN]
    khung = im * 75 + _giong(50, 8000) + _giong(50, 2000) + im * 75
    luot = _chay(khung)
    assert len(luot) == 1 and luot[0][1] >= 1.9, f"lượt: {luot}"


def test_nguong_theo_dinh_khong_lam_chat_them_min_turn(monkeypatch):
    """Ngưỡng tương đối chỉ để ĐÓNG lượt, không được làm chặt thêm MIN_TURN_MS.

    Chạy lại bản ghi 2fe53f0c (14-08) với hệ số 0,15: tiếng đáp 180ms ở giây
    21,5 (đỉnh ~6500, đuôi 2 khung 1116/550) BIẾN MẤT lần nữa - cùng lỗi đã
    gặp với lưới gió: đuôi bị tính là im nên phần tiếng đếm được còn 120ms.
    Bộ đếm cho MIN_TURN phải dùng ngưỡng cố định như trước.
    """
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    im = [b"\x00" * FRAME_BYTES_LEN]
    # 9 khung 8000 (180ms) + 2 khung đuôi 900: trên 500 nhưng dưới 15% đỉnh.
    khung = im * 75 + _giong(9, 8000) + _giong(2, 900) + im * 75
    luot = _chay(khung)
    assert len(luot) == 1, "tiếng đáp 180ms có đuôi nhỏ phải thành lượt như trước"
