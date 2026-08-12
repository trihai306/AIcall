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
    HE_SO_BU_LANG, NHIP_CHUAN_AM_TIET_PHUT, SPEED_CHUAN,
    TOI_THIEU_AM_TIET_DE_EP, so_am_tiet, thoi_luong_ep,
)

REF = 5.45      # đoạn mẫu đang dùng, giây

# SÀN PHÁT ÂM của F5 với giọng đang chạy, đo được chứ không chọn.
#
# Cấp thời lượng nhiều hơn thứ F5 cần thì nó KHÔNG đọc chậm lại tương ứng - nó
# đọc gần như cùng tốc rồi lấy IM LẶNG tiêu chỗ thừa. Quét hệ số cấp trên mảnh
# 20 từ, 3 lượt mỗi mức (scripts/chan_doan_manh_dai.py):
#
#   hệ số  cấp dư   quãng lặng F5 tự bịa   còn sót sau khi lọc   nhịp phát âm
#   0.85     16%       2 quãng /  820ms      14 quãng / 3460ms     341
#   1.11     34%      12 quãng / 6080ms      34 quãng / 6820ms     297
#
# Cấp dư gấp đôi thì số quãng lặng bịa ra gấp SÁU. Đó chính là thứ người dùng
# nghe thành "đọc bị cách ra dù không có dấu chấm phẩy" và "đoạn sau đọc giãn".
#
# Nhịp phát âm chỉ nhích từ 297 lên 341 khi cắt bớt 24% thời lượng - tức F5 gần
# như không chịu đọc chậm hơn ~300 âm tiết/phút. Dưới mốc đó, mọi giây cấp thêm
# đều biến thành lỗ hổng giữa câu.
SAN_PHAT_AM_AM_TIET_PHUT = 300.0
# Cấp dư bao nhiêu thì còn an toàn. 16% đo ra 2 quãng bịa, 34% đo ra 12.
DU_TOI_DA = 1.25


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
    # chia lại cho hệ số cấp thì phải về đúng mốc
    assert nhip == pytest.approx(NHIP_CHUAN_AM_TIET_PHUT / HE_SO_BU_LANG, rel=0.02)


# --- không được cấp thời lượng dưới sàn phát âm của F5 -------------------
#
# Đây là lỗi đã bắt được ngoài đời: khách nghe "đọc bị cách ra dù không có dấu
# chấm phẩy", "đoạn sau đọc giãn giữa các từ", "lắp từ", "đọc sai từ". Cả bốn
# đều là MỘT nguyên nhân - cấp thừa thời lượng rồi F5 lấy im lặng tiêu chỗ thừa.

@pytest.mark.parametrize("speed", [0.98, 1.10, SPEED_CHUAN])
def test_khong_cap_cham_hon_san_phat_am(speed):
    """Nhịp CẤP RA phải nằm trong tầm F5 đọc được, không chậm hơn.

    Chậm hơn sàn thì F5 không đọc chậm lại - nó chèn quãng lặng vào giữa câu.
    """
    cau = ("bên em đang có chương trình vay tín chấp anh không cần thế chấp gì "
           "hết lãi suất hiện tại từ bảy phẩy chín phần trăm")
    n = so_am_tiet(cau)
    d = thoi_luong_ep(cau, REF, speed)
    nhip_cap = n / (d - REF) * 60
    assert nhip_cap >= SAN_PHAT_AM_AM_TIET_PHUT / DU_TOI_DA, (
        f"cấp {nhip_cap:.0f} âm tiết/phút ở speed {speed} - chậm hơn sàn phát âm "
        f"{SAN_PHAT_AM_AM_TIET_PHUT:.0f} quá {DU_TOI_DA:.0%}, F5 sẽ độn im lặng"
    )


