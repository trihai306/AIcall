"""Chờ bao lâu để gom thêm mảnh trước khi sinh tiếng.

Gộp mảnh chỉ ăn được 25% chỗ nối trên cuộc gọi thật, vì lúc vòng tiêu thụ lấy
mảnh 2 thì LLM chưa kịp sinh mảnh 3 (đo được: hai mảnh cách nhau 521-1377ms).
Chờ thêm thì gộp được nhiều hơn, nhưng chờ là ăn vào DƯ ĐỊA PHÁT - phần tiếng
đã gửi mà khách chưa nghe tới. Hết dư địa là khách nghe quãng im.

Đo trên cuộc gọi thật lúc sinh mảnh 2: dư địa 1070-2165ms.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.pipeline.text_chunker import (JITTER_MS, TRAN_CHO_MS,
                                           cho_gom_ms, uoc_sinh_ms)


# --- ước thời gian sinh --------------------------------------------------

def test_uoc_sinh_tang_theo_do_dai():
    assert uoc_sinh_ms("một hai ba") < uoc_sinh_ms("một hai ba bốn năm sáu")


def test_uoc_sinh_sat_so_do_that():
    """Đo 05-09-2026 (gộp CFG + CUDA graphs): 3 âm tiết 140ms, 22 âm tiết 314ms.
    Ước phải nằm trong ±30% số đo, không được quay về 45ms/âm tiết cũ."""
    assert 100 <= uoc_sinh_ms("một hai ba") <= 190
    assert 230 <= uoc_sinh_ms("một " * 22) <= 400


def test_uoc_sinh_co_phan_co_dinh():
    """16 bước khuếch tán tốn thời gian dù câu ngắn: 1 âm tiết không phải ~8ms."""
    assert uoc_sinh_ms("dạ") >= 100


def test_uoc_sinh_chuoi_rong():
    assert uoc_sinh_ms("") >= 0


# --- quyết định chờ ------------------------------------------------------

def test_HET_du_dia_thi_KHONG_cho():
    """Không dư địa mà còn chờ là khách nghe im - hỏng đúng thứ đang muốn chữa."""
    assert cho_gom_ms(0, 1000) == 0
    assert cho_gom_ms(300, 1000) == 0


def test_du_dia_VUA_DU_thi_cho_it():
    cho = cho_gom_ms(2000, 1000)
    assert 0 < cho <= TRAN_CHO_MS


def test_du_dia_LON_thi_van_chan_boi_TRAN():
    """Dư địa 8 giây cũng không chờ quá trần: chờ lâu là lượt bị kéo dài ra."""
    assert cho_gom_ms(8000, 1000) == TRAN_CHO_MS


def test_TRU_ca_thoi_gian_SINH():
    """Dư địa phải trừ luôn thời gian sinh, không thì chờ xong mới phát hiện
    không đủ chỗ cho chính lượt sinh sắp tới."""
    assert cho_gom_ms(1500, 1400) < cho_gom_ms(1500, 200)


def test_con_chua_jitter():
    """Còn đúng bằng thời gian sinh thì vẫn chưa được chờ - phải chừa jitter."""
    assert cho_gom_ms(1000 + JITTER_MS - 1, 1000) == 0


def test_khong_bao_gio_am():
    for du in (-500, 0, 100, 5000):
        assert cho_gom_ms(du, 900) >= 0
