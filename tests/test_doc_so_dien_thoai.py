"""Số điện thoại phải đọc TỪNG CHỮ SỐ, không đọc như số lượng.

Lỗi thật bắt được 2026-08-10 trên cuộc gọi thử hai giọng:
    "0912345678" -> "chín trăm mười hai TRIỆU ba trăm bốn mươi lăm nghìn
                     sáu trăm bảy mươi tám"
Thành một số tiền, và mất luôn số 0 đầu. Khách nghe xong không ghi lại được số.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline.text_normalizer import doc_tung_chu_so, normalize_for_tts

DOC_DUNG = "không chín một hai ba bốn năm sáu bảy tám"


@pytest.mark.parametrize("goc", [
    "số điện thoại của em là 0912345678 nhé",
    "gọi vào 091 234 5678 giúp em",
    "số 0912.345.678 ạ",
    "liên hệ 091-234-5678",
])
def test_doc_tung_chu_so_moi_dang_viet(goc):
    ra = normalize_for_tts(goc)
    assert DOC_DUNG in ra, ra
    assert "triệu" not in ra and "nghìn" not in ra


def test_khong_mat_so_khong_dau():
    assert normalize_for_tts("số 0912345678").startswith("số không chín")


def test_doc_tung_chu_so_thuan():
    assert doc_tung_chu_so("0912") == "không chín một hai"
    assert doc_tung_chu_so("") == ""


# --- khoảng bằng dấu gạch: chỉ số NGẮN mới là khoảng --------------------

@pytest.mark.parametrize("goc,phai_co", [
    ("từ 22-60 tuổi", "đến"),
    ("thời hạn 12 - 60 tháng", "đến"),
    ("nhóm nợ 3-5", "đến"),
])
def test_khoang_ngan_doc_thanh_den(goc, phai_co):
    assert phai_co in normalize_for_tts(goc)


@pytest.mark.parametrize("goc", [
    "hợp đồng MN-2023-11204",
    "mã TC-2024-00871",
])
def test_ma_hop_dong_KHONG_bi_chen_den(goc):
    """Mã giấy tờ đầy dấu gạch, không cái nào là khoảng.

    Luật đổi gạch -> "đến" thêm 2026-08-09 ban đầu nuốt luôn mã hợp đồng.
    """
    assert " đến " not in normalize_for_tts(goc)


def test_so_tien_va_phan_tram_khong_hong():
    assert "năm trăm triệu" in normalize_for_tts("hạn mức 500.000.000 đồng")
    assert "bảy phẩy chín phần trăm" in normalize_for_tts("lãi suất 7.9%/năm")
    assert "một trăm bốn mươi hai triệu" in normalize_for_tts("dư nợ 142.500.000 đồng")
