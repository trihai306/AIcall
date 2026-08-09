"""Vượt trần biên độ thì HẠ MỨC cả mảnh, đừng xén cứng.

Đo 08-08: F5 với ref ngắn trả về đỉnh 1.09-1.40, tức vượt trần. `np.clip` cắt
phẳng ngọn sóng -> méo. Bản ghi cuộc gọi có 114 chuỗi bão hoà vì chuyện này.
Hạ mức giữ nguyên DẠNG sóng, chỉ nhỏ đi chút.
"""
import numpy as np
from backend.services.audio_utils import ha_muc_neu_qua


def test_giu_nguyen_khi_chua_vuot_tran():
    x = np.array([0.5, -0.8, 0.99], dtype=np.float32)
    assert np.allclose(ha_muc_neu_qua(x), x)


def test_ha_ca_manh_khi_vuot_tran():
    x = np.array([0.5, -1.4, 0.7], dtype=np.float32)
    ra = ha_muc_neu_qua(x)
    assert np.abs(ra).max() <= 1.0
    # Ti le giua cac mau phai GIU NGUYEN - do moi la khac biet voi np.clip
    assert np.allclose(ra / ra[0], x / x[0])


def test_khong_lam_to_len_khi_tieng_nho():
    x = np.array([0.01, -0.02], dtype=np.float32)
    assert np.allclose(ha_muc_neu_qua(x), x)


def test_mang_rong_va_toan_khong():
    assert len(ha_muc_neu_qua(np.array([], dtype=np.float32))) == 0
    z = np.zeros(4, dtype=np.float32)
    assert np.allclose(ha_muc_neu_qua(z), z)
