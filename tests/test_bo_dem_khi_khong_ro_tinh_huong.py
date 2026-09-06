"""Không nhận ra tình huống thì THÔI, đừng phát câu đệm chung.

Người dùng 06-09-2026: "sao vẫn vào none nhiều, nếu none thì thôi không câu đệm
cho tôi".

Số đo cùng ngày (`latency_metrics`, hai phiên 10:25 và 10:31): 3/5 lượt có
`tinh_huong_id` rỗng mà vẫn phát câu đệm lấy từ rổ chung.

Đường GÕ CHỮ không đụng tới: ở đó `n_audio = 0` nên máy không hề thử phân loại,
áp luật này vào là xoá sạch câu đệm của một đường vốn đang đúng.
"""
from backend.services.filler_pick import nen_bo_cau_dem


def test_khong_ro_tinh_huong_tren_duong_tieng_thi_bo():
    assert nen_bo_cau_dem(None, co_audio=True) is True


def test_ro_tinh_huong_thi_van_phat():
    assert nen_bo_cau_dem("hoi_lai_suat", co_audio=True) is False


def test_duong_go_chu_giu_nguyen_hanh_vi():
    """`n_audio = 0`: chưa từng thử phân loại nên không có gì để mà 'không rõ'."""
    assert nen_bo_cau_dem(None, co_audio=False) is False
