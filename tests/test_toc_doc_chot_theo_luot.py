"""Tốc đọc của lượt phải CHỐT MỘT LẦN, không đổi giữa chừng.

Ghi chú: `TOC_DOC_THEO_TINH_HUONG` đang TẮT (xem chú thích ở đó để biết vì sao),
nên tốc luôn là tốc của giọng. Bất biến mà tệp này canh KHÔNG phụ thuộc cờ đó:
tốc phải GIỐNG NHAU trước và sau `clear_speculation()`.

LỖI CÓ SẴN, phát hiện 06-09-2026: `_toc_cho_phien` đọc `session.tinh_huong` để
lấy tốc đọc riêng của tình huống. Nhưng `_generate_response` gọi
`clear_speculation()` NGAY ĐẦU HÀM, mà hàm đó đặt `tinh_huong = None` — trước
mọi lệnh gọi TTS thật.

Hai hệ quả:
  1. Tính năng "tốc đọc theo tình huống" là MÃ CHẾT trên đường thoại: mọi lệnh
     gọi TTS đều thấy `tinh_huong = None` nên luôn rơi về tốc của giọng.
  2. `speed` nằm trong khoá cache TTS `(voice, text, fast, target_sr, nfe_step,
     speed)`. Ai dựng sẵn tiếng lúc `tinh_huong` còn sống sẽ tạo khoá KHÁC với
     lúc phát thật -> cache trượt 100%, việc dựng sẵn thành vô nghĩa.

Nên tốc đọc phải được chốt vào phiên trước khi dọn bản đoán, và mọi lệnh gọi
TTS sau đó đọc từ đó.
"""
import pytest

from backend.pipeline.session_manager import CallSession
from backend.pipeline.streaming_pipeline import StreamingPipeline


class TtsGia:
    def toc_do_cua(self, voice):
        return 1.00

    def he_so_thoai(self):
        return 0.90


def _phien_thoai(tinh_huong=None):
    s = CallSession(voice_name="giong_a")
    s.audio_rate = 8000                      # đường thoại
    s.tinh_huong = tinh_huong
    return s


def test_toc_doc_khong_doi_sau_khi_don_ban_doan():
    """Chốt xong thì dọn bản đoán KHÔNG được làm đổi tốc đọc.

    Đây là bất biến giữ cho khoá cache TTS giống nhau ở hai thời điểm, bất kể
    `TOC_DOC_THEO_TINH_HUONG` bật hay tắt.
    """
    s = _phien_thoai((3500, "hoi_lai_suat", 0.95))
    tts = TtsGia()

    StreamingPipeline._chot_toc_doc(tts, s, "giong_a")
    truoc = StreamingPipeline._toc_cho_phien(tts, s, "giong_a")
    s.clear_speculation()                     # đúng thứ `_generate_response` làm
    sau = StreamingPipeline._toc_cho_phien(tts, s, "giong_a")

    assert truoc == sau == pytest.approx(1.00 * 0.90), (
        "tốc đọc đổi giữa lượt -> khoá cache TTS lệch, và tốc theo tình huống "
        "không bao giờ tới được TTS")


def test_khong_co_tinh_huong_thi_dung_toc_cua_giong():
    s = _phien_thoai(None)
    tts = TtsGia()
    StreamingPipeline._chot_toc_doc(tts, s, "giong_a")
    assert StreamingPipeline._toc_cho_phien(tts, s, "giong_a") == pytest.approx(0.90)


def test_luot_moi_chot_lai_tu_dau():
    """Chốt là theo LƯỢT: lượt sau tình huống khác thì tốc phải tính lại."""
    s = _phien_thoai(None)
    tts = TtsGia()
    StreamingPipeline._chot_toc_doc(tts, s, "giong_a")
    assert s.toc_doc_luot == pytest.approx(0.90)
    s.toc_doc_luot = None                     # sang lượt mới
    StreamingPipeline._chot_toc_doc(tts, s, "giong_a")
    assert s.toc_doc_luot == pytest.approx(0.90)
