"""Hỏi rõ Shinhan không được kéo theo con số giả từ sản phẩm demo."""

import asyncio

import numpy as np
from types import SimpleNamespace

from backend.pipeline.streaming_pipeline import StreamingPipeline
from backend.services.rag_service import RAGService


class _Embedder:
    def encode(self, _texts):
        return np.asarray([[0.1, 0.2]], dtype=np.float32)


class _Collection:
    def __init__(self):
        self.where = None
        self.where_document = None

    def count(self):
        return 2

    def get(self, ids=None, include=None):
        if ids:
            return {"documents": ["Hạn mức giả 500 triệu"], "ids": ids}
        return {"metadatas": [
            {"source": "knowledge/products/the_tin_dung.md"},
            {"source": "knowledge/shinhan/shinhan_card_user_guide_vi.md", "bank": "shinhan"},
        ]}

    def query(self, *, query_embeddings, n_results, include, where=None,
              where_document=None):
        self.where = where
        self.where_document = where_document
        if where == {"bank": "shinhan"}:
            return {
                "documents": [["Shinhan Bank — kích hoạt thẻ qua SOL"]],
                "metadatas": [[{"source": "knowledge/shinhan/shinhan_card_user_guide_vi.md", "bank": "shinhan"}]],
                "distances": [[0.2]],
            }
        return {
            "documents": [["Hạn mức giả 500 triệu"]],
            "metadatas": [[{"source": "knowledge/products/the_tin_dung.md"}]],
            "distances": [[0.1]],
        }


def test_truy_van_shinhan_chi_lay_nguon_shinhan():
    rag = RAGService()
    rag._is_loaded = True
    rag._embedder = _Embedder()
    rag._collection = _Collection()

    context, detail = asyncio.run(rag.retrieve_chi_tiet(
        "Thẻ tín dụng Shinhan kích hoạt thế nào?", top_k=2,
        san_pham="thẻ tín dụng",
    ))

    assert rag._collection.where == {"bank": "shinhan"}
    assert "kích hoạt thẻ qua SOL" in context
    assert "500 triệu" not in context
    assert all(m["nguon"].startswith("shinhan_") for m in detail)


def test_the_dien_tu_loc_muc_dien_tu_truoc_khi_xep_hang():
    rag = RAGService()
    rag._is_loaded = True
    rag._embedder = _Embedder()
    rag._collection = _Collection()
    asyncio.run(rag.retrieve_chi_tiet(
        "Thẻ điện tử Shinhan có mất phí không?", top_k=3,
        san_pham="thẻ tín dụng Shinhan",
    ))
    assert rag._collection.where == {"bank": "shinhan"}
    assert rag._collection.where_document == {"$contains": "thẻ điện tử"}


def test_kich_ban_shinhan_neo_ca_cau_khach_khong_nhac_ten_ngan_hang():
    session = SimpleNamespace(
        product="thẻ tín dụng",
        scenario={"org_name": "Ngân hàng Shinhan"},
    )
    query = StreamingPipeline._truy_van_rag("Tôi bị mất thẻ", session)
    assert query == "Shinhan thẻ tín dụng Tôi bị mất thẻ"


def test_cau_the_dien_tu_da_ro_khong_bi_neo_ve_the_vat_ly():
    session = SimpleNamespace(
        product="thẻ tín dụng Shinhan",
        scenario={"org_name": "Ngân hàng Shinhan"},
    )
    text = "Đăng ký và kích hoạt thẻ điện tử Shinhan thế nào?"
    query = StreamingPipeline._truy_van_rag(text, session)
    assert query == text
    assert StreamingPipeline._rag_top_k(query) == 3
    assert not StreamingPipeline._spec_hit(
        "Đăng ký thẻ điện tử Shinhan",
        "Đăng ký thẻ điện tử Shinhan và kích hoạt thế nào?")
