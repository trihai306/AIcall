"""Gộp nhiều mảnh thành MỘT phát ngôn cho F5.

Xem `gom_thanh_mot_luot` trong `text_chunker.py` để biết vì sao: F5 kéo dài âm
tiết cuối của TỪNG mảnh, nên càng ít mảnh càng ít chỗ ngân giữa câu.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline.text_chunker import (TRAN_AM_TIET_GOP, gom_thanh_mot_luot,
                                           noi_lo)


# --- nối chữ -------------------------------------------------------------

def test_noi_bang_MOT_khoang_trang():
    assert noi_lo(["Dạ em hiểu ạ.", "Em cảm ơn anh."]) == "Dạ em hiểu ạ. Em cảm ơn anh."


def test_bo_manh_rong_va_khoang_thua():
    assert noi_lo(["  Dạ ạ. ", "", "   ", "Em nghe."]) == "Dạ ạ. Em nghe."


def test_mot_manh_thi_giu_nguyen():
    assert noi_lo(["Dạ em hiểu ạ."]) == "Dạ em hiểu ạ."
    assert noi_lo([]) == ""


def test_KHONG_them_dau_cau():
    """Nối là nối, không được tự chèn dấu - dấu quyết định ngữ điệu của F5."""
    assert noi_lo(["Dạ vâng", "em nghe ạ."]) == "Dạ vâng em nghe ạ."


# --- chọn gom bao nhiêu --------------------------------------------------

def test_gom_het_khi_con_ngan():
    dan = ["Dạ em hiểu ạ.", "Em cảm ơn anh chị.", "Em xin phép ạ."]
    assert gom_thanh_mot_luot(dan) == len(dan)


def test_DUNG_LAI_khi_qua_tran():
    """Phát ngôn quá dài thì sinh lâu, tiếng đang phát có thể hết trước khi
    mảnh sau kịp ra - thành quãng im giữa lượt."""
    dai = "một hai ba bốn năm sáu bảy tám chín mười " * 3      # 30 âm tiết
    n = gom_thanh_mot_luot([dai, dai, dai])
    assert n < 3, "gom quá trần mà không dừng"
    assert n >= 1, "phải lấy ít nhất một mảnh"


def test_LUON_lay_it_nhat_mot_manh():
    """Mảnh đơn lẻ đã vượt trần thì vẫn phải trả về 1, không được trả 0 -
    trả 0 là bỏ rơi mảnh đó, khách mất luôn đoạn tiếng ấy."""
    qua_dai = "một " * (TRAN_AM_TIET_GOP + 20)
    assert gom_thanh_mot_luot([qua_dai, "Em nghe ạ."]) == 1


def test_tran_tinh_theo_AM_TIET_khong_phai_so_tu():
    """Số viết một từ nhưng đọc thành nhiều âm tiết - đếm từ là hụt ngân sách."""
    so = "500.000.000 đồng"                     # đọc ra ~15 âm tiết
    nhieu_so = [so] * 8
    assert gom_thanh_mot_luot(nhieu_so) < 8


def test_danh_sach_rong():
    assert gom_thanh_mot_luot([]) == 0
