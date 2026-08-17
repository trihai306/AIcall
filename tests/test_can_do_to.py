"""Cân độ to giữa các mảnh TTS.

Bên A nghe "tiếng lúc to lúc bé" (bộ kiểm Lần 9, câu 2 và 3). Đo độ to RMS từng
mảnh trên chính hai tệp đó:

    câu 2   -12.1  -17.2  -12.8  -11.7  -12.7    tụt 5,1dB NGAY SAU "Dạ vâng,"
    câu 3   -14.5  -16.4  -19.5                  tụt dần đều, nghe như lịm đi

Câu 2 đúng là chỗ bên A viết *"sau chữ 'dạ vâng' bị cắt tiếng, cảm giác không
liên mạch"* - không phải mất tiếng, mà là mảnh kế TO NHỎ lệch hẳn.

ĐỪNG dùng "độ chênh lớn nhất trong lượt" làm thước đo: câu 5 bên A KHEN là OK
lại chênh tới 6,3dB. Cái tai nghe ra là BƯỚC NHẢY giữa hai mảnh liền nhau, và
cách chữa là kéo mọi mảnh về cùng một mức.

Có giới hạn mức kéo: mảnh nói nhỏ thật (thì thầm, cuối câu) mà kéo hết cỡ thì
vừa lộ nhiễu nền vừa mất sắc thái.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from backend.services.tts_service import (GIOI_HAN_KEO_DB, MUC_DICH_DBFS,
                                          can_do_to)

SR = 24000


def tieng(ms, dbfs, he_so_dinh_db=14.0):
    """Giả tiếng nói với HỆ SỐ ĐỈNH THẬT.

    Sóng sin có hệ số đỉnh 3dB, còn mảnh F5 thật đo được 10-19dB và đỉnh luôn
    chạm 0 dBFS. Dựng test bằng sin thì bỏ lọt đúng lỗi đã mắc: bản đầu của
    `can_do_to` gần như không làm gì trên tiếng thật vì chốt chống vỡ biên nuốt
    hết phần kéo, mà test sin vẫn xanh.
    """
    n = int(SR * ms / 1000)
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, n)
    x = x / np.sqrt((x ** 2).mean())                       # RMS = 1
    # cấy vài gai để đẩy đỉnh lên đúng hệ số đỉnh mong muốn
    x[:: max(1, n // 40)] = 10 ** (he_so_dinh_db / 20)
    x = x / np.sqrt((x ** 2).mean())
    return (x * 10 ** (dbfs / 20)).astype(np.float32)


def dbfs(x):
    x = np.asarray(x, dtype=np.float64)
    return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12)


def test_manh_NHO_thi_DE_YEN():
    """Mảnh F5 nào cũng chạm trần 0 dBFS - nâng thêm là vỡ tiếng, nên chỉ hạ."""
    x = tieng(500, MUC_DICH_DBFS - 4.0)
    assert np.array_equal(can_do_to(x, SR), x)


def test_manh_TO_duoc_ha_xuong():
    ra = can_do_to(tieng(500, -8.0), SR)
    assert dbfs(ra) < -8.0 - 1.0, "mảnh to không được hạ xuống"


def test_ve_dung_MUC_DICH_khi_trong_tam_keo():
    ra = can_do_to(tieng(500, MUC_DICH_DBFS + 3.0), SR)
    assert abs(dbfs(ra) - MUC_DICH_DBFS) < 0.6


def test_KHONG_ha_qua_gioi_han():
    goc = MUC_DICH_DBFS + 20.0
    ra = can_do_to(tieng(500, goc), SR)
    assert dbfs(ra) >= goc - GIOI_HAN_KEO_DB - 0.6, "hạ quá giới hạn đã chốt"


def test_thu_hep_BUOC_NHAY_giua_hai_manh():
    """Đây chính là thứ bên A nghe ra (số lấy từ câu 2 của bộ kiểm)."""
    a, b = tieng(500, -12.1), tieng(500, -14.5)
    truoc = abs(dbfs(a) - dbfs(b))
    sau = abs(dbfs(can_do_to(a, SR)) - dbfs(can_do_to(b, SR)))
    assert sau < truoc / 2, f"bước nhảy {truoc:.1f}dB -> {sau:.1f}dB, chưa đủ"


def test_khong_lam_vo_bien_do():
    """Tiếng thật đỉnh chạm 0 dBFS - sau khi cân KHÔNG được to hơn trước."""
    x = tieng(500, -10.0)
    ra = can_do_to(x, SR)
    assert np.abs(ra).max() <= np.abs(x).max() + 1e-6


def test_manh_im_thi_giu_nguyen():
    im = np.zeros(SR // 2, dtype=np.float32)
    assert np.array_equal(can_do_to(im, SR), im)


def test_rong():
    assert can_do_to(np.array([], dtype=np.float32), SR).size == 0
