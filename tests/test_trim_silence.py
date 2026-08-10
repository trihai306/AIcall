"""Cắt lặng hai đầu mảnh TTS, chịu được nhiễu nền.

Bản đầu neo vào MỘT MẪU vượt biên độ 0.005. Đo trên bản ghi cuộc gọi thật thì
đầu mảnh có dải nhiễu nền RMS 0.003-0.007 (-45dB so với tiếng, tai không nghe
thấy) mà đỉnh chạm 0.041 - một gai là hàm dừng cắt, để lại tới 1,2 GIÂY trống
trước khi ra chữ. Khách nghe thành "sao nó lâu nói thế", còn mọi phép đo trên
biên độ đều báo "sạch".

Nên xét năng lượng từng khung 20ms và so với chính mảnh.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from backend.services.tts_service import trim_silence

SR = 24000
KEEP_MS = 25
# Cắt theo khung 20ms nên mốc cắt lùi tối đa một khung, cộng phần chừa 25ms.
SAI_SO_MS = 20 + KEEP_MS + 15


def tieng(ms: float, bien: float = 0.5) -> np.ndarray:
    rng = np.random.default_rng(3)
    return (rng.standard_normal(int(SR * ms / 1000)) * bien).astype(np.float32)


def im(ms: float) -> np.ndarray:
    return np.zeros(int(SR * ms / 1000), dtype=np.float32)


def nhieu_nen(ms: float, rms: float = 0.005, gai: float = 0.041) -> np.ndarray:
    """Nhiễu nền thật ở đầu mảnh F5: RMS rất thấp nhưng CÓ gai vượt 0.005.

    Chính cái gai này làm bản cũ tưởng đã có tiếng và ngừng cắt.
    """
    rng = np.random.default_rng(11)
    n = int(SR * ms / 1000)
    x = rng.standard_normal(n) * rms
    x[n // 3] = gai                      # đúng một gai, như đo được ngoài đời
    return x.astype(np.float32)


def dai_ms(x: np.ndarray) -> float:
    return len(x) / SR * 1000


# --- việc cơ bản --------------------------------------------------------

def test_cat_lang_so_hoc_hai_dau():
    x = np.concatenate([im(800), tieng(500), im(800)])
    assert dai_ms(trim_silence(x, SR)) == pytest.approx(500, abs=SAI_SO_MS)


def test_chua_lai_hai_dau_chu_khong_cat_sat():
    """Phụ âm bật hơi vào rất nhẹ - cắt sát quá là mất tiếng đầu."""
    x = np.concatenate([im(800), tieng(500), im(800)])
    assert dai_ms(trim_silence(x, SR)) > 500


# --- ca đã làm hỏng bản ghi thật ----------------------------------------

@pytest.mark.parametrize("dai", [400, 700, 1200])
def test_cat_duoc_nhieu_nen_co_gai(dai):
    """1,2 giây nhiễu nền đầu mảnh phải bị cắt dù nó có gai vượt 0.005."""
    x = np.concatenate([nhieu_nen(dai), tieng(500), im(200)])
    assert dai_ms(trim_silence(x, SR)) == pytest.approx(500, abs=SAI_SO_MS)


def test_cat_nhieu_nen_o_ca_hai_dau():
    x = np.concatenate([nhieu_nen(900), tieng(500), nhieu_nen(600)])
    assert dai_ms(trim_silence(x, SR)) == pytest.approx(500, abs=SAI_SO_MS)


# --- không được cắt quá tay ---------------------------------------------

def test_khong_cat_tieng_nho_that():
    """Tiếng nhỏ 15% vẫn là tiếng - ngưỡng 4% phải chừa nó lại."""
    x = np.concatenate([im(400), tieng(300, 0.5 * 0.15), tieng(500), im(400)])
    assert dai_ms(trim_silence(x, SR)) == pytest.approx(800, abs=SAI_SO_MS)


def test_manh_noi_nho_deu_van_giu_nguyen_tieng():
    """Cả mảnh nói nhỏ: ngưỡng theo tỉ lệ nên vẫn giữ đủ, không xén cụt."""
    x = np.concatenate([im(400), tieng(600, 0.02), im(400)])
    assert dai_ms(trim_silence(x, SR)) == pytest.approx(600, abs=SAI_SO_MS)


# --- ca biên ------------------------------------------------------------

def test_ca_manh_im_thi_tra_nguyen():
    x = im(500)
    assert trim_silence(x, SR) is x


def test_rong_va_qua_ngan():
    assert len(trim_silence(np.array([], dtype=np.float32), SR)) == 0
    ngan = tieng(10)
    assert len(trim_silence(ngan, SR)) <= len(ngan)


def test_toan_tieng_thi_gan_nhu_khong_doi():
    x = tieng(1000)
    assert dai_ms(trim_silence(x, SR)) == pytest.approx(1000, abs=SAI_SO_MS)
