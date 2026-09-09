"""Tài liệu sản phẩm phải để LƯỚI đọc được, không chỉ để người đọc được.

`gia_tri_tai_lieu` đọc TỪNG DÒNG - từ khoá của thuộc tính này không được vơ lấy
con số của dòng khác. Hệ quả người viết tài liệu hay quên: đặt chữ "lãi suất" ở
TIÊU ĐỀ MỤC rồi liệt kê mức lãi ở các dòng dưới thì lưới không thấy dòng nào là
lãi suất, và sẽ báo lệch MỌI mức lãi thật.

Đã mắc ngay khi viết `tiet_kiem.md` lần đầu (09-09-2026): bảng ghi
"Kỳ hạn 6 tháng: 4.5%/năm" dưới tiêu đề "## Lãi suất theo kỳ hạn", lưới chỉ đọc
ra hai mức 0.2% và 0.5% rồi chặn câu "lãi suất 3.5%" vốn đúng tài liệu.

Không ghi lời dặn đó vào chính tài liệu: RAG sẽ lôi nó ra và AI đọc lên cho
khách nghe. Nên đặt ở đây, dạng test.
"""
import glob
import io
import os

import pytest

from backend.pipeline.thuoc_tinh import THUOC_TINH_MAC_DINH, gia_tri_tai_lieu

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _doc(ten: str) -> str:
    return io.open(os.path.join(GOC, "knowledge", "products", f"{ten}.md"),
                   encoding="utf-8").read()


# (tài liệu, thuộc tính, vài giá trị BẮT BUỘC lưới phải đọc ra)
CAN_DOC_RA = [
    ("tiet_kiem", "lãi suất", {"3.5", "4.5", "5.5", "6"}),
    ("vay_tin_chap", "lãi suất", {"7.9"}),
    ("vay_tin_chap", "hạn mức", {"500"}),
    ("the_tin_dung", "hạn mức", {"500"}),
]


@pytest.mark.parametrize("ten, thuoc_tinh, phai_co", CAN_DOC_RA)
def test_luoi_doc_ra_duoc_gia_tri_trong_tai_lieu(ten, thuoc_tinh, phai_co):
    kho = gia_tri_tai_lieu(_doc(ten), THUOC_TINH_MAC_DINH)
    doc_duoc = {so for so, _dvi in kho.get(thuoc_tinh, set())}
    thieu = phai_co - doc_duoc
    assert not thieu, (
        f"{ten}.md: lưới KHÔNG đọc ra {sorted(thieu)} cho {thuoc_tinh!r} "
        f"(chỉ thấy {sorted(doc_duoc)}). Nhiều khả năng dòng chứa con số không "
        f"tự nhắc lại từ khoá của thuộc tính - xem đầu tệp test này.")


def test_moi_san_pham_deu_co_tai_lieu():
    """Sản phẩm không có tài liệu thì AI BỊA - đã đo, bịa ở cả 4 cách nạp ngữ cảnh.

    Trước 09-09-2026 `knowledge/` không có tệp tiết kiệm nào, và mọi cấu hình
    đều bịa lãi suất tiết kiệm ở cùng một câu hỏi của khách.
    """
    co = {os.path.basename(f)[:-3]
          for f in glob.glob(os.path.join(GOC, "knowledge", "**", "*.md"),
                             recursive=True)}
    # đúng bảng ánh xạ sản phẩm -> tệp mà đường sinh đang dùng
    can = {"vay_tin_chap", "the_tin_dung", "vay_mua_nha", "tiet_kiem"}
    assert can <= co, f"thiếu tài liệu cho: {sorted(can - co)}"
