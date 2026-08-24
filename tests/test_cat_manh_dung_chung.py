"""Cách cắt mảnh phải là MỘT, dùng chung cho cả RAG lẫn khung xem trước.

VÌ SAO CÓ. Hộp soạn tài liệu có khung "sẽ cắt thành mấy mảnh" để người viết thấy
trước hậu quả. Nếu chép thuật toán cắt ra chỗ khác thì một ngày nào đó sửa RAG mà
quên sửa bản xem trước, và khung đó bắt đầu nói dối - tệ hơn là không có, vì
người dùng tin nó.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("chromadb")

from backend.services.rag_service import RAGService, cat_manh  # noqa: E402


def test_ngan_hon_mot_manh_thi_de_nguyen():
    assert cat_manh("Lãi suất 7.9%/năm", 500, 50) == ["Lãi suất 7.9%/năm"]


def test_rong_thi_khong_ra_manh_nao():
    assert cat_manh("   \n  ", 500, 50) == []


def test_dai_thi_cat_ra_nhieu_manh_co_chong_lan():
    text = "a" * 120
    manh = cat_manh(text, 50, 10)
    assert len(manh) == 3
    # Chồng 10 ký tự: mảnh sau bắt đầu lùi lại, không cắt đứt hẳn.
    assert manh[1].startswith("a" * 10)


def test_dich_vu_rag_dung_dung_ham_nay():
    """Khoá lại mối nối: `_chunk_text` phải là chính `cat_manh`, không phải bản chép.

    Đây là test giữ cho khung xem trước không bao giờ lệch khỏi RAG thật.
    """
    rag = RAGService()
    text = "\n".join(f"dòng số {i} của tài liệu thử" for i in range(60))
    assert rag._chunk_text(text, 500, 50) == cat_manh(text, 500, 50)
