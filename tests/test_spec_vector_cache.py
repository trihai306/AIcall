"""Không nhúng lại cùng một transcript đã được BGE-M3 xử lý lúc đoán trước."""

from types import SimpleNamespace

import numpy as np

import backend.pipeline.streaming_pipeline as streaming
from backend.pipeline.session_manager import CallSession


class RagGia:
    def __init__(self):
        self.calls = []

    def embed(self, ds):
        ds = list(ds)
        self.calls.append(ds)
        return np.asarray([[1.0, 0.0] for _ in ds], dtype=np.float32)


def _pipe(rag):
    pipe = object.__new__(streaming.StreamingPipeline)
    pipe.rag = rag
    return pipe


def _state(monkeypatch, *, bang=False):
    import backend.main as main

    if bang:
        st = SimpleNamespace(
            hoi_dap={
                "lai": {
                    "id": "lai",
                    "san_pham": "",
                    "tra_loi": "Lãi suất theo tài liệu.",
                }
            },
            hoi_dap_vector={
                "lai": np.asarray([[1.0, 0.0]], dtype=np.float32),
            },
            kho_vector={},
        )
    else:
        st = SimpleNamespace(
            hoi_dap={},
            hoi_dap_vector={},
            kho_vector={
                "lai": np.asarray([[1.0, 0.0]], dtype=np.float32),
            },
        )
    monkeypatch.setattr(main, "app_state", st, raising=False)
    return st


def test_faq_dung_lai_vector_khi_text_khop_tuyet_doi(monkeypatch):
    _state(monkeypatch, bang=True)
    rag = RagGia()
    pipe = _pipe(rag)
    session = SimpleNamespace(product="")
    cache = ("lai suat", np.asarray([1.0, 0.0], dtype=np.float32))

    dong = pipe._tra_bang_hoi_dap("lai suat", session, vector_cache=cache)

    assert dong["id"] == "lai"
    assert rag.calls == []


def test_faq_text_thay_doi_thi_phai_nhung_lai(monkeypatch):
    _state(monkeypatch, bang=True)
    rag = RagGia()
    pipe = _pipe(rag)
    session = SimpleNamespace(product="")
    cache = ("lai suat", np.asarray([1.0, 0.0], dtype=np.float32))

    dong = pipe._tra_bang_hoi_dap("con lai suat", session, vector_cache=cache)

    assert dong["id"] == "lai"
    assert rag.calls == [["con lai suat"]]


def test_phan_loai_dong_bo_dung_lai_vector_spec(monkeypatch):
    _state(monkeypatch)
    rag = RagGia()
    pipe = _pipe(rag)
    session = SimpleNamespace(
        tinh_huong=None,
        spec_stt=(1234, "lai suat"),
        spec_vector=("lai suat", np.asarray([1.0, 0.0], dtype=np.float32)),
        da_tu_van=set(),
    )

    pipe._phan_loai_dong_bo(session)

    assert session.tinh_huong[1] == "lai"
    assert rag.calls == []


def test_clear_speculation_xoa_vector_cache():
    session = CallSession()
    session.spec_vector = ("lai suat", np.asarray([1.0, 0.0], dtype=np.float32))

    session.clear_speculation()

    assert session.spec_vector is None

