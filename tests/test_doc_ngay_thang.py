"""Ngày tháng phải đọc ra ngày tháng, không thành "hoặc".

Người dùng 16-08-2026: *"nó đọc lúc nhanh lúc chậm"*. Truy ra một nguồn cụ thể:
`15/09/2026` rơi vào luật "liệt kê" của `doc_dau_xien` và thành

    "ngày mười lăm HOẶC 09 HOẶC 2026"

Hai cái hỏng cùng lúc, và cái thứ hai mới là thứ người dùng nghe ra:

1. SAI NỘI DUNG - khách nghe một câu vô nghĩa, ngay chỗ nói về hạn trả nợ.
2. LỆCH NHỊP - `so_am_tiet` ước theo 1,5 âm tiết/chữ số, mà chuỗi "09 hoặc 2026"
   còn nguyên chữ số nên ước +64% so với thật. `thoi_luong_ep` cấp dư 64% thời
   lượng cho mảnh đó, và F5 tiêu chỗ thừa bằng cách đọc chậm hẳn lại.

Đo trên chính bộ 100 tệp đã xuất, nhịp phát âm:

    ai_001 "Em vẫn nghe anh chị ạ."              319 âm tiết/phút
    ai_002 "Dạ em vẫn nghe anh chị ạ."           309
    ai_003 "…đến hạn ngày 02/09/2026 ạ."         146   <- chậm hơn MỘT NỬA
    ai_010 "…là ngày 02/09…"                     163

Câu 9 âm tiết mà mất 3,83 giây. Đặt cạnh câu thường là nghe ra ngay.

Trên 1385 lời AI phân biệt trong `conversation_turns`: **45 câu (3,2%)** còn chữ
số sau chuẩn hoá, gần như toàn bộ là ngày tháng.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline.text_normalizer import normalize_for_tts


def khong_con_so(t: str) -> bool:
    return not re.search(r"\d", t)


# --- ngày tháng ---------------------------------------------------------

def test_ngay_day_du_khong_thanh_hoac():
    ra = normalize_for_tts("Khoản này đến hạn ngày 15/09/2026 ạ.")
    assert "hoặc" not in ra, f"dấu / vẫn thành 'hoặc': {ra!r}"
    assert khong_con_so(ra), f"còn chữ số chưa đọc được: {ra!r}"
    assert "tháng chín" in ra
    assert "mười lăm" in ra


def test_ngay_khong_co_nam():
    ra = normalize_for_tts("Hạn thanh toán của anh chị là ngày 02/09 ạ.")
    assert "hoặc" not in ra
    assert khong_con_so(ra), ra
    assert "tháng chín" in ra


def test_so_khong_dung_dau_khong_doc_thanh_khong():
    """"09" là tháng chín, không phải "không chín"."""
    ra = normalize_for_tts("đến hạn ngày 02/09/2026")
    assert "không chín" not in ra, ra


# --- KHÔNG được phá các luật dấu / đang chạy ----------------------------

def test_24_7_van_doc_lien():
    assert "trên bảy" in normalize_for_tts("hỗ trợ 24/7 ạ")


def test_liet_ke_van_la_hoac():
    assert "hoặc" in normalize_for_tts("anh chuẩn bị CMND/CCCD ạ")


def test_xung_ho_van_doc_lien():
    ra = normalize_for_tts("Anh/chị cho em hỏi")
    assert "anh chị" in ra and "hoặc" not in ra


def test_don_vi_van_la_mot_nam():
    ra = normalize_for_tts("lãi suất 7,9%/năm")
    assert "một năm" in ra and "hoặc" not in ra


# --- ca THẬT lấy từ conversation_turns ----------------------------------

@pytest.mark.parametrize("cau", [
    "Sản phẩm này sẽ hết hạn vào ngày 15/09/2026, thời gian còn lại là 21 tháng.",
    "Hạn cuối khoản vay của anh là ngày 15/09/2026.",
    "Khoản vay của anh/chị dự kiến hết hạn vào ngày 15/09/2026 ạ.",
    "Khoản này đến hạn ngày 02/09/2026 ạ.",
])
def test_cau_that_khong_con_chu_so(cau):
    ra = normalize_for_tts(cau)
    assert khong_con_so(ra), f"{cau!r} -> {ra!r}"
    assert "hoặc" not in ra or "CMND" in cau
