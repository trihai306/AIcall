"""Tên ngân hàng kiểu HOA + "Bank" phải được đánh vần, không giao thẳng cho F5.

`_ACRONYM_RE` (`\\b[A-Z]{2,}\\b`) trượt "VPBank" vì sau "VP" là "ank" - vẫn là ký
tự từ nên không có ranh giới từ. Chuỗi Latin xuống tới F5 thì nó tự đoán cách
đọc, mỗi lần một kiểu: đo 12-08-2026 cho STT nghe lại 10 lần sinh -> sai 10/10
("vấp banh", "phập banh", "vạc bánh", "việt anh"...).

Đây là lỗi chiếm phần lớn trong toàn bộ bản ghi khách gửi về.
"""
import pytest

from backend.pipeline.text_normalizer import normalize_for_tts


@pytest.mark.parametrize("ten,doc", [
    # VPBank có ngoại lệ riêng: người dùng chốt "vê BÊ banh" (13-08-2026).
    ("VPBank", "vê bê banh"),
    ("TPBank", "tê pê banh"),
    ("MBBank", "em bê banh"),
    ("HDBank", "hát dê banh"),
    ("ABBank", "a bê banh"),
])
def test_ten_ngan_hang_duoc_danh_van(ten, doc):
    assert normalize_for_tts(f"tại ngân hàng {ten} ạ") == f"tại ngân hàng {doc} ạ"


def test_khong_con_chuoi_latin_lot_xuong_f5():
    """Điều kiện thật sự cần: không còn cụm chữ Latin nào không đọc được."""
    ra = normalize_for_tts("Em làm tại ngân hàng VPBank ạ.")
    assert "vpbank" not in ra
    assert "bank" not in ra


def test_ten_thuan_viet_khong_bi_dung_toi():
    assert normalize_for_tts("ngân hàng Quân đội") == "ngân hàng quân đội"
    assert normalize_for_tts("ngân hàng Á Châu") == "ngân hàng á châu"


def test_ten_doc_lien_khong_bi_danh_van():
    """"Vietcombank"/"Techcombank" đọc liền được, không có cụm HOA nào."""
    assert normalize_for_tts("ngân hàng Vietcombank") == "ngân hàng vietcombank"
    assert normalize_for_tts("ngân hàng Techcombank") == "ngân hàng techcombank"


def test_viet_tat_thuan_hoa_van_chay_luat_cu():
    """Không được làm hỏng đường cũ: VIB, ABC vẫn đánh vần như trước."""
    assert normalize_for_tts("ngân hàng VIB") == "ngân hàng vê i bê"
    assert normalize_for_tts("ngân hàng ABC") == "ngân hàng a bê xê"


def test_tu_thuong_khong_bi_nham():
    """"bank" viết thường giữa câu không phải tên ngân hàng."""
    assert "ben" not in normalize_for_tts("mở internet banking cho anh")


# --- dấu câu lặp ---------------------------------------------------------

@pytest.mark.parametrize("vao,ra", [
    ("bên em...... Không biết", "bên em. không biết"),
    ("bên em.. Không biết", "bên em. không biết"),
    ("thế nào,,, anh nhé", "thế nào, anh nhé"),
    ("thật không??? em hỏi", "thật không? em hỏi"),
])
def test_gop_dau_cau_lap(vao, ra):
    """F5 cấp thời lượng theo BYTE - 6 dấu chấm là 6 ký tự không có âm, model
    lấp chỗ thừa bằng cách kéo giãn từ quanh đó rồi bịa thêm âm ở cuối."""
    assert normalize_for_tts(vao) == ra


def test_dau_don_khong_bi_dung_toi():
    """Dấu đứng một mình thì để yên, chỉ dấu LẶP mới bị gộp.

    Câu này từng kỳ vọng "dạ, vâng ạ." vì bản vá cũ chèn phẩy ngay sau "Dạ".
    Nay quy tắc chỉ ra tay khi phía sau còn ít nhất hai từ - ở đây chỉ có "ạ."
    nên không có gì để bảo vệ, câu giữ nguyên. Xem `tests/test_da_dau_luot.py`.
    """
    assert normalize_for_tts("Dạ vâng ạ. Em nghe đây.") == "dạ vâng ạ. em nghe đây."


def test_khong_gop_dau_phan_cach_nghin():
    """"142.500.000" - các dấu chấm KHÔNG liền nhau nên không phải dấu lặp."""
    ra = normalize_for_tts("dư nợ 142.500.000 đồng")
    assert "142" not in ra or "." not in ra.split("đồng")[0].replace("142.500.000", "")
