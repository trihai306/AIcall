"""Chọn tình huống bằng cosine. Thuần numpy, không GPU."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from backend.services.filler_situation import (
    NGUONG_DIEM, chon_tinh_huong, chuan_hoa,
)


def v(*x) -> np.ndarray:
    return np.array(x, dtype=np.float32)


def test_chon_tinh_huong_diem_cao_nhat():
    kho = {
        "lai_suat": chuan_hoa(np.stack([v(1, 0, 0)])),
        "ho_so": chuan_hoa(np.stack([v(0, 1, 0)])),
    }
    id_th, diem = chon_tinh_huong(chuan_hoa(v(0.9, 0.1, 0))[0], kho)
    assert id_th == "lai_suat" and diem > NGUONG_DIEM


def test_lay_vi_du_khop_nhat_trong_cung_tinh_huong():
    """Một tình huống có nhiều ví dụ: lấy ví dụ KHỚP NHẤT, không lấy trung bình.
    Trung bình làm loãng - hai ví dụ trái nhau triệt tiêu nhau."""
    kho = {"a": chuan_hoa(np.stack([v(1, 0, 0), v(0, 0, 1)]))}
    id_th, diem = chon_tinh_huong(chuan_hoa(v(0, 0, 1))[0], kho)
    assert id_th == "a" and diem == pytest.approx(1.0, abs=1e-5)


def test_duoi_nguong_tra_none_kem_diem():
    """Trả cả điểm để nơi gọi ghi log được vì sao trượt."""
    kho = {"a": chuan_hoa(np.stack([v(1, 0, 0)]))}
    id_th, diem = chon_tinh_huong(chuan_hoa(v(0, 1, 0))[0], kho)
    assert id_th is None and diem < NGUONG_DIEM


def test_kho_rong():
    id_th, diem = chon_tinh_huong(chuan_hoa(v(1, 0, 0))[0], {})
    assert id_th is None and diem == 0.0


def test_tinh_huong_khong_co_vi_du_bi_bo_qua():
    """Ma trận rỗng không được làm hàm nổ."""
    kho = {"rong": np.zeros((0, 3), dtype=np.float32),
           "a": chuan_hoa(np.stack([v(1, 0, 0)]))}
    assert chon_tinh_huong(chuan_hoa(v(1, 0, 0))[0], kho)[0] == "a"


def test_chuan_hoa_vector_khong():
    """Vector 0 không được sinh NaN - chia cho 0 là bẫy im lặng."""
    r = chuan_hoa(v(0, 0, 0))
    assert not np.isnan(r).any()


def test_nguong_tuy_chinh():
    kho = {"a": chuan_hoa(np.stack([v(1, 0, 0)]))}
    q = chuan_hoa(v(0.8, 0.6, 0))[0]
    assert chon_tinh_huong(q, kho, nguong=0.9)[0] is None
    assert chon_tinh_huong(q, kho, nguong=0.5)[0] == "a"


# --- Ngưỡng siết lên 0,90 ngày 05-09-2026 -------------------------------------
#
# Đo lại trên 102 lượt tiếng khách THẬT (trích từ 47 bản ghi cuộc gọi,
# `scripts/do_nguong_tinh_huong.py`) cho kết quả KHÁC HẲN phép đo cũ vốn dựa
# trên tập nhỏ:
#
#     mốc 1000ms   0,75 -> chọn 29, đúng 15, SAI 14   (52%)
#                  0,90 -> chọn  4, đúng  4, SAI  0   (100%)
#     mốc 1200ms   0,75 -> chọn 33, đúng 20, SAI 13   (61%)
#                  0,90 -> chọn  5, đúng  5, SAI  0   (100%)
#
# Comment cũ ghi "0,75 -> phân loại 4 lần, đúng 4 (100%)" — đúng với tập đo lúc
# đó, nhưng trên tiếng thật thì 0,75 để lọt gần MỘT NỬA số lần chọn là sai.
#
# Nguyên tắc không đổi, chỉ có số đo tốt hơn: chọn sai mẩu mở đầu tệ hơn không
# có mẩu nào, vì rổ chung vốn trung tính còn chọn sai thì nghe như AI hiểu nhầm.

def test_nguong_cau_dem_du_cao_de_bo_cau_cut():
    """Câu cụt hay cho điểm 0,75-0,85 và chính là chỗ phân loại hay sai."""
    from backend.services.filler_situation import NGUONG_CAU_DEM
    assert NGUONG_CAU_DEM >= 0.90, (
        "hạ ngưỡng câu đệm xuống dưới 0,90 thì tỷ lệ chọn đúng rơi về ~50-60%, "
        "xem scripts/do_nguong_tinh_huong.py"
    )


def test_nguong_cau_dem_KHONG_dung_chung_voi_nguong_chung():
    """Nâng `NGUONG_DIEM` chung là âm thầm siết luôn BẢNG HỎI-ĐÁP.

    `_tra_bang_hoi_dap` cũng gọi `chon_tinh_huong` với ngưỡng mặc định. Lần sửa
    đầu nâng thẳng `NGUONG_DIEM` lên 0,90 và bộ test đã bắt được qua
    `test_nguong_doc_thang_cao_hon_nguong_trung` (đọc thẳng 0,90 phải CAO HƠN
    ngưỡng trúng bảng). Hai đường chịu rủi ro khác nhau nên phải có hai ngưỡng.
    """
    from backend.services.filler_situation import NGUONG_CAU_DEM
    assert NGUONG_CAU_DEM > NGUONG_DIEM
