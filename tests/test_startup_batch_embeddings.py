"""Startup phải gom embedding theo batch nhưng giữ nguyên ma trận từng nhóm."""

import numpy as np
import asyncio
import sqlite3
import threading
from types import SimpleNamespace
import pytest

from backend.core.startup import _nhung_theo_nhom
from backend.services.filler_situation import chon_tinh_huong, chuan_hoa


class RagGia:
    def __init__(self):
        self.cac_lan = []

    def embed(self, ds):
        ds = list(ds)
        self.cac_lan.append(ds)
        # Vector chỉ phụ thuộc nội dung, không phụ thuộc kích thước/vị trí batch.
        bang = {
            "lai suat": [1.0, 0.0, 0.0],
            "lai vay": [0.9, 0.1, 0.0],
            "han muc": [0.0, 1.0, 0.0],
            "vay toi da": [0.0, 0.9, 0.1],
            "phi bao nhieu": [0.0, 0.0, 1.0],
        }
        return np.asarray([bang[x] for x in ds], dtype=np.float32)


def test_nhung_nhieu_nhom_chi_goi_model_mot_lan_va_cat_dung_ma_tran():
    rag = RagGia()
    kho = _nhung_theo_nhom(rag, (
        ("lai", ("lai suat", "lai vay")),
        ("han_muc", ("han muc", "vay toi da")),
    ))

    assert rag.cac_lan == [["lai suat", "lai vay", "han muc", "vay toi da"]]
    assert {k: v.shape for k, v in kho.items()} == {
        "lai": (2, 3),
        "han_muc": (2, 3),
    }
    np.testing.assert_allclose(
        kho["lai"],
        chuan_hoa([[1.0, 0.0, 0.0], [0.9, 0.1, 0.0]]),
    )
    np.testing.assert_allclose(
        kho["han_muc"],
        chuan_hoa([[0.0, 1.0, 0.0], [0.0, 0.9, 0.1]]),
    )


def test_batch_giu_nguyen_hanh_vi_chon_tinh_huong():
    rag = RagGia()
    kho = _nhung_theo_nhom(rag, (
        ("lai", ("lai suat", "lai vay")),
        ("han_muc", ("han muc", "vay toi da")),
    ))
    q = chuan_hoa(rag.embed(["lai suat"]))[0]

    ma, _ = chon_tinh_huong(q, kho, nguong=0.75)
    assert ma == "lai"


def test_nhom_rong_khong_goi_embedding():
    rag = RagGia()
    assert _nhung_theo_nhom(rag, (("rong", ()),)) == {}
    assert rag.cac_lan == []


def test_startup_and_reload_layout_indexes_managed_answers_and_keeps_legacy(monkeypatch):
    from backend.core.startup import _nhung_bang_hoi_dap
    from backend.config import settings
    from backend.services.bang_hoi_dap import doc_dong, retrieval_texts, RETRIEVAL_LAYOUT_VERSION

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE hoi_dap (id TEXT,cau_dem TEXT,cau_hoi TEXT,tra_loi TEXT,san_pham TEXT,bat INTEGER)")
    conn.executemany("INSERT INTO hoi_dap VALUES (?,'',?,?, '',1)", [
        ("ab_manual_answer", "[]", "Đáp án duy nhất."),
        ("ab_auto_examples", '["Cách hỏi phụ"]', "Nội dung có điều kiện."),
        ("legacy", '["Câu hỏi cũ"]', "Không nhúng đáp án legacy."),
    ])
    rows = doc_dong(conn)
    main_thread, calls = threading.get_ident(), []

    def embed(texts):
        assert threading.get_ident() != main_thread
        calls.append(list(texts))
        return np.ones((len(texts), 2), dtype=np.float32)

    rag = SimpleNamespace(embed=embed)
    state = SimpleNamespace(rag=rag)
    monkeypatch.setattr(settings, "embedding_device", "cpu")
    asyncio.run(_nhung_bang_hoi_dap(state, rows))
    assert calls == [[text for row in rows for text in retrieval_texts(row)]]
    assert {key: len(matrix) for key, matrix in state.hoi_dap_vector.items()} == {
        "ab_manual_answer": 1, "ab_auto_examples": 2, "legacy": 1}
    assert state._hoi_dap_vector_rag is rag
    assert state._hoi_dap_vector_layout == RETRIEVAL_LAYOUT_VERSION


def test_answer_only_managed_validation_does_not_relax_legacy_or_empty_answer():
    from backend.services.bang_hoi_dap import kiem_dong, LoiBang

    kiem_dong({"id": "ab_manual_x", "cau_hoi": [], "tra_loi": "Có nội dung"})
    with pytest.raises(LoiBang, match="không có cách hỏi"):
        kiem_dong({"id": "legacy", "cau_hoi": [], "tra_loi": "Có nội dung"})
    with pytest.raises(LoiBang, match="trả lời rỗng"):
        kiem_dong({"id": "ab_manual_x", "cau_hoi": [], "tra_loi": "   "})


def test_khoi_dong_lan_hai_chi_nhung_van_ban_moi(monkeypatch):
    """Lần khởi động sau không nhúng lại cả kho: 5.500 đáp án từng mất 36 phút."""
    from backend.core.startup import _nhung_bang_hoi_dap
    from backend.config import settings
    from backend.services.bang_hoi_dap import doc_dong, retrieval_texts

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE hoi_dap (id TEXT,cau_dem TEXT,cau_hoi TEXT,tra_loi TEXT,san_pham TEXT,bat INTEGER)")
    conn.execute("INSERT INTO hoi_dap VALUES ('a','','[\"Hỏi một\"]','Đáp một.','',1)")
    calls = []

    def embed(texts):
        calls.append(list(texts))
        return np.array([[float(len(t)), 1.0] for t in texts], dtype=np.float32)

    state = SimpleNamespace(rag=SimpleNamespace(embed=embed))
    monkeypatch.setattr(settings, "embedding_device", "cpu")
    asyncio.run(_nhung_bang_hoi_dap(state, doc_dong(conn)))
    lan_dau = {k: v.copy() for k, v in state.hoi_dap_vector.items()}

    conn.execute("INSERT INTO hoi_dap VALUES ('b','','[\"Hỏi hai\"]','Đáp hai.','',1)")
    rows = doc_dong(conn)
    calls.clear()
    asyncio.run(_nhung_bang_hoi_dap(state, rows))
    moi = [t for t in retrieval_texts(rows[1]) if t not in retrieval_texts(rows[0])]
    assert calls == [moi]
    assert np.allclose(state.hoi_dap_vector["a"], lan_dau["a"])
    assert len(state.hoi_dap_vector["b"]) == len(retrieval_texts(rows[1]))

    calls.clear()
    asyncio.run(_nhung_bang_hoi_dap(state, rows))
    assert calls == []
