"""Nén phần ngân ở đuôi mảnh.

Xem `backend/services/nen_duoi_manh.py` để biết vì sao: F5 kéo dài âm cuối của
TỪNG mảnh, và ở mảnh giữa thì chỗ kéo dài đó rơi vào giữa câu.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from backend.services.nen_duoi_manh import (BOT_TOI_DA_MS, CHUYEN_TIEP_MS,
                                            GIU_CUOI_MS, TOI_THIEU_MS, nen_duoi)

SR = 24000


def tieng(ms, bien=8000):
    """Sóng sin 200Hz - đủ giống một nguyên âm ngân cho phép thử."""
    n = int(SR * ms / 1000)
    t = np.arange(n) / SR
    return (bien * np.sin(2 * np.pi * 200 * t)).astype(np.int16)


def lang(ms):
    return np.zeros(int(SR * ms / 1000), dtype=np.int16)


def test_duoi_NGAN_thi_giu_nguyen():
    """Đuôi vốn đã bình thường thì đừng đụng vào."""
    x = np.concatenate([tieng(400), lang(80), tieng(150)])
    assert len(nen_duoi(x, SR)) == len(x)


def test_duoi_DAI_thi_bi_nen():
    x = np.concatenate([tieng(400), lang(80), tieng(600)])
    ra = nen_duoi(x, SR)
    assert len(ra) < len(x), "đuôi 600ms mà không nén gì"
    bot_ms = (len(x) - len(ra)) / SR * 1000
    assert 50 < bot_ms <= BOT_TOI_DA_MS + 1, f"cắt {bot_ms:.0f}ms — ngoài dự kiến"


def test_khong_cat_qua_TOI_THIEU():
    """Sau khi nén, đuôi vẫn phải dài hơn ngưỡng - không được bóp thành cụt."""
    x = np.concatenate([tieng(400), lang(80), tieng(700)])
    ra = nen_duoi(x, SR)
    con_lai = 700 - (len(x) - len(ra)) / SR * 1000
    assert con_lai >= TOI_THIEU_MS * 0.6, f"đuôi còn {con_lai:.0f}ms — quá cụt"


def test_giu_doan_TAT_DAN_cuoi():
    """Phần cuối phải còn NGUYÊN VĂN: cắt sát mép thì nghe cụt lủn.

    Trừ `CHUYEN_TIEP_MS` đầu của đoạn giữ lại - chỗ đó bị trộn với đuôi đoạn
    trước để chỗ nối không kêu "tạch". Phần sau nó phải y hệt bản gốc.
    """
    x = np.concatenate([tieng(400), lang(80), tieng(600)])
    ra = nen_duoi(x, SR)
    n = int(SR * (GIU_CUOI_MS - CHUYEN_TIEP_MS) / 1000)
    assert np.array_equal(ra[-n:], x[-n:]), "đoạn tắt dần cuối bị đụng vào"


def test_khong_deo_them_gi():
    x = np.concatenate([tieng(400), lang(80), tieng(600)])
    ra = nen_duoi(x, SR)
    assert ra.dtype == np.int16
    assert len(ra) > 0


def test_tieng_rong_va_qua_ngan():
    assert nen_duoi(np.array([], dtype=np.int16), SR).size == 0
    ngan = tieng(20)
    assert len(nen_duoi(ngan, SR)) == len(ngan)


def test_khong_lam_vo_bien_do():
    """Chuyển tiếp mềm cộng hai đoạn - không được tràn int16."""
    x = np.concatenate([tieng(400), lang(80), tieng(600, bien=32000)])
    ra = nen_duoi(x, SR)
    assert np.abs(ra).max() <= 32767
