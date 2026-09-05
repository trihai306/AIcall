"""Sửa lời KHÁCH bị nghe nhầm, sau STT và trước khi đưa cho LLM.

Khác `sua_chu_mo_hinh` bên `text_normalizer`: chỗ kia sửa chữ MÔ HÌNH viết ra,
chỗ này sửa chữ MÁY NGHE ra từ tiếng khách.

Các mục mới thêm 05-09-2026 đến từ đo trên tiếng khách THẬT
(`scripts/do_xu_ly_tieng_khach.py`, 7 lượt của cuộc gọi 4cd44fb7 đã qua
GSM/AMR). Cùng một từ "hạn mức" hỏng theo cùng một kiểu ở **7/7 cách xử lý âm
thanh** — lọc nhiễu, cổng phổ, chuẩn hoá mức đều không cứu được:

    "hạn mức vay tín chấp bao nhiêu" -> `lợn sơn vay tín chấp bao nhiêu`
    "hạn mức được bao nhiêu"         -> `hắn mừng được mừng nhiều`
    "hạn mức được bao nhiêu"         -> `sẵn mức được bao nhiêu`

Ổn định như thế nghĩa là tiếng không mang đủ thông tin, không phải nhiễu che
mất - nên chữa ở tầng CHỮ là đúng chỗ, và cũng là chỗ rẻ nhất.

HẸP một cách cố ý, y như bảng gốc: chỉ sửa đúng cụm đã thấy. Dò gần đúng cả câu
thì sớm muộn cũng sửa hỏng một câu vốn đúng, mà lỗi đó khó thấy hơn nhiều.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.services.stt_service import _sua_nghe_nham


# --- các mục đã có từ trước, neo lại để đừng ai gỡ nhầm -------------------
@pytest.mark.parametrize("vao, ra", [
    ("lãi xuất bao nhiêu", "lãi suất bao nhiêu"),
    ("lại suất vay", "lãi suất vay"),
    ("cần cẩn cước công dân", "cần căn cước công dân"),
    ("vay tính chấp", "vay tín chấp"),
    ("hạng mức bao nhiêu", "hạn mức bao nhiêu"),
])
def test_muc_cu_van_chay(vao, ra):
    assert _sua_nghe_nham(vao) == ra


# --- ba mục mới, quan sát trên tiếng khách thật ---------------------------
@pytest.mark.parametrize("vao, ra", [
    # đo được 7/7 cách xử lý âm thanh đều cho ra chuỗi này
    ("lợn sơn vay tín chấp bao nhiêu", "hạn mức vay tín chấp bao nhiêu"),
    ("lớn sơn vay tín chấp bao nhiêu", "hạn mức vay tín chấp bao nhiêu"),
    ("hắn mừng được bao nhiêu", "hạn mức được bao nhiêu"),
    ("hắn mừng được mừng nhiều", "hạn mức được mừng nhiều"),
    ("sẵn mức được bao nhiêu", "hạn mức được bao nhiêu"),
])
def test_muc_moi_tu_tieng_khach_that(vao, ra):
    assert _sua_nghe_nham(vao) == ra


# --- CHỐT CHẶN: không được đụng vào câu vốn đúng --------------------------
#
# Mỗi mục dưới đây là một câu tiếng Việt THẬT chứa đúng cụm bị nhắm tới. Bảng
# sửa mà đụng vào đây là nó đã quá rộng.
@pytest.mark.parametrize("cau", [
    # "hắn mừng" là cụm có thật - chỉ được sửa khi theo sau là "được"
    "hắn mừng lắm khi nghe tin",
    "thấy hắn mừng ra mặt",
    # "có sẵn mức" là cách nói có thật trong bán hàng
    "bên em có sẵn mức giá tốt cho anh",
    "công ty có sẵn mức chiết khấu riêng",
    # "tính chất" là từ thật khi KHÔNG đứng sau "vay"
    "tính chất của khoản vay này khác",
    # "lợn" và "sơn" đứng riêng thì không được đụng
    "giá thịt lợn hôm nay bao nhiêu",
    "anh làm nghề sơn nhà",
])
def test_KHONG_dung_toi_cau_vot_dung(cau):
    assert _sua_nghe_nham(cau) == cau


def test_chuoi_rong_khong_no():
    assert _sua_nghe_nham("") == ""


def test_sua_duoc_nhieu_cum_trong_mot_cau():
    assert _sua_nghe_nham("lãi xuất với hạng mức thế nào") == "lãi suất với hạn mức thế nào"


# --- Mục thêm 05-09-2026 (chiều), tìm bằng cách ĐÀO 2086 lượt phiên âm thật ---
#
# `scripts/soi_cum_hong.py`: đếm cụm 2 từ trong toàn bộ lượt do STT sinh (lọc
# `content[0].islower()` để bỏ lượt gõ tay khi test), rồi so với từ khoá nghiệp
# vụ. Một cụm VÔ NGHĨA xuất hiện nhiều lần qua nhiều phiên thì gần như chắc chắn
# là lỗi máy nghe, không phải lời khách - biết được điều đó mà KHÔNG cần nghe.
#
#     "tính chóp"  18 lần
#     "tính chớp"   4 lần
#
# Ngữ cảnh thật xác nhận: "vay tính chóp thì cần những giấy tờ gì", "lãi suất
# vay tính chóp bên em bao nhiêu một năm".
#
# ĐÃ LOẠI một ứng viên vì xem ngữ cảnh: "giao ngân" (4 lần) trông như "giải
# ngân", nhưng câu thật là "sổ đỏ có phải GIAO NGÂN HÀNG không" - đúng rồi. Thêm
# luật cho nó là tự tay làm hỏng một câu vốn đúng.

@pytest.mark.parametrize("vao,ra", [
    ("vay tính chóp thì cần những giấy tờ gì",
     "vay tín chấp thì cần những giấy tờ gì"),
    ("lãi suất vay tính chóp bên em bao nhiêu một năm",
     "lãi suất vay tín chấp bên em bao nhiêu một năm"),
    ("lãi suất vay tính chớp bên em bao nhiêu một năm",
     "lãi suất vay tín chấp bên em bao nhiêu một năm"),
    ("vậy tính chóp thì cần những giấy tờ gì",
     "vậy tín chấp thì cần những giấy tờ gì"),
])
def test_tinh_chop_thanh_tin_chap(vao, ra):
    assert _sua_nghe_nham(vao) == ra


@pytest.mark.parametrize("cau", [
    "sổ đỏ có phải giao ngân hàng không",   # ứng viên đã loại - câu này ĐÚNG
    "chóp núi cao quá",
    "anh tính chi phí giúp em",
])
def test_KHONG_dung_toi_cau_dung_gan_giong(cau):
    assert _sua_nghe_nham(cau) == cau
