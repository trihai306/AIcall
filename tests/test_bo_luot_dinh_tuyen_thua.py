"""Không gọi LLM hai lần khi trọn tài liệu sản phẩm đã có sẵn."""

import asyncio
from types import SimpleNamespace

from backend.config import settings
from backend.pipeline.streaming_pipeline import StreamingPipeline


class _LLMKhongDuocGoi:
    async def stream_response(self, *args, **kwargs):
        raise AssertionError("không được gọi model để định tuyến lượt này")
        yield  # pragma: no cover


def _pipeline():
    p = object.__new__(StreamingPipeline)
    p.llm = _LLMKhongDuocGoi()
    p.rag = None
    return p


def test_cau_tu_nhien_bo_luot_llm_dinh_tuyen_khi_da_co_tron_tai_lieu(monkeypatch):
    monkeypatch.setattr(settings, "ngu_canh_tron_tai_lieu", True)
    metrics = {}
    ra = asyncio.run(_pipeline()._tra_bang_cong_cu(
        "gói này có ưu điểm gì em", SimpleNamespace(), metrics))
    assert ra == ""
    assert metrics["cong_cu_bo_dinh_tuyen"] == "khong_co_dau_hieu_ho_so"


def test_cau_san_pham_khong_tra_lai_tai_lieu_da_co(monkeypatch):
    monkeypatch.setattr(settings, "ngu_canh_tron_tai_lieu", True)
    metrics = {}
    ra = asyncio.run(_pipeline()._tra_bang_cong_cu(
        "lãi suất như vậy hơi cao", SimpleNamespace(), metrics))
    assert ra == ""
    assert metrics["cong_cu_bo_dinh_tuyen"] == "tai_lieu_san_pham_da_co"


def test_hoi_ho_so_rieng_van_giu_duong_tra_nhanh(monkeypatch):
    monkeypatch.setattr(settings, "ngu_canh_tron_tai_lieu", True)
    metrics = {}
    phien = SimpleNamespace(phone="", ngu_canh_khach="", product="vay tín chấp")
    ra = asyncio.run(_pipeline()._tra_bang_cong_cu(
        "dư nợ của anh còn bao nhiêu", phien, metrics))
    assert "chưa gắn số điện thoại" in ra
    assert metrics["cong_cu"] == "tra_ho_so_khach"
    assert metrics["cong_cu_nhanh"] is True
