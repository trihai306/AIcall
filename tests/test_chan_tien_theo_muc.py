"""Lưới chặn tiền phải đối chiếu theo MỤC tài liệu, và không được tha khi
ngữ cảnh rỗng số.

Hai lỗ hổng bắt được 05-09-2026 khi chạy lại cuộc gọi thật `4cd44fb7` bằng
chính giọng khách (`scripts/goi_lai_bang_giong_that.py`). Khách hỏi hạn mức,
máy nghe sai thành "hắn mừng được mời nhiều", AI trả lời:

    "Hạn mức vay tín chấp bên em từ 200 triệu đến ba trăm triệu ạ."

Tài liệu ghi 500 triệu. Sai, và LẶP LẠI cả 3 lần chạy độc lập.

LỖ HỔNG A - ngữ cảnh rỗng số thì lưới THA HẲN.
`ngu_canh` thật của lượt đó chỉ 63 ký tự ("ngân hàng nào dám cho vay quá nhiều
ạ / ợ trước hạn sau 3 năm") vì câu hỏi méo kéo RAG đi lạc. Không có số tiền nào
-> `hop_le` rỗng -> `if not hop_le: return text, None`. Số bịa đi thẳng ra loa.
Đây mới là đường mà câu "300 triệu" thật sự đi qua.

LỖ HỔNG B - có tài liệu thì lại lấy số của MỤC KHÁC.
Với ngữ cảnh đầy đủ, lưới chặn nhưng sửa "200 triệu" -> "ba trăm triệu", vì
`vay_tin_chap.md` có dòng ví dụ trả góp "Vay 300 triệu, 48 tháng" và 300 là số
GẦN NHẤT. Kết quả "từ ba trăm triệu đến ba trăm triệu" - vô nghĩa, mà vẫn sai
(hạn mức đúng là 500). Lưới chỉ hỏi "số này có trong tài liệu không", không hỏi
"số này thuộc MỤC nào".

Ràng buộc #2 trong docstring `chan_tien_sai` ("để nguyên kể cả khi nằm ở phần
ví dụ") vẫn ĐÚNG ở thời điểm nó được viết: câu dẫn ví dụ trả góp cần đúng con số
ví dụ. Nay siết lại CÓ ĐIỀU KIỆN - chỉ khi câu nêu rõ chủ đề và mục đó có số.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.pipeline.text_normalizer import CAU_KIEM_TRA_LAI, chan_tien_sai

# Tài liệu THẬT của vay tín chấp: hạn mức ở một mục, ví dụ trả góp ở mục khác.
TL_DAY_DU = """# Vay Tín Chấp Cá Nhân

## Lãi suất
- Lãi suất: từ 7.9%/năm

## Hạn mức
- Hạn mức: lên đến 500 triệu đồng

## Ví dụ khoản vay
- Vay 200 triệu, 36 tháng: trả hàng tháng khoảng 6.8 triệu
- Vay 300 triệu, 48 tháng: trả hàng tháng khoảng 8.2 triệu
"""

# Ngữ cảnh THẬT của lượt 6, đo bằng rag.retrieve(top_k=2) đúng như pipeline.
NC_RONG_SO = "ngân hàng nào dám cho vay quá nhiều ạ\n---\nợ trước hạn sau 3 năm"

CAU_LOI = ("Hạn mức vay tín chấp bên em từ 200 triệu đến ba trăm triệu ạ. "
           "Anh/chị cần vay số tiền bao nhiêu?")


# --- LỖ HỔNG A: ngữ cảnh không có số tiền nào -------------------------------

def test_chan_khi_ngu_canh_khong_co_so_tien():
    """Đúng câu đã tới tai khách trong cuộc gọi thật."""
    ra, sua = chan_tien_sai(CAU_LOI, NC_RONG_SO,
                            khach_noi="hắn mừng được mời nhiều")
    assert sua is not None, "phải chặn - đây là số bịa từ trí nhớ model"
    assert "200 triệu" not in ra and "ba trăm triệu" not in ra
    assert CAU_KIEM_TRA_LAI in ra


def test_ngu_canh_rong_nhung_so_do_KHACH_neu_thi_tha():
    """AI nhắc lại con số của khách là đúng, kể cả khi tài liệu rỗng."""
    ra, sua = chan_tien_sai("Dạ anh vay 80 triệu đúng không ạ.", NC_RONG_SO,
                            khach_noi="anh cần vay 80 triệu")
    assert sua is None and "80 triệu" in ra


@pytest.mark.parametrize("cau", [
    "Hồ sơ duyệt trong 24 giờ ạ.",
    "Anh sinh năm 1990 phải không ạ.",
    "Số điện thoại của em là 0912345678 ạ.",
    "Dạ em xin phép kiểm tra lại thông tin ạ.",
])
def test_ngu_canh_rong_khong_chan_cau_khong_co_tien(cau):
    """Chỉ chặn khi câu thật sự nêu SỐ TIỀN."""
    ra, sua = chan_tien_sai(cau, NC_RONG_SO, khach_noi="")
    assert sua is None, f"đã chặn nhầm: {ra}"
    assert ra == cau


# --- LỖ HỔNG B: đối chiếu theo mục ------------------------------------------

def test_han_muc_khong_duoc_lay_so_cua_muc_vi_du():
    """200/300 có thật trong tài liệu, nhưng ở mục VÍ DỤ - không phải hạn mức."""
    ra, sua = chan_tien_sai(CAU_LOI, TL_DAY_DU, khach_noi="")
    assert sua is not None, "phải sửa"
    assert "năm trăm triệu" in ra, f"phải lấy số của mục Hạn mức: {ra}"
    assert "ba trăm triệu" not in ra and "200 triệu" not in ra


def test_khong_de_lai_dai_trung_lap():
    """Thay xong không được ra "từ năm trăm triệu đến năm trăm triệu"."""
    ra, _ = chan_tien_sai(CAU_LOI, TL_DAY_DU, khach_noi="")
    assert "đến năm trăm triệu" not in ra, f"dải trùng chưa rút gọn: {ra}"


def test_cau_dan_vi_du_tra_gop_van_giu_nguyen_so():
    """Van an toàn: câu KHÔNG nói về hạn mức thì số ví dụ vẫn hợp lệ."""
    cau = "Vay 300 triệu trong 48 tháng thì trả hàng tháng khoảng 8.2 triệu ạ."
    ra, sua = chan_tien_sai(cau, TL_DAY_DU, khach_noi="")
    assert sua is None, f"đã siết oan câu dẫn ví dụ: {ra}"
    assert "300 triệu" in ra


def test_cau_han_muc_dung_so_thi_khong_dung_toi():
    ra, sua = chan_tien_sai("Hạn mức vay tín chấp lên đến 500 triệu đồng ạ.",
                            TL_DAY_DU, khach_noi="")
    assert sua is None and "500 triệu" in ra


def test_khong_nhan_ra_chu_de_thi_giu_hanh_vi_cu():
    """Van an toàn: câu không nêu chủ đề nào -> vẫn đối chiếu cả tài liệu."""
    cau = "Bên em hỗ trợ 300 triệu ạ."
    ra, sua = chan_tien_sai(cau, TL_DAY_DU, khach_noi="")
    assert sua is None, f"300 có trong tài liệu, không được chặn: {ra}"
