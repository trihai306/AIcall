"""Chuẩn mức đường thoại phải tính trên PHẦN CÓ TIẾNG, không tính khung lặng.

Cuộc 08c0d3e0 (07-09-2026), người dùng nghe: "sau khi đọc hết câu đệm, từ liền
kề tiếp theo ... tiếng to hơn nghe rất giả". Diễn lại đúng tiếng khách đó trên
code 11-09: 4/11 chỗ nối câu đệm -> câu trả lời vẫn nhảy +2,5 đến +6,3 dB.

Một nguồn đo được bằng chính hàm này: pipeline chèn nhịp lặng vào ĐẦU mảnh trả
lời đầu tiên (`_nghi_noi_cau_dem`) rồi `chuan_muc_thoai` chia cho RMS của CẢ
mảnh. Khoảng lặng kéo RMS xuống nên hệ số khuếch đại tăng: chèn 180ms -> phần
tiếng to thêm +1,1 dB, chèn 600ms -> +3,0 dB. Tức chính bản chữa "đè lên từ
phía trước" lại đẻ ra một phần của "tiếng to hơn".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from backend.config import settings
from backend.services.phone_call_service import chuan_muc_thoai

SR = 24000


def tieng(ms, he_so_dinh_db=14.0, seed=1):
    """Giả tiếng nói với HỆ SỐ ĐỈNH THẬT (10-19dB như mảnh F5).

    Không dùng sóng sin: hệ số đỉnh 3dB của sin từng làm test độ to xanh trong
    khi hàm gần như không làm gì trên tiếng thật - xem `test_can_do_to.py`.
    """
    n = int(SR * ms / 1000)
    x = np.random.default_rng(seed).normal(0, 1, n)
    x = x / np.sqrt((x ** 2).mean())
    x[:: max(1, n // 40)] = 10 ** (he_so_dinh_db / 20)
    return (x * 10 ** (-26 / 20)).astype(np.float32)


def lang(ms):
    return np.zeros(int(SR * ms / 1000), np.float32)


def muc(x):
    return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12)


def test_lang_dau_manh_khong_lam_phan_tieng_to_len():
    s = tieng(600)
    goc = muc(chuan_muc_thoai(s.copy()))
    for ms in (180, 600):
        n = len(lang(ms))
        ra = chuan_muc_thoai(np.concatenate([lang(ms), s]))
        lech = muc(ra[n:n + len(s)]) - goc
        assert abs(lech) <= 0.3, f"lặng đầu {ms}ms làm phần tiếng lệch {lech:+.2f} dB"


def test_lang_cuoi_manh_cung_khong_lam_phan_tieng_to_len():
    """Mảnh ĐẦU của câu trả lời thường ngắn (cắt sớm cho TTFA) nên đuôi lặng
    của F5 chiếm phần lớn - cùng một cơ chế khuếch đại oan."""
    s = tieng(400)
    goc = muc(chuan_muc_thoai(s.copy()))
    ra = chuan_muc_thoai(np.concatenate([s, lang(500)]))
    lech = muc(ra[:len(s)]) - goc
    assert abs(lech) <= 0.3, f"lặng cuối 500ms làm phần tiếng lệch {lech:+.2f} dB"


def test_manh_toan_tieng_van_ve_dung_muc_dich():
    ra = chuan_muc_thoai(tieng(800))
    assert abs(muc(ra) - settings.phone_muc_dbfs) <= 0.3
    assert np.abs(ra).max() <= settings.phone_dinh_toi_da + 1e-6


def test_manh_toan_lang_khong_vo():
    ra = chuan_muc_thoai(lang(300))
    assert np.all(np.isfinite(ra)) and np.abs(ra).max() == 0.0
