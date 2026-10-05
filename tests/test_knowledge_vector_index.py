"""API lập chỉ mục tài liệu: bỏ qua file mới nhất và chỉ re-index file đổi."""

import asyncio
import hashlib

from backend.api import knowledge as kn


class _RagGia:
    def __init__(self, content: str | None = None):
        self.content = content
        self.ingest_calls = 0
        self.clear_calls = 0

    def thong_tin_nguon(self, _sources):
        if self.content is None:
            return {"so_manh": 0, "hashes": [], "indexed_at": None}
        digest = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        return {"so_manh": 1, "hashes": [digest], "indexed_at": 123.0}

    def xoa_theo_nguon(self, _source):
        self.content = None
        return 1

    def ingest_text(self, content, doc_id, metadata=None):
        assert doc_id == "faq_test"
        assert metadata and metadata.get("knowledge_relpath") == "faq/faq_test.md"
        self.content = content
        self.ingest_calls += 1

    def dem_theo_nguon(self, _source):
        return 1 if self.content is not None else 0

    def clear(self):
        self.clear_calls += 1
        raise AssertionError("nap_lai không được clear toàn bộ vector store")

    def ingest_directory(self, _directory):
        return {"files": 5, "changed": 1, "skipped": 4, "stale_chunks": 0}


def test_lap_chi_muc_bo_qua_file_da_moi_nhat(monkeypatch, tmp_path):
    root = tmp_path / "knowledge"
    p = root / "faq" / "faq_test.md"
    p.parent.mkdir(parents=True)
    p.write_text("nội dung đang dùng", encoding="utf-8")

    rag = _RagGia("nội dung đang dùng")
    monkeypatch.setattr(kn, "GOC", root)
    monkeypatch.setattr(kn, "_rag", lambda: rag)

    d = asyncio.run(kn.lap_chi_muc("faq", "faq_test", force=False))

    assert d["ok"] is True
    assert d["bo_qua"] is True
    assert d["so_manh"] == 1
    assert rag.ingest_calls == 0


def test_file_doi_thi_chi_lap_lai_vector_file_do(monkeypatch, tmp_path):
    root = tmp_path / "knowledge"
    p = root / "faq" / "faq_test.md"
    p.parent.mkdir(parents=True)
    p.write_text("bản mới", encoding="utf-8")

    rag = _RagGia("bản cũ")
    monkeypatch.setattr(kn, "GOC", root)
    monkeypatch.setattr(kn, "_rag", lambda: rag)

    d = asyncio.run(kn.lap_chi_muc("faq", "faq_test", force=False))

    assert d["ok"] is True
    assert d["bo_qua"] is False
    assert d["trang_thai_chi_muc"] == "da_lap"
    assert rag.ingest_calls == 1
    assert rag.content == "bản mới"


def test_nap_lai_toan_kho_dung_incremental_khong_clear(monkeypatch, tmp_path):
    root = tmp_path / "knowledge"
    root.mkdir()
    rag = _RagGia()
    monkeypatch.setattr(kn, "GOC", root)
    monkeypatch.setattr(kn, "_rag", lambda: rag)

    d = asyncio.run(kn.nap_lai())

    assert d["ok"] is True
    assert d["so_tai_lieu"] == 5
    assert d["da_cap_nhat"] == 1
    assert d["giu_nguyen"] == 4
    assert rag.clear_calls == 0
