"""Bộ dò âm rác ở đầu phải bắt được rác thật mà không báo nhầm STT nghe chệch.

Dữ liệu trong đây là các ca THẬT ghi được ngày 2026-08-09, chép từ log máy chủ
STT và từ báo cáo nghiệm thu — không phải ca bịa. Bản dò đầu tiên dùng
`startswith` báo nhầm 4/42 tệp câu đệm; bốn ca đó nằm ở nhóm KHÔNG_RÁC dưới đây.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

from nghiem_thu_giong import chuan, co_rac_dau

# (mô tả, câu gốc, STT nghe lại)
CO_RAC = [
    ("bịa 4 chữ, ca kinh điển",
     "Lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm",
     "ca hếu cá nhân lãi suất vay tính chất của bâm là là"),
    ("bịa 2 chữ",
     "Lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm",
     "thể hiếu lãi suất vay tín chấp của em bên em là từ bảy"),
    ("bịa 5 chữ",
     "Lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm",
     "khởi hiếu kì hội kính nhắm lãi suất vay tính chấp của bên em"),
    ("bịa ĐÚNG 1 chữ - ca dễ lọt nhất",
     "Anh chị cho em xin ít phút để em tư vấn kỹ hơn được không ạ?",
     "cán anh chị cho em xin ít phút để em tư vấn kỹ hơn được không"),
    ("bịa 2 chữ ở đầu câu chào",
     "Dạ em chào anh chị, em gọi từ ngân hàng để tư vấn về khoản vay tín chấp ạ.",
     "cá nhân dạ em chào anh chị em gọi từ ngân hàng để tư vấn về"),
]

KHONG_RAC = [
    ("STT đảo thứ tự trên câu 3 âm tiết", "dạ em rõ", "em dạ"),
    ("STT nghe chệch nghe->ngay", "vâng em nghe ạy", "vâng em ngay ạy"),
    ("STT nuốt một tiếng đệm", "vâng ẹ em xem", "vâng em xem"),
    ("STT nghe chệch tra->trai", "vâng em tra giúp anh chị nhé", "vâng em trai giúp anh chị nhé"),
    ("chép lại y hệt", "dạ vâng anh chị chờ em một chút", "dạ vâng anh chị chờ em một chút"),
    ("STT trả về rỗng thì không kết luận gì", "dạ em rõ", ""),
]


@pytest.mark.parametrize("mo_ta,goc,nghe", CO_RAC, ids=[c[0] for c in CO_RAC])
def test_bat_duoc_rac_that(mo_ta, goc, nghe):
    assert co_rac_dau(goc, nghe) is True


@pytest.mark.parametrize("mo_ta,goc,nghe", KHONG_RAC, ids=[c[0] for c in KHONG_RAC])
def test_khong_bao_nham(mo_ta, goc, nghe):
    assert co_rac_dau(goc, nghe) is False


def test_chuan_bo_dau_va_dau_cau():
    assert chuan("Dạ vâng, anh chị ạ!") == "da vang anh chi a"
    assert chuan("  nhiều   khoảng   trắng  ") == "nhieu khoang trang"


def test_chuan_khong_phan_biet_hoa_thuong():
    assert chuan("LÃI SUẤT") == chuan("lãi suất")
