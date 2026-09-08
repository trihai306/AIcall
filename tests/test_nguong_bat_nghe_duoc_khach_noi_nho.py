"""Khách nói nhỏ vẫn phải mở được lượt.

Cuộc gọi 08c0d3e0 (07-09-2026, số 0386503822): khách hỏi "lãi suất bao nhiêu" ở
giây 25,8 sau khi bắt máy mà máy KHÔNG mở lượt, khách phải hỏi lại lần hai ở giây
30,3 mới được nghe. Trước đó ở giây 13,1 cũng mất một lượt y như vậy. Người dùng
báo đúng triệu chứng: "nói BOT không nghe thấy".

Gốc: `nguong_on()` có SÀN CỨNG 700, mà nền kênh thoại thật chỉ 8 (trung vị 8, max
30 trên 73 cuộc gọi) nên nhánh thích nghi `nen × 3` không bao giờ vượt sàn - ngưỡng
đứng nguyên ở 87 lần mức nền. Hai lời khách trên đều VƯỢT 700 (đỉnh 1431 và 1051)
nhưng chỉ được 3 khung liên tiếp rồi tụt xuống ở chỗ trũng giữa hai âm tiết, trong
khi `VAD_ON_FRAMES = 4` đòi 4 khung - hụt đúng một khung.

Hai dãy dưới đây là RMS 20ms ĐO THẲNG từ kênh khách của chính bản ghi đó, không
phải số bịa. Đo trên 454 lời khách thật trích từ 73 bản ghi: sàn 700 bỏ sót 8,1%,
sàn 500 bỏ sót 4,4%.
"""
import asyncio

import numpy as np

import backend.services.phone_call_service as pcs
from backend.pipeline.session_manager import CallSession
from backend.services.phone_call_service import FRAME_BYTES_LEN, PhoneCallBridge, RATE_LEN

# RMS 20ms kênh khách, bản ghi 08c0d3e0, giây 43,0-44,2 của file (= +25,8s sau khi
# bắt máy). PhoWhisper nghe ra "lãi suất bao nhiêu". Chuỗi liên tiếp trên 700 dài
# nhất chỉ 3 khung (779, 805, 793) - hụt một khung so với VAD_ON_FRAMES.
LAI_SUAT_BAO_NHIEU = [
    8, 8, 8, 8, 14, 53, 14, 7, 8, 8, 19, 211, 133, 779, 805, 793, 671, 339, 90,
    69, 223, 413, 125, 1051, 924, 185, 75, 66, 107, 178, 273, 595, 483, 338, 210,
    206, 223, 235, 294, 299, 284, 301, 313, 340, 326, 364, 333, 223, 198, 150, 88,
    40, 42, 33, 13, 8, 8, 6, 9, 9,
]

# Cùng bản ghi, giây 30,1-31,1 (= +13,1s sau khi bắt máy). Chuỗi trên 700 dài nhất
# cũng đúng 3 khung (1086, 1431, 966).
LOI_KHACH_GIAY_13 = [
    8, 8, 10, 92, 24, 8, 8, 8, 10, 165, 550, 1086, 1431, 966, 390, 173, 354, 594,
    485, 526, 346, 127, 68, 43, 54, 419, 1200, 1172, 633, 266, 259, 325, 435, 435,
    515, 476, 435, 195, 152, 103, 51, 17, 13, 8, 8, 7, 6, 6, 5, 7,
]


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
        self.luot = []

    async def speculate(self, *a, **k):
        pass

    async def process_turn(self, audio_bytes=b"", **k):
        self.luot.append(len(audio_bytes) / 2 / RATE_LEN)


def _giong_theo_muc(muc_tung_khung):
    """Một khung 20ms cho mỗi mức RMS, phổ giọng 400-2600Hz để không bị lưới gió.

    Cùng cách dựng với `tests/test_nguong_tat_theo_dinh_luot.py::_giong`, chỉ khác
    là mức đổi theo từng khung thay vì cố định.
    """
    mau = FRAME_BYTES_LEN // 2
    ra = []
    for k, muc in enumerate(muc_tung_khung):
        if muc <= 0:
            ra.append(b"\x00" * FRAME_BYTES_LEN)
            continue
        t = (np.arange(mau) + k * mau) / RATE_LEN
        x = sum(np.sin(2 * np.pi * f * t) for f in (400, 900, 1800, 2600))
        ra.append((x / float(np.sqrt(np.mean(x ** 2))) * muc).astype(np.int16).tobytes())
    return ra


def _chay(khung):
    pipeline = PipelineGia()
    bridge = PhoneCallBridge(pipeline=pipeline, session=CallSession(customer_name="K"))
    reader = ReaderGia(khung, bridge)
    bridge.reader, bridge.running = reader, True
    asyncio.run(asyncio.wait_for(bridge._read_loop(), timeout=20))
    return pipeline.luot


def _chay_voi_nen_im(muc, monkeypatch):
    """75 khung im để máy đo nền kênh (ra 0, đúng như cuộc thật đo được 8), rồi
    phát dãy mức thật, rồi im đủ dài để lượt đóng."""
    monkeypatch.setattr(pcs, "SILENCE_END_MS", 1000)
    im = [b"\x00" * FRAME_BYTES_LEN]
    return _chay(im * 75 + _giong_theo_muc(muc) + im * 75)


def test_khach_hoi_lai_suat_o_giay_25_phai_mo_duoc_luot(monkeypatch):
    luot = _chay_voi_nen_im(LAI_SUAT_BAO_NHIEU, monkeypatch)
    assert len(luot) == 1, (
        f"khách hỏi 'lãi suất bao nhiêu' (đỉnh 1051) mà máy mở {len(luot)} lượt - "
        "khách phải hỏi lại lần hai mới được nghe, đúng lỗi cuộc gọi 08c0d3e0"
    )


def test_loi_khach_giay_13_phai_mo_duoc_luot(monkeypatch):
    luot = _chay_voi_nen_im(LOI_KHACH_GIAY_13, monkeypatch)
    assert len(luot) == 1, (
        f"lời khách ở +13,1s (đỉnh 1431) mà máy mở {len(luot)} lượt"
    )


def test_lao_xao_duoi_nguong_van_khong_mo_luot(monkeypatch):
    """Lưới chặn cho chiều ngược lại: KHÔNG được hạ ngưỡng bật xuống dải 400-500.

    `phone_vad_rms_off = 500` chọn được là nhờ cuộc `decf104f` (06-09-2026): kênh
    đó có tiếng lạo xạo mức 400-500 rải rác, ngưỡng TẮT để 400 thì suốt 18,4 giây
    không có nổi một khoảng im 1000ms và lượt chỉ đóng ở trần MAX_TURN_MS - khách
    nói xong ngồi chờ 15 giây. Ngưỡng BẬT mà tụt vào dải đó thì chính tiếng lạo
    xạo ấy mở lượt.
    """
    luot = _chay_voi_nen_im([460] * 60, monkeypatch)
    assert luot == [], (
        f"mức 460 (dải lạo xạo của decf104f) không được mở lượt, mở {len(luot)}"
    )
