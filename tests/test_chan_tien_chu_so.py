"""Lưới chặn tiền sai phải bắt cả tiền viết TOÀN CHỮ SỐ.

Lỗ hổng thật, bắt được 2026-08-09 trên bản ghi hội thoại: tài liệu ghi hạn mức
vay tín chấp 500 triệu, mô hình trả lời "2.000.000.000 đồng" và LỌT THẲNG tới
khách. Cùng câu hỏi lần khác lại ra 500 triệu - bịa không nhất quán.

Nguyên nhân: `_TIEN_SO_RE` đòi phải có chữ đơn vị đi kèm, nên "2 tỷ đồng" thì
chặn được mà "2.000.000.000 đồng" thì không. Mà mô hình lại hay viết dạng chữ số
khi trả lời về hạn mức.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline.text_normalizer import chan_tien_sai

TAI_LIEU = "- Hạn mức: lên đến 500 triệu đồng\nVay tín chấp tối đa 500 triệu."
CO_HO_SO = TAI_LIEU + "\nHỒ SƠ KHÁCH: dư nợ hiện tại 142.500.000 đồng."


@pytest.mark.parametrize("cau", [
    "Anh chị được duyệt tới 2.000.000.000 đồng ạ.",
    "Hạn mức đã duyệt là 2.000.000.000 đồng ạ.",
    "Anh vay 300.000.000 được không ạ.",
])
def test_chan_tien_viet_bang_chu_so(cau):
    ra, sua = chan_tien_sai(cau, TAI_LIEU, khach_noi="")
    assert sua is not None, "phải chặn"
    assert "năm trăm triệu" in ra
    assert "2.000.000.000" not in ra and "300.000.000" not in ra


def test_van_chan_duoc_dang_co_chu_don_vi():
    """Dạng cũ không được hỏng khi thêm dạng mới."""
    ra, sua = chan_tien_sai("vay tối đa 2 tỷ đồng ạ.", TAI_LIEU, khach_noi="")
    assert sua is not None and "năm trăm triệu" in ra


def test_khong_dung_so_dung():
    ra, sua = chan_tien_sai("Hạn mức tối đa là 500 triệu đồng ạ.", TAI_LIEU,
                            khach_noi="")
    assert sua is None and "500 triệu" in ra


def test_khong_dung_so_co_trong_ho_so_khach():
    """Dư nợ thật tra từ CSDL nằm trong ngữ cảnh - chặn nó mới là sai."""
    ra, sua = chan_tien_sai("Dư nợ của anh là 142.500.000 đồng ạ.", CO_HO_SO,
                            khach_noi="")
    assert sua is None and "142.500.000" in ra


def test_khong_dung_so_khach_vua_neu():
    ra, sua = chan_tien_sai("Dạ anh vay 300.000.000 đúng không ạ.", TAI_LIEU,
                            khach_noi="anh muốn vay 300.000.000")
    assert sua is None and "300.000.000" in ra


@pytest.mark.parametrize("cau", [
    "Số điện thoại của em là 0912345678 ạ.",
    "Hồ sơ duyệt trong 24 giờ ạ.",
    "Anh sinh năm 1990 phải không ạ.",
])
def test_khong_nham_so_khong_phai_tien(cau):
    ra, sua = chan_tien_sai(cau, TAI_LIEU, khach_noi="")
    assert sua is None, f"đã sửa nhầm: {ra}"


def test_khong_lam_dinh_chu():
    """Bản đầu nuốt cả khoảng trắng: "300.000.000 được" -> "triệuđược"."""
    ra, _ = chan_tien_sai("Anh vay 300.000.000 được không ạ.", TAI_LIEU,
                          khach_noi="")
    assert "triệuđược" not in ra
    assert "triệu được" in ra
