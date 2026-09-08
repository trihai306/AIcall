"""Sửa file trong `knowledge/` rồi nạp lại thì kho vector PHẢI đổi theo.

BẪY TÌM RA 07-09-2026, và nó làm hỏng mọi nỗ lực sửa nội dung:

`ingest_text` gọi `collection.add(ids=[f"{doc_id}_chunk_{i}"])`. Chroma KHÔNG ghi
đè khi id đã tồn tại - nó bỏ qua im lặng. Nên nạp lại một file ĐÃ SỬA là vô tác
dụng, và kho vector đứng nguyên ở bản đầu tiên từng nạp.

Đo được trên máy chạy thật: `ingest_directory` báo "Ingested 3 chunks from
'vay_tin_chap'" nhưng số mảnh trong kho không đổi (9 trước, 9 sau), và câu mới
thêm vào file KHÔNG có trong kho. Kho vẫn giữ bản cũ, trong đó có dòng:

    - Nợ xấu vẫn có cách lách để vay được

Đó chính là nguồn của câu AI nói với khách: "Bên em vẫn có cách LÁCH để anh/chị
vay được ạ". Mô hình KHÔNG bịa - nó đọc đúng tài liệu. Grep trên các file ở đĩa
không thấy gì, vì dòng đó chỉ còn tồn tại trong kho vector.

Hệ quả rộng hơn: người dùng sửa tri thức bao nhiêu lần cũng không ăn, mà không có
gì báo lỗi - log vẫn ghi "Ingested ... chunks" như bình thường.
"""
import pytest

from backend.services.rag_service import RAGService


class KhoGia:
    """Kho vector giả, đúng phần hợp đồng mà `ingest_text` dùng tới."""

    def __init__(self):
        self.ids: list[str] = []
        self.docs: list[str] = []

    def add(self, documents, embeddings, ids, metadatas):
        for i, d in zip(ids, documents):
            if i in self.ids:          # Chroma bỏ qua id trùng - mô phỏng đúng
                continue
            self.ids.append(i)
            self.docs.append(d)

    def get(self, *a, **k):
        return {"ids": list(self.ids), "documents": list(self.docs)}

    def delete(self, ids=None, **k):
        for i in list(ids or []):
            if i in self.ids:
                v = self.ids.index(i)
                self.ids.pop(v)
                self.docs.pop(v)

    def count(self):
        return len(self.ids)


class NhungGia:
    def encode(self, texts):
        # numpy chứ không phải list: `ingest_text` gọi `.tolist()` lên kết quả.
        import numpy as np
        return np.array([[float(len(t)), 0.0] for t in texts], dtype=np.float32)


@pytest.fixture
def rag():
    r = RAGService()
    r._is_loaded = True
    r._collection = KhoGia()
    r._embedder = NhungGia()
    return r


def test_nap_lai_ban_da_sua_thi_kho_phai_doi_theo(rag):
    rag.ingest_text("Nợ xấu vẫn có cách lách để vay được.", doc_id="vay_tin_chap")
    assert any("lách" in d for d in rag._collection.docs)

    rag.ingest_text("Nợ xấu nhóm 3-5 tại CIC thì hồ sơ khó được duyệt ạ.",
                    doc_id="vay_tin_chap")
    con_lai = " ".join(rag._collection.docs)
    assert "lách" not in con_lai, (
        "bản CŨ còn nằm trong kho - đây đúng là lỗi đã làm AI nói 'cách lách' "
        "suốt dù file trên đĩa đã bỏ dòng đó")
    assert "nhóm 3-5" in con_lai, "bản MỚI chưa vào kho"


def test_ban_moi_it_manh_hon_thi_khong_de_lai_manh_thua(rag):
    """Bản cũ dài hơn bản mới: mảnh thừa của bản cũ phải biến mất.

    Đây là ca thật: kho có 4 mảnh `vay_tin_chap`, file sửa lại chỉ còn 3. Xoá
    thiếu thì mảnh thứ tư của bản cũ sống sót và vẫn được RAG lôi ra.
    """
    rag.ingest_text("x" * 1400, doc_id="tai_lieu")
    nhieu = rag._collection.count()
    rag.ingest_text("y" * 200, doc_id="tai_lieu")
    assert rag._collection.count() < nhieu
    assert not any("x" in d for d in rag._collection.docs)


def test_khong_dung_toi_tai_lieu_KHAC(rag):
    rag.ingest_text("nội dung của tài liệu A", doc_id="a")
    rag.ingest_text("nội dung của tài liệu B", doc_id="b")
    rag.ingest_text("B đã sửa", doc_id="b")
    con_lai = " ".join(rag._collection.docs)
    assert "tài liệu A" in con_lai, "nạp lại B mà xoá nhầm mảnh của A"
    assert "B đã sửa" in con_lai
