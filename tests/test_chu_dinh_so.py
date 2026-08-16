"""Chữ dính số, "đ" viết tắt, và "tháng MM/YYYY" - ba lớp làm chữ số lọt xuống F5.

Chữ số lọt qua chuẩn hoá gây ĐÚNG hai hậu quả như ca ngày tháng
(`test_doc_ngay_thang.py`): F5 đọc ra thứ vô nghĩa, VÀ `so_am_tiet` ước sai nên
`thoi_luong_ep` cấp sai thời lượng, làm mảnh đó lệch nhịp hẳn so với mảnh bên
cạnh - người dùng nghe ra là "đọc lúc nhanh lúc chậm".

Sau khi chữa ngày tháng còn 24/1385 lời AI dính. Soi cả 24 thì ra BA lớp:

    A. chữ dính số   "thu nhập15 triệu", "tối đa là10 tỷ", "cần từ22 - sáu mươi"
    B. "đ" viết tắt  "200.000đ" -> "hai trăm.000đ"   (bộ đọc số cần chữ "đồng")
    C. tháng/năm     "tháng 10/2023" -> "tháng mười HOẶC 2023"

Hai ca còn lại là LLM viết bậy thật ("7.9%/năm7.9%", "chúng tôi2.5%10.99%") -
chuẩn hoá không cứu được nội dung, nhưng sau khi tách chữ-số thì ít nhất phần
số cũng đọc ra thành số thay vì rơi nguyên chữ số xuống F5.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline.text_normalizer import normalize_for_tts


def khong_con_so(t: str) -> bool:
    return not re.search(r"\d", t)


# --- A. chữ dính số -----------------------------------------------------

@pytest.mark.parametrize("cau", [
    "Dạ theo thông tin anh chị cung cấp, với thu nhập15 triệu một tháng.",
    "Hạn mức vay lên đến 80% giá trị bất động sản, tối đa là10 tỷ đồng.",
    "Sản phẩm của chúng em, hạn mức từ10 triệu đến năm trăm triệu.",
    "Khoản vay hai mươi triệu, lãi suất là7.9% một năm.",
    "Bên em, khách hàng cần từ22 - 60 tuổi.",
])
def test_tach_chu_dinh_so(cau):
    ra = normalize_for_tts(cau)
    assert khong_con_so(ra), f"{cau!r} -> {ra!r}"


def test_khoang_gach_van_chay_sau_khi_tach():
    """"từ22 - 60 tuổi" phải thành "hai mươi hai ĐẾN sáu mươi", không phải trừ."""
    ra = normalize_for_tts("khách hàng cần từ22 - 60 tuổi")
    assert "đến" in ra, ra


# --- B. "đ" viết tắt của "đồng" -----------------------------------------

@pytest.mark.parametrize("cau,mong", [
    ("Phí thường niên là 200.000đ một năm.", "nghìn đồng"),
    ("Phí từ 400.000đ đến 800.000đ mỗi năm.", "nghìn đồng"),
])
def test_doc_dong_viet_tat(cau, mong):
    ra = normalize_for_tts(cau)
    assert khong_con_so(ra), f"{cau!r} -> {ra!r}"
    assert mong in ra, ra


def test_khong_dung_toi_chu_d_khong_dung_sau_so():
    """"đ" không đứng ngay sau chữ số thì để yên - đó là chữ thường."""
    ra = normalize_for_tts("anh đưa giấy tờ đi ạ")
    assert "đồng" not in ra, ra


# --- C. tháng MM/YYYY ---------------------------------------------------

def test_thang_nam_khong_thanh_hoac():
    ra = normalize_for_tts("Khoản này hết tháng 10/2023 ạ.")
    assert "hoặc" not in ra, ra
    assert khong_con_so(ra), ra
    assert "tháng mười" in ra


# --- KHÔNG được phá thứ đang chạy ---------------------------------------

def test_khong_tach_viet_tat_CO_CHU_SO():
    """Viết tắt chữ HOA có số không được tách: "F5" phải còn là một cụm."""
    ra = normalize_for_tts("mô hình F5 chạy tốt")
    assert "f 5" not in ra and "ép 5" not in ra, ra


@pytest.mark.parametrize("cau", [
    "hỗ trợ 24/7 ạ",
    "anh chuẩn bị CMND/CCCD ạ",
    "Anh/chị cho em hỏi",
    "lãi suất 7,9%/năm",
    "Khoản này đến hạn ngày 15/09/2026 ạ.",
])
def test_cac_luat_cu_van_nguyen(cau):
    """Bốn luật dấu "/" và luật ngày tháng vừa thêm phải không bị đụng."""
    ra = normalize_for_tts(cau)
    assert ra and ra.strip()
    if "24/7" in cau:      assert "trên bảy" in ra
    if "CMND" in cau:      assert "hoặc" in ra
    if "Anh/chị" in cau:   assert "anh chị" in ra and "hoặc" not in ra
    if "%/năm" in cau:     assert "một năm" in ra
    if "15/09" in cau:     assert khong_con_so(ra) and "hoặc" not in ra
