"""Câu đệm KHÔNG được kết bằng chữ "thì".

Người dùng 13-09-2026 sau cuộc gọi 5 phút `7db3f780`: *"Cả cái chỗ nó cứ 'thì'
ở cuối câu nối, xem có cách nào khắc phục triệt để"*. Kho tình huống thật trên
máy Win có 34/154 mẩu mở đầu kết bằng "thì,", và 15/27 lượt của cuộc gọi đó
phát câu đệm theo tình huống. Câu đệm phát xong rồi mới tới câu trả lời, giữa
hai bên luôn có một quãng chờ, nên chữ "thì" treo lơ lửng đúng chỗ đó.

Triệt để nghĩa là không chỉ sửa dữ liệu hôm nay: người vận hành gõ mẩu mới, bảng
hỏi-đáp, và câu đệm do LLM sinh đều đi qua cùng MỘT hàm chuẩn hoá.
"""
import pytest

from backend.pipeline.bo_thi_cuoi import bo_thi_cuoi


@pytest.mark.parametrize("vao, ra", [
    ("Dạ về lãi suất thì,", "Dạ về lãi suất,"),
    ("Dạ về hạn mức vay thì,", "Dạ về hạn mức vay,"),
    ("Dạ lãi suất bên em thì,", "Dạ về lãi suất bên em,"),
    ("Dạ hạn mức bên em thì,", "Dạ về hạn mức bên em,"),
    ("Dạ nếu anh chị trả sớm thì,", "Dạ về việc anh chị trả sớm,"),
    ("Dạ để tăng hạn mức thẻ thì,", "Dạ về việc tăng hạn mức thẻ,"),
    ("Dạ nếu chậm thanh toán thẻ thì,", "Dạ về việc chậm thanh toán thẻ,"),
    ("Dạ trường hợp này thì,", "Dạ về trường hợp này,"),
    ("Dạ hai loại thẻ này thì,", "Dạ về hai loại thẻ này,"),
    ("Dạ về trường hợp có nợ xấu thì,", "Dạ về trường hợp có nợ xấu,"),
    ("Dạ vâng, về lãi suất thì,", "Dạ vâng, về lãi suất,"),
    ("Lãi suất bên em thì,", "Về lãi suất bên em,"),
])
def test_bo_thi_va_giu_khung_ve(vao, ra):
    assert bo_thi_cuoi(vao) == ra


@pytest.mark.parametrize("cau", [
    "Dạ về lãi suất thì,", "Dạ nếu anh chị trả sớm thì,", "Dạ trường hợp này thì",
])
def test_khong_con_chu_thi_o_cuoi(cau):
    assert not bo_thi_cuoi(cau).rstrip(" ,.").endswith("thì")


def test_giu_nguyen_dau_cuoi():
    """Dấu phẩy cuối là luật của kho (thiếu phẩy F5 hạ giọng kết câu)."""
    assert bo_thi_cuoi("Dạ về hồ sơ thì") == "Dạ về hồ sơ"
    assert bo_thi_cuoi("Dạ về hồ sơ thì.") == "Dạ về hồ sơ."


@pytest.mark.parametrize("cau", [
    "Dạ vâng ạ,", "Dạ,", "Dạ em nói về hồ sơ,", "Dạ mức lãi hiện tại,",
    "Dạ nếu vay thì em tính giúp,",           # "thì" giữa câu: không đụng
    "Dạ về thời hạn vay bên em,", "",
])
def test_khong_co_thi_cuoi_thi_giu_nguyen_tung_byte(cau):
    """Vân tay clip tính theo chuỗi chữ. Đổi một byte là dựng lại clip."""
    assert bo_thi_cuoi(cau) == cau


def test_chi_con_le_phep():
    assert bo_thi_cuoi("Dạ thì,") == "Dạ,"


def test_khong_nham_chu_co_thi_ben_trong():
    """"thìa" hay "thịt" không phải chữ "thì"."""
    assert bo_thi_cuoi("Dạ về cái thìa,") == "Dạ về cái thìa,"
