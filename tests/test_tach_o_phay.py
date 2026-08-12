"""Tách thêm ở dấu PHẨY khi cả hai vế đủ dài.

Vì sao cần: F5 nhận được dấu phẩy nhưng LỜ nó. Đo 12-08-2026 trên hai cặp câu
(có/không phẩy, 3 lần mỗi bản, `scripts/do_nghi_o_phay.py`): không quãng nghỉ
nào rơi vào vị trí dấu phẩy, số quãng hai bản gần như nhau (5 so với 7 trên 6
lượt), vị trí đổi ngẫu nhiên mỗi lần sinh. Mà phẩy cũng KHÔNG phải chỗ cắt mảnh
nên `nhip_nghi_sau` không chèn gì -> không cơ chế nào tạo quãng nghỉ ở dấu phẩy.

Người dùng nghe ra trước khi có số: file "Đoạn 'em là dương, chuyên viên tư vấn'
không ngắt dấu phẩy.wav".
"""
import pytest

from backend.pipeline.text_chunker import (NGHI_CHAM_MS, NGHI_PHAY_MS,
                                           TOI_THIEU_TU_MOI_VE, nhip_nghi_sau,
                                           tach_manh)


def _cat_het(buffer: str) -> list[str]:
    """Cắt tới khi hết đệm, trả danh sách mảnh."""
    ra, buf, i = [], buffer, 0
    while buf.strip() and i < 30:
        m, buf = tach_manh(buf)
        if m is None:
            break
        ra.append(m)
        i += 1
    return ra


def test_tach_o_phay_khi_hai_ve_du_dai():
    """Đúng ca người dùng báo: 'Em là Dương, chuyên viên tư vấn…'."""
    manh = _cat_het("Em là Dương, chuyên viên tư vấn tín dụng. ")
    assert manh[0] == "Em là Dương,"
    assert manh[1] == "chuyên viên tư vấn tín dụng."


def test_ve_dau_qua_ngan_thi_khong_tach():
    """'Dạ,' một từ mà tách riêng là tốn trọn một lượt F5 cho 0,3 giây tiếng,
    và F5 sinh mỗi mảnh như phát ngôn trọn vẹn nên nó nghe tách hẳn khỏi câu."""
    manh = _cat_het("Dạ, em là Dương chuyên viên tư vấn. ")
    assert manh[0] == "Dạ, em là Dương chuyên viên tư vấn."


def test_ve_sau_chua_du_dai_thi_doi_them():
    """Đang nhận token dở: sau phẩy mới có 1 từ thì CHƯA được cắt, không thì vế
    sau thành mẩu cụt."""
    m, con_lai = tach_manh("Em là Dương, chuyên ")
    assert m is None
    assert con_lai == "Em là Dương, chuyên "


def test_khong_tach_giua_so_thap_phan():
    """Tiếng Việt dùng phẩy làm dấu thập phân - '7,9' không phải chỗ ngắt ý."""
    manh = _cat_het("Lãi suất là 7,9 phần trăm một năm ạ. ")
    assert manh == ["Lãi suất là 7,9 phần trăm một năm ạ."]


def test_dau_ket_cau_toi_truoc_thi_van_thang():
    manh = _cat_het("Dạ vâng ạ. Em là Dương, chuyên viên tư vấn. ")
    assert manh[0] == "Dạ vâng ạ."


def test_nhip_nghi_sau_manh_ket_bang_phay():
    """Mảnh kết bằng phẩy phải được chèn nhịp nghỉ NGẮN HƠN nhịp kết câu."""
    assert nhip_nghi_sau("Em là Dương,") == NGHI_PHAY_MS
    assert nhip_nghi_sau("Em là Dương.") == NGHI_CHAM_MS
    assert NGHI_PHAY_MS < NGHI_CHAM_MS


@pytest.mark.parametrize("dau", [",", ";", ":"])
def test_ca_ba_dau_ngat_y(dau):
    manh = _cat_het(f"Em là Dương{dau} chuyên viên tư vấn tín dụng. ")
    assert manh[0] == f"Em là Dương{dau}"


def test_nguong_khop_voi_ca_hong_that():
    """Vế 'Em là Dương' chỉ có 3 từ. Ngưỡng lớn hơn 3 là đúng ca người dùng báo
    vẫn không tách - ghi lại để ai chỉnh ngưỡng thấy ngay hệ quả."""
    assert TOI_THIEU_TU_MOI_VE <= 3


# --- ngắt mềm cho câu dài không có dấu phẩy ------------------------------

def test_ngat_mem_dang_TAT():
    """Ngắt mềm TẮT, và đây là test canh giữ quyết định đó.

    Nó từng được bật dựa trên số đo lấy từ bản code ĐÃ HỒI QUY (thiếu bản vá
    `HE_SO_BU_LANG` 1.11 -> 0.85 của main). Đo lại trên code đúng, số tất định:

        19 âm tiết:  nguyên 35%  |  tách 13%
        22 âm tiết:  nguyên 26%  |  tách 36%   <- tách LÀM TỆ HƠN

    Câu 22 âm tiết chính là câu nó sinh ra để chữa. Ai bật lại thì phải đo lại
    trên code đúng và tìm ngưỡng mới - con số 16 không còn căn cứ nào.
    """
    from backend.pipeline.text_chunker import NGAT_MEM
    assert NGAT_MEM is False
    manh = _cat_het("Không biết hiện tại anh chị đang có nhu cầu vay để làm gì "
                    "và dự kiến cần vay khoảng bao nhiêu ạ? ")
    assert len(manh) == 1, "ngắt mềm đang tắt thì câu này phải giữ nguyên một mảnh"


def test_dau_phay_van_thang_ngat_mem():
    """Có dấu phẩy thì tách ở phẩy, không đợi tới từ nối."""
    manh = _cat_het("Dạ vâng ạ, em xin phép kiểm tra lại hồ sơ của anh chị "
                    "và báo lại ngay ạ. ")
    assert manh[0] == "Dạ vâng ạ,"
