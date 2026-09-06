"""Khách nói con số mà QUÊN đơn vị thì AI nhắc lại kèm đơn vị vẫn là đúng.

VÌ SAO CÓ FILE NÀY. Hai cuộc gọi thật liên tiếp, cùng một hình dạng lỗi:

    `885911a9` khách: "ừ anh muốn vay bốn trăm"
               AI   : "...400 triệu..."   -> CHẶN TIỀN SAI, thay cả câu
    `ccb61c05` khách: "anh vay một lăm"
               AI   : "...150 triệu..."   -> CHẶN TIỀN SAI, thay cả câu

Ca đầu là CHẶN NHẦM, ca sau là CHẶN ĐÚNG - và khác biệt giữa chúng chính là
luật của file này.

`chan_tien_sai` đã có ràng buộc #1: *"Số khách vừa nói thì KHÔNG đụng - AI nhắc
lại con số của khách là đúng"*. Ràng buộc đó vẫn đúng; chỗ hỏng là cách cài nó.
`_tien_trong` chỉ nhận số ĐI KÈM ĐƠN VỊ ("bốn trăm triệu"), nên khách nói trống
đơn vị là lưới coi như khách chưa nêu số nào.

Luật: số TRẦN khách nói được phép ghép với đơn vị tiền, nhưng
  - phải ĐÚNG con số đó (400 -> "400 triệu" được; 400 -> "450 triệu" KHÔNG),
  - và không vượt số tiền lớn nhất trong tài liệu (thường là hạn mức).

Cái chặn thứ hai là thứ giữ cho bản sửa này khỏi thành lỗ hổng: không có nó thì
khách nói "anh vay trong một năm" là AI được phép nói "1 tỷ".
"""
import pytest

from backend.pipeline.text_normalizer import CAU_KIEM_TRA_LAI, chan_tien_sai

TAI_LIEU = ("Lãi suất: từ 7.9%/năm\nHạn mức: lên đến 500 triệu đồng\n"
            "Thời hạn: 12 - 60 tháng")


def _chan(cau, khach):
    return chan_tien_sai(cau, TAI_LIEU, khach_noi=khach)


# --- Ca chặn NHẦM, phải hết -----------------------------------------------

def test_khach_noi_bon_tram_thi_400_trieu_duoc_qua():
    ra, sua = _chan("Dạ anh muốn vay 400 triệu đồng ạ.", "ừ anh muốn vay bốn trăm")
    assert ra != CAU_KIEM_TRA_LAI, f"chặn nhầm số của chính khách: {sua}"
    assert "400 triệu" in ra


def test_khach_noi_bang_chu_so():
    ra, _ = _chan("Dạ anh muốn vay 400 triệu đồng ạ.", "anh vay 400 nhé")
    assert "400 triệu" in ra


def test_khach_noi_hai_tram_thi_200_trieu_duoc_qua():
    ra, _ = _chan("Dạ anh vay 200 triệu ạ.", "anh vay hai trăm thôi")
    assert "200 triệu" in ra


# --- Ca chặn ĐÚNG, phải giữ nguyên ---------------------------------------

def test_doi_con_so_thi_van_chan():
    """Cùng hình dạng ca `ccb61c05`: mô hình nói một con số KHÁC số khách nêu."""
    ra, sua = _chan("Dạ anh vay 450 triệu ạ.", "ừ anh muốn vay bốn trăm")
    assert ra == CAU_KIEM_TRA_LAI, "450 không phải con số khách nói"


def test_cum_chu_khong_doc_duoc_thi_khong_noi_long():
    """`một lăm` trong `ccb61c05` không đọc ra 15 bằng luật số tiếng Việt hiện
    có (`_chu_thanh_so` ra 6). KHÔNG đoán hộ khách: cụm nào không đọc chắc thì
    coi như khách chưa nêu số, và lượt đó vẫn bị chặn - hướng an toàn."""
    ra, _ = _chan("Dạ anh vay 150 triệu ạ.", "anh vay một lăm")
    assert ra == CAU_KIEM_TRA_LAI


def test_vuot_han_muc_thi_van_chan():
    """Không có mắt này thì 'anh vay trong một năm' cho phép AI nói '1 tỷ'."""
    ra, _ = _chan("Dạ hạn mức lên đến 1 tỷ đồng ạ.", "anh vay trong một năm")
    assert ra == CAU_KIEM_TRA_LAI


def test_so_khong_ai_neu_thi_van_chan():
    ra, _ = _chan("Dạ hạn mức bên em là 300 triệu ạ.", "cho anh hỏi lãi suất")
    assert ra == CAU_KIEM_TRA_LAI


def test_tai_lieu_khong_co_tien_thi_khong_noi_long():
    """Không có trần thì không có gì chặn số bịa - giữ hành vi cũ, chặt hơn."""
    ra, _ = _chan("Dạ anh vay 400 triệu ạ.", "anh muốn vay bốn trăm")
    ra2, _ = chan_tien_sai("Dạ anh vay 400 triệu ạ.", "Thời hạn 12 - 60 tháng",
                           khach_noi="anh muốn vay bốn trăm")
    assert ra2 == CAU_KIEM_TRA_LAI


# --- Không đụng các đường đang chạy đúng ---------------------------------

def test_so_trong_tai_lieu_van_qua_binh_thuong():
    ra, sua = _chan("Dạ hạn mức lên đến 500 triệu đồng ạ.", "hạn mức bao nhiêu")
    assert sua is None
    assert "500 triệu" in ra


def test_khach_noi_du_don_vi_van_qua():
    ra, sua = _chan("Dạ anh vay 400 triệu ạ.", "anh muốn vay bốn trăm triệu")
    assert sua is None


def test_cau_khong_neu_tien_thi_khong_dung_gi():
    cau = "Dạ thời hạn vay từ 12 đến 60 tháng ạ."
    ra, sua = _chan(cau, "anh vay bốn trăm")
    assert (ra, sua) == (cau, None)
