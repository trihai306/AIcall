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
    """Cả hai vế phải đủ `TOI_THIEU_TU_MOI_VE` từ thì phẩy mới thành chỗ cắt."""
    manh = _cat_het("Em là Dương chuyên viên, phụ trách hồ sơ vay tín chấp bên em ạ. ")
    assert manh[0] == "Em là Dương chuyên viên,"
    assert manh[1] == "phụ trách hồ sơ vay tín chấp bên em ạ."


def test_ve_dau_qua_ngan_thi_KHONG_tach():
    """Chính câu người dùng báo, và nay nó KHÔNG còn được tách - đó là chủ ý.

    ĐỔI 13-08-2026, ngưỡng 3 -> 4. Đây là chỗ hai lần góp ý của người dùng đánh
    nhau, và cả hai đều về ĐÚNG câu này:
        Lần 4: "đoạn 'em là dương, chuyên viên tư vấn' không ngắt dấu phẩy"
        Lần 5: "bị giật cục chữ 'Dương' giây 2"
    Ngưỡng 3 tách được đúng chỗ họ muốn ở Lần 4, nhưng vế đầu chỉ 3 từ nên nửa
    giây đầu bị chẻ làm ba mẩu - thành ra Lần 5. Đo (`scripts/thu_nguong_phay.py`):
        ngưỡng 3   3 mảnh [4, 3, 10 từ]   quãng lặng 0,80s(200ms) VÀ 1,45s(125ms)
        ngưỡng 4+  2 mảnh [4, 13 từ]      quãng lặng 0,80s(200ms)
    Hai chỗ dừng trong 1,5 giây đầu chính là thứ nghe ra "giật cục".
    """
    manh = _cat_het("Em là Dương, chuyên viên tư vấn tín dụng. ")
    assert manh == ["Em là Dương, chuyên viên tư vấn tín dụng."]


def test_tieng_dap_mo_dau_van_duoc_mien_nguong():
    """"Dạ," vẫn tách riêng dù chỉ 1 từ - người dùng đòi ba lần liền.

    Không có cơ chế nào khác tạo được quãng nghỉ ở đó: F5 lờ dấu phẩy (đo 0/6),
    còn nhịp nghỉ do code chèn thì chỉ chèn GIỮA HAI MẢNH. Nên phải miễn ngưỡng
    cho đúng mấy tiếng đáp này, không nới ngưỡng chung.
    """
    from backend.pipeline.text_chunker import MO_DAU_TACH_RIENG
    assert MO_DAU_TACH_RIENG == {"dạ", "vâng", "dạ vâng"}
    manh = _cat_het("Dạ, em là Dương chuyên viên tư vấn. ")
    assert manh[0] == "Dạ,"
    assert manh[1] == "em là Dương chuyên viên tư vấn."


def test_da_vang_a_van_giu_nguyen_mot_manh():
    """"Dạ vâng ạ," KHÔNG tách - nó kết bằng tiểu từ, tách ra là lỗi "chữ ạ bị
    tách" quay lại (xem TIEU_TU_CUOI_VE)."""
    manh = _cat_het("Dạ vâng ạ, em xin phép kiểm tra lại hồ sơ của anh chị nhé. ")
    assert manh[0].startswith("Dạ vâng ạ,")


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
    manh = _cat_het(f"Em là Dương chuyên viên{dau} phụ trách hồ sơ vay tín chấp bên em ạ. ")
    assert manh[0] == f"Em là Dương chuyên viên{dau}"


def test_nguong_khop_voi_ca_hong_that():
    """Ngưỡng phải LỚN HƠN 3, không phải nhỏ hơn.

    Khẳng định này từng là `<= 3` và đã lật ngày 13-08-2026 - xem
    `test_ve_dau_qua_ngan_thi_KHONG_tach`. Vế "Em là Dương" có 3 từ; để ngưỡng
    ≤ 3 thì nó tách, và nửa giây đầu bị chẻ làm ba mẩu ("giật cục chữ Dương").

    Ghi lại cả hai chiều để ai chỉnh ngưỡng thấy ngay mình đang đánh đổi cái gì:
    hạ xuống 3 là lỗi Lần 5 quay lại, nâng quá cao là lỗi Lần 4 quay lại.
    """
    assert TOI_THIEU_TU_MOI_VE == 4


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


def test_khong_tach_o_phay_sau_TIEU_TU_CUOI_VE():
    """Vế trái kết bằng "ạ"/"nhé"… thì KHÔNG tách, dù đủ dài.

    ĐỔI 15-08-2026. Người dùng: "voice cái chữ 'ạ' ở cuối cũng rất hay bị tách,
    nghe lạc quê hẳn". F5 sinh mỗi mảnh như một phát ngôn trọn vẹn, nên khi "ạ"
    là từ cuối trước dấu phẩy - cực phổ biến trong câu lễ phép - nó bị đóng
    khung thành câu riêng, kèm quãng lặng nghe rõ ngay sau:

        "Vâng ạ, lãi suất … một năm ạ."   2 mảnh, LẶNG 210ms sau "ạ"
        "Vâng ạ lãi suất … một năm ạ."    1 mảnh, KHÔNG quãng lặng nào

    Trên 1653 lượt trả lời thật, 1,5% số mảnh là mảnh ngắn ≤5 từ kết bằng "ạ".
    Đo đối chứng 60 câu sau khi vá: mảnh cụt sau tiểu từ 24 -> 0, tổng mảnh
    137 -> 92, thời lượng tiếng 371s -> 370s (không đánh đổi tốc độ).

    "dạ"/"vâng"/"dạ vâng" thì GIỮ nguyên miễn trừ - quãng nghỉ sau "Dạ," là thứ
    người dùng đòi ba lần, gỡ nốt là lỗi cũ quay lại.
    """
    from backend.pipeline.text_chunker import TIEU_TU_CUOI_VE
    assert "ạ" in TIEU_TU_CUOI_VE
    manh = _cat_het("Dạ vâng ạ, em xin phép kiểm tra lại hồ sơ của anh chị "
                    "và báo lại ngay ạ. ")
    assert manh == ["Dạ vâng ạ, em xin phép kiểm tra lại hồ sơ của anh chị "
                    "và báo lại ngay ạ."]
