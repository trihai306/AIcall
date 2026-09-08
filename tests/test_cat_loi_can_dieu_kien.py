"""Vòng thu tiếng: tiếng động vặt KHÔNG cắt lời AI, câu thật thì có.

Đây là nghiệm thu của chính hành vi người dùng yêu cầu 06-09-2026: "không phải
cứ có tiếng là dừng". Test bơm khung PCM thật vào `_read_loop` qua một reader
giả, nên nó đo đúng đường mã chạy trên cuộc gọi, không phải một bản mô phỏng.
"""
import asyncio

import numpy as np

from backend.pipeline.session_manager import CallSession
from backend.services.phone_call_service import (
    FRAME_BYTES_LEN, PhoneCallBridge, RATE_LEN,
)


class ReaderGia:
    """Trả về từng khung 20ms đã dựng sẵn, hết khung thì bảo vòng thu dừng.

    Phải hạ `bridge.running` chứ không chỉ ném lỗi đọc: vòng thu coi lỗi đọc là
    đứt ổ cắm và thử nối lại mãi, mỗi vòng ngủ 0,5 giây.
    """

    def __init__(self, khung: list[bytes], bridge=None):
        self._khung = list(khung)
        self.bridge = bridge

    async def readexactly(self, n: int) -> bytes:
        if not self._khung:
            if self.bridge is not None:
                self.bridge.running = False
            raise asyncio.IncompleteReadError(b"", n)
        return self._khung.pop(0)


def _khung_im(n: int) -> list[bytes]:
    return [b"\x00" * FRAME_BYTES_LEN] * n


def _khung_tieng(n: int, muc: int = 3000) -> list[bytes]:
    """Khung có giọng: phổ đặt ở 300-3000Hz để qua được lưới lọc gió."""
    mau = FRAME_BYTES_LEN // 2
    ra = []
    for k in range(n):
        t = (np.arange(mau) + k * mau) / RATE_LEN
        x = sum(np.sin(2 * np.pi * f * t) for f in (400, 900, 1800, 2600))
        x = (x / 4 * muc).astype(np.int16)
        ra.append(x.tobytes())
    return ra


class PipelineGia:
    """Thay chỗ pipeline thật: `speculate` ghi sẵn phiên âm tạm mà STT sẽ cho ra.

    Cần vì vòng thu gọi `clear_speculation()` lúc mở đoạn, nên đặt `spec_stt`
    trước khi chạy là vô ích - trên cuộc gọi thật chính `speculate` điền lại nó
    sau ~600ms tiếng.
    """

    def __init__(self, chu_tam: str = ""):
        self.chu_tam = chu_tam

    async def speculate(self, session, ngay: bool = False):
        if self.chu_tam:
            session.spec_stt = (session.audio_len(), self.chu_tam)

    async def process_turn(self, *a, **k):
        pass


async def _chay(khung: list[bytes], chu_ai: str = "dạ hạn mức bên em",
                chu_tam: str = "") -> CallSession:
    session = CallSession(customer_name="Khách")
    bridge = PhoneCallBridge(pipeline=PipelineGia(chu_tam), session=session)
    bridge.reader = ReaderGia(khung, bridge)
    bridge.running = True
    # AI đang nói dở: 100 khung (2 giây) tiếng còn nằm trong hàng đợi.
    for f in _khung_tieng(100):
        bridge._out.put_nowait(f)
    bridge._so_manh.them(chu_ai, 100)
    await asyncio.wait_for(bridge._read_loop(), timeout=5)
    return session, bridge


def test_tieng_ho_ngan_khong_cat_loi_ai():
    # 75 khung im để đo nền kênh, rồi 15 khung tiếng (300ms) - cỡ một tiếng ho.
    khung = _khung_im(75) + _khung_tieng(15) + _khung_im(60)
    session, bridge = asyncio.run(_chay(khung))
    assert session.yeu_cau_huy is False, "tiếng ho 300ms không được cắt lời AI"
    assert bridge._out.qsize() == 100, "tiếng AI đang xếp hàng phải còn nguyên"


def test_khach_noi_du_dai_thi_cat_loi_va_giu_phan_do():
    # 50 khung tiếng = 1 giây, vượt ngưỡng 700ms.
    khung = _khung_im(75) + _khung_tieng(50) + _khung_im(60)
    session, bridge = asyncio.run(_chay(khung))
    # Không xét `yeu_cau_huy` hay `cau_ai_con_do`: cả hai được TIÊU THỤ ngay khi
    # lượt mới mở, nên tới lúc test đọc thì đã bị dọn dù việc cắt đã xảy ra.
    # `da_doc_not` chỉ bật khi đã đi trọn chuỗi: cắt -> giữ phần khách chưa nghe
    # -> lượt sau phát lại đúng phần đó.
    assert session.da_doc_not is True, "khách nói 1 giây phải cắt được lời AI"
    # 101 = 1 khung vuốt nhỏ dần mà `drop_pending_audio` để lại chống tiếng
    # "tách", cộng 100 khung phần dở được phát lại nguyên vẹn.
    assert bridge._out.qsize() == 101, "phần khách chưa nghe phải được phát lại"


def test_khach_da_theo_thi_khong_cat_du_noi_dai():
    # Khách "dạ vâng" trong lúc nghe: dài hơn ngưỡng 700ms nhưng không phải
    # giành lượt nói. Lưới chặn ngược của `nen_dung`.
    khung = _khung_im(75) + _khung_tieng(50) + _khung_im(60)
    session, bridge = asyncio.run(_chay(khung, chu_tam="dạ vâng"))
    assert bridge._out.qsize() == 100, "tiếng đế không được cắt lời AI"
    assert session.cau_ai_con_do == ""


def test_tieng_ai_vong_nguoc_vao_mic_khong_cat_loi():
    # Đo 05-09-2026 (scripts/do_dem_truoc.py): vọng AI 30% làm PhoWhisper chép
    # lời AI thành lời khách. Không có lưới này thì AI tự cắt lời chính nó.
    khung = _khung_im(75) + _khung_tieng(50) + _khung_im(60)
    session, bridge = asyncio.run(_chay(
        khung,
        chu_ai="dạ hạn mức vay tín chấp bên em tối đa năm trăm triệu",
        chu_tam="hạn mức vay tín chấp"))
    assert bridge._out.qsize() == 100, "tiếng AI vọng lại không được cắt lời AI"


def test_so_manh_don_sach_khi_mo_luot_moi():
    # Không dọn thì sổ tích luỹ cả cuộc gọi: lưới vọng đối chiếu với lời của
    # mười lượt trước (chặn oan), và `con_do` duyệt ngược sang mảnh lượt cũ rồi
    # bắt khách nghe lại câu từ đời nào.
    session = CallSession(customer_name="Khách")
    bridge = PhoneCallBridge(pipeline=PipelineGia(), session=session)
    bridge._so_manh.them("câu của lượt trước", 50)
    asyncio.run(bridge._handle_turn(b"\x00" * 320))
    assert bridge._so_manh.chu_da_xep() == ""
