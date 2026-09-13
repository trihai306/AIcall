"""Amount-independent regression and generated conversational tests."""
from decimal import Decimal
import json
import random

import pytest

from backend.pipeline.du_kien_khoan_vay import quantities, resolve


def users(*texts):
    return [{"role": "user", "content": t} for t in texts]


def spell(n):
    # Independent test-data generator, not the parser under test.
    digits = "không một hai ba bốn năm sáu bảy tám chín".split()
    h, rem = divmod(n, 100)
    t, u = divmod(rem, 10)
    out = [digits[h], "trăm"] if h else []
    if t == 0 and h and u:
        out += ["linh"]
    elif t == 1:
        out += ["mười"]
    elif t > 1:
        out += [digits[t], "mươi"]
    if u:
        out += ["lăm" if u == 5 and t else "mốt" if u == 1 and t > 1 else digits[u]]
    return " ".join(out)


@pytest.mark.parametrize("n", list(range(1, 1000, 7)) + [15, 21, 105, 115, 125, 999])
def test_generated_new_amount_always_wins(n):
    old = (n + 103) * 10**6
    for form in (str(n) + "tr", spell(n) + " triệu", f"{n * 10**6} đồng"):
        state = resolve(users(f"anh vay {old} đồng trong 24 tháng"),
                        f"đổi sang vay {form} trong vòng mười tám tháng")
        assert state.amount.status == "known", (form, state.evidence())
        assert state.amount.value == n * 10**6
        assert state.term.value == 18


@pytest.mark.parametrize("n", [12, 27, 85, 147, 236, 379, 481, 562, 715, 843, 998])
@pytest.mark.parametrize("ending", ["", " được không", " trong vòng mười hai tháng thì mỗi tháng bao nhiêu"])
def test_missing_unit_is_replacement_not_no_update(n, ending):
    state = resolve(users("anh vay 900 triệu"), f"anh muốn vay {spell(n)}{ending}")
    assert state.amount.status == "missing_unit"
    assert state.amount.value is None
    assert state.amount.coefficient == n
    assert resolve(users("anh vay 900 triệu", f"anh muốn vay {spell(n)}{ending}",
                         "mỗi tháng đóng bao nhiêu")).amount.value is None


@pytest.mark.parametrize("spoken, expected", [
    ("1,5 tỷ", 1500000000), ("1.25 tỷ", 1250000000),
    ("một tỷ hai trăm triệu", 1200000000), ("một tỷ rưỡi", 1500000000),
    ("hai phẩy năm triệu", 2500000), ("250.000.000 đồng", 250000000),
    ("375000000 VND", 375000000), ("hai trăm linh năm triệu", 205000000),
])
def test_units_compounds_decimals(spoken, expected):
    state = resolve(text=f"anh muốn vay {spoken}")
    assert state.amount.value == expected, state.evidence()


@pytest.mark.parametrize("sentence, expected", [
    ("không phải 650 triệu mà 275 triệu", 275000000),
    ("275 triệu chứ không phải 650 triệu", 275000000),
    ("anh vay 650 triệu à nhầm 275 triệu", 275000000),
    ("anh muốn vay 275 triệu không phải 650 triệu", 275000000),
])
def test_corrections_and_negated_numbers(sentence, expected):
    state = resolve(users("anh vay 650 triệu"), sentence)
    assert state.amount.value == expected, state.evidence()


@pytest.mark.parametrize("sentence", [
    "anh vay 250 hoặc 350 triệu", "anh vay ba bốn trăm triệu",
    "anh muốn vay 250 triệu hay 350 triệu", "anh muốn vay 300-400 triệu",
    "anh vay hai triệu ba", "đổi sang số khác", "không phải 650 triệu",
])
def test_unresolved_replacement_blocks_stale_amount(sentence):
    state = resolve(users("anh vay 650 triệu"), sentence)
    assert state.amount.status in ("ambiguous", "missing_unit"), state.evidence()
    assert state.amount.value is None


@pytest.mark.parametrize("sentence", [
    "anh muốn vay 275 triệu, lương 18 triệu một tháng",
    "lương anh 18 triệu một tháng và anh muốn vay 275 triệu",
])
def test_income_and_principal_in_same_utterance(sentence):
    state = resolve(users("anh vay 650 triệu trong 36 tháng"), sentence)
    assert state.amount.value == 275000000
    assert state.income.value == 18000000
    assert state.term.value == 36


def test_income_employment_phone_payoff_are_not_loan_updates():
    state = resolve(users("anh vay 275 triệu trong 36 tháng", "lương 18 triệu một tháng",
                          "anh làm công ty ba năm", "số điện thoại 0396130621",
                          "nếu tất toán sau sáu tháng thì sao"))
    assert state.amount.value == 275000000
    assert state.term.value == 36


def test_term_can_update_separately_and_payoff_does_not_replace_it():
    state = resolve(users("anh vay 275 triệu trong 12 tháng", "đổi sang 36 tháng",
                          "nếu trả trước sau sáu tháng thì sao"))
    assert state.amount.value == 275000000
    assert state.term.value == 36, state.evidence()


