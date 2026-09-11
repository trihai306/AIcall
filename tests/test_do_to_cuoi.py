"""Mọi mảnh xuống điện thoại phải TO BẰNG NHAU theo thước chuẩn ITU-R BS.1770.

Đo 11-09-2026 trên 52 clip thật (38 câu đệm + 14 tiếng sẵn) qua đúng chuỗi của
máy thật (`chuan_muc_thoai` -> hạ 8kHz -> `tang_tuan_hoan`): độ to các mảnh lệch
nhau 2,4 LU (-21,6 .. -19,2 LUFS). `chuan_muc_thoai` cân NĂNG LƯỢNG (RMS) chứ
không cân độ to tai nghe (lọc K của BS.1770), và nó chạy TRƯỚC hai khâu còn đổi
mức. Câu đệm và câu trả lời là hai mảnh khác nhau nên lệch theo đúng mức đó -
người dùng nghe ra "tiếng to hơn nghe rất giả".

Nguyên mẫu chuẩn LUFS ở CUỐI chuỗi rồi giới hạn đỉnh mềm (thứ tự của EBU R128):
0,00 LU trên cả 52 clip, bộ giới hạn chỉ chạm 1/52.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from scipy.signal import butter, lfilter

import backend.services.phone_call_service as pcs
from backend.config import settings
from backend.services.audio_utils import do_to_lufs, do_to_tieng_noi


def sin(hz, dbfs, sr, giay=3.0):
    t = np.arange(int(sr * giay)) / sr
    return (np.sin(2 * np.pi * hz * t) * 10 ** (dbfs / 20)).astype(np.float32)


def tieng(sr, ms, sang=False, he_so_dinh_db=14.0, seed=1):
    """Giả tiếng nói, hệ số đỉnh THẬT, phổ TỐI (trầm) hoặc SÁNG (nhiều dải cao).

    Hai mảnh cùng RMS mà khác phổ thì tai nghe to nhỏ khác nhau - đúng chỗ cân
    theo RMS không thấy. Không dùng sóng sin cho test mức: xem test_can_do_to.py.
    """
    n = int(sr * ms / 1000)
    x = np.random.default_rng(seed).normal(0, 1, n)
    if sang:
        x = np.diff(x, prepend=0.0)
    else:
        b, a = butter(2, 500 / (sr / 2))
        x = lfilter(b, a, x)
    x = x / np.sqrt((x ** 2).mean())
    x[:: max(1, n // 40)] = 10 ** (he_so_dinh_db / 20)
    return (x * 0.05).astype(np.float32)


def test_thuoc_do_dung_chuan_bs1770():
    """BS.1770-4: sin 1 kHz đỉnh -20 dBFS cho đúng -23,0 LUFS, ở mọi tần số mẫu."""
    for sr in (48000, 24000, 8000):
        assert abs(do_to_lufs(sin(1000, -20, sr), sr) - (-23.0)) <= 0.1, sr


def test_moi_manh_ra_cung_mot_do_to_du_khac_pho_va_khac_muc():
    sr = 8000
    vao = (tieng(sr, 1500) * 6.0, tieng(sr, 1500, sang=True) * 0.8, tieng(sr, 600, seed=3) * 2.0)
    ra = [do_to_lufs(pcs.can_do_to_cuoi(x, sr), sr) for x in vao]
    assert max(ra) - min(ra) <= 0.2, ra
    assert abs(np.mean(ra) - settings.phone_do_to_lufs) <= 0.2, ra


def test_khong_bao_gio_vuot_tran_dinh():
    x = tieng(8000, 1200, he_so_dinh_db=19.0) * 8.0
    assert np.abs(pcs.can_do_to_cuoi(x, 8000)).max() <= settings.phone_dinh_toi_da + 1e-6


def test_manh_lang_hoac_chi_co_tap_am_khong_bi_keo_len():
    assert np.abs(pcs.can_do_to_cuoi(np.zeros(4000, np.float32), 8000)).max() == 0.0
    tap = (np.random.default_rng(5).normal(0, 1, 8000) * 1e-4).astype(np.float32)   # ~-80 dBFS
    assert do_to_lufs(pcs.can_do_to_cuoi(tap, 8000), 8000) < -60


def test_lang_dau_manh_khong_doi_do_to_phan_tieng():
    sr = 8000
    s = tieng(sr, 1500)
    goc = do_to_lufs(pcs.can_do_to_cuoi(s.copy(), sr), sr)
    n = int(sr * 0.6)
    ra = pcs.can_do_to_cuoi(np.concatenate([np.zeros(n, np.float32), s]), sr)
    assert abs(do_to_lufs(ra[n:], sr) - goc) <= 0.3


def test_duong_xuong_cho_moi_manh_cung_do_to():
    """Đầu vào như TTS thật (24kHz), đầu ra đúng tần số đường xuống của máy."""
    vao = (tieng(24000, 1500) * 6.0, tieng(24000, 1500, sang=True) * 0.8)
    ra = [do_to_lufs(pcs.xu_ly_tieng_xuong(x, 24000), pcs.RATE_XUONG) for x in vao]
    assert max(ra) - min(ra) <= 0.2, ra


def test_thuoc_do_tieng_noi_dung_chuan_khi_toan_tieng():
    for sr in (48000, 24000, 8000):
        assert abs(do_to_tieng_noi(sin(1000, -20, sr), sr) - (-23.0)) <= 0.1, sr


def test_thuoc_do_tieng_noi_khong_doi_khi_them_lang_hai_dau():
    """Cổng khối 400ms của BS.1770 KHÔNG đủ cho mảnh ngắn: lặng 200ms trước mảnh
    1s làm phép đo lệch 0,35 LU. Cổng theo khung tiếng nói thì không lệch."""
    sr = 8000
    s = tieng(sr, 1000)
    goc = do_to_tieng_noi(s, sr)
    for ms in (200, 600):
        z = np.zeros(int(sr * ms / 1000), np.float32)
        assert abs(do_to_tieng_noi(np.concatenate([z, s, z]), sr) - goc) <= 0.1, ms
