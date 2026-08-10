"""Tra tốc đọc phải quy bí danh "default" về giọng thật.

Lỗi đã bắt được 2026-08-10, và nó câm hoàn toàn:

    phiên mới mặc định voice_name = "default"
    -> `default.speed` không bao giờ tồn tại
    -> rơi về `settings.f5tts_speed`, mà .env đang để 0.64

Nên cuộc gọi thật đọc ở tốc 0.64 trong khi mọi bản xuất bằng script (gọi thẳng
tên "giong_heu") đọc ở 1.20 - chậm gấp rưỡi. Người dùng nghe ra ngay: "sao 120
thì ổn khi xuất mà khi AI nói chuyện lại khác". Suốt nhiều vòng đo trước đó đều
đo trên đường xuất nên không phép đo nào chạm tới.

`synthesize` không dính vì nó `ensure_voice` giải tên ngay đầu hàm. Chỗ dính là
những nơi tra tốc TRƯỚC rồi mới truyền vào: `_toc_cho_phien` của pipeline và
`test-tts` của trang giọng.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.services.tts_service import F5TTSService


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """Service rỗng, chỉ đủ để tra tốc - không nạp model."""
    from backend.services import tts_service as T
    monkeypatch.setattr(T.settings, "f5tts_ref_audio",
                        str(tmp_path / "giong_that.wav"))
    monkeypatch.setattr(T.settings, "f5tts_speed", 0.64)   # giá trị sót trong .env
    s = F5TTSService()
    s._default_voice = "giong_that"
    s._voices = {"giong_that": object(), "giong_khac": object()}
    (tmp_path / "giong_that.speed").write_text("1.200", encoding="utf-8")
    (tmp_path / "giong_khac.speed").write_text("0.950", encoding="utf-8")
    return s


# --- ca đã làm hỏng cuộc gọi -------------------------------------------

def test_bi_danh_default_lay_toc_cua_giong_that(svc):
    assert svc.toc_do_cua("default") == 1.2


def test_none_cung_lay_toc_cua_giong_that(svc):
    assert svc.toc_do_cua(None) == 1.2


def test_khong_roi_ve_toc_chung_khi_co_giong_that(svc):
    """0.64 là tốc chung trong .env - không được lòi ra ở đường nào cả."""
    for ten in ("default", None, "giong_that", "giong_da_xoa"):
        assert svc.toc_do_cua(ten) != 0.64, ten


# --- vẫn phải phân biệt giọng ------------------------------------------

def test_giong_co_ten_that_van_lay_dung_toc_rieng(svc):
    assert svc.toc_do_cua("giong_khac") == 0.95


def test_ten_la_thi_quy_ve_giong_mac_dinh(svc):
    """Phiên cũ còn giữ tên giọng đã xoá - hỏi tệp của giọng thật."""
    assert svc.toc_do_cua("giong_da_xoa") == 1.2


def test_khong_co_giong_nao_thi_moi_dung_toc_chung(svc):
    svc._voices = {}
    svc._default_voice = "khong_ton_tai"
    assert svc.toc_do_cua("default") == 0.64


# --- đường GHI không được quy tên lạ -----------------------------------

def test_dat_toc_cho_giong_chua_nap_khong_de_len_giong_dang_chay(svc, tmp_path):
    """Quy MỌI tên lạ về mặc định là hỏng: ghi nhầm sang tệp giọng đang chạy."""
    svc.dat_toc_do("giong_moi_upload", 1.35)
    assert (tmp_path / "giong_moi_upload.speed").exists()
    assert (tmp_path / "giong_that.speed").read_text(encoding="utf-8").strip() == "1.200"


def test_dat_toc_cho_bi_danh_default_ghi_vao_giong_that(svc, tmp_path):
    """Thanh trượt trên trang giọng gửi 'default' - phải ăn vào giọng thật.

    Trước đây nó ghi ra `default.speed`, một tệp không ai đọc, nên kéo thanh
    trượt xong nghe y như cũ.
    """
    svc.dat_toc_do("default", 1.35)
    assert (tmp_path / "giong_that.speed").read_text(encoding="utf-8").strip() == "1.350"
    assert not (tmp_path / "default.speed").exists()
