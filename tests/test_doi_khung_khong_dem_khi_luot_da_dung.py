"""ĐÓI KHUNG chỉ được đếm khi TTS thật sự đẻ không kịp, không phải khi lượt đã
bị cắt/kết thúc trong lúc vòng ghi đang chờ khung.

Cuộc gọi 64b6f2ac (06-09-2026): khách cắt lời lúc 21:04:38, hàng đợi bị dọn,
lượt kết thúc; khung kế tiếp mãi 21:04:46 mới có (lượt sau). Vòng ghi chờ suốt
7,8 giây và ghi "ĐÓI KHUNG 7792ms giữa câu - TTS đẻ không kịp" - sai: TTS không
nợ gì, cờ `_luot_dang_chay` chỉ được xét TRƯỚC khi chờ.
"""
import asyncio

from backend.pipeline.session_manager import CallSession
from backend.services.phone_call_service import FRAME_BYTES_XUONG, PhoneCallBridge


class PipelineGia:
    async def speculate(self, *a, **k): pass
    async def process_turn(self, *a, **k): pass


def test_luot_ket_thuc_trong_luc_cho_thi_khong_phai_doi_khung():
    bridge = PhoneCallBridge(pipeline=PipelineGia(), session=CallSession(customer_name="K"))
    bridge._luot_dang_chay = True
    # Đệm mồi phải NHỎ hơn RESET_GAP (0,5s) như trên máy thật (250ms), không thì
    # khung đầu tiên đã bị coi là "ngoài câu" và test xanh oan dù chưa sửa gì.
    bridge.dem_mo_s = 0.25
    # Bộ đếm lượt đã kết thúc phải có sẵn trên cầu tiếng (sản phẩm tạo ra, không
    # phải test). Kiểm ở đây cho RED rõ ràng: thiếu nó thì task nền bên dưới ném
    # AttributeError và CHẾT LẶNG, khung không tới, timeout, bộ đếm 0 và test
    # xanh oan - đã xảy ra đúng như thế.
    assert hasattr(bridge, "_so_luot_ket_thuc"), "cầu tiếng chưa đếm lượt đã kết thúc"
    tac_vu = []

    class WriterGia:
        def __init__(self): self.n = 0
        def write(self, b):
            self.n += 1
            if self.n == 1:
                # Khung đầu vừa đi, lượt VẪN đang chạy lúc vòng ghi bắt đầu chờ.
                # Rồi trong lúc chờ: khách cắt lời, lượt kết thúc (cờ hạ), và
                # khung kế tiếp thuộc lượt MỚI, tới sau 0,4s (> ngưỡng 200ms).
                async def sau():
                    await asyncio.sleep(0.1)
                    # Lượt cũ kết thúc - đúng như `PhoneAudioSink` làm ở
                    # `turn_complete`: hạ cờ và đếm thêm một lượt đã xong.
                    bridge._luot_dang_chay = False
                    bridge._so_luot_ket_thuc += 1
                    await asyncio.sleep(0.3)
                    bridge._luot_dang_chay = True        # lượt mới
                    bridge._out.put_nowait(b"\x01" * FRAME_BYTES_XUONG)
                tac_vu.append(asyncio.get_event_loop().create_task(sau()))
            elif self.n >= 2:
                bridge.running = False
        async def drain(self): pass

    bridge.writer, bridge.running = WriterGia(), True
    bridge._out.put_nowait(b"\x01" * FRAME_BYTES_XUONG)
    try:
        asyncio.run(asyncio.wait_for(bridge._write_loop(), timeout=5))
    except asyncio.TimeoutError:
        pass
    assert tac_vu and tac_vu[0].done() and tac_vu[0].exception() is None, (
        f"task nền hỏng: {tac_vu[0].exception() if tac_vu else 'không chạy'}")
    assert bridge._doi_lan == 0, (
        f"đếm {bridge._doi_lan} lần đói khung dù lượt đã kết thúc trong lúc chờ")
