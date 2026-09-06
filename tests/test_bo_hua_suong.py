"""Bỏ câu hứa "em sẽ kiểm tra rồi báo lại" khi lượt ĐÃ nói ra nội dung thật.

VÌ SAO CÓ FILE NÀY. Cuộc gọi thật `99ee5360` (05-09-2026), hai lượt liên tiếp:

    "Em hiểu rồi ạ. Anh cần em kiểm tra mã doanh thu cho hợp đồng của anh, đúng
     không? Em sẽ kiểm tra thông tin cho anh ngay."
    "... có doanh thu là 142.500.000 đồng ạ. Dạ chính xác nhất."

Rồi AI IM 6 giây và khách cúp máy (`dumpsys telecom`: REMOTE/NORMAL). Khách nghe
"em sẽ kiểm tra rồi báo" thì ngồi chờ một cuộc gọi lại không bao giờ tới - trong
khi câu trả lời đã có ngay trước đó.

`bo_cau_lui_thua` đã có sẵn nhưng dùng `re.match`, tức CHỈ cắt khi câu lùi đứng
ĐẦU. Ở đây nó đứng CUỐI nên lọt.

Vì sao phải giữ trạng thái theo LƯỢT chứ không xét từng mảnh: bộ cắt mảnh chia
câu trả lời ra nhiều mảnh rồi đẩy xuống TTS từng cái. Mảnh chứa câu hứa thường
KHÔNG chứa nội dung nào khác, nên nhìn trong phạm vi một mảnh thì không phân biệt
được "hứa thừa sau khi đã trả lời" với "thật sự không tra được".
"""
import pytest

from backend.pipeline.text_normalizer import BoHuaSuong


def chay(*manh: str) -> list[str]:
    """Chạy một lượt qua bộ lọc, trả về các mảnh còn lại (bỏ mảnh rỗng)."""
    bo = BoHuaSuong()
    return [r for r in (bo(m) for m in manh) if r.strip()]


# --- Đã trả lời rồi thì câu hứa phía sau là thừa --------------------------

def test_cat_cau_hua_sau_khi_da_tra_loi_trong_cung_mot_manh():
    ra = chay("Dạ anh chị đang còn dư nợ 142.500.000 đồng ạ. Em sẽ kiểm tra thông tin cho anh ngay.")
    assert len(ra) == 1
    assert "142.500.000" in ra[0]
    assert "kiểm tra" not in ra[0].lower()


def test_cat_cau_hua_khi_no_nam_o_manh_rieng():
    """Đúng hình dạng của cuộc gọi thật: nội dung ở mảnh trước, hứa ở mảnh sau."""
    ra = chay("Dạ anh chị đang còn dư nợ 142.500.000 đồng ạ.",
              "Em sẽ kiểm tra thông tin cho anh ngay.")
    assert ra == ["Dạ anh chị đang còn dư nợ 142.500.000 đồng ạ."]


def test_cat_cau_hua_sau_cau_hoi_lai_co_noi_dung():
    ra = chay("Em hiểu rồi ạ. Anh cần em kiểm tra mã hợp đồng của anh, đúng không?",
              "Em sẽ kiểm tra thông tin cho anh ngay.")
    assert len(ra) == 1
    assert "đúng không" in ra[0]


# --- Không có nội dung thì câu hứa CHÍNH LÀ câu trả lời, phải giữ ---------

def test_giu_khi_ca_luot_chi_co_cau_hua():
    """Mô hình thật sự không tra được -> bỏ đi là để lại lượt rỗng, tệ hơn hẳn."""
    ra = chay("Dạ em xin phép kiểm tra lại rồi báo lại anh chị ngay ạ.")
    assert ra == ["Dạ em xin phép kiểm tra lại rồi báo lại anh chị ngay ạ."]


def test_giu_cau_hua_dung_dau_khi_phia_sau_chua_co_gi():
    ra = chay("Em sẽ kiểm tra thông tin cho anh ngay.")
    assert len(ra) == 1 and "kiểm tra" in ra[0].lower()


# --- Không được cắt câu có nội dung thật ----------------------------------

@pytest.mark.parametrize("cau", [
    "Dạ em kiểm tra thấy hạn mức của anh là 300 triệu đồng ạ.",
    "Dạ em vừa xem lại, lãi suất đang áp dụng là 8.5% một năm ạ.",
])
def test_cau_co_so_thi_khong_cat(cau):
    """Câu có CON SỐ là câu trả lời, dù mở đầu bằng 'em kiểm tra'."""
    ra = chay("Dạ dư nợ của anh là 142.500.000 đồng ạ.", cau)
    assert len(ra) == 2, f"đã cắt nhầm câu có nội dung: {ra}"


def test_khong_dung_toi_cau_binh_thuong():
    ra = chay("Dạ lãi suất vay tín chấp từ 7.9% một năm ạ.",
              "Anh chị cần chuẩn bị căn cước và sao kê lương ba tháng ạ.")
    assert len(ra) == 2


def test_khong_cat_loi_moi_ket_thuc():
    """"Gọi lại vào lúc khác" là lời hẹn thật, không phải hứa tra cứu."""
    ra = chay("Dạ dư nợ của anh là 142.500.000 đồng ạ.",
              "Em xin phép gọi lại cho anh vào thời điểm khác để tư vấn thêm ạ.")
    assert len(ra) == 2
