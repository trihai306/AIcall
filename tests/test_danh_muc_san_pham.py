"""Khách hỏi bên em có những sản phẩm gì: trả lời theo DANH MỤC có tài liệu.

Cuộc gọi `7db3f780` lượt 1: "bên bạn cho vay những cái gì" đi xuống mô hình.
Lần đó mô hình đáp đúng, nhưng danh mục là dữ kiện xác định (kho có tài liệu nào
thì bán sản phẩm đó), không có lý do để mô hình đoán. Và khách hỏi sản phẩm KHÔNG
có tài liệu ("có bảo hiểm không") thì mô hình dễ nói "có" rồi bịa.
"""
import pytest

from backend.pipeline.danh_muc_san_pham import TEN, tra_loi

KHO = {"vay_tin_chap", "vay_mua_nha", "the_tin_dung", "tiet_kiem"}


@pytest.mark.parametrize("cau", [
    "bên bạn cho vay những cái gì",
    "bên em cho vay những gì",
    "ngân hàng có những gói vay nào",
    "bên em có mấy loại vay",
])
def test_hoi_cac_loai_vay_chi_ke_san_pham_vay(cau):
    got = tra_loi(cau, KHO)
    assert got and got[0] == "danh_muc_vay"
    assert "vay tín chấp" in got[1] and "vay mua nhà" in got[1]
    assert "thẻ" not in got[1] and "tiết kiệm" not in got[1]
    assert "vay vay" not in got[1]


@pytest.mark.parametrize("cau", [
    "bên em có những sản phẩm gì",
    "ngân hàng bên bạn có dịch vụ gì",
    "bên em có những sản phẩm nào vậy",
])
def test_hoi_chung_ke_du_danh_muc(cau):
    got = tra_loi(cau, KHO)
    assert got and got[0] == "danh_muc_san_pham"
    for ten in ("vay tín chấp", "vay mua nhà", "thẻ tín dụng", "tiết kiệm"):
        assert ten in got[1]


def test_ke_theo_dung_kho_dang_co():
    got = tra_loi("bên em có những sản phẩm gì", {"vay_tin_chap", "tiet_kiem"})
    assert "vay tín chấp" in got[1] and "tiết kiệm" in got[1]
    assert "vay mua nhà" not in got[1] and "thẻ" not in got[1]


@pytest.mark.parametrize("cau, ten", [
    ("bên bạn có vay tín chấp không", "vay tín chấp"),
    ("bên em có làm thẻ tín dụng không", "thẻ tín dụng"),
    ("có gửi tiết kiệm không em", "tiết kiệm"),
])
def test_hoi_co_san_pham_co_tai_lieu(cau, ten):
    got = tra_loi(cau, KHO)
    assert got and got[0] == "co_san_pham"
    assert ten in got[1] and "chưa có" not in got[1]


@pytest.mark.parametrize("cau, ten", [
    ("bên em có bảo hiểm không", "bảo hiểm"),
    ("có đổi ngoại tệ không em", "ngoại tệ"),
])
def test_hoi_san_pham_khong_co_thi_noi_chua_co_va_ke_cai_dang_co(cau, ten):
    got = tra_loi(cau, KHO)
    assert got and got[0] == "chua_co_san_pham"
    assert "chưa có" in got[1] and ten in got[1]
    assert "vay tín chấp" in got[1]


@pytest.mark.parametrize("cau", [
    "hồ sơ cần những gì",
    "có ưu đãi gì không",
    "vay tín chấp có cần thế chấp không",
    "anh có vay tín chấp được không",
    "giấy tờ gồm những gì",
    "lãi suất vay tín chấp bao nhiêu",
    "vay tín chấp thì cần điều kiện gì",
])
def test_khong_bat_nham_cau_hoi_khac(cau):
    assert tra_loi(cau, KHO) is None


def test_kho_chua_nap_thi_de_mo_hinh():
    assert tra_loi("bên em có những sản phẩm gì", None) is None
    assert tra_loi("bên em có những sản phẩm gì", set()) is None


def test_hoi_them_khi_chua_ro_san_pham():
    got = tra_loi("bên em có những sản phẩm gì", KHO, hoi_them=True)
    assert got[1].rstrip().endswith("?")
    got = tra_loi("bên em có những sản phẩm gì", KHO, hoi_them=False)
    assert not got[1].rstrip().endswith("?")


def test_ten_khop_bang_tu_khoa_cua_rag():
    """Hai bảng tên phải khớp nhau, không thì danh mục đọc tên khác với tên
    mà RAG dùng để neo sản phẩm."""
    from backend.services.rag_service import RAGService
    for ma, cum in RAGService._TU_KHOA_SP:
        assert TEN[ma] == cum[0]


@pytest.mark.parametrize("cau", [
    "vay tín chấp có bảo hiểm không",
    "khoản vay có bảo hiểm không em",
    "thẻ có bảo hiểm không",
])
def test_hoi_bao_hiem_cua_khoan_vay_khong_phai_hoi_san_pham(cau):
    """Hỏi THUỘC TÍNH khoản vay, không hỏi bên em có bán bảo hiểm."""
    assert tra_loi(cau, KHO) is None


@pytest.mark.parametrize("cau", [
    "thế có bán bảo hiểm không em vậy",
    "thế bên em có bảo hiểm không",
])
def test_the_dem_dau_cau_khong_phai_the_tin_dung(cau):
    """Bộ thử 10k: "thế" bỏ dấu thành "the" giống "thẻ" nên bị coi là hỏi thẻ."""
    got = tra_loi(cau, KHO)
    assert got and got[0] == "chua_co_san_pham"


@pytest.mark.parametrize("cau, ten", [
    ("cho chị hỏi là có cho vay kinh doanh không thế", "vay kinh doanh"),
    ("bên em có vay mua xe không", "vay mua xe"),
])
def test_san_pham_ngan_hang_khong_ban(cau, ten):
    got = tra_loi(cau, KHO)
    assert got and got[0] == "chua_co_san_pham" and ten in got[1]