@pytest.mark.parametrize("phrase, months", [("hai năm", 24), ("mười năm", 120), ("1,5 năm", 18)])
def test_years_become_months(phrase, months):
    state = resolve(text=f"vay 275 triệu trong {phrase}")
    assert state.term.value == months, state.evidence()


def test_unit_confirmation_not_inferred_from_assistant():
    history = users("anh vay 650 triệu", "anh muốn vay hai trăm bảy mươi lăm")
    history += [{"role": "assistant", "content": "Anh cần vay 900 triệu đúng không?"}]
    assert resolve(history, "đúng rồi").amount.value is None
    assert resolve(history, "triệu").amount.value == 275000000
    assert resolve(history, "tỷ").amount.value == 275000000000


def test_assistant_does_not_create_customer_facts():
    state = resolve([{"role": "assistant", "content": "Anh vay 650 triệu trong 36 tháng"}],
                    "mỗi tháng bao nhiêu")
    assert state.amount.value is None and state.term.value is None


def test_cancel_does_not_resurrect_previous_amount():
    state = resolve(users("anh vay 275 triệu trong 36 tháng", "không vay nữa", "tính đi"))
    assert state.amount.value is None and state.term.value is None


def test_reconnect_replay_idempotency_and_interrupted_history():
    history = users("anh vay 650 triệu trong 12 tháng", "anh vay 275 triệu", "đổi sang 36 tháng")
    state = resolve(history)
    assert resolve(json.loads(json.dumps(history))).evidence() == state.evidence()
    assert resolve(history, history[-1]["content"]).evidence() == state.evidence()
    assert resolve(history[:-1]).term.value == 12
    assert resolve(history[:1]).amount.value == 650000000


def test_random_multi_turn_updates_have_no_stale_fallback():
    rng = random.Random(20260912)
    history = []
    for _ in range(120):
        amount = rng.randrange(11, 999)
        history += users(f"anh vay {amount} triệu", f"anh vay {amount + 1}")
        assert resolve(history).amount.value is None
        history += users("triệu", "lương 18 triệu một tháng")
        assert resolve(history).amount.value == (amount + 1) * 10**6


def test_zero_and_nonintegral_months_require_clarification():
    assert resolve(text="anh vay 0 triệu").amount.status == "ambiguous"
    assert resolve(text="anh vay 275 triệu trong 1,2 tháng").term.status == "ambiguous"


def test_rejected_term_does_not_resurrect_old_term():
    state = resolve(users("anh vay 275 triệu trong 36 tháng", "không phải 36 tháng", "tính đi"))
    assert state.amount.value == 275000000
    assert state.term.value is None


def test_rejected_salary_does_not_invalidate_loan_amount():
    state = resolve(users("anh vay 275 triệu trong 36 tháng", "lương anh không phải 18 triệu"))
    assert state.amount.value == 275000000
    assert state.income.value is None


def test_missing_term_unit_has_own_confirmation():
    history = users("anh vay 275 triệu trong 36 tháng", "đổi kỳ hạn thành 24")
    state = resolve(history)
    assert state.term.status == "missing_unit" and state.term.value is None
    assert state.amount.value == 275000000
    assert resolve(history, "tháng").term.value == 24


@pytest.mark.parametrize("new", [95, 175, 285, 360, 475, 690])
@pytest.mark.parametrize("phrase", ["anh nói {n} triệu", "tôi bảo {n} triệu", "đổi xuống {n} triệu", "sửa lại {n} triệu", "{n} triệu chứ"])
def test_general_repair_language_without_repeating_vay(new, phrase):
    state = resolve(users("anh vay 850 triệu"), phrase.format(n=new))
    assert state.amount.value == new * 10**6, state.evidence()


@pytest.mark.parametrize("unrelated", ["khoản vay cũ 100 triệu trong 48 tháng", "dư nợ 95 triệu",
                                      "hạn mức vay 500 triệu", "vay tối đa 500 triệu",
                                      "nếu tất toán trong vòng sáu tháng thì sao",
                                      "sao kê trong ba tháng"])
def test_existing_contract_and_limit_are_not_new_demand(unrelated):
    state = resolve(users("anh vay 275 triệu trong 24 tháng"), unrelated)
    assert state.amount.value == 275000000
    assert state.term.value == 24


@pytest.mark.parametrize("question", [
    "nhắc lại số tiền anh nói lúc đầu", "số tiền anh đã nói là bao nhiêu",
    "kỳ hạn anh nói là bao nhiêu", "thu nhập anh nói là bao nhiêu",
])
def test_readback_questions_do_not_modify_facts(question):
    history = users("anh vay 275 triệu trong 24 tháng", "lương anh 18 triệu")
    before = resolve(history)
    assert resolve(history, question).evidence() == before.evidence()


