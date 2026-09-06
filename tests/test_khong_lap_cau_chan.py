"""Lưới chặn số không được phát CÙNG MỘT CÂU hai lượt liền.

VÌ SAO CÓ FILE NÀY. Cuộc gọi thật `ccb61c05` (06-09-2026), hai lượt cuối:

    09:43:04  khách: anh vay một lăm
    09:43:06  CHẶN TIỀN SAI: 150 triệu -> thay cả câu
    09:43:06  AI  : "Em xin phép kiểm tra lại thông tin này rồi báo lại anh chị ngay ạ. ..."
    09:43:17  khách: anh vay trong một năm
    09:43:18  CHẶN TIỀN SAI: 150 triệu -> thay cả câu
    09:43:18  AI  : "Em xin phép kiểm tra lại thông tin này rồi báo lại anh chị ngay ạ. ..."

CHẶN LÀ ĐÚNG: khách nói "một lăm", mô hình hiểu thành "150 triệu" rồi nói ra
con số đó; nó không có trong tài liệu, cũng không phải chữ khách nói. Cái sai
nằm ở CHỖ KHÁC - hai lượt liền mở đầu bằng đúng một câu, và khách nghe ra là AI
chỉ biết mỗi một câu. Đây là điều người dùng than: *"hỏi lãi cao vậy sao nó trả
lời 1 kiểu"*.

Câu mẫu cũ còn là ngõ cụt: "em kiểm tra lại rồi báo sau" không giải quyết được
gì, nên lượt sau mô hình vẫn nói lại đúng con số đó và lại bị chặn. Câu thay
phải HỎI LẠI con số - đó mới là thứ gỡ được vòng lặp, vì gốc là khách nói mờ.

`da_chan_bia` trong `streaming_pipeline` đã chặn lặp TRONG một lượt. File này lo
phần giữa các lượt.
"""
import re

import pytest

from backend.pipeline.cau_chan_lap import (CAU_CHAN, cau_chan,
                                           dem_chan_lien_tiep)
from backend.pipeline.text_normalizer import CAU_KIEM_TRA_LAI


# --- Chọn câu -------------------------------------------------------------

def test_lan_dau_van_la_cau_cu():
    """Lượt bị chặn đơn lẻ là ca thường gặp nhất - đừng đổi thứ đang chạy tốt."""
    assert cau_chan(1) == CAU_KIEM_TRA_LAI


def test_lan_thu_hai_phai_khac():
    assert cau_chan(2) != CAU_KIEM_TRA_LAI


def test_lan_thu_ba_khac_ca_hai_lan_truoc():
    assert len({cau_chan(1), cau_chan(2), cau_chan(3)}) == 3


def test_cau_thay_phai_hoi_lai_khach():
    """Ngõ cụt là thứ đẻ ra vòng lặp. Từ lần hai trở đi phải là câu HỎI."""
    for n in range(2, len(CAU_CHAN) + 1):
        assert cau_chan(n).rstrip().endswith("?") or "cho em xin" in cau_chan(n)


def test_khong_cau_nao_co_con_so():
    """Câu chặn mà chứa số thì chính nó lại rơi vào lưới chặn số."""
    for c in CAU_CHAN:
        assert not re.search(r"\d", c), c


def test_qua_so_cau_thi_lay_cau_cuoi():
    assert cau_chan(99) == CAU_CHAN[-1]


def test_so_lan_khong_hop_le_khong_vo():
    assert cau_chan(0) == CAU_CHAN[0]
    assert cau_chan(-3) == CAU_CHAN[0]


# --- Đếm liên tiếp --------------------------------------------------------

def test_hai_luot_lien_nhau_thi_dem_len():
    so, moc = dem_chan_lien_tiep(luot=5, moc_cu=4, so_lan_cu=1)
    assert (so, moc) == (2, 5)


def test_cach_quang_thi_dem_lai_tu_dau():
    """Giữa hai lần chặn có lượt trả lời bình thường thì khách không thấy lặp."""
    so, moc = dem_chan_lien_tiep(luot=9, moc_cu=4, so_lan_cu=3)
    assert (so, moc) == (1, 9)


def test_lan_dau_tien_trong_cuoc_goi():
    so, moc = dem_chan_lien_tiep(luot=0, moc_cu=None, so_lan_cu=0)
    assert (so, moc) == (1, 0)


def test_chan_hai_lan_trong_CUNG_mot_luot_khong_dem_len():
    """`_chan_so` chạy trên TỪNG MẢNH của một lượt. Đếm theo mảnh thì một lượt
    hai mảnh đã nhảy sang câu thứ hai, dù khách mới nghe chặn một lần."""
    so, moc = dem_chan_lien_tiep(luot=5, moc_cu=5, so_lan_cu=2)
    assert (so, moc) == (2, 5)
