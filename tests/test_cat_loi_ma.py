"""Không được "cắt lời" khi AI thật ra đã nói xong.

Cuộc gọi 64b6f2ac (06-09-2026), 21:04:23: "khách cắt lời sau 940ms tiếng — bỏ 0
khung tiếng AI, còn dở 0.0s". `dang_noi` được chụp lúc khách MỞ MIỆNG (câu chào
còn vài khung trong hàng đợi), nhưng quyết định cắt đến 940ms sau - lúc đó hàng
đợi đã rỗng và không lượt nào đang sinh. Cắt "ma" như thế đặt `yeu_cau_huy` lên
một lượt không tồn tại và ghi log làm người đọc tưởng AI bị ngắt.
"""
import asyncio

import numpy as np

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
    async def speculate(self, *a, **k): pass
    async def process_turn(self, *a, **k): pass


def _giong(n, muc=3000):
    mau = FRAME_BYTES_LEN // 2
    ra = []
    for k in range(n):
        t = (np.arange(mau) + k * mau) / RATE_LEN
        x = sum(np.sin(2 * np.pi * f * t) for f in (400, 900, 1800, 2600))
        ra.append((x / float(np.sqrt(np.mean(x ** 2))) * muc).astype(np.int16).tobytes())
    return ra


def test_ai_da_noi_xong_thi_khong_cat_loi():
    bridge = PhoneCallBridge(pipeline=PipelineGia(), session=CallSession(customer_name="K"))
    # Lúc khách mở miệng: AI còn đúng 3 khung (60ms) trong hàng đợi - sắp hết.
    for f in _giong(3):
        bridge._out.put_nowait(f)
    khung = [b"\x00" * FRAME_BYTES_LEN] * 75 + _giong(60) + [b"\x00" * FRAME_BYTES_LEN] * 75
    reader = ReaderGia(khung, bridge)
    # Hàng đợi cạn ngay sau khi khách bắt đầu nói (vòng ghi rút hết).
    goc = reader.readexactly
    async def doc(n):
        if len(reader._khung) == 75 + 55:
            while not bridge._out.empty():
                bridge._out.get_nowait()
        return await goc(n)
    reader.readexactly = doc
    bridge.reader, bridge.running = reader, True
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=10))
    assert bridge._so_lan_cat_loi == 0, "AI đã nói xong mà vẫn ghi nhận một lần cắt lời"


def test_khong_co_tieng_dang_phat_thi_chi_cat_khi_co_chu():
    """AI chưa phát tiếng (đang sinh câu trả lời) mà bị "cắt" chỉ vì có tiếng đủ
    dài, không có chữ, thì mất trắng câu trả lời cho khách.

    Cuộc 18d6836b (06-09-2026, TV mở): khách hỏi "cho anh hỏi khoản vay bên
    mình thôi" 21:47:22; 1 giây sau, lúc LLM đang sinh và chưa có khung tiếng
    nào, TV kêu 720ms (nghe được '') -> "cắt lời... bỏ 0 khung" -> lượt bị huỷ,
    AI: '' , rồi câu khách bị ghép với tiếng TV thành câu rác và AI đáp câu rác.

    Bỏ tiếng đang phát vì một tiếng động là rẻ (khách nghe lại được); huỷ câu
    trả lời đang sinh vì một tiếng động là đắt. Không có gì đang phát thì chỉ
    cắt khi ĐÃ CÓ CHỮ có nghĩa.
    """
    import asyncio as _a

    class PipelineTreo:
        async def speculate(self, *a, **k): pass
        async def process_turn(self, *a, **k): await _a.sleep(30)

    bridge = PhoneCallBridge(pipeline=PipelineTreo(), session=CallSession(customer_name="K"))
    khung = [b"\x00" * FRAME_BYTES_LEN] * 75 + _giong(50) + [b"\x00" * FRAME_BYTES_LEN] * 75
    reader = ReaderGia(khung, bridge)
    # Lượt đang sinh (task treo), hàng đợi tiếng RỖNG.
    async def chay():
        bridge._luot_task = asyncio.create_task(_a.sleep(30))
        bridge.reader, bridge.running = reader, True
        await asyncio.wait_for(bridge._read_loop(), timeout=10)
        bridge._luot_task.cancel()
    asyncio.run(chay())
    assert bridge._so_lan_cat_loi == 0, "không có tiếng đang phát, không có chữ - vẫn huỷ lượt đang sinh"
