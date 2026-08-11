"""`noi_wav` ghép các mảnh TTS thành một wav cho trang nghe thử.

Neo hai thứ dễ vỡ âm thầm: tổng số mẫu phải bằng đúng tổng các phần (ghép mà mất
mẫu thì tiếng bị hụt chữ, không ai thấy trên biểu đồ), và nhịp nghỉ chèn vào phải
ĐÚNG số mẫu chứ không xấp xỉ.
"""

import struct

from backend.services.audio_utils import chen_lang_dau_wav, noi_wav, pcm_to_wav

SR = 24000


def wav_cua(so_mau: int, gia_tri: int = 1000) -> bytes:
    return pcm_to_wav(struct.pack(f"<{so_mau}h", *([gia_tri] * so_mau)),
                      sample_rate=SR)


def so_mau(wav: bytes) -> int:
    i = wav.find(b"data", 12)
    return len(wav[i + 8:]) // 2


def test_tong_mau_bang_tong_cac_phan():
    a, b, c = wav_cua(100), wav_cua(250), wav_cua(7)
    assert so_mau(noi_wav([a, b, c])) == 100 + 250 + 7


def test_giu_dung_tan_so_va_kenh():
    ra = noi_wav([wav_cua(10), wav_cua(10)])
    assert struct.unpack("<I", ra[24:28])[0] == SR
    assert struct.unpack("<H", ra[22:24])[0] == 1
    assert struct.unpack("<H", ra[34:36])[0] == 16


def test_giu_nguyen_mau_khong_doi_gia_tri():
    """Ghép không được đụng vào mẫu - chỉ nối."""
    ra = noi_wav([wav_cua(3, 111), wav_cua(2, 222)])
    i = ra.find(b"data", 12)
    assert struct.unpack("<5h", ra[i + 8:i + 18]) == (111, 111, 111, 222, 222)


def test_bo_qua_manh_rong_va_khong_phai_wav():
    a = wav_cua(50)
    assert so_mau(noi_wav([b"", a, b"khong phai RIFF", a])) == 100


def test_danh_sach_rong_ra_bytes_rong():
    assert noi_wav([]) == b""
    assert noi_wav([b"", b"xxx"]) == b""


def test_mot_manh_thi_khong_doi_gi():
    a = wav_cua(64)
    assert so_mau(noi_wav([a])) == 64


def test_nhip_nghi_chen_dung_so_mau():
    """200ms ở 24kHz = đúng 4800 mẫu, không xấp xỉ."""
    a = wav_cua(1000)
    assert so_mau(chen_lang_dau_wav(a, 200.0)) == 1000 + 4800


def test_nhip_nghi_0_thi_khong_chen():
    a = wav_cua(1000)
    assert so_mau(chen_lang_dau_wav(a, 0.0)) == 1000


def test_ghep_co_nhip_nghi_cong_dung_tong():
    """Đường chạy thật: mảnh sau được chèn lặng rồi mới ghép."""
    a, b = wav_cua(1000), chen_lang_dau_wav(wav_cua(1000), 200.0)
    assert so_mau(noi_wav([a, b])) == 1000 + 4800 + 1000
