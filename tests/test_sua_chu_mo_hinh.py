"""Sửa chữ MÔ HÌNH viết sai, trước khi đọc ra.

Người dùng báo Lần 7: *"đọc sai 'lương' thì đọc là 'lượng'"*. Soi lại thì TTS
đọc ĐÚNG - chính văn bản đã ghi "chị nhà có lượng thì cho sao kê là được anh ạ"
(xem `Check giọng/Lan 7/3/Text.docx`), và máy nghe lại cũng ra "lượng". Chỗ sai
nằm ở VĂN BẢN, sửa ở TTS là sửa nhầm chỗ.

Khác `_SUA_NGHE_NHAM` bên `stt_service`: chỗ kia sửa lời KHÁCH bị nghe nhầm,
chỗ này sửa lời MÔ HÌNH viết ra.

HẸP một cách cố ý. "lượng" là từ thật và rất hay dùng - "số lượng", "chất
lượng", "khối lượng". Chỉ sửa khi nó đứng cạnh những từ mà "lượng" không thể
đúng. Dò gần đúng cả câu thì sớm muộn cũng sửa hỏng câu vốn đúng, mà lỗi đó khó
thấy hơn nhiều.
"""
import pytest

from backend.pipeline.text_normalizer import sua_chu_mo_hinh


@pytest.mark.parametrize("vao,ra", [
    ("Chị nhà có lượng thì cho sao kê là được anh ạ.",
     "Chị nhà có lương thì cho sao kê là được anh ạ."),
    ("Anh cho em xin sao kê lượng ba tháng ạ.",
     "Anh cho em xin sao kê lương ba tháng ạ."),
    ("Anh nhận lượng qua tài khoản nào ạ?",
     "Anh nhận lương qua tài khoản nào ạ?"),
    ("Lượng tháng của anh khoảng bao nhiêu ạ?",
     "Lương tháng của anh khoảng bao nhiêu ạ?"),
    ("Bảng lượng ba tháng gần nhất ạ.", "Bảng lương ba tháng gần nhất ạ."),
])
def test_sua_dung_cho(vao, ra):
    assert sua_chu_mo_hinh(vao) == ra


@pytest.mark.parametrize("cau", [
    "Số lượng hồ sơ trong tháng này ạ.",
    "Chất lượng dịch vụ bên em rất tốt ạ.",
    "Khối lượng công việc lớn ạ.",
    "Định lượng rủi ro của khoản vay ạ.",
    "Lượng khách hàng tăng mạnh ạ.",
    "Anh cho em xin bảng lương ba tháng ạ.",
])
def test_KHONG_dung_toi_cau_vot_dung(cau):
    """Ranh giới giữa sửa đúng và sửa hỏng.

    "lượng" là từ thật; chặn rộng là tự tay làm hỏng những câu vốn đúng, mà lỗi
    kiểu đó khó phát hiện hơn hẳn lỗi nó sinh ra để chữa.
    """
    assert sua_chu_mo_hinh(cau) == cau


def test_giu_hoa_thuong():
    """Mảnh có thể đứng đầu câu - đổi chữ mà mất chữ hoa là hỏng chỗ khác."""
    assert sua_chu_mo_hinh("Lượng tháng bao nhiêu ạ?").startswith("Lương")
    assert sua_chu_mo_hinh("lượng tháng bao nhiêu ạ?").startswith("lương")


def test_chuoi_rong_khong_no():
    assert sua_chu_mo_hinh("") == ""
