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


@pytest.fixture(autouse=True)
def _tat_chi_chon_trong_kho(request, monkeypatch):
    """`chi_chon_trong_kho` mặc định BẬT trên máy thật: kho không có thì AI hẹn
    liên hệ sau, mô hình không sinh. Bộ test cũ kiểm đường mô hình sinh (prompt,
    lưới chặn số, prefill...) nên chạy với nó TẮT; chỉ file test của chính chế
    độ này mới bật."""
    from backend.config import settings
    monkeypatch.setattr(settings, "chi_chon_trong_kho",
                        "chi_chon" in request.module.__name__)
