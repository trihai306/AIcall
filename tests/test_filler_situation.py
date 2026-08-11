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
