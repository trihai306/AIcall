"""Nạp knowledge tăng dần: file không đổi không được encode lại mỗi startup."""

import numpy as np

from backend.services.rag_service import RAGService, cat_manh


class _KhoGia:
    def __init__(self):
        self.rows: dict[str, tuple[str, dict]] = {}

    def add(self, documents, embeddings, ids, metadatas):
        for chunk_id, doc, meta in zip(ids, documents, metadatas):
            if chunk_id not in self.rows:
                self.rows[chunk_id] = (doc, dict(meta))

    def get(self, ids=None, include=None, **_kwargs):
        keys = list(ids) if ids is not None else list(self.rows)
        keys = [k for k in keys if k in self.rows]
        return {
            "ids": keys,
            "documents": [self.rows[k][0] for k in keys],
            "metadatas": [self.rows[k][1] for k in keys],
        }

    def delete(self, ids=None, **_kwargs):
        for chunk_id in list(ids or []):
            self.rows.pop(chunk_id, None)

    def count(self):
        return len(self.rows)


class _NhungDem:
    def __init__(self):
        self.calls = 0

    def encode(self, texts):
        self.calls += 1
        return np.array([[float(len(t)), 0.0] for t in texts], dtype=np.float32)


def _rag() -> tuple[RAGService, _NhungDem]:
    rag = RAGService()
    embedder = _NhungDem()
    rag._is_loaded = True
    rag._collection = _KhoGia()
    rag._embedder = embedder
    return rag, embedder


def test_file_khong_doi_thi_khong_nhung_lai(tmp_path):
    root = tmp_path / "knowledge"
    root.mkdir()
    file_path = root / "faq.md"
    file_path.write_text("nội dung ban đầu", encoding="utf-8")

    rag, embedder = _rag()
    rag.ingest_directory(str(root))
    assert embedder.calls == 1

    rag.ingest_directory(str(root))
    assert embedder.calls == 1, "startup thứ hai vẫn encode lại file không đổi"

    file_path.write_text("nội dung đã sửa", encoding="utf-8")
    rag.ingest_directory(str(root))
    assert embedder.calls == 2
    assert "đã sửa" in rag._collection.rows["faq_chunk_0"][0]


def test_file_bi_xoa_thi_chunk_cu_bien_mat_but_du_lieu_ngoai_con_nguyen(tmp_path):
    root = tmp_path / "knowledge"
    root.mkdir()
    a = root / "a.md"
    b = root / "b.md"
    a.write_text("tài liệu A", encoding="utf-8")
    b.write_text("tài liệu B", encoding="utf-8")

    rag, _embedder = _rag()
    rag.ingest_directory(str(root))
    rag._collection.rows["external_chunk_0"] = (
        "dữ liệu ngoài",
        {"source": "ds:excel-bang-gia"},
    )

    a.unlink()
    rag.ingest_directory(str(root))

    assert "a_chunk_0" not in rag._collection.rows
    assert "b_chunk_0" in rag._collection.rows
    assert "external_chunk_0" in rag._collection.rows


def test_markdown_giu_nguyen_hai_y_de_qwen_doc_du_ca_hai():
    content = ("# Shinhan Bank — thẻ điện tử\n\nNguồn PDF: tài liệu chính thức\n\n"
               "## register_digital_card\n\nĐăng ký trên SOL và xác nhận thỏa thuận.\n\n"
               "## activate_digital_card\n\nNhận mã SMS rồi nhập mã để kích hoạt.")
    chunks = cat_manh(content, chunk_size=110)
    assert len(chunks) == 2
    assert chunks[0].startswith("# Shinhan Bank")
    assert "Đăng ký trên SOL" in chunks[0]
    assert chunks[1].startswith("# Shinhan Bank")
    assert "Nhận mã SMS" in chunks[1]
    assert all(not chunk.startswith("tử trong") for chunk in chunks)


def test_doi_cach_cat_thi_nhung_lai_file_du_noi_dung_khong_doi(tmp_path):
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "faq.md").write_text("# FAQ\n\n## Mục\n\nNội dung", encoding="utf-8")
    rag, embedder = _rag()
    rag.ingest_directory(str(root))
    assert embedder.calls == 1
    rag._collection.rows["faq_chunk_0"][1]["chunker_version"] = "legacy"
    rag.ingest_directory(str(root))
    assert embedder.calls == 2
