"""Khách nhắc sản phẩm nào thì NHỚ, để lượt sau không phải hỏi lại.

LỖI THẬT trên cuộc gọi `73992c8d` (07-09-2026 18:49, `product=''`):

    khách: bên bạn có cho vay tín chấp không
    AI   : Anh/chị cần là công dân Việt Nam từ 22-60 tuổi...
    khách: mức lãi suất là bao nhiêu nhỉ
    AI   : Em xin phép kiểm tra lại... Anh/chị cần tư vấn sản phẩm nào cụ thể không?
    khách: mức lãi suất CỦA VAY TÍN CHẤP là bao nhiêu     <- khách phải tự nhắc lại
    AI   : Từ 7.9% một năm ạ.

Gốc: `san_pham_neo()` chỉ nhìn `session.product` hoặc CÂU HIỆN TẠI, không bao
giờ nhìn lịch sử. Còn `session.product` chỉ được đặt một lần lúc mở phiên
(`websocket.py` `set_session`) - gọi tay không chọn sản phẩm thì nó rỗng suốt
cuộc gọi. Đến lượt hỏi "lãi suất bao nhiêu" thì không còn gì neo.

Sửa ở tầng THẤP NHẤT có thể: ghi vào chính `session.product`. Mọi chỗ đang đọc
trường đó đều được hưởng - neo truy vấn RAG, trọn tài liệu nạp vào prompt, tài
liệu đối chiếu của lưới thuộc tính, và dòng "Sản phẩm quan tâm" trong prompt.
"""
import pytest

from backend.services.rag_service import RAGService

CO_TAI_LIEU = {"vay_tin_chap", "vay_mua_nha", "the_tin_dung", "tiet_kiem"}


@pytest.mark.parametrize("ma, ten", [
    ("vay_tin_chap", "vay tín chấp"),
    ("the_tin_dung", "thẻ tín dụng"),
    ("tiet_kiem", "tiết kiệm"),
])
def test_ma_ra_ten_hien_thi(ma, ten):
    """Phải ra TÊN người đọc được: nó đi thẳng vào dòng "Sản phẩm quan tâm"."""
    assert RAGService.ten_san_pham(ma) == ten


def test_ma_la_thi_tra_rong():
    assert RAGService.ten_san_pham("khong_ton_tai") == ""


def test_khach_nhac_san_pham_thi_neo_duoc():
    assert RAGService.neo_moi_tu_cau(
        "bên bạn có cho vay tín chấp không", CO_TAI_LIEU) == "vay tín chấp"


def test_cau_KHONG_neu_san_pham_thi_giu_nguyen():
    """Phần lớn lượt là kiểu này ("lãi suất bao nhiêu") - đừng đoán bừa."""
    for cau in ("lãi suất bao nhiêu", "hạn mức được bao nhiêu", "ừ", ""):
        assert RAGService.neo_moi_tu_cau(cau, CO_TAI_LIEU) == ""


def test_san_pham_KHONG_co_tai_lieu_thi_khong_neo():
    """Neo vào thứ không có tài liệu là mời AI đọc số của sản phẩm khác."""
    assert RAGService.neo_moi_tu_cau(
        "gói bảo hiểm nhân thọ đóng bao nhiêu", CO_TAI_LIEU) == ""


def test_khach_doi_san_pham_thi_neo_theo_cai_moi():
    """Khách chuyển chủ đề giữa cuộc thì phải theo, không dính neo cũ."""
    assert RAGService.neo_moi_tu_cau(
        "thế còn thẻ tín dụng thì sao em", CO_TAI_LIEU) == "thẻ tín dụng"


def test_chua_biet_danh_muc_thi_van_neo_duoc():
    """`_san_pham_co_tai_lieu()` trả None khi kho chưa nạp - đừng vì thế mà câm."""
    assert RAGService.neo_moi_tu_cau(
        "cho anh hỏi vay tín chấp", None) == "vay tín chấp"


# --- canh dây nối trong đường sinh -----------------------------------------

def test_duong_sinh_co_neo_san_pham():
    import inspect
    from backend.pipeline import streaming_pipeline
    assert "neo_moi_tu_cau" in inspect.getsource(streaming_pipeline)


def test_neo_TRUOC_khi_nap_tron_tai_lieu():
    """Neo xong mới nạp tài liệu, không thì lượt neo được vẫn dùng tài liệu cũ."""
    import inspect
    from backend.pipeline import streaming_pipeline
    ma = inspect.getsource(streaming_pipeline)
    assert ma.index("neo_moi_tu_cau") < ma.index("_toan_van_tai_lieu(session.product)")
