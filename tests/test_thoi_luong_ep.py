"""Ép thời lượng theo ÂM TIẾT để mọi mảnh đọc cùng một nhịp.

F5 cấp thời lượng theo số BYTE của chữ, mà tai nghe nhịp theo ÂM TIẾT. Chữ có
dấu tốn 3 byte, chữ không dấu tốn 1 - nên hai câu cùng số âm tiết mà khác mật độ
dấu được cấp thời lượng khác hẳn. Đo được tương quan byte/âm tiết với nhịp là
-0.74, và các câu ra từ 194 đến 500 âm tiết/phút.

Ép theo âm tiết hạ lệch nhịp giữa các câu từ 38% xuống 6%.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.services.tts_service import (
    NHIP_CHUAN_AM_TIET_PHUT, SPEED_CHUAN, TOI_THIEU_AM_TIET_DE_EP,
    so_am_tiet, thoi_luong_ep,
)

REF = 5.45      # đoạn mẫu đang dùng, giây


# --- đếm âm tiết ---------------------------------------------------------

def test_dem_tu_thuong():
    assert so_am_tiet("anh chị cho em xin") == 5


def test_chu_so_dem_theo_LOI_DOC_khong_theo_tu_viet():
    """"2.000.000.000" viết một từ nhưng đọc thành "hai tỷ" - nhiều âm tiết.

    Đếm là 1 thì thời lượng ép ra quá ngắn và tiếng bị cụt.
    """
    assert so_am_tiet("2.000.000.000") > 5
    assert so_am_tiet("142.500.000") > 5


def test_so_lan_trong_cau():
    it = so_am_tiet("hạn mức năm trăm triệu")
    nhieu = so_am_tiet("hạn mức 500.000.000")
    assert nhieu >= it, "số viết bằng chữ số phải được cấp thời lượng không kém"


def test_dau_khong_lam_doi_so_am_tiet():
    """Đây chính là điểm mấu chốt: dấu đổi số BYTE nhưng không đổi số âm tiết."""
    assert so_am_tiet("dạ vâng ạ em nghe") == so_am_tiet("da vang a em nghe")


def test_chuoi_rong():
    assert so_am_tiet("") == 0
    assert so_am_tiet("   ") == 0


# --- tính thời lượng -----------------------------------------------------

def test_tra_none_khi_manh_qua_ngan():
    """Mảnh 1-2 âm tiết thì sai số một âm tiết đã là 50-100% - để F5 tự lo."""
    assert thoi_luong_ep("dạ", REF, 1.20) is None
    assert thoi_luong_ep("dạ vâng", REF, 1.20) is None
    assert thoi_luong_ep("dạ vâng ạ", REF, 1.20) is not None


def test_bao_gom_ca_doan_mau():
    """fix_duration của F5 tính CẢ đoạn mẫu, không chỉ phần sinh ra."""
    d = thoi_luong_ep("anh chị cho em xin", REF, 1.20)
    assert d > REF


def test_dai_hon_khi_nhieu_am_tiet_hon():
    ngan = thoi_luong_ep("anh chị cho em xin", REF, 1.20)
    dai = thoi_luong_ep("anh chị cho em xin ít phút để em tư vấn thêm", REF, 1.20)
    assert dai > ngan


def test_speed_cao_hon_thi_thoi_luong_NGAN_hon():
    """speed phải giữ nguyên ý nghĩa: cao hơn = đọc nhanh hơn = ít thời gian hơn."""
    cham = thoi_luong_ep("anh chị cho em xin ít phút", REF, 0.90)
    nhanh = thoi_luong_ep("anh chị cho em xin ít phút", REF, 1.50)
    assert nhanh < cham


def test_o_speed_chuan_thi_ra_dung_nhip_chuan():
    cau = "anh chị cho em xin ít phút để em tư vấn"
    n = so_am_tiet(cau)
    d = thoi_luong_ep(cau, REF, SPEED_CHUAN)
    nhip = n / (d - REF) * 60
    # chia lại cho hệ số bù lặng thì phải về đúng mốc
    assert nhip == pytest.approx(NHIP_CHUAN_AM_TIET_PHUT / 1.11, rel=0.02)


@pytest.mark.parametrize("speed", [0.0, -1.0])
def test_speed_khong_hop_le_thi_de_F5_tu_lo(speed):
    assert thoi_luong_ep("anh chị cho em xin", REF, speed) is None


def test_doan_mau_khong_hop_le_thi_de_F5_tu_lo():
    assert thoi_luong_ep("anh chị cho em xin", 0.0, 1.20) is None


def test_cung_so_am_tiet_thi_cung_thoi_luong_du_khac_dau():
    """Chính là thứ cần chữa: mật độ dấu không được làm đổi thời lượng."""
    a = thoi_luong_ep("dạ vâng ạ em nghe", REF, 1.20)
    b = thoi_luong_ep("da vang a em nghe", REF, 1.20)
    assert a == pytest.approx(b)


def test_nguong_toi_thieu_dung_nhu_khai_bao():
    assert TOI_THIEU_AM_TIET_DE_EP == 3


# --- bỏ dấu câu khỏi chữ đưa vào F5 --------------------------------------

from backend.services.tts_service import bo_dau_cau_cho_f5  # noqa: E402


def test_bo_dau_cham_phay():
    assert bo_dau_cau_cho_f5("Dạ vâng ạ, em nghe.") == "Dạ vâng ạ em nghe"


@pytest.mark.parametrize("dau", [",", ".", ";", ":", "!", "?", "…"])
def test_bo_moi_loai_dau_gay_nghi(dau):
    assert dau not in bo_dau_cau_cho_f5(f"anh chị{dau} cho em xin")


def test_giu_nguyen_chu_va_dau_thanh():
    """Chỉ bỏ dấu CÂU. Dấu thanh mà mất là sai 1/3 số chữ - đã đo."""
    ra = bo_dau_cau_cho_f5("Lãi suất bảy phẩy chín phần trăm.")
    assert "Lãi suất bảy phẩy chín phần trăm" == ra


def test_khong_de_lai_khoang_trang_thua():
    assert bo_dau_cau_cho_f5("anh  chị ,  cho em") == "anh chị cho em"


def test_khong_dung_toi_dau_gach_va_so():
    """Số và dấu gạch phải nguyên: "22-60" bỏ đi là đọc sai khoảng tuổi."""
    assert bo_dau_cau_cho_f5("từ 22-60 tuổi") == "từ 22-60 tuổi"


def test_chuoi_rong():
    assert bo_dau_cau_cho_f5("") == ""
    assert bo_dau_cau_cho_f5("   ") == ""


def test_manh_chi_co_dau_thi_thanh_rong():
    assert bo_dau_cau_cho_f5(" . ") == ""
