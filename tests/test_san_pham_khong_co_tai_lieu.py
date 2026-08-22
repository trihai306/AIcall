"""Sản phẩm KHÔNG có tài liệu thì không được mượn số của sản phẩm khác.

Lỗi thật, đo 13-08-2026 và lặp lại cả ba lần: hỏi "lãi suất gửi tiết kiệm bao
nhiêu" thì AI đáp **7,9%/năm** - đó là lãi VAY TÍN CHẤP. `knowledge/products/`
chỉ có `the_tin_dung.md`, `vay_mua_nha.md`, `vay_tin_chap.md`; không tệp nào
nhắc tới tiết kiệm.

`_mat_na_loc` gộp hai ca khác hẳn nhau vào một nhánh "moc not in ma -> giữ hết":

    a) sản phẩm CÓ tài liệu nhưng truy vấn này hụt  -> giữ hết là ĐÚNG
    b) sản phẩm KHÔNG HỀ có tài liệu                -> giữ hết là mời mô hình
                                                       đọc số của sản phẩm khác

Báo sai lãi suất cho khách trong cuộc gọi bán sản phẩm tài chính là lỗi nặng,
nên ca (b) phải bỏ hết mảnh sản phẩm - vẫn giữ FAQ/chính sách để mô hình còn
ngữ cảnh nói "em xin phép kiểm tra lại" theo quy tắc 3.
"""
import pytest

from backend.services.rag_service import RAGService


def _meta(duong: str) -> dict:
    return {"source": duong}


DOCS = ["lãi suất vay tín chấp 7.9%/năm",
        "lãi suất vay mua nhà 6.5%/năm",
        "giờ làm việc từ 8h đến 17h"]
METAS = [_meta("knowledge/products/vay_tin_chap.md"),
         _meta("knowledge/products/vay_mua_nha.md"),
         _meta("knowledge/faq/chung.md")]
CO_TAI_LIEU = {"vay_tin_chap", "vay_mua_nha", "the_tin_dung"}


def test_tiet_kiem_khong_muon_so_cua_san_pham_khac():
    """Ca đã hỏng: hỏi tiết kiệm, AI đáp 7,9% (lãi vay tín chấp)."""
    giu = RAGService._mat_na_loc(DOCS, METAS, "tiết kiệm", CO_TAI_LIEU)
    assert giu == [False, False, True], (
        "mảnh sản phẩm khác vẫn lọt - mô hình sẽ đọc số của người ta")


def test_van_giu_faq_de_con_ngu_canh_ma_noi_khong_biet():
    giu = RAGService._mat_na_loc(DOCS, METAS, "tiết kiệm", CO_TAI_LIEU)
    assert giu[2] is True, "bỏ cả FAQ thì mô hình không còn gì để bám"


def test_hut_truy_van_thi_VAN_giu_het():
    """Ca (a): sản phẩm CÓ tài liệu, chỉ là truy vấn này không lôi được.

    Đây là chỗ dễ sửa hỏng nhất - lọc luôn ở đây thì câu hỏi chung chung về một
    sản phẩm có thật lại ra ngữ cảnh rỗng.
    """
    giu = RAGService._mat_na_loc(DOCS, METAS, "thẻ tín dụng", CO_TAI_LIEU)
    assert giu == [True, True, True]


def test_dung_san_pham_thi_loc_nhu_cu():
    giu = RAGService._mat_na_loc(DOCS, METAS, "vay tín chấp", CO_TAI_LIEU)
    assert giu == [True, False, True]


def test_khong_truyen_danh_muc_thi_giu_hanh_vi_CU():
    """Lối gọi chưa biết danh mục không được đổi hành vi âm thầm."""
    assert RAGService._mat_na_loc(DOCS, METAS, "tiết kiệm") == [True, True, True]


@pytest.mark.parametrize("sp", ["", None])
def test_khong_co_san_pham_thi_khong_loc(sp):
    assert RAGService._mat_na_loc(DOCS, METAS, sp or "", CO_TAI_LIEU) == [True] * 3


def test_danh_muc_rong_van_khong_loc_sach_khi_khong_biet():
    """`_san_pham_co_tai_lieu` trả None khi đọc kho lỗi - phải giữ hành vi cũ.

    Trả tập rỗng ở đó là sai hướng an toàn: mọi sản phẩm thành "không có tài
    liệu" và ngữ cảnh bị lọc sạch trên toàn hệ thống.
    """
    assert RAGService._mat_na_loc(DOCS, METAS, "vay tín chấp", None) == [True, False, True]
