"""Mở đầu lượt bằng "Dạ" một mình thì F5 dựng hỏng chính âm tiết đó.

Đo 13-08-2026 trên ĐÚNG đường cuộc gọi (cắt mảnh như pipeline -> ghép kèm nhịp
nghỉ -> kênh 8kHz), 12 câu gồm cả câu hỏi lẫn câu kể, hạt giống cố định nên số
tất định (`scripts/chot_mo_dau.py`):

    "Dạ ..."        chữ đầu  4/12   CER 6,6%   câu đạt 4/12
    "Dạ vâng ..."   chữ đầu  8/12   CER 3,1%   câu đạt 9/12
    bỏ hẳn          chữ đầu 11/12   CER 2,1%   câu đạt 9/12

Cái đắt không phải chữ "dạ" bị nghe nhầm - đó chỉ là tiếng lễ phép. Cái đắt là
hỏng LAN sang từ mang nội dung liền sau: "Dạ hạn mức vay" nghe ra "giảm mức vay",
mất chữ "hạn". Nối thành "Dạ vâng" thì "vâng" hứng đòn thay, nên câu đạt nhảy
4/12 lên 9/12.

Bản vá CŨ (chèn dấu phẩy sau "Dạ") không còn ăn - đo lại: có phẩy 0/6, bỏ phẩy
2/6, CER 10,2% so với 10,0%. Dấu phẩy không phải cơ chế.
"""
import pytest

from backend.pipeline.text_normalizer import normalize_for_tts


def test_noi_dai_da_dau_luot():
    assert normalize_for_tts("Dạ hạn mức vay ạ.").startswith("dạ vâng hạn mức")


def test_khong_noi_them_khi_da_du_dai():
    """'Dạ vâng' sẵn rồi thì để yên, không thành 'dạ vâng vâng'."""
    assert normalize_for_tts("Dạ vâng em hiểu ạ.").startswith("dạ vâng em hiểu")
    assert "vâng vâng" not in normalize_for_tts("Dạ vâng em hiểu ạ.")
    assert normalize_for_tts("Dạ thưa anh chị.").startswith("dạ thưa")


@pytest.mark.parametrize("sau", ["em", "anh", "chị"])
def test_da_em_da_anh_van_duoc_noi_dai(sau):
    """KHÔNG miễn trừ mấy từ này: 'dạ' vẫn đứng một mình ở vị trí mong manh.

    Ca thật đã hỏng: 'Dạ em là Dương, chuyên viên...' nghe ra 'em là rước...'.
    """
    assert normalize_for_tts(f"Dạ {sau} nói ạ.").startswith(f"dạ vâng {sau}")


def test_khong_dung_toi_da_giua_cau():
    """Chỗ hỏng chỉ ở âm tiết ĐẦU LƯỢT. 'Dạ' giữa câu đọc bình thường."""
    ra = normalize_for_tts("Anh nói dạ em nghe ạ.")
    assert "dạ vâng" not in ra


def test_khong_dung_toi_cau_khong_mo_bang_da():
    assert normalize_for_tts("Hạn mức vay ạ.").startswith("hạn mức")


def test_khong_con_chen_dau_phay_sau_da():
    """Bản vá cũ đã bị thay. Ai chèn lại phẩy thì phải đo lại - nó không ăn nữa."""
    assert not normalize_for_tts("Dạ hạn mức vay ạ.").startswith("dạ,")
