"""Câu trả lời nêu mức phần trăm KHÔNG có trong tài liệu -> con số đó là BỊA.

Đo 14-08-2026, ngay sau khi lưới lọc sản phẩm thôi cho mượn tài liệu của sản
phẩm khác: mô hình quay sang lấy số TỪ TRÍ NHỚ. Cùng câu hỏi "lãi suất gửi tiết
kiệm bao nhiêu", ngữ cảnh RỖNG, hai lần hỏi ra hai số khác nhau - **4,2%** rồi
**3,5%**. `knowledge/` không có tài liệu tiết kiệm nào nên cả hai đều bịa.

Quy tắc 3 của `CORE_RULES` đã dặn đúng điều này, bộ dữ liệu train cũng có mẫu
KHÔNG BIẾT. Cả hai đều không giữ được - cùng bài học với việc đọc sai số và với
chữ "ạ": prompt không chữa được thì chặn bằng code.

BẢN ĐẦU CỦA HÀM CHỈ HỎI "tài liệu có phần trăm hay không" VÀ NÓ KHÔNG NỔ trên
máy thật: `ngu_canh` còn ghép thêm HỒ SƠ KHÁCH (đo được 594 ký tự khi RAG trả
rỗng), trong đó có phần trăm của khoản vay khách đang có - lưới tưởng có căn cứ
rồi tha. Lãi vay của khách không chứng minh được gì về lãi tiết kiệm. Nay so
ĐÚNG CON SỐ.
"""
import pytest

from backend.pipeline.text_normalizer import CAU_KIEM_TRA_LAI, chan_lai_suat_bia


@pytest.mark.parametrize("cau", [
    "Dạ hiện tại lãi suất cho tiết kiệm của chúng em là 4,2% trong một năm ạ.",
    "Dạ lãi suất là bảy phẩy chín phần trăm ạ.",
    "Dạ mức này được 3.5 % một năm ạ.",
    "Dạ bên em áp dụng 12 phần trăm ạ.",
])
def test_chan_khi_tai_lieu_khong_co_phan_tram(cau):
    ra, sua = chan_lai_suat_bia(cau, "")
    assert ra == CAU_KIEM_TRA_LAI
    assert sua and "bịa" in sua


@pytest.mark.parametrize("cau,tai_lieu", [
    ("Dạ lãi suất vay tín chấp là 7.9%/năm ạ.", "lãi suất từ 7.9%/năm"),
    ("Dạ vay được 70 phần trăm giá trị nhà ạ.", "cho vay tối đa 70% giá trị"),
    ("Dạ lãi suất là sáu phẩy năm phần trăm ạ.", "ưu đãi 6.5%/năm"),
    # dạng CHỮ phải khớp được với dạng CHỮ SỐ trong tài liệu, không thì lưới
    # chặn nhầm mọi câu đã qua `doc_so_trong_cau`.
    ("Dạ lãi suất là bảy phẩy chín phần trăm ạ.", "Lãi suất: từ 7.9%/năm"),
])
def test_dung_con_so_trong_tai_lieu_thi_de_yen(cau, tai_lieu):
    """Có căn cứ thì không đụng - `chan_so_sai` mới là hàng rào đúng ở đó."""
    ra, sua = chan_lai_suat_bia(cau, tai_lieu)
    assert ra == cau and sua is None


HO_SO = "Hồ sơ khách: khoản vay hiện tại 200 triệu, lãi suất 9.5%/năm."


def test_ho_so_khach_co_phan_tram_KHONG_bao_ke_cho_so_bia():
    """Chính ca làm bản đầu không nổ.

    `ngu_canh` ghép hồ sơ khách vào, hồ sơ có 9.5% của khoản vay đang có - nhưng
    nó không chứng minh được gì về lãi TIẾT KIỆM.
    """
    ra, sua = chan_lai_suat_bia("Dạ lãi suất tiết kiệm là 4,2% một năm ạ.", HO_SO)
    assert ra == CAU_KIEM_TRA_LAI
    assert sua and "9.5%" in sua


def test_nhac_lai_dung_so_trong_ho_so_thi_de_yen():
    ra, sua = chan_lai_suat_bia("Dạ khoản vay của anh đang là 9.5%/năm ạ.", HO_SO)
    assert ra.startswith("Dạ khoản vay") and sua is None


def test_bat_luon_lop_loi_cu_doc_sai_so():
    """Tài liệu ghi 7.9% mà mô hình nói 6.5% - lỗi đã có tiền lệ trong dự án."""
    ra, sua = chan_lai_suat_bia("Dạ lãi suất là sáu phẩy năm phần trăm ạ.",
                                "Lãi suất: từ 7.9%/năm")
    assert ra == CAU_KIEM_TRA_LAI


@pytest.mark.parametrize("cau", [
    "Dạ anh vay 100 triệu trong 36 tháng ạ.",  # noqa: E501
    "Dạ hạn mức lên đến 500 triệu đồng ạ.",
    "Dạ hồ sơ duyệt trong 2 ngày làm việc ạ.",
    "Dạ phí bảo hiểm tùy sản phẩm và nhu cầu của anh chị ạ.",
])
def test_KHONG_chan_cac_so_khac(cau):
    """Chỉ chặn PHẦN TRĂM.

    Câu trả lời hợp lệ vẫn đầy số không đến từ tài liệu: nhắc lại số tiền khách
    vừa nói, số ngày, số tháng. Chặn rộng là tự tay bịt mồm những câu đúng.
    """
    ra, sua = chan_lai_suat_bia(cau, "")
    assert ra == cau and sua is None


def test_cau_thay_the_khong_chua_con_so_nao():
    """Câu thay vào mà lỡ nêu số thì hàng rào tự phá chính nó."""
    import re
    assert not re.search(r"\d", CAU_KIEM_TRA_LAI)
    assert "%" not in CAU_KIEM_TRA_LAI


def test_chuoi_rong_khong_no():
    assert chan_lai_suat_bia("", "") == ("", None)
