"""Thiết lập chung cho bộ test."""
import pytest


@pytest.fixture(autouse=True)
def _bat_cau_dem_cho_test_cau_dem(request, monkeypatch):
    """Câu đệm mặc định TẮT (config.cau_dem_bat). Các file test của chính logic
    câu đệm vẫn phải chạy với nó BẬT để mã đó không mục dần."""
    ten = request.module.__name__
    if "cau_dem" in ten or "filler" in ten:
        from backend.config import settings
        monkeypatch.setattr(settings, "cau_dem_bat", True)
