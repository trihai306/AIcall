"""Bóp quãng lặng F5 tự bịa vào giữa câu, KHÔNG đụng nhịp nghỉ thật của dấu câu.

Ngưỡng 360ms lấy từ đo thật ở đúng cấu hình đang chạy, 10 lượt mỗi bản:

    nghỉ THẬT   không dấu giữa 0ms | 1 phẩy 160ms | 1 chấm 320ms | 2 chấm 260ms
    quãng BỊA   380 - 1600ms   (đo trên bản ghi hội thoại thật)

Từng thử ngưỡng 260ms và SAI: nghỉ thật ở dấu chấm chạm 320ms nên nó cắt nhầm
ranh giới câu, hai câu dính vào nhau.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from backend.services.tts_service import (
    GIU_LANG_MS, NGUONG_LANG_BIA_MS, cat_lang_bia,
)

SR = 24000


def tieng(ms: float) -> np.ndarray:
    """Đoạn 'có tiếng' - biên độ đủ cao để không bị coi là lặng."""
    return np.full(int(SR * ms / 1000), 0.5, dtype=np.float32)


def im(ms: float) -> np.ndarray:
    return np.zeros(int(SR * ms / 1000), dtype=np.float32)


def do_lang_giua(x: np.ndarray, nguong_bien=0.015) -> list[float]:
    n = int(SR * 0.02)
    k = len(x) // n
    to = np.abs(x[: k * n].reshape(k, n)).max(axis=1)
    lang = to < nguong_bien
    ra, i = [], 0
    while i < k:
        if lang[i]:
            j = i
            while j < k and lang[j]:
                j += 1
            if i > 0 and j < k:
                ra.append((j - i) * 20.0)
            i = j
        else:
            i += 1
    return ra


# --- bóp đúng thứ cần bóp -----------------------------------------------

@pytest.mark.parametrize("dai_ms", [400, 600, 1000, 1600])
def test_bop_quang_bia(dai_ms):
    x = np.concatenate([tieng(500), im(dai_ms), tieng(500)])
    z = cat_lang_bia(x, SR)
    con = do_lang_giua(z)
    assert con and con[0] == pytest.approx(GIU_LANG_MS, abs=25)


def test_giu_nguyen_nhip_nghi_that_cua_dau_cham():
    """320ms là nghỉ THẬT ở dấu chấm - không được đụng vào."""
    x = np.concatenate([tieng(500), im(320), tieng(500)])
    z = cat_lang_bia(x, SR)
    assert len(z) == len(x)
    assert do_lang_giua(z)[0] == pytest.approx(320, abs=25)


def test_giu_nguyen_nhip_nghi_dau_phay():
    x = np.concatenate([tieng(500), im(160), tieng(500)])
    assert len(cat_lang_bia(x, SR)) == len(x)


def test_dung_ngay_moc_thi_khong_bop():
    """Đúng bằng ngưỡng thì giữ - chỉ bóp khi VƯỢT."""
    x = np.concatenate([tieng(400), im(NGUONG_LANG_BIA_MS), tieng(400)])
    assert len(cat_lang_bia(x, SR)) == len(x)


# --- không đụng hai đầu -------------------------------------------------

def test_khong_dung_lang_o_hai_dau():
    """Hai đầu là việc của trim_silence, và nhịp nối mảnh do chỗ khác chèn."""
    x = np.concatenate([im(800), tieng(500), im(800)])
    assert len(cat_lang_bia(x, SR)) == len(x)


# --- không làm hỏng thứ khác --------------------------------------------

def test_nhieu_quang_bop_het():
    x = np.concatenate([tieng(300), im(700), tieng(300), im(900), tieng(300)])
    con = do_lang_giua(cat_lang_bia(x, SR))
    assert len(con) == 2
    assert all(c == pytest.approx(GIU_LANG_MS, abs=25) for c in con)


def test_khong_co_gi_de_bop_thi_tra_nguyen_vat():
    x = np.concatenate([tieng(500), im(160), tieng(500)])
    assert cat_lang_bia(x, SR) is x


def test_tieng_lien_mach_khong_doi():
    x = tieng(2000)
    assert cat_lang_bia(x, SR) is x


def test_rong_va_qua_ngan():
    assert len(cat_lang_bia(np.array([], dtype=np.float32), SR)) == 0
    ngan = tieng(10)
    assert cat_lang_bia(ngan, SR) is ngan


def test_khong_lam_mat_tieng():
    """Tổng lượng tiếng (mẫu vượt ngưỡng) phải giữ nguyên."""
    x = np.concatenate([tieng(500), im(900), tieng(700)])
    z = cat_lang_bia(x, SR)
    assert int((np.abs(z) >= 0.015).sum()) == int((np.abs(x) >= 0.015).sum())
