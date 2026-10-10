"""Hard conversational regressions from the 10-10 customer-quality corpus."""
from decimal import Decimal
import json

import pytest

from backend.pipeline.du_kien_khoan_vay import (
    chuan_hoa_so_khong_dau,
    is_readback,
    quantities,
    resolve,
)


@pytest.fixture(autouse=True)
def _khong_tu_doan_don_vi(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "suy_don_vi_trieu", False)


def users(*texts):
    return [{"role": "user", "content": text} for text in texts]


@pytest.mark.parametrize("denial", [
    "Anh có nói vay ba trăm đâu, vẫn hai trăm mà.",
    "Anh không nói vay ba trăm, vẫn hai trăm mà.",
    "Không phải ba trăm, vẫn hai trăm.",
])
def test_scoped_denial_rejects_wrong_number_and_reaffirms_old_amount(denial):
    history = users("anh vay 200 triệu trong 24 tháng")
    state = resolve(history, denial)
    assert state.amount.status == "known", state.evidence()
    assert state.amount.value == 200_000_000
    assert state.term.value == 24


def test_true_correction_unknown_replacement_and_cancellation_remain_distinct():
    history = users("anh vay 200 triệu trong 24 tháng")

    corrected = resolve(history, "à không anh vay ba trăm triệu cơ")
    assert not is_readback("à không anh vay ba trăm triệu cơ")
    assert corrected.amount.value == 300_000_000 and corrected.term.value == 24

    unknown = resolve(history, "đổi sang số khác")
    assert unknown.amount.status == "ambiguous" and unknown.amount.value is None
    assert unknown.term.value == 24

    cancelled = resolve(history, "không vay nữa")
    assert cancelled.amount.status == cancelled.term.status == "cancelled"
    assert cancelled.amount.value is None and cancelled.term.value is None


def test_scoped_denial_can_confirm_a_different_explicit_replacement():
    history = users("anh vay 200 triệu trong 24 tháng")
    state = resolve(history, "Không phải ba trăm triệu, vẫn hai trăm năm mươi triệu.")
    assert state.amount.value == 250_000_000
    assert state.term.value == 24


def test_retracted_amount_stays_unresolved_across_reconnect_and_later_term():
    history = [
        {"role": "assistant", "content": "Anh cần vay bao nhiêu tiền ạ?"},
        {"role": "user", "content": "Hai trăm... à khoan, không, mấy trăm gì đấy."},
    ]
    retracted = resolve(history)
    assert retracted.amount.status == "ambiguous", retracted.evidence()
    assert retracted.amount.value is None
    assert resolve(json.loads(json.dumps(history))).evidence() == retracted.evidence()

    later = resolve(history, "Ba năm đi, nhưng anh chưa quyết định số tiền.")
    assert later.amount.status == "ambiguous" and later.amount.value is None
    assert later.term.status == "known" and later.term.value == 36


@pytest.mark.parametrize(("text", "normalized"), [
    ("sau thang", "sáu tháng"),
    ("the mot nam", "the một năm"),
    ("vay200trieu24thang", "vay200triệu24tháng"),
])
def test_ascii_numeric_normalization_is_local_and_length_preserving(text, normalized):
    assert chuan_hoa_so_khong_dau(text) == normalized
    assert len(normalized) == len(text)


@pytest.mark.parametrize("text", [
    "sau khi",
    "trong nam nay",
    "trong năm nay",
    "khong can",
    "qua ngan hang",
    "năm đầu miễn rồi năm sau có tự thu không",
])
def test_ascii_ordinary_prose_is_not_converted_to_quantities(text):
    assert chuan_hoa_so_khong_dau(text) == text.lower()
    assert quantities(text) == []
    state = resolve(text=text)
    assert state.amount.status == state.term.status == "unknown"


def test_sau_before_an_accented_duration_remains_an_ordinary_preposition():
    text = "Anh bán nhà sau một năm, trả trước có mất phí không?"
    assert chuan_hoa_so_khong_dau(text) == text.lower()
    assert [(q.raw, q.value, q.kind) for q in quantities(text)] == [
        ("một năm", Decimal(12), "duration")
    ]


@pytest.mark.parametrize("text", [
    "toi vay sau thang nay",
    "toi vay sau thang toi",
    "toi vay sau thang sau",
    "tôi vay sau thang này",
    "tôi vay sau thang tới",
])
def test_sau_thang_with_right_deictic_is_a_time_phrase_not_six_months(text):
    assert chuan_hoa_so_khong_dau(text) == text.lower()
    assert quantities(text) == []
    state = resolve(text=text)
    assert state.term.status == "unknown" and state.term.value is None


@pytest.mark.parametrize("text", ["sau thang", "vay sau thang", "vay sau thang nhe"])
def test_standalone_sau_thang_remains_numeric_six_months(text):
    found = quantities(text)
    assert len(found) == 1
    assert (found[0].raw, found[0].value, found[0].kind) == (
        "sau thang", Decimal(6), "duration")
    assert text[found[0].start:found[0].end] == found[0].raw
    if text.startswith("vay"):
        assert resolve(text=text).term.value == 6


