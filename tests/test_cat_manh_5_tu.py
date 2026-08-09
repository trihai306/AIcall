"""Luật cắt mảnh: cứ 5 từ một, trừ hai chỗ không được cắt.

Đổi từ "cắt ở dấu câu" ngày 2026-08-09 vì mảnh dài làm F5 tự bịa quãng dừng giữa
câu — 19 quãng 300-1600ms trong bản ghi hội thoại thật 111 giây. Đo đối chứng
cùng đoạn văn, cùng lúc Ollama đang sinh token:

    dấu câu (cũ)  6 mảnh   1 quãng lặng > 250ms
    5 từ         18 mảnh   0
    3 từ         29 mảnh   3, kèm 21 lần sinh không kịp phát

Test này khoá cả ba thứ: đúng 5 từ, không bẻ cụm số, không xé số phân cách nghìn.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline.text_chunker import (
    GIOI_HAN_TU_MANH, nhip_nghi_sau, tach_manh,
)


def cat(van: str, first: bool = True) -> list[str]:
    """Cắt y hệt vòng stream của pipeline.

    Token của Ollama mang dấu cách ở ĐẦU (" ngay"), nên phải nối kiểu " " + tu
    chứ không strip - đó chính là cách đệm hình thành trên đường chạy thật.
    """
    ra, dem = [], ""
    for t in van.split():
        dem += " " + t
        manh, dem = tach_manh(dem, first_chunk=(first and not ra))
        if manh:
            ra.append(manh)
    if dem.strip():
        ra.append(dem.strip())
    return ra


def du(dem: str) -> bool:
    """Đã tách được mảnh chưa. Thêm dấu cách cuối = token sau đã bắt đầu."""
    return tach_manh(dem + " ")[0] is not None


# --- cắt đúng 5 từ -------------------------------------------------------

def test_cat_dung_moc_5_tu():
    assert GIOI_HAN_TU_MANH == 5
    m = cat("anh chị vui lòng chờ em chút xíu nhé ạ")
    assert m == ["anh chị vui lòng chờ", "em chút xíu nhé ạ"]


def test_chua_du_5_tu_thi_chua_cat():
    assert du("anh chị cho em") is False
    assert du("anh chị cho em xin") is True


def test_manh_dau_khong_con_luat_rieng():
    """Trước đây mảnh đầu cắt ở 12 từ. Nay mọi mảnh đều 5 từ."""
    van = "anh chị vui lòng chờ em một chút để em tra cứu"
    assert cat(van, first=True) == cat(van, first=False)


def test_du_thi_gom_vao_manh_cuoi():
    m = cat("anh chị cho em xin ít phút")
    assert m[0] == "anh chị cho em xin"
    assert " ".join(m) == "anh chị cho em xin ít phút"


# --- không bẻ đôi cụm số -------------------------------------------------

@pytest.mark.parametrize("dem", [
    "hạn mức tối đa năm",          # "năm" mở đầu "năm trăm triệu"
    "lãi suất chỉ có bảy",         # "bảy" mở đầu "bảy phẩy chín"
    "vay được tối đa khoảng",      # "khoảng" đứng trước số
    "thời hạn vay lên tới",        # "tới" đứng trước số
    "lãi suất là sáu phần",        # "phần" mở đầu "phần trăm"
])
def test_khong_cat_giua_cum_so(dem):
    assert du(dem) is False, f"đã cắt sau {dem.split()[-1]!r}"


def test_cum_so_dong_thi_cat_duoc():
    """Có dấu câu ở cuối nghĩa là cụm đã đóng."""
    assert du("bảy phẩy chín phần trăm,") is True


def test_cum_so_khong_giu_buffer_mai():
    """Chuỗi toàn từ số phải được giao khi quá trần, không kẹt vô hạn."""
    m = cat("một hai ba bốn năm sáu bảy tám chín mười mười một mười hai")
    assert len(m) >= 2
    assert all(len(x.split()) <= 12 for x in m)


# --- không xé số phân cách nghìn ----------------------------------------

def test_khong_xe_so_phan_cach_nghin():
    """"142." là dấu phân cách nghìn, không phải hết câu.

    Lỗi thật bắt được 2026-08-06: khách nghe "một trăm bốn mươi hai" rồi mới tới
    "năm trăm nghìn". Ca nguy hiểm là khi mốc 5 từ rơi ĐÚNG ngay sau "142.".
    """
    assert du("anh ơi dư nợ 142.") is False


def test_moc_5_tu_khong_cham_vao_so_thi_cat_binh_thuong():
    """Số nằm ở từ thứ 6 thì mốc 5 từ không đụng tới nó - cứ cắt."""
    assert du("dư nợ của anh là 142.") is True


def test_so_da_tron_thi_cat_duoc():
    assert du("dư nợ của anh 142.500.000") is True


# --- nhịp nghỉ vẫn hoạt động --------------------------------------------

def test_nhip_nghi_theo_dau_cuoi_manh():
    assert nhip_nghi_sau("em xin phép hỏi ạ.") > nhip_nghi_sau("em xin phép hỏi ạ,")
    assert nhip_nghi_sau("cắt giữa chừng không dấu") == 0.0


def test_dem_rong_khong_cat():
    assert tach_manh("")[0] is None
    assert tach_manh("   ")[0] is None
