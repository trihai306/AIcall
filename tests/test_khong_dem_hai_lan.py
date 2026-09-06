"""Không để khách nghe "em kiểm tra lại" HAI LẦN trong một lượt.

Người dùng 06-09-2026, kèm ảnh chụp màn hình gạch đỏ:
"đã có câu đệm rồi AI lại trả lời thêm câu đệm nữa thì thành ra 2 lần đệm".

Hai cơ chế ĐỘC LẬP nói cùng một điều:
    câu đệm  : "Vâng ạ, em kiểm tra lại thông tin rồi trả lời anh chị cho chính xác nhé"
    lưới chặn: "Dạ em xin phép kiểm tra lại thông tin này rồi báo lại anh chị ngay ạ."

`cau_chan_lap` chỉ chống lặp GIỮA HAI LƯỢT, không thấy được câu đệm vừa phát
trong CHÍNH lượt này - nên lượt đầu tiên bị chặn là đã nghe hai lần rồi.

Câu thứ hai trong kho vừa không lặp vừa GỠ được bế tắc (hỏi lại con số), nên
dùng nó thay vì bịa câu mới.
"""
from backend.pipeline.cau_chan_lap import CAU_CHAN, CAU_NGAN_SAU_DEM, cau_chan
from backend.pipeline.text_normalizer import CAU_KIEM_TRA_LAI


def test_da_phat_cau_dem_thi_dap_NGAN_thoi():
    """Người dùng 06-09-2026, sau khi nghe cuộc gọi thật:

        "cái câu em xin phép kiểm tra lại rồi báo anh chị nó dài, chỉ cần
         dạ vâng hoặc 1 câu đệm đã thêm là đủ rồi"

    Câu đệm vừa hứa "em kiểm tra lại rồi báo lại" xong; nhắc lại trọn lời hứa
    đó lần nữa vừa thừa vừa dài. Một tiếng đáp ngắn là đủ.
    """
    ra = cau_chan(1, da_co_cau_dem=True)
    assert ra != CAU_KIEM_TRA_LAI, (
        "câu đệm vừa hứa 'em kiểm tra lại rồi báo lại', câu chặn hứa y hệt "
        "-> khách nghe hai lần liền")
    assert len(ra.split()) <= 5, f"vẫn còn dài ({len(ra.split())} từ): {ra!r}"
    assert ra == CAU_NGAN_SAU_DEM


def test_cau_ngan_khong_duoc_chua_chu_so():
    """Cùng ràng buộc với mọi câu chặn: chính chúng lại đi qua lưới chặn số."""
    import re
    assert not re.search(r"\d", cau_chan(1, da_co_cau_dem=True))


def test_chua_phat_cau_dem_thi_giu_nguyen_cau_cu():
    """Không có câu đệm thì câu 1 vẫn là câu tự nhiên nhất - đừng đổi vô cớ."""
    assert cau_chan(1, da_co_cau_dem=False) == CAU_KIEM_TRA_LAI
    assert cau_chan(1) == CAU_KIEM_TRA_LAI


def test_lan_chan_thu_hai_van_hoi_lai_con_so():
    """Đã lặp thì phải HỎI LẠI - lúc đó câu dài là đáng, vì nó GỠ được bế tắc.

    Chỉ lần chặn ĐẦU mới rút ngắn: lúc đó câu đệm vừa nói xong nên khách đã
    nghe lời hứa rồi.
    """
    assert cau_chan(2, da_co_cau_dem=True) == cau_chan(2)
    assert "nhắc lại" in cau_chan(2)
