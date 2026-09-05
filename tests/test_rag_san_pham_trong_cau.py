"""RAG phải nhìn sản phẩm KHÁCH ĐANG HỎI, không chỉ sản phẩm của phiên.

Lỗ hổng bắt được 05-09-2026 khi chạy 8 vòng (`scripts/do_luoi_nhieu_vong.py`):

    khách: "gửi tiết kiệm tối thiểu bao nhiêu tiền"
    AI   : "gửi tiết kiệm tối thiểu 200 triệu đồng ạ"

200 triệu là hạn mức VAY TÍN CHẤP. `knowledge/products/` không có tài liệu tiết
kiệm nào.

`_mat_na_loc` ĐÃ có ca (b) xử đúng chuyện này - "sản phẩm không hề có tài liệu
thì bỏ hết mảnh sản phẩm" - nhưng nó chỉ soi `san_pham` của PHIÊN. Trong cuộc
gọi thật phiên đang tư vấn vay tín chấp (sản phẩm CÓ tài liệu), nên ca (b) không
bao giờ chạy, dù câu khách hỏi lại về sản phẩm khác.

ĐÃ ĐO VÀ BÁC BỎ hướng ngưỡng điểm khớp (`scripts/do_nguong_rag.py`): hai nhóm
chồng nhau, và neo sản phẩm còn kéo chúng chồng NHIỀU HƠN vì neo thêm chữ "vay
tín chấp" làm mọi truy vấn giống tài liệu đó.

    không neo   CÓ tài liệu 0.041-0.480 | KHÔNG có 0.086-0.208
    CÓ neo      CÓ tài liệu 0.211-0.458 | KHÔNG có 0.118-0.279
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from backend.services.rag_service import RAGService

CO_TAI_LIEU = {"vay_tin_chap", "vay_mua_nha", "the_tin_dung"}


@pytest.mark.parametrize("cau", [
    "gửi tiết kiệm tối thiểu bao nhiêu tiền",
    "sổ tiết kiệm mở tối thiểu bao nhiêu",
    "lãi suất gửi tiết kiệm kỳ hạn 6 tháng",
    "bảo hiểm nhân thọ đóng bao nhiêu một năm",
    "gói bảo hiểm rẻ nhất giá bao nhiêu",
])
def test_nhan_ra_san_pham_KHONG_co_tai_lieu(cau):
    assert RAGService._san_pham_trong_cau(cau, CO_TAI_LIEU) == "khong_co_tai_lieu"


@pytest.mark.parametrize("cau", [
    "lãi suất vay tín chấp bao nhiêu",
    "thẻ tín dụng hạn mức bao nhiêu",
    "vay mua nhà lãi suất bao nhiêu",
])
def test_san_pham_CO_tai_lieu_thi_khong_chan(cau):
    assert RAGService._san_pham_trong_cau(cau, CO_TAI_LIEU) != "khong_co_tai_lieu"


@pytest.mark.parametrize("cau", [
    "hạn mức được bao nhiêu",
    "thủ tục như nào",
    "lãi suất bao nhiêu",
    "đúng rồi",
    "",
])
def test_cau_khong_neu_san_pham_thi_de_yen(cau):
    """Van an toàn: câu không nhắc sản phẩm nào -> giữ nguyên hành vi cũ.

    Đây là phần lớn lượt trong cuộc gọi thật; siết ở đây là làm hỏng cả những
    lượt đang chạy tốt.
    """
    assert RAGService._san_pham_trong_cau(cau, CO_TAI_LIEU) == ""


def test_khong_chan_khi_san_pham_do_CO_tai_lieu():
    """Nếu mai có tài liệu tiết kiệm thì phải thôi chặn ngay, không cần sửa code."""
    assert RAGService._san_pham_trong_cau(
        "gửi tiết kiệm tối thiểu bao nhiêu", CO_TAI_LIEU | {"tiet_kiem"}) != "khong_co_tai_lieu"
