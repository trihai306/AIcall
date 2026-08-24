"""Lấy các mảnh mà kho vector ĐANG giữ cho một tài liệu.

VÌ SAO CÓ. Trang Tri thức mới chỉ đếm được số mảnh, không xem được mảnh. Mà cắt
theo ký tự (`chunk_size=500`) thì bảng lãi suất bị chặt ngang là chuyện thường -
bot đọc thiếu cột mà không có gì báo. Muốn nhìn ra thì phải đọc đúng thứ trong
kho, không phải cắt lại từ file trên đĩa.

Thứ tự mảnh là phần dễ hỏng nhất: id có dạng `<tên>_chunk_<i>`, sắp theo CHUỖI
thì mảnh 10 đứng trước mảnh 2 và người đọc tưởng tài liệu bị đảo lộn.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("chromadb")

from backend.services.rag_service import RAGService  # noqa: E402

NGUON = "knowledge/products/vay_tin_chap.md"


class _KhoGia:
    """Chroma giả. `get()` thật KHÔNG hứa trả về theo thứ tự thêm vào."""

    def __init__(self, ids, docs):
        self._ids, self._docs = ids, docs

    def get(self, where=None, include=None):
        giu = [(i, d) for i, d in zip(self._ids, self._docs)
               if (where or {}).get("source") in (None, NGUON)]
        return {"ids": [i for i, _ in giu], "documents": [d for _, d in giu]}


def _dich_vu(ids, docs):
    rag = RAGService()
    rag._is_loaded = True
    rag._collection = _KhoGia(ids, docs)
    return rag


def test_tra_ve_noi_dung_cac_manh_cua_nguon():
    rag = _dich_vu(["a_chunk_0", "a_chunk_1"], ["mảnh đầu", "mảnh sau"])
    assert rag.lay_theo_nguon(NGUON) == ["mảnh đầu", "mảnh sau"]


def test_sap_theo_so_thu_tu_chu_khong_theo_chuoi():
    """Tài liệu trên 10 mảnh: sắp kiểu chuỗi thì mảnh 10 nhảy lên trước mảnh 2."""
    rag = _dich_vu(["a_chunk_10", "a_chunk_2", "a_chunk_1"],
                   ["mười", "hai", "một"])
    assert rag.lay_theo_nguon(NGUON) == ["một", "hai", "mười"]


def test_nguon_rong_thi_tra_danh_sach_rong():
    rag = _dich_vu(["a_chunk_0"], ["gì đó"])
    assert rag.lay_theo_nguon("") == []
