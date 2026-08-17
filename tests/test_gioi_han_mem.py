"""Hạn biên MỀM, để có chỗ nâng mảnh nói nhỏ.

VÌ SAO CẦN. Bản cân độ to đầu tiên chỉ HẠ được, không nâng, nên câu 3 của bộ
kiểm Lần 9 (-14,5 / -16,4 / -19,5 dB) vẫn tụt dần y như cũ. Lý do tưởng là "hết
chỗ": mọi mảnh đều chạm đúng 0 dBFS.

Nhưng 0 dBFS TRÒN như vậy không phải tự nhiên - đó là `ha_muc_neu_qua` chia cho
đỉnh. Chính comment của nó ghi: *"F5 trả về đỉnh 1.09-1.40, tức vượt trần thường
xuyên"*. Tức mọi mảnh đang bị chuẩn hoá theo ĐỈNH, và đó chính là nguồn của "lúc
to lúc bé": cùng đỉnh nhưng hệ số đỉnh khác nhau (đo được 10-19dB) thì độ to
nghe được lệch nhau tới 5dB.

Chữa đúng gốc: chuẩn theo ĐỘ TO, còn vài cái gai biên độ thì bẻ mềm thay vì lấy
chúng làm chuẩn. Gai rất thưa - với hệ số đỉnh 12-19dB thì phần vượt ngưỡng chỉ
là một phần nghìn số mẫu - nên bẻ mềm gần như không nghe ra.

KHÔNG dùng `np.clip`: clip cắt phẳng ngọn sóng nên sinh méo hài, nghe gắt. Đây
là lý do `ha_muc_neu_qua` tồn tại ngay từ đầu.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from backend.services.audio_utils import TRAN_MEM, gioi_han_mem

SR = 24000


def gai(n, muc, dinh):
    """Nhiễu mức `muc` cấy vài gai - giống mảnh F5 thật.

    Các gai phải KHÁC biên độ nhau (rải từ ngưỡng tới `dinh`), không thì phép
    thử "bẻ mềm giữ được chi tiết" trở thành vô nghĩa: gai nào cũng như nhau thì
    cắt phẳng hay bẻ mềm cũng cho ra một giá trị duy nhất.
    """
    rng = np.random.default_rng(3)
    x = rng.normal(0, 1, n)
    x = x / np.sqrt((x ** 2).mean()) * muc
    buoc = max(1, n // 30)
    cho = np.arange(0, n, buoc)
    x[cho] = np.linspace(0.55, dinh, len(cho))
    return x.astype(np.float32)


def test_KHONG_vuot_tran():
    x = gai(SR // 2, 0.15, 1.8)
    assert np.abs(gioi_han_mem(x)).max() <= TRAN_MEM + 1e-6


def test_phan_NHO_giu_NGUYEN_VAN():
    """Chỉ được đụng vào phần vượt ngưỡng - còn lại phải y hệt."""
    x = gai(SR // 2, 0.15, 1.8)
    ra = gioi_han_mem(x)
    nho = np.abs(x) < 0.3
    assert np.allclose(ra[nho], x[nho]), "đụng vào cả phần nhỏ"


def test_KHONG_lam_to_hon():
    x = gai(SR // 2, 0.15, 0.5)
    assert np.abs(gioi_han_mem(x)).max() <= np.abs(x).max() + 1e-6


def test_duoi_nguong_thi_khong_doi_gi():
    """Mảnh nào không có gai nào vượt ngưỡng thì phải đi qua nguyên văn."""
    rng = np.random.default_rng(7)
    x = rng.normal(0, 1, SR // 2)
    x = (x / np.abs(x).max() * 0.4).astype(np.float32)      # đỉnh 0.4 < NGUONG_MEM
    assert np.array_equal(gioi_han_mem(x), x)


def test_giu_DAU_cua_song():
    x = gai(SR // 2, 0.15, 1.8)
    ra = gioi_han_mem(x)
    khac0 = x != 0
    assert np.all(np.sign(ra[khac0]) == np.sign(x[khac0])), "đảo dấu -> vỡ dạng sóng"


def test_meo_it_hon_clip():
    """Thước đo: bẻ mềm phải làm đổi ÍT mẫu hơn so với cắt phẳng ở cùng trần."""
    x = gai(SR, 0.15, 1.8)
    mem = gioi_han_mem(x)
    cung = np.clip(x, -TRAN_MEM, TRAN_MEM)
    # cắt phẳng làm mọi mẫu vượt trần thành ĐÚNG trần (mất hết chi tiết);
    # bẻ mềm giữ chúng phân biệt nhau
    assert len(np.unique(np.abs(mem[np.abs(x) > TRAN_MEM]))) > \
           len(np.unique(np.abs(cung[np.abs(x) > TRAN_MEM])))


def test_rong_va_im():
    assert gioi_han_mem(np.array([], dtype=np.float32)).size == 0
    im = np.zeros(100, dtype=np.float32)
    assert np.array_equal(gioi_han_mem(im), im)
