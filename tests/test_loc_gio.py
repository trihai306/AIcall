"""Gió không được coi là khách nói - nếu không thì nó cắt mất câu chào của AI.

Số liệu trong file này lấy từ cuộc gọi thật `f2f61c42` (06-09-2026), đo từng
khung 20ms trên kênh khách:

    giây 1,40   mức 1201   dưới-300Hz 98,6%   <- gió, nhưng VƯỢT ngưỡng VAD 700
    giây 1,44   mức 1507   dưới-300Hz 99,1%   <- đủ 3 khung -> cắt lời AI
    giây 3,20   mức 4070   dưới-300Hz  0,9%   <- khách nói thật
    giây 3,46   mức 2163   dưới-300Hz 20,8%   <- khách nói thật, ca "thấp" nhất

Khoảng trống giữa 20,8% và 92% là chỗ đặt ngưỡng 70%.
"""
import numpy as np
import pytest

from backend.services.loc_gio import CAT_HZ, la_gio, ty_le_dai_thap

SR = 8000
N = SR * 20 // 1000          # khung 20ms = 160 mẫu


def _gio(bien_do=0.05, seed=0):
    """Gió thổi vào micro: năng lượng dồn xuống 20-250Hz, pha ngẫu nhiên.

    Dựng bằng tổng sin tần thấp chứ không phải nhiễu-rồi-lọc: lọc trung bình
    trượt cắt quá thoải (còn 30-40% năng lượng trên 300Hz) nên gió giả không
    giống gió thật, và test hỏng vì DỮ LIỆU chứ không vì hàm cần kiểm.
    Gió thật đo được 92-99% năng lượng dưới 300Hz.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(N) / SR
    x = np.zeros(N)
    for f in rng.uniform(20, 250, 12):
        x += rng.uniform(0.4, 1.0) * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28))
    return (x / (np.abs(x).max() + 1e-9) * bien_do).astype(np.float32)


def _tieng_noi(f0=140.0, bien_do=0.2):
    """Tiếng nói qua kênh thoại: hài của F0, năng lượng chính ở 300-3400Hz."""
    t = np.arange(N) / SR
    x = np.zeros(N)
    for k in range(2, 20):                     # bỏ hài 1 (F0 dưới 300Hz)
        if f0 * k >= 3400:
            break
        x += np.sin(2 * np.pi * f0 * k * t) / k
    return (x / (np.abs(x).max() + 1e-9) * bien_do).astype(np.float32)


# --- Nhận ra gió ----------------------------------------------------------

def test_gio_bi_nhan_ra():
    assert la_gio(_gio(), SR) is True


def test_gio_to_van_la_gio():
    """Gió mạnh vượt xa ngưỡng VAD 700 - đúng ca đã cắt mất câu chào."""
    assert la_gio(_gio(bien_do=0.3), SR) is True


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_gio_nhieu_lan_deu_nhan_ra(seed):
    assert la_gio(_gio(seed=seed), SR) is True


# --- KHÔNG được bắt nhầm tiếng nói ---------------------------------------

@pytest.mark.parametrize("f0", [110.0, 140.0, 180.0, 220.0])
def test_tieng_noi_khong_bi_coi_la_gio(f0):
    """Cả giọng nam trầm (F0 110Hz) cũng phải lọt - bỏ sót lời khách đắt hơn
    nhiều so với bỏ sót một cơn gió."""
    assert la_gio(_tieng_noi(f0), SR) is False


def test_tieng_noi_nho_van_khong_phai_gio():
    assert la_gio(_tieng_noi(bien_do=0.02), SR) is False


# --- Biên -----------------------------------------------------------------

def test_khung_lang_khong_vo():
    assert la_gio(np.zeros(N, dtype=np.float32), SR) is False


def test_khung_rong_khong_vo():
    assert la_gio(np.zeros(0, dtype=np.float32), SR) is False
    assert ty_le_dai_thap(np.zeros(0, dtype=np.float32), SR) == 0.0


def test_lech_mot_chieu_khong_lam_lech_ket_qua():
    """Kênh thoại hay có lệch DC. Không trừ trung bình thì vạch 0Hz nuốt hết
    tỉ lệ và MỌI khung đều thành 'gió'."""
    assert la_gio(_tieng_noi() + 0.5, SR) is False


def test_ty_le_nam_trong_khoang_0_1():
    for x in (_gio(), _tieng_noi(), np.zeros(N, dtype=np.float32)):
        assert 0.0 <= ty_le_dai_thap(x, SR) <= 1.0


def test_moc_cat_la_300hz():
    assert CAT_HZ == 300.0
