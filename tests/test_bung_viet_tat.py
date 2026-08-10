"""Bung viết tắt và khoảng-bằng-dấu-gạch trước khi đưa vào TTS.

Ba lỗi thật bắt được trên bản ghi hội thoại 2026-08-09:
    "KT3"   -> "kt3"                    STT nghe lại thành "kiev ba"
    "CIC"   -> "cic"
    "22-60" -> "hai mươi hai-sáu mươi"  dấu gạch còn nguyên, đọc lên dính
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline.text_normalizer import normalize_for_tts


@pytest.mark.parametrize("goc,phai_co", [
    ("Anh nộp KT3 nhé", "ca tê ba"),
    ("nợ xấu tại CIC", "xê i xê"),
    ("cần BHXH", "bảo hiểm xã hội"),
    ("cần HĐLĐ còn hiệu lực", "hợp đồng lao động"),
    ("chuẩn bị CMND", "chứng minh nhân dân"),
    ("hoặc CCCD", "căn cước công dân"),
])
def test_bung_viet_tat(goc, phai_co):
    assert phai_co in normalize_for_tts(goc)


def test_viet_tat_co_chu_so_o_duoi():
    """`\\b[A-Z]{2,}\\b` KHÔNG khớp "KT3" - sau "T" là "3" nên không có ranh giới từ."""
    assert "kt3" not in normalize_for_tts("nộp KT3 giúp em")


def test_viet_tat_co_chu_D_hoa():
    """`[A-Z]` là bảng ASCII nên bỏ sót "Đ" - đúng loại hay gặp trong hồ sơ vay."""
    assert "hđlđ" not in normalize_for_tts("cần HĐLĐ")


@pytest.mark.parametrize("goc", ["từ 22-60 tuổi", "từ 22 - 60 tuổi", "từ 22–60 tuổi"])
def test_khoang_bang_dau_gach_doc_thanh_den(goc):
    ra = normalize_for_tts(goc)
    assert "đến" in ra
    assert "-" not in ra and "–" not in ra


def test_khong_dung_toi_so_tien():
    assert "năm trăm triệu" in normalize_for_tts("hạn mức 500.000.000 đồng")


def test_khong_dung_toi_phan_tram():
    assert "bảy phẩy chín phần trăm" in normalize_for_tts("lãi suất 7.9%/năm")