@pytest.mark.parametrize("text", ["sau khi", "vay sau khi duoc duyet", "sau khi vay"])
def test_sau_khi_never_becomes_six_or_a_term(text):
    assert chuan_hoa_so_khong_dau(text) == text.lower()
    assert quantities(text) == []
    assert resolve(text=text).term.status == "unknown"


@pytest.mark.parametrize(("text", "raw", "value", "kind", "span"), [
    ("sau thang", "sau thang", Decimal(6), "duration", (0, 9)),
    ("the mot nam", "mot nam", Decimal(12), "duration", (4, 11)),
])
def test_ascii_duration_keeps_original_raw_text_and_span(text, raw, value, kind, span):
    found = quantities(text)
    assert [(q.raw, q.value, q.kind, (q.start, q.end)) for q in found] == [
        (raw, value, kind, span)
    ]


def test_compact_ascii_amount_and_term_keep_raw_spans_and_resolve_together():
    text = "vay200trieu24thang"
    assert [(q.raw, q.value, q.kind, (q.start, q.end)) for q in quantities(text)] == [
        ("200trieu", Decimal(200_000_000), "money", (3, 11)),
        ("24thang", Decimal(24), "duration", (11, 18)),
    ]
    state = resolve(text=text)
    assert state.amount.value == 200_000_000
    assert state.term.value == 24


def test_cancelled_and_unknown_states_replay_and_recover_only_from_explicit_new_facts():
    cancelled_history = users("anh vay 200 triệu trong 24 tháng", "không vay nữa")
    cancelled = resolve(json.loads(json.dumps(cancelled_history)))
    assert cancelled.amount.status == cancelled.term.status == "cancelled"
    assert resolve(cancelled_history, "để anh nghĩ đã").evidence() == cancelled.evidence()

    recovered = resolve(cancelled_history, "giờ anh muốn vay 300 triệu trong 36 tháng")
    assert recovered.amount.value == 300_000_000 and recovered.term.value == 36

    unknown_history = users("anh vay 200 triệu trong 24 tháng", "đổi sang số khác")
    unknown = resolve(json.loads(json.dumps(unknown_history)))
    assert unknown.amount.status == "ambiguous" and unknown.term.value == 24
    later_term = resolve(unknown_history, "ba năm đi, nhưng chưa quyết định số tiền")
    assert later_term.amount.status == "ambiguous" and later_term.amount.value is None
    assert later_term.term.value == 36


@pytest.mark.parametrize("text", [
    "lương 20 triệu",
    "lương anh 20 triệu",
    "chị có thu nhập 20 triệu một tháng",
])
def test_direct_income_is_owned_by_the_caller(text):
    income = resolve(text=text).income
    assert income.value == 20_000_000
    assert income.owner == "self"
    assert income.evidence()["owner"] == "self"


@pytest.mark.parametrize("text", [
    "thu nhập hai vợ chồng 40 triệu",
    "thu nhập hai vợ chồng chị là bốn mươi triệu một tháng",
    "vợ chồng tôi thu nhập 40 triệu",
    "tổng thu nhập gia đình 40 triệu",
])
def test_joint_income_is_known_but_typed_as_household(text):
    income = resolve(text=text).income
    assert income.value == 40_000_000
    assert income.owner == "household"
    assert income.evidence()["owner"] == "household"


@pytest.mark.parametrize("text", [
    "Vợ tôi lương 20 triệu",
    "Chồng tôi lương 20 triệu",
    "Bạn tôi lương 20 triệu",
    "Mẹ tôi lương 20 triệu",
    "Đồng nghiệp tôi lương 20 triệu",
    "Ngân hàng nói lương 20 triệu mới được vay",
    "Ngân hàng yêu cầu thu nhập 20 triệu mới cho vay",
    "Ngân hàng yêu cầu thu nhập hai vợ chồng 40 triệu mới cho vay",
    "Vợ chồng bạn tôi lương 40 triệu",
    "Ngân hàng nói lương3.4triệu hoặc5triệu mới được vay",
    "Vợ tôi lương3.4triệu hoặc5triệu",
])
def test_third_party_or_quoted_income_is_not_customer_income(text):
    income = resolve(text=text).income
    assert income.status == "unknown" and income.value is None
    assert income.owner == ""


@pytest.mark.parametrize("quoted", [
    "Vợ tôi lương 20 triệu",
    "Bạn tôi lương 20 triệu",
    "Ngân hàng nói lương 20 triệu mới được vay",
])
def test_third_party_income_does_not_overwrite_prior_self_income(quoted):
    history = users("lương anh 12 triệu")
    income = resolve(history, quoted).income
    assert income.value == 12_000_000
    assert income.owner == "self"
    assert income.raw == "12 triệu"


@pytest.mark.parametrize("text", [
    "bạn tôi lương 6 triệu, còn anh 12 triệu",
    "anh lương 12 triệu, còn bạn tôi 6 triệu",
])
def test_mixed_clauses_keep_only_the_callers_income(text):
    income = resolve(text=text).income
    assert income.status == "known" and income.value == 12_000_000
    assert income.owner == "self"