@pytest.mark.parametrize("sentence, field", [
    ("đổi kỳ hạn sang số khác", "term"), ("sửa thu nhập lại", "income"),
    ("anh muốn vay vài tỷ", "amount"), ("anh muốn vay âm 200 triệu", "amount"),
    ("anh muốn vay -200 triệu", "amount"),
])
def test_unresolved_update_invalidates_only_its_own_field(sentence, field):
    history = users("anh vay 275 triệu trong 24 tháng", "lương anh 18 triệu")
    before = resolve(history)
    after = resolve(history, sentence)
    assert getattr(after, field).status == "ambiguous", after.evidence()
    for other in {"amount", "term", "income"} - {field}:
        assert getattr(after, other) == getattr(before, other)


@pytest.mark.parametrize("sentence, expected", [
    ("anh vay nửa tỷ", 500000000), ("anh vay nửa triệu", 500000),
])
def test_half_money_unit(sentence, expected):
    assert resolve(users("anh vay 850 triệu"), sentence).amount.value == expected


@pytest.mark.parametrize("sentence", ["275 trong 24 tháng", "275 trong vòng hai năm"])
def test_numeric_reply_with_term_invalidates_old_amount(sentence):
    state = resolve(users("anh vay 850 triệu trong 36 tháng"), sentence)
    assert state.amount.status == "missing_unit", state.evidence()
    assert state.amount.coefficient == 275
    assert state.term.value == 24


@pytest.mark.parametrize("sentence", ["275 hay 350 triệu", "275 triệu hoặc 350 triệu"])
def test_numeric_reply_alternatives_remain_ambiguous(sentence):
    assert resolve(users("anh vay 850 triệu"), sentence).amount.status == "ambiguous"


@pytest.mark.parametrize("reply", ["triệu", "triệu đồng", "triệu đồng ạ", "là triệu nhé"])
def test_explicit_unit_reply_allows_polite_words(reply):
    history = users("anh vay 850 triệu", "anh vay 275")
    assert resolve(history, reply).amount.value == 275000000


def test_unit_confirmation_does_not_bypass_term_validation():
    history = users("anh vay 275 triệu trong 24 tháng", "đổi kỳ hạn thành 1,2")
    assert resolve(history, "tháng").term.status == "ambiguous"


def test_scope_survives_mixed_new_demand_and_old_contract():
    state = resolve(text="anh vay 275 triệu trong 24 tháng, dư nợ cũ 100 triệu trong 48 tháng")
    assert state.amount.value == 275000000 and state.term.value == 24


@pytest.mark.parametrize("number", range(1, 10))
def test_single_digit_spoken_update_does_not_retain_old_amount(number):
    history = users("anh vay 850 triệu")
    state = resolve(history, f"anh muốn vay {spell(number)}")
    assert state.amount.status == "missing_unit", state.evidence()
    assert state.amount.coefficient == number


@pytest.mark.parametrize("sentence", ["anh vay năm nay", "lương năm nay của anh vẫn vậy"])
def test_calendar_year_is_not_a_five_unit_loan(sentence):
    history = users("anh vay 275 triệu trong 24 tháng", "lương anh 18 triệu")
    assert resolve(history, sentence).evidence() == resolve(history).evidence()


# --- Cặp số nói tắt cho KỲ HẠN: "ba sáu tháng" = 36 tháng -------------------
#
# Cuộc gọi thật 7db3f780 (13-09-2026): khách nói "vay một trăm triệu trong ba
# sáu tháng", bộ đọc trả `term=ambiguous` rồi AI hỏi lại "vay bao nhiêu tháng"
# SÁU lượt liền. Người Việt nói tắt hai chữ số cho kỳ hạn rất phổ biến
# (hai bốn, ba sáu, bốn tám). Chỉ nhận cặp có chữ số sau CHẴN và chữ số đầu
# từ 2 trở lên: "hai ba tháng" có thể là "2-3 tháng" nên vẫn để mơ hồ.
@pytest.mark.parametrize("cau, thang", [
    ("vay một trăm triệu trong ba sáu tháng", 36),
    ("vay trong hai bốn tháng", 24),
    ("bốn tám tháng", 48),
    ("ba sáu tháng thì mỗi tháng bao nhiêu", 36),
])
def test_cap_so_noi_tat_ky_han(cau, thang):
    state = resolve(users("anh vay một trăm triệu"), cau)
    assert state.term.status == "known", state.evidence()
    assert state.term.value == thang


@pytest.mark.parametrize("cau", ["vay trong hai ba tháng", "một hai tháng", "năm năm tháng"])
def test_cap_so_co_the_la_khoang_thi_van_mo_ho(cau):
    state = resolve(users("anh vay một trăm triệu"), cau)
    assert state.term.status != "known", state.evidence()


def test_cap_so_noi_tat_khong_ap_cho_tien():
    # "ba sáu triệu" không được đoán là 36 triệu: tiền để mơ hồ, hỏi lại đơn vị.
    state = resolve(None, "anh vay ba sáu triệu")
    assert state.amount.value != 36 * 10**6
