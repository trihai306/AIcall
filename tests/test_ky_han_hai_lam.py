"""Khóa biên mơ hồ ``hai lăm`` mà không làm hỏng kỳ hạn 15/45/55."""

from decimal import Decimal

from backend.pipeline.du_kien_khoan_vay import (
    ky_han_suy_ra,
    resolve,
    voi_tran_san_pham,
)


def test_hai_lam_khong_tu_suy_thang_cho_ca_co_dau_va_ascii(monkeypatch):
    from backend import config

    monkeypatch.setattr(config.settings, "suy_don_vi_trieu", True)
    with voi_tran_san_pham(500_000_000, 60):
        assert ky_han_suy_ra(Decimal(25), "hai lăm") is None
        assert ky_han_suy_ra(Decimal(25), "hai lam") is None


def test_chi_hai_lam_bi_giu_lai_con_15_45_55_van_suy_thang(monkeypatch):
    from backend import config

    monkeypatch.setattr(config.settings, "suy_don_vi_trieu", True)
    with voi_tran_san_pham(500_000_000, 60):
        assert ky_han_suy_ra(Decimal(15), "mười lăm") == 15
        assert ky_han_suy_ra(Decimal(45), "bốn lăm") == 45
        assert ky_han_suy_ra(Decimal(55), "năm lăm") == 55


def test_hai_lam_co_don_vi_thang_van_la_25_thang(monkeypatch):
    from backend import config

    monkeypatch.setattr(config.settings, "suy_don_vi_trieu", True)
    with voi_tran_san_pham(500_000_000, 60):
        state = resolve(text="Anh vay hai lăm tháng")

    assert state.term.status == "known"
    assert state.term.value == Decimal(25)

