"""Sửa lời đoạn mẫu — lời do máy nghe ra thì phải sửa được bằng tay.

VÌ SAO CÓ. Giọng tách từ bản ghi dài mang theo lời do STT nghe ra, mà bản ghi
nguồn nằm ngoài miền từ vựng ngân hàng nên nó nghe sai tên riêng, sai số, nuốt
tiểu từ cuối câu. Lời đó KHÔNG phải chú thích: F5 dùng đúng nó để căn chữ với
tiếng trong đoạn mẫu, sai một chữ là đoạn mẫu lệch và giọng lắp ra đọc hỏng mà
không có gì báo lỗi.

Sửa lời là đổi luôn số tiếng, nên nhịp gốc và tốc đề xuất phải đo lại theo lời
MỚI. Giữ số cũ thì tốc đề xuất đang tính trên một câu không còn tồn tại - đúng
kiểu hỏng câm mà dự án này đã gặp nhiều lần với đoạn mẫu.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("fastapi")

from backend.api.voices import NHIP_MUON, _do_nhip  # noqa: E402


def test_dem_tieng_theo_loi():
    assert _do_nhip("dạ vâng em nghe anh ạ", 2.0)["am_tiet"] == 6


def test_khoang_trang_thua_khong_thanh_tieng():
    """Người gõ tay hay để lọt dấu cách kép và xuống dòng - không phải tiếng."""
    assert _do_nhip("  dạ  vâng \n em ạ ", 2.0)["am_tiet"] == 4


def test_sua_loi_thi_nhip_doi_theo():
    """Máy nghe nuốt mất hai tiếng: sửa vào là nhịp phải nhích lên."""
    may_nghe = _do_nhip("dạ vâng em nghe", 2.0)
    nguoi_sua = _do_nhip("dạ vâng em nghe anh ạ", 2.0)
    assert nguoi_sua["nhip_goc"] > may_nghe["nhip_goc"]


def test_toc_de_xuat_khong_bao_gio_vuot_1():
    """Đoạn nói CHẬM hơn nhịp muốn thì để nguyên, không kéo nhanh lên.

    Ép tốc là bóp thẳng vào nhịp, mà tai người nhận ra một người chủ yếu qua
    nhịp - xem docs/doan-mau-va-nhip-noi.md.
    """
    assert _do_nhip("dạ vâng ạ", 5.0)["toc_de_xuat"] == 1.0


def test_doan_noi_nhanh_thi_ha_toc():
    d = _do_nhip(" ".join(["tiếng"] * 40), 5.0)      # 480 âm tiết/phút
    assert d["nhip_goc"] == 480
    assert d["toc_de_xuat"] == round(NHIP_MUON / 480, 2)


def test_loi_rong_khong_chia_cho_khong():
    assert _do_nhip("", 3.0) == {"am_tiet": 0, "nhip_goc": 0, "toc_de_xuat": 1.0}


def test_dai_bang_khong_khong_chia_cho_khong():
    assert _do_nhip("dạ vâng ạ", 0.0)["toc_de_xuat"] == 1.0
