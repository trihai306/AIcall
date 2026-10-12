"""Regression: ``sua/doi + đồ vật`` là mục đích, không phải sửa dữ kiện vay."""
from pathlib import Path

import pytest

from backend.pipeline.du_kien_khoan_vay import quantities, resolve
from backend.pipeline.tra_loi_khoan_vay import tra_loi


ROOT = Path(__file__).resolve().parents[1]
TC = (ROOT / "knowledge/products/vay_tin_chap.md").read_text(encoding="utf-8")


def users(*texts):
    return [{"role": "user", "content": text} for text in texts]


@pytest.mark.parametrize("purpose", [
    "doi xe thi can 200 trieu",
    "đổi xe thì cần 200 triệu",
    "sua bep het tam 80 trieu",
    "sửa bếp hết tầm 80 triệu",
])
def test_purpose_with_sua_doi_preserves_prior_income_and_quantity_offsets(purpose):
    state = resolve(users("luong anh 12 trieu"), purpose)

    assert state.income.status == "known"
    assert state.income.value == 12_000_000
    assert state.income.owner == "self"
    assert state.amount.status == "unknown"
    number = quantities(purpose)[0]
    assert purpose[number.start:number.end] == number.raw


@pytest.mark.parametrize("purpose", [
    "doi xe thi can 200 trieu",
    "sua bep het tam 80 trieu",
])
def test_ascii_purpose_does_not_invalidate_an_existing_principal(purpose):
    state = resolve(users("anh vay 300 trieu"), purpose)

    assert state.amount.status == "known"
    assert state.amount.value == 300_000_000


@pytest.mark.parametrize(("history", "correction", "field", "expected"), [
    ("luong anh 12 trieu", "sua lai 15 trieu", "income", 15_000_000),
    ("lương anh 12 triệu", "sua lai 15 triệu", "income", 15_000_000),
    ("anh vay 300 trieu", "sua lai 150 trieu", "amount", 150_000_000),
    ("anh vay 300 triệu", "sua lai 150 triệu", "amount", 150_000_000),
])
def test_sua_lai_without_a_purpose_noun_remains_a_real_correction(
        history, correction, field, expected):
    state = resolve(users(history), correction)

    assert getattr(state, field).status == "known"
    assert getattr(state, field).value == expected


@pytest.mark.parametrize("purpose", [
    "doi xe thi can 200 trieu",
    "sua bep het tam 80 trieu",
])
def test_affordability_uses_real_income_after_ascii_purpose(purpose):
    history = users("luong anh 12 trieu", purpose)

    code, answer = tra_loi(
        "anh vay 100 triệu trong 24 tháng, khoản trả hàng tháng có quá sức không?",
        TC,
        history=history,
    )

    assert code == "can_nhac_kha_nang_tra"
    assert "tháng đầu khoảng 4,8 triệu đồng" in answer
    assert "thấp hơn mức thu nhập 12 triệu đồng" in answer
    assert "mức thu nhập 200 triệu đồng" not in answer
