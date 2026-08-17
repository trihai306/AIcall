"""Cắt đuôi thở ở cuối mảnh TTS.

Bên A nghe ra một tiếng "hợp" rất nhẹ sau mỗi vế (bộ kiểm Lần 9, 17-08-2026:
*"'hợp' ba lần, sau 'giảm dần', 'trả bớt', 'anh nhé'"*). Cho máy nhận dạng nghe
thì KHÔNG ra chữ nào — nội dung hoàn toàn đúng. Đo mức dB từng 20ms mới thấy:

    sau "giảm dần,"   -27 -30 -31 -33 -38 -36 -37 -37 -37 -41  rồi mới tới im
    giữa mảnh         không có đoạn nào như vậy

Tức F5 để lại một ĐUÔI THỞ ~200ms ở mức -27…-41dB, rồi code chèn quãng nghỉ
vào sau. Khách nghe thành: chữ -> hơi thở -> im -> vế sau.

`trim_silence` không bắt được vì ngưỡng của nó là 4% RMS ĐỈNH CỦA MẢNH, mà RMS
đỉnh thấp hơn biên độ đỉnh chừng 12dB - sàn cắt thực tế rơi vào ~-40dB nên cả
đuôi thở lọt qua.

Chữa: tách ngưỡng ĐUÔI khỏi ngưỡng ĐẦU. Đầu mảnh phải giữ ngưỡng thấp vì phụ âm
bật hơi ("kh", "th", "ph") vào rất nhẹ, cắt sát là mất tiếng đầu - đã ghi trong
docstring của `trim_silence` và đừng làm hỏng lại.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from backend.services.tts_service import (TI_LE_DAU, TI_LE_DUOI, trim_silence)

SR = 24000


def tieng(ms, bien=0.5, f=200):
    n = int(SR * ms / 1000)
    t = np.arange(n) / SR
    return (bien * np.sin(2 * np.pi * f * t)).astype(np.float32)


def tho(ms, bien=0.02):
    """Hơi thở: nhiễu mức thấp, giống đuôi -30dB đo được trên tệp thật."""
    rng = np.random.default_rng(0)
    return (rng.normal(0, bien, int(SR * ms / 1000))).astype(np.float32)


def muc_db(x, dinh):
    return 20 * np.log10(np.sqrt((x.astype(np.float64) ** 2).mean()) / dinh + 1e-12)


def test_DUOI_THO_bi_cat():
    """Đây là lỗi bên A báo — phải cắt được."""
    x = np.concatenate([tieng(600), tho(200)])
    ra = trim_silence(x, SR)
    bot_ms = (len(x) - len(ra)) / SR * 1000
    assert bot_ms > 100, f"chỉ cắt {bot_ms:.0f}ms — đuôi thở vẫn còn"


def test_KHONG_an_vao_tieng_that():
    x = np.concatenate([tieng(600), tho(200)])
    ra = trim_silence(x, SR)
    assert len(ra) >= int(SR * 0.6), "cắt lẹm vào phần có tiếng"


def test_DAU_MANH_van_giu_nguong_thap():
    """Phụ âm bật hơi đầu câu vào rất nhẹ — ngưỡng đầu KHÔNG được nâng theo.

    Nâng cả hai đầu thì mất tiếng đầu, đúng lỗi mà docstring đã cảnh báo.
    """
    assert TI_LE_DAU < TI_LE_DUOI, "ngưỡng đầu phải thấp hơn ngưỡng đuôi"
    x = np.concatenate([tho(150, bien=0.03), tieng(600)])
    ra = trim_silence(x, SR)
    assert len(ra) >= int(SR * 0.62), "cắt mất phụ âm bật hơi đầu mảnh"


def test_manh_im_hoan_toan_thi_tra_nguyen():
    x = tho(300, bien=0.001)
    assert len(trim_silence(x, SR)) == len(x)


def test_rong_va_qua_ngan():
    assert trim_silence(np.array([], dtype=np.float32), SR).size == 0
    ngan = tieng(5)
    assert len(trim_silence(ngan, SR)) == len(ngan)


def test_khong_deo_them_gi():
    x = np.concatenate([tieng(400), tho(150)])
    ra = trim_silence(x, SR)
    assert len(ra) <= len(x)
    assert np.abs(ra).max() <= np.abs(x).max() + 1e-6
