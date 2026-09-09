"""Lời KHÁCH không bao giờ được cắt khỏi sổ căn cứ, dù tài liệu có tràn.

LỖI THẬT đo được 09-09-2026 trên cuộc gọi 14 lượt:

    [lượt 1]  khách: chào em, lương anh 18 triệu một tháng
    [lượt 9]  khách: lúc nãy anh nói lương bao nhiêu ấy nhỉ
              AI   : "Dạ anh Minh có thu nhập 5 triệu/tháng ạ."   <- SAI

Mô hình NHỚ đúng 18 triệu (lượt 14 nhớ được cả "công ty xây dựng 5 năm"). Thứ
hỏng là lưới: con số 18 triệu đã rơi khỏi sổ căn cứ nên bị coi là bịa, rồi bản
sửa thay bằng 5 triệu - thu nhập TỐI THIỂU trong tài liệu.

Gốc: `ghi_tai_lieu` và `ghi_khach` dùng CHUNG một hàng đợi có trần 20000 ký tự.
Tài liệu to gấp ba lời khách hàng trăm lần, nên nó đẩy lời khách ra trước. Từ
09-09 ngữ cảnh nạp trọn tài liệu (~2918 ký tự/lượt thay vì ~1005) nên sổ đầy sau
7 lượt thay vì 20.

Hai loại căn cứ có giá trị khác hẳn nhau:
  - lời khách: NHỎ, quý, không bao giờ lấy lại được nếu mất
  - tài liệu : TO, và lưới vẫn nhận `ngu_canh` của lượt hiện tại qua đường riêng
"""
from backend.pipeline.so_can_cu import SoCanCu

TAI_LIEU = "x" * 3000


def test_loi_khach_song_qua_tran_tai_lieu():
    so = SoCanCu()
    so.ghi_khach("lương anh 18 triệu một tháng")
    for i in range(30):                      # thừa sức làm tràn trần 20000
        so.ghi_tai_lieu(f"{TAI_LIEU} [lượt {i}]")
    assert "18 triệu" in so.can_cu, "lời khách bị tài liệu đẩy ra khỏi sổ"


def test_tai_lieu_van_bi_cat_khi_tran():
    """Nới cho lời khách KHÔNG được biến sổ thành vô hạn."""
    so = SoCanCu()
    for i in range(30):
        so.ghi_tai_lieu(f"{TAI_LIEU} [lượt {i}]")
    assert len(so.can_cu) <= SoCanCu.TRAN_KY_TU * 1.1
    assert "[lượt 0]" not in so.can_cu, "tài liệu cũ nhất phải bị cắt"


def test_doi_san_pham_van_giu_loi_khach():
    """Đổi sản phẩm xoá căn cứ TÀI LIỆU, nhưng thu nhập của khách thì không đổi.

    Khách hỏi sang thẻ tín dụng giữa cuộc thì `doi_neo` xoá sổ - và trước bản
    sửa này nó xoá luôn "lương anh 18 triệu", đúng cái mà lượt sau cần.
    """
    so = SoCanCu()
    so.doi_neo("vay_tin_chap")
    so.ghi_khach("lương anh 18 triệu một tháng")
    so.ghi_tai_lieu("- Hạn mức: 500 triệu")
    so.doi_neo("the_tin_dung")
    assert "18 triệu" in so.can_cu, "đổi sản phẩm mà xoá luôn lời khách"
    assert "500 triệu" not in so.can_cu, "căn cứ tài liệu cũ phải bị xoá"


def test_khach_noi_trung_thi_khong_ghi_hai_lan():
    so = SoCanCu()
    so.ghi_khach("lương anh 18 triệu")
    so.ghi_khach("lương anh 18 triệu")
    assert so.can_cu.count("18 triệu") == 1
