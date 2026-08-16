"""Cắt mẩu bù đuôi bằng mốc từng chữ.

Xem `backend/services/bu_duoi.py` để biết vì sao phải dùng mốc chữ thay vì dò
khe lặng: KHÔNG phải câu nào F5 cũng chừa khe trước mẩu bù (quét 7 mẩu, tốt nhất
chỉ 7/8 câu), nên ba cách cắt bằng tín hiệu đều ăn vào chữ thật.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from backend.services.bu_duoi import (LUI_MS, MAU_BU, cat_theo_moc, tim_moc_cat)


def chu(w, s, e):
    return {"word": w, "start": s, "end": e}


# --- tìm mốc -------------------------------------------------------------

def test_tim_duoc_moc_cua_mau_bu():
    doan = [{"words": [chu("nhé", 1.5, 1.8), chu("Vâng", 2.0, 2.3), chu("ạ", 2.3, 2.6)]}]
    assert tim_moc_cat(doan) == pytest.approx(2.0)


def test_khop_KHONG_DAU():
    """PhoWhisper hay trả "tam" thay vì "tạm" - một dấu sai không được phá chỗ cắt."""
    doan = [{"words": [chu("nhé", 1.5, 1.8), chu("vang", 2.0, 2.3)]}]
    assert tim_moc_cat(doan) == pytest.approx(2.0)


def test_bo_qua_dau_cau_bam_vao_chu():
    doan = [{"words": [chu("Vâng,", 2.0, 2.3)]}]
    assert tim_moc_cat(doan) == pytest.approx(2.0)


def test_lay_lan_CUOI_CUNG():
    """Câu của khách cũng có thể chứa "vâng" - lần cuối mới là mẩu bù."""
    doan = [{"words": [chu("vâng", 0.4, 0.7), chu("ạ", 0.7, 1.0),
                       chu("Vâng", 3.0, 3.3), chu("ạ", 3.3, 3.6)]}]
    assert tim_moc_cat(doan) == pytest.approx(3.0)


def test_khong_co_thi_tra_None():
    assert tim_moc_cat([{"words": [chu("xong", 1.0, 1.3)]}]) is None
    assert tim_moc_cat([]) is None
    assert tim_moc_cat([{}]) is None


# --- cắt -----------------------------------------------------------------

def test_cat_dung_cho_va_lui_them():
    sr = 24000
    pcm = np.ones(sr * 3, dtype=np.int16)          # 3 giây
    ra = cat_theo_moc(pcm, sr, 2.0)
    assert len(ra) == pytest.approx(int((2.0 - LUI_MS / 1000) * sr), abs=2)


def test_moc_None_thi_giu_nguyen():
    pcm = np.ones(1000, dtype=np.int16)
    assert len(cat_theo_moc(pcm, 24000, None)) == 1000


def test_moc_QUA_SOM_thi_giu_nguyen():
    """Lưới an toàn: STT nghe nhầm chữ nào đó thành "vâng" thì cắt sẽ mất nửa câu.

    Thà giữ nguyên (còn chữ ngân) hơn là giao cho khách một câu bị cụt.
    """
    sr = 24000
    pcm = np.ones(sr * 3, dtype=np.int16)
    assert len(cat_theo_moc(pcm, sr, 0.5)) == len(pcm)      # 0.5s / 3s = 17%


def test_mau_bu_KHONG_duoc_ngat_cau():
    """Dấu chấm phía trước tạo CÂU MỚI -> chữ cuối của khách vẫn ở vị trí kết
    câu và vẫn bị ngân. Đo được: ngân 1.82x -> 2.09x, TỆ HƠN không bù."""
    assert not MAU_BU.lstrip().startswith((".", "!", "?", ";"))
    assert MAU_BU.startswith(" ")
