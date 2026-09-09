"""Trọn tài liệu sản phẩm + FAQ, dùng thay hai mảnh RAG trên đường thoại.

Vì sao đọc từ ĐĨA chứ không từ kho vector: trang Tri thức sửa tài liệu bằng cách
ghi file xuống đĩa rồi mới nạp lại RAG (`api/knowledge._nap_lai_mot_tep`), nên
đĩa mới là bản gốc. Ghép lại từ mảnh trong kho còn phải gỡ 50 ký tự chồng lấn ở
mỗi chỗ nối, thừa việc mà kết quả xấu hơn.

Số đo và lý do chọn cách này nằm ở đầu `tests/test_ngu_canh_tai_lieu.py`.
"""

import logging
import os
import re
import unicodedata

logger = logging.getLogger(__name__)

# (mtime, kích thước) của từng tệp đã đọc -> nội dung. Nhớ theo cả hai vì mtime
# trên một số hệ tệp chỉ chính xác tới giây, sửa nhanh hai lần trong cùng giây
# thì chỉ nhìn mtime là tưởng chưa đổi.
_NHO: dict[str, tuple[float, int, str]] = {}


def quen_nho() -> None:
    """Xoá bộ nhớ tạm. Cho test, và cho lúc nạp lại toàn bộ tri thức."""
    _NHO.clear()


def _ma(s: str) -> str:
    """"Vay Tín Chấp" -> "vay_tin_chap". Cùng luật với `RAGService._ma_san_pham`."""
    s = unicodedata.normalize("NFD", (s or "").strip().lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _doc_tep(duong: str) -> str:
    """Nội dung tệp, nhớ lại theo (mtime, kích thước). Tệp không có -> "" ."""
    try:
        st = os.stat(duong)
    except OSError:
        _NHO.pop(duong, None)
        return ""
    cu = _NHO.get(duong)
    if cu and cu[0] == st.st_mtime and cu[1] == st.st_size:
        return cu[2]
    try:
        with open(duong, encoding="utf-8", errors="replace") as f:
            noi_dung = f.read()
    except OSError as e:
        # Đọc hỏng thì trả rỗng để đường sinh RƠI VỀ RAG, đừng để cả lượt chết
        # vì một tệp. Nhưng phải kêu to: im lặng ở đây là bot tư vấn thiếu.
        logger.warning("Không đọc được tài liệu %r: %s", duong, e)
        return ""
    _NHO[duong] = (st.st_mtime, st.st_size, noi_dung)
    return noi_dung


def _goc_mac_dinh() -> str:
    """Thư mục dự án, suy từ vị trí tệp này (backend/pipeline/x.py -> ../..)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def toan_van(san_pham: str | None, goc: str | None = None) -> str:
    """Trọn tài liệu của `san_pham` kèm FAQ chung; "" nếu không có tài liệu.

    Trả "" là tín hiệu để đường sinh RƠI VỀ mảnh RAG như cũ - dùng cho lượt chưa
    biết sản phẩm (đo được 14/250 lượt lịch sử) và cho sản phẩm chưa có tài liệu.
    """
    ma = _ma(san_pham or "")
    if not ma:
        return ""
    thu = goc or _goc_mac_dinh()
    sp = _doc_tep(os.path.join(thu, "knowledge", "products", f"{ma}.md"))
    if not sp.strip():
        return ""
    faq = _doc_tep(os.path.join(thu, "knowledge", "faq", "faq_banking.md"))
    return f"{sp.strip()}\n\n{faq.strip()}".strip() if faq.strip() else sp.strip()