def test_manh_dai_khong_duoc_cap_du_nhieu_hon_manh_ngan():
    """Cấp dư phải tỉ lệ, không được dồn cục vào mảnh dài.

    Mảnh 5 từ có 17 mép mảnh để `trim_silence` nuốt chỗ thừa; mảnh 20 từ chỉ có
    5. Cùng một tỉ lệ dư, mảnh to đẩy phần thừa vào GIỮA câu.
    """
    ngan = "anh chị cho em xin ít phút"
    dai = " ".join([ngan] * 4)
    r_ngan = so_am_tiet(ngan) / (thoi_luong_ep(ngan, REF, 1.20) - REF)
    r_dai = so_am_tiet(dai) / (thoi_luong_ep(dai, REF, 1.20) - REF)
    assert r_ngan == pytest.approx(r_dai, rel=0.01)


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

import backend.services.tts_service as _tts                             # noqa: E402
from backend.services.tts_service import bo_dau_cau_cho_f5              # noqa: E402

# Bản cũ chưa có cờ này - lúc đó hàm luôn bỏ dấu.
BO_DAU_CAU = getattr(_tts, "BO_DAU_CAU", True)

# `BO_DAU_CAU` tắt từ 2026-08-11 (cùng lúc với `CAT_THEO_CAU`): cắt theo nguyên
# câu thì dấu nằm đúng chỗ của nó, phải để dấu tới được F5 cho nó tự nghỉ.
# Test viết theo cờ chứ không theo một chiều, để bật lại cờ là bộ test vẫn đúng.
bo_dau = pytest.mark.skipif(not BO_DAU_CAU, reason="BO_DAU_CAU đang tắt")
giu_dau = pytest.mark.skipif(BO_DAU_CAU, reason="BO_DAU_CAU đang bật")


@giu_dau
def test_cho_tat_thi_giu_nguyen_dau_cau():
    """Tắt cờ thì hàm phải là no-op, kể cả khoảng trắng thừa cũng không đụng.

    Đây là đường đang chạy. Xoá dấu thì F5 không còn mốc nào để nghỉ - đo được
    2 quãng lặng trong 13,8 giây, còn người thật 22 quãng trong 16 giây.
    """
    assert bo_dau_cau_cho_f5("Dạ vâng ạ, em nghe.") == "Dạ vâng ạ, em nghe."
    assert bo_dau_cau_cho_f5("anh  chị ,  cho em") == "anh  chị ,  cho em"


@bo_dau
def test_bo_dau_cham_phay():
    assert bo_dau_cau_cho_f5("Dạ vâng ạ, em nghe.") == "Dạ vâng ạ em nghe"


@bo_dau
@pytest.mark.parametrize("dau", [",", ".", ";", ":", "!", "?", "…"])
def test_bo_moi_loai_dau_gay_nghi(dau):
    assert dau not in bo_dau_cau_cho_f5(f"anh chị{dau} cho em xin")


@bo_dau
def test_giu_nguyen_chu_va_dau_thanh():
    """Chỉ bỏ dấu CÂU. Dấu thanh mà mất là sai 1/3 số chữ - đã đo."""
    ra = bo_dau_cau_cho_f5("Lãi suất bảy phẩy chín phần trăm.")
    assert "Lãi suất bảy phẩy chín phần trăm" == ra


@bo_dau
def test_khong_de_lai_khoang_trang_thua():
    assert bo_dau_cau_cho_f5("anh  chị ,  cho em") == "anh chị cho em"


@bo_dau
def test_manh_chi_co_dau_thi_thanh_rong():
    assert bo_dau_cau_cho_f5(" . ") == ""


def test_khong_dung_toi_dau_gach_va_so():
    """Số và dấu gạch phải nguyên: "22-60" bỏ đi là đọc sai khoảng tuổi."""
    assert bo_dau_cau_cho_f5("từ 22-60 tuổi") == "từ 22-60 tuổi"


def test_chuoi_rong_bo_dau():
    assert bo_dau_cau_cho_f5("") == ""
