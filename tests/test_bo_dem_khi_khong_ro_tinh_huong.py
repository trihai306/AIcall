"""Không rõ tình huống thì VẪN phát câu đệm rổ chung.

LỊCH SỬ, giữ lại vì nó là bài học có số đo:

Sáng 06-09-2026 người dùng yêu cầu "None thì thôi không câu đệm cho tôi", và
luật đó đã chạy thật. Đo trên cuộc gọi `e036b33b` cho thấy cái giá:

    khách dứt lời -> AI cất tiếng
      560ms   lượt có tình huống  (có câu đệm)
     1920ms   lượt None           (không đệm)
     1880ms   lượt None           (không đệm)

Tức 2/4 lượt khách ngồi im gần 2 giây. Sau khi nâng mốc im lặng lên 1 giây thì
quãng đó thành ~2,7 giây - dài tới mức nghe như rớt máy.

Nên chiều 06-09 người dùng đảo lại quyết định: thà nghe câu đệm trung tính còn
hơn nghe im lặng. Cờ `BO_DEM_KHI_KHONG_RO` giữ nguyên đường code cũ để bật lại
bằng một dòng nếu đổi ý.
"""
from backend.services.filler_pick import nen_bo_cau_dem


def test_khong_ro_tinh_huong_van_phat_dem():
    """Đây là thứ đổi so với bản sáng: None KHÔNG còn nghĩa là im lặng."""
    assert nen_bo_cau_dem(None, co_audio=True) is False


def test_ro_tinh_huong_thi_van_phat():
    assert nen_bo_cau_dem("hoi_lai_suat", co_audio=True) is False


def test_duong_go_chu_giu_nguyen_hanh_vi():
    assert nen_bo_cau_dem(None, co_audio=False) is False


def test_bat_co_lai_thi_quay_ve_hanh_vi_cu():
    """Cờ phải thật sự điều khiển được, nếu không nó chỉ là chú thích."""
    from backend.services import filler_pick
    cu = filler_pick.BO_DEM_KHI_KHONG_RO
    try:
        filler_pick.BO_DEM_KHI_KHONG_RO = True
        assert filler_pick.nen_bo_cau_dem(None, co_audio=True) is True
        assert filler_pick.nen_bo_cau_dem("hoi_lai_suat", co_audio=True) is False
    finally:
        filler_pick.BO_DEM_KHI_KHONG_RO = cu
