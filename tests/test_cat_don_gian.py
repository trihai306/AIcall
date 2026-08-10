"""Lối cắt MÁY MÓC: đủ 5 từ là giao, nối thẳng, không chèn nghỉ.

Người dùng chốt 2026-08-10: "bỏ hết logic tách đi, giờ dùng mỗi F5 tạo rồi nối
5 từ 1". Lý do: sau khi chữa hai hàm cắt lặng (85dd22a) họ vẫn nghe là chậm và
"đọc từng từ một".

Đây là lối ĐANG CHẠY. Lối cắt thông minh vẫn còn trong mã và được khoá bởi
`tests/test_cat_manh.py`.

Chỉ MỘT thứ được giữ lại từ lối cũ: chốt chặn cắt-giữa-token. Nó không phải luật
cắt mà là chống hỏng chữ - LLM đẩy "ngay" thành "ng" rồi "ay", bỏ nó ra thì
khách nghe đọc rời "ng" rồi "ay", đã xảy ra trên máy thật.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline import text_chunker
from backend.pipeline.text_chunker import (
    GIOI_HAN_TU_MANH, nhip_nghi_sau, tach_manh,
)


@pytest.fixture(autouse=True)
def cat_may_moc(monkeypatch):
    monkeypatch.setattr(text_chunker, "CAT_DON_GIAN", True)
    monkeypatch.setattr(text_chunker, "CHAN_CUM_SO", False)


def cat(van: str) -> list[str]:
    """Cắt y hệt vòng stream của pipeline.

    Token của Ollama mang dấu cách ở ĐẦU (" ngay") nên phải nối kiểu " " + tu
    chứ không strip - đó chính là cách đệm hình thành trên đường chạy thật.
    """
    ra, dem = [], ""
    for tu in van.split():
        dem = f"{dem} {tu}" if dem else tu
        while True:
            m, dem = tach_manh(dem)
            if m is None:
                break
            ra.append(m)
    if dem.strip():
        ra.append(dem.strip())
    return ra


# --- đúng 5 từ, không hơn không kém ------------------------------------

def test_cat_dung_so_tu():
    van = " ".join(f"tu{i}" for i in range(1, 21))
    manh = cat(van)
    assert [len(m.split()) for m in manh[:-1]] == [GIOI_HAN_TU_MANH] * 3


def test_khong_cat_som_o_dau_cau():
    """Khác hẳn lối cũ: dấu phẩy sau 3 từ KHÔNG còn là chỗ cắt."""
    manh = cat("Dạ vâng ạ, em xin phép trả lời anh ngay bây giờ")
    assert manh[0] == "Dạ vâng ạ, em xin"


def test_khong_ne_cum_so():
    """Chấp nhận bẻ cụm số - đây là cái GIÁ của lối máy móc, ghi lại cho rõ."""
    manh = cat("Hạn mức của anh là hai mươi triệu đồng một tháng nhé")
    assert manh[0] == "Hạn mức của anh là"
    assert manh[1].startswith("hai mươi triệu")


def test_giu_lai_chan_cum_so_neu_bat_co(monkeypatch):
    """Bật CHAN_CUM_SO thì lùi chỗ cắt cho tới khi hết cụm số."""
    van = "Hạn mức của anh khoảng hai mươi triệu đồng một tháng nhé"
    assert cat(van)[0] == "Hạn mức của anh khoảng"      # tắt: bẻ ngay sau "khoảng"
    monkeypatch.setattr(text_chunker, "CHAN_CUM_SO", True)
    # Lùi tới khi từ cuối KHÔNG còn là từ số: "triệu" vẫn là, "đồng" thì hết.
    assert cat(van)[0] == "Hạn mức của anh khoảng hai mươi triệu đồng"


# --- chống hỏng chữ vẫn phải còn ---------------------------------------

def test_khong_cat_giua_token():
    """LLM đẩy 'ngay' thành 'ng' rồi 'ay' - không được giao khi từ chưa trọn.

    Đệm có đúng 5 mẩu nhưng mẩu cuối chưa có gì đứng sau nó, nên chỉ 4 mẩu là
    chắc trọn - chưa đủ 5, phải đợi.
    """
    m, con = tach_manh("em xin phép báo ng")
    assert m is None and con == "em xin phép báo ng"


def test_giao_ngay_khi_tu_cuoi_da_tron():
    """Có dấu cách ở cuối thì mẩu thứ 5 cũng đã trọn - giao trọn 5 từ."""
    m, con = tach_manh("em xin phép báo ngay ")
    assert m == "em xin phép báo ngay" and con == ""


# --- không chèn nhịp nghỉ ----------------------------------------------

@pytest.mark.parametrize("chu", [
    "câu này kết bằng dấu chấm.",
    "câu này kết bằng dấu phẩy,",
    "câu này cắt giữa chừng không dấu",
])
def test_khong_chen_nghi_o_bat_ky_ranh_gioi_nao(chu):
    assert nhip_nghi_sau(chu) == 0.0


# --- ca biên ------------------------------------------------------------

def test_dem_rong_va_thieu_chu():
    assert tach_manh("") == (None, "")
    assert tach_manh("một hai ba ") == (None, "một hai ba ")


def test_khong_mat_chu_nao():
    van = "Dạ em xin phép kiểm tra lại hồ sơ và báo anh chị ngay trong hôm nay ạ"
    assert " ".join(cat(van)).split() == van.split()
