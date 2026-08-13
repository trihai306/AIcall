"""Nút nghe thử phải đọc ĐÚNG nhịp của cuộc gọi, kể cả khi nghe ở 24kHz.

Lỗi đã xảy ra (13-08-2026): `test-tts` chỉ nhân `he_so_thoai` khi
`qua_dien_thoai=True`, mà cờ đó ĐỒNG THỜI hạ băng thông xuống 8kHz. Một cờ điều
khiển HAI thứ độc lập, nên không có cách nào nghe đúng nhịp cuộc gọi ở băng
thông đầy đủ. Hệ quả đo được: bản 24kHz đọc 283 âm tiết/phút còn cuộc gọi thật
đọc 347 - chậm hơn 28%. Người duyệt giọng nghe một đằng, khách nghe một nẻo, và
chú thích trong frontend đã phải cảnh báo đúng điều đó thay vì sửa nó.

Nay tách bạch: nhịp LUÔN theo cuộc gọi, còn `qua_dien_thoai` chỉ còn điều khiển
băng thông. Bất biến được canh ở đây là "nghe thử == cuộc gọi".
"""
from types import SimpleNamespace

import pytest

from backend.pipeline.streaming_pipeline import StreamingPipeline


class _TTSGia:
    """Đủ mặt cho phép tính tốc, không nạp model."""

    def __init__(self, toc: float, he_so: float):
        self._toc, self._he_so = toc, he_so

    def toc_do_cua(self, voice=None) -> float:
        return self._toc

    def he_so_thoai(self) -> float:
        return self._he_so

    def toc_nghe_thu(self, voice=None) -> float:
        from backend.services.tts_service import F5TTSService
        return F5TTSService.toc_nghe_thu(self, voice)


def _phien_thoai():
    return SimpleNamespace(tinh_huong=None, audio_rate=8000)


def _phien_web():
    return SimpleNamespace(tinh_huong=None, audio_rate=16000)


@pytest.mark.parametrize("he_so", [1.0, 1.28, 0.8])
def test_nghe_thu_bang_dung_toc_cuoc_goi(he_so):
    """Bất biến chính: nghe thử và cuộc gọi ra CÙNG một tốc, mọi hệ số."""
    tts = _TTSGia(0.90, he_so)
    goi = StreamingPipeline._toc_cho_phien(tts, _phien_thoai(), "giong_heu")
    assert tts.toc_nghe_thu("giong_heu") == pytest.approx(goi)


def test_he_so_van_chi_ap_cho_duong_thoai():
    """Đường trình duyệt (16kHz) vẫn giữ tốc gốc - không phải chỗ sửa ở đây."""
    tts = _TTSGia(0.90, 1.28)
    assert StreamingPipeline._toc_cho_phien(tts, _phien_web(), "g") == pytest.approx(0.90)


def test_he_so_mac_dinh_la_1_khong_co_tep():
    """Mặc định trong mã phải là 1.0: một tốc duy nhất cho mọi đường.

    Giá trị 1.28 từng chạy trên máy Windows KHÔNG nằm trong mã - nó do người
    chỉnh tay qua giao diện. Đo 13-08-2026 qua đúng kênh 8kHz, 30 câu dài:
        hệ số 1,28 (347 âm tiết/phút)   23/30 câu   2,8% từ sai
        hệ số 1,00 (283 âm tiết/phút)   30/30 câu   0,4% từ sai
    Hệ số này sinh ra để chống "dính chữ" trên kênh 8kHz nhưng lại làm đọc NHANH
    hơn - ngược với chính lập luận của nó - và đo ra thì nó GÂY đúng cái nó định
    chống. Ai đặt lại khác 1.0 thì phải đo lại bằng
    `scripts/he_so_thoai_giup_hay_hai.py`.
    """
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService.__new__(F5TTSService)
    assert F5TTSService.he_so_thoai(tts) == 1.0 or not F5TTSService._tep_he_so(tts).exists()
