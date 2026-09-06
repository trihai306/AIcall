"""Không nghe ra chữ thì HỎI LẠI, đừng im - và đừng hỏi mãi.

Thay cho cơ chế nhắc theo im lặng đã bỏ (xem `backend/pipeline/hoi_lai.py`).
Bản cũ: khách nói mà STT trả rỗng thì lượt đó IM HOÀN TOÀN - chỉ gửi sự kiện lỗi
rồi đóng lượt, nghe như máy đã chết.
"""
import re

import pytest

from backend.pipeline.hoi_lai import (CAU_HOI_LAI, TOI_DA_LIEN_TIEP,
                                      chon_cau_hoi_lai, nen_hoi_lai)


def test_lan_dau_khong_ra_chu_thi_hoi():
    assert nen_hoi_lai(0) is True


def test_lan_hai_van_hoi():
    assert nen_hoi_lai(1) is True


def test_qua_so_lan_thi_thoi():
    """Kênh ồn liên tục hoặc khách đã bỏ máy - hỏi mãi thì phiền hơn là im."""
    assert nen_hoi_lai(TOI_DA_LIEN_TIEP) is False
    assert nen_hoi_lai(TOI_DA_LIEN_TIEP + 5) is False


def test_so_lan_am_khong_lam_vo():
    assert nen_hoi_lai(-1) is False


def test_hai_lan_hoi_noi_hai_cau_khac_nhau():
    assert chon_cau_hoi_lai(0) != chon_cau_hoi_lai(1)


def test_qua_so_cau_thi_lay_cau_cuoi():
    assert chon_cau_hoi_lai(99) == CAU_HOI_LAI[-1]
    assert chon_cau_hoi_lai(-5) == CAU_HOI_LAI[0]


@pytest.mark.parametrize("cau", CAU_HOI_LAI)
def test_cau_hoi_lai_khong_chua_so(cau):
    """Câu đi thẳng xuống TTS, không qua RAG lẫn bộ chặn số."""
    assert not re.search(r"\d", cau)


@pytest.mark.parametrize("cau", CAU_HOI_LAI)
def test_cau_hoi_lai_la_loi_moi_noi_lai(cau):
    t = cau.lower()
    assert ("nói lại" in t or "nhắc lại" in t), f"phải mời khách nói lại: {cau!r}"


def test_khong_con_hoi_theo_dong_ho():
    """Cơ chế nhắc theo im lặng phải TẮT mặc định."""
    from backend.config import settings
    assert settings.phone_nhac_im_lang is False
