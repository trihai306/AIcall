"""Tóm tắt phải chờ tới khi không còn cuộc nào đang gọi (12-10-2026)."""

import asyncio

from backend.services import summarizer


def test_cho_toi_khi_het_cuoc_goi(monkeypatch):
    dang_goi = [True, True, False]
    monkeypatch.setattr(summarizer, "_co_cuoc_dang_dien_ra", lambda: dang_goi.pop(0) if dang_goi else False)
    asyncio.run(summarizer.BoTomTat._cho_het_cuoc_goi(toi_da_s=5, nhip_s=0.01))
    assert dang_goi == []


def test_khong_cho_qua_tran(monkeypatch):
    monkeypatch.setattr(summarizer, "_co_cuoc_dang_dien_ra", lambda: True)
    asyncio.run(summarizer.BoTomTat._cho_het_cuoc_goi(toi_da_s=0.05, nhip_s=0.01))


def test_goi_lien_tuc_thi_lua_khe_mo_hinh_ranh(monkeypatch):
    ranh = [False, False, True]
    monkeypatch.setattr(summarizer, "_co_cuoc_dang_dien_ra", lambda: True)
    monkeypatch.setattr(summarizer, "mo_hinh_dang_ranh", lambda lang_s=1.0: ranh.pop(0) if ranh else True)
    asyncio.run(summarizer.BoTomTat._cho_het_cuoc_goi(toi_da_s=5, nhip_s=0.01, cho_khe_sau_s=0))
    assert ranh == []


def test_danh_dau_viec_gap():
    from backend.services import llm_service as ls
    assert ls._viec_gap["dang_chay"] == 0
    with ls.viec_gap():
        assert not ls.mo_hinh_dang_ranh(0)
    assert ls.mo_hinh_dang_ranh(0) and not ls.mo_hinh_dang_ranh(60)