def test_household_clause_does_not_relabel_later_personal_income():
    income = resolve(text="thu nhập hai vợ chồng 40 triệu, còn lương anh 12 triệu").income
    assert income.status == "ambiguous" and income.value is None
    # Both accepted quantities intentionally remain unresolved rather than
    # choosing one, but provenance follows the latest personal clause.
    assert income.owner == "self"


def test_self_income_correction_preserves_self_provenance():
    history = users("lương anh 12 triệu")
    income = resolve(history, "không phải 12 triệu mà 15 triệu").income
    assert income.value == 15_000_000
    assert income.owner == "self"


@pytest.mark.parametrize(("text", "expected"), [
    ("lương anh ba chục triệu, vợ anh hai chục triệu", 30_000_000),
    ("lương anh ba chục triệu vợ anh hai chục triệu", 30_000_000),
    ("lương anh ba triệu vợ anh hai mươi triệu", 3_000_000),
])
def test_split_spousal_income_keeps_only_the_callers_own_amount(text, expected):
    income = resolve(text=text).income
    assert income.status == "known" and income.value == expected
    assert income.owner == "self"


@pytest.mark.parametrize("text", [
    "thu nhập hai vợ chồng 40 triệu",
    "tổng thu nhập gia đình 40 triệu",
])
def test_explicit_household_aggregate_remains_household(text):
    income = resolve(text=text).income
    assert income.status == "known" and income.value == 40_000_000
    assert income.owner == "household"


def test_income_provenance_replays_and_does_not_change_amount_term_evidence_shape():
    history = users("anh vay 200 triệu trong 24 tháng", "lương anh 12 triệu")
    first = resolve(history)
    replayed = resolve(json.loads(json.dumps(history)))
    assert replayed.evidence() == first.evidence()
    assert first.income.owner == "self"
    assert "owner" not in first.amount.evidence()
    assert "owner" not in first.term.evidence()


@pytest.mark.parametrize("text", [
    "Anh nghe nói yêu cầu lương20triệu mới được vay đúng không?",
    "Anh nghe họ bảo lương20triệu mới được vay đúng không?",
    "Anh nghe người ta nói thu nhập20triệu mới được vay à?",
    "Hồ sơ yêu cầu thu nhập20triệu đúng không em?",
    "Hồ sơ cần lương20triệu mới được duyệt đúng không?",
    "Nhân viên bên em bảo lương20triệu mới được vay",
    "Người yêu tôi lương20triệu",
    "Sếp của tôi lương20triệu",
    "Quản lý của tôi thu nhập20triệu",
    "Nhân viên của tôi lương20triệu",
    "Bạn gái tôi lương20triệu",
    "Chị tôi lương20triệu",
])
def test_reported_thresholds_and_broader_third_parties_are_not_caller_income(text):
    income = resolve(text=text).income
    assert income.status == "unknown" and income.value is None
    assert income.owner == ""


@pytest.mark.parametrize("reported", [
    "Anh nghe nói yêu cầu lương 20 triệu thì anh có vay được không?",
    "Anh nghe họ bảo lương 20 triệu mới được vay đúng không?",
    "Hồ sơ yêu cầu thu nhập 20 triệu đúng không?",
    "Người yêu tôi lương 20 triệu",
    "Sếp của tôi lương 20 triệu",
    "Chị tôi lương 20 triệu",
])
def test_reported_income_never_overwrites_known_caller_income(reported):
    income = resolve(users("lương anh 12 triệu"), reported).income
    assert income.status == "known" and income.value == 12_000_000
    assert income.owner == "self" and income.raw == "12 triệu"


@pytest.mark.parametrize("text", [
    "Anh làm ngân hàng, lương20triệu",
    "Anh là nhân viên ngân hàng lương20triệu",
    "Anh là sếp ngân hàng, thu nhập20triệu",
    "Thu nhập của tôi20triệu",
])
def test_callers_job_title_does_not_turn_own_salary_into_reported_income(text):
    income = resolve(text=text).income
    assert income.status == "known" and income.value == 20_000_000
    assert income.owner == "self"


@pytest.mark.parametrize("text", [
    "Anh lương30triệu, người yêu anh lương20triệu",
    "Lương anh30triệu, sếp của anh lương20triệu",
])
def test_direct_self_salary_wins_over_separately_qualified_third_party_salary(text):
    income = resolve(text=text).income
    assert income.status == "known" and income.value == 30_000_000
    assert income.owner == "self"


@pytest.mark.parametrize("text", [
    "lương anh ba chục triệu, vợ anh hai chục triệu, căn nhà giá một trăm triệu",
    "lương anh ba chục triệu, căn hộ trị giá một trăm triệu",
    "lương anh ba chục triệu, xe giá khoảng một trăm triệu",
])
def test_property_price_cannot_inherit_an_earlier_income_anchor(text):
    state = resolve(text=text)
    assert state.income.status == "known" and state.income.value == 30_000_000
    assert state.income.owner == "self" and state.income.raw == "ba chục triệu"
