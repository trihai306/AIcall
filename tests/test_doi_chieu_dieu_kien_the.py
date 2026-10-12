"""Numeric card-condition comparison stays grounded in customer/source facts."""
import pytest

from backend.core.banking_fact_precheck import direct_condition_answer


SOURCE = """THÔNG TIN THAM KHẢO:
## Các loại thẻ
1. Thẻ Classic: Hạn mức 10-50 triệu, phí thường niên 200.000đ/năm
2. Thẻ Gold: Hạn mức 30-200 triệu, phí thường niên 400.000đ/năm
3. Thẻ Platinum: Hạn mức 100-500 triệu, phí thường niên 800.000đ/năm
## Điều kiện mở thẻ
- Từ 18 tuổi trở lên
- Thu nhập từ 5 triệu đồng/tháng
- CMND/CCCD còn hiệu lực
"""
QUESTION = "Nếu đối chiếu điều kiện công bố thì đã chắc chắn được cấp thẻ và hạn mức cao nhất chưa?"


def user(content):
    return {"role": "user", "content": content}


def assistant(content):
    return {"role": "assistant", "content": content}


def ask(age, income, tier="Gold"):
    return direct_condition_answer([
        user(f"Tôi muốn mở thẻ {tier} và quan tâm hạn mức."),
        user(f"Tôi {age} tuổi, thu nhập riêng {income} triệu mỗi tháng."),
        user(QUESTION),
    ], SOURCE)


@pytest.mark.parametrize(("age", "income", "age_result", "income_result"), [
    (17, 3, "17 tuổi chưa đạt mức tối thiểu 18 tuổi",
     "3 triệu/tháng chưa đạt mức tối thiểu 5 triệu/tháng"),
    (17, 12, "17 tuổi chưa đạt mức tối thiểu 18 tuổi",
     "12 triệu/tháng đạt mức tối thiểu 5 triệu/tháng"),
    (18, 5, "18 tuổi đạt mức tối thiểu 18 tuổi",
     "5 triệu/tháng đạt mức tối thiểu 5 triệu/tháng"),
    (30, 4, "30 tuổi đạt mức tối thiểu 18 tuổi",
     "4 triệu/tháng chưa đạt mức tối thiểu 5 triệu/tháng"),
    (35, 8, "35 tuổi đạt mức tối thiểu 18 tuổi",
     "8 triệu/tháng đạt mức tối thiểu 5 triệu/tháng"),
])
def test_real_boundaries_compare_both_customer_facts(age, income, age_result, income_result):
    answer = ask(age, income)
    assert age_result in answer
    assert income_result in answer
    assert "Thẻ Gold có dải hạn mức 30-200 triệu" in answer
    assert "chưa thể khẳng định được cấp thẻ hay được hạn mức cao nhất" in answer


def test_household_and_other_people_are_not_used_as_personal_facts():
    household = direct_condition_answer([
        user("Tôi muốn thẻ Gold."), user("Tôi 30 tuổi."),
        user("Tổng thu nhập gia đình là 15 triệu mỗi tháng."), user(QUESTION),
    ], SOURCE)
    assert "thu nhập hộ gia đình chưa thay cho thu nhập riêng" in household

    other = direct_condition_answer([
        user("Tôi muốn thẻ Gold."),
        user("Con trai tôi 17 tuổi và có thu nhập 35 triệu mỗi tháng."),
        user(QUESTION),
    ], SOURCE)
    assert "cần xác nhận tuổi hiện tại của người đứng tên" in other
    assert "cần xác nhận một mức thu nhập riêng" in other
    assert "17 tuổi chưa đạt" not in other and "35 triệu/tháng đạt" not in other

    mixed = direct_condition_answer([
        user("Tôi muốn thẻ Gold và thu nhập riêng của tôi là 8 triệu."),
        user("Con tôi 17 tuổi và có thu nhập 35 triệu mỗi tháng."),
        user(QUESTION),
    ], SOURCE)
    assert "cần xác nhận tuổi hiện tại của người đứng tên" in mixed
    assert "8 triệu/tháng đạt" in mixed
    assert "17 tuổi chưa đạt" not in mixed and "35 triệu/tháng" not in mixed


def test_latest_corrections_win_and_retractions_request_verification():
    corrected = direct_condition_answer([
        user("Tôi muốn thẻ Gold."),
        user("Tôi 17 tuổi, thu nhập riêng 4 triệu mỗi tháng."),
        user("Tôi sửa lại: 30 tuổi, không phải 4 triệu mà là 8 triệu."),
        user(QUESTION),
    ], SOURCE)
    assert "30 tuổi đạt" in corrected and "8 triệu/tháng đạt" in corrected
    assert "17 tuổi" not in corrected and "4 triệu/tháng" not in corrected

    retracted = direct_condition_answer([
        user("Tôi muốn thẻ Gold."),
        user("Tôi 30 tuổi, thu nhập riêng 8 triệu mỗi tháng."),
        user("Rút lại thông tin tuổi và thu nhập đó."), user(QUESTION),
    ], SOURCE)
    assert "cần xác nhận tuổi hiện tại" in retracted
    assert "cần xác nhận một mức thu nhập riêng" in retracted


def test_unknown_or_multiple_values_and_tiers_are_never_selected_arbitrarily():
    answer = direct_condition_answer([
        user("Tôi đang cân nhắc thẻ Gold hay Platinum."),
        user("Tôi 18 hay 30 tuổi, thu nhập riêng 5 hoặc 8 triệu."),
        user(QUESTION),
    ], SOURCE)
    assert "cần xác nhận tuổi hiện tại" in answer
    assert "cần xác nhận một mức thu nhập riêng" in answer
    assert "Cần xác nhận một loại thẻ cụ thể" in answer
    assert "30-200 triệu" not in answer and "100-500 triệu" not in answer


def test_current_source_only_and_no_assistant_or_future_fact_leakage():
    messages = [
        user("Tôi muốn thẻ Gold."),
        assistant("Lịch cho thấy tháng sau anh đủ 40 tuổi, lương 40 triệu."),
        user("Hiện tôi 17 tuổi, sang năm tôi 18 tuổi; thu nhập riêng 8 triệu."),
        user("Nguồn cũ tôi nghe nói yêu cầu 21 tuổi và thu nhập 10 triệu."),
        user(QUESTION),
    ]
    answer = direct_condition_answer(messages, SOURCE)
    assert "17 tuổi chưa đạt mức tối thiểu 18 tuổi" in answer
    assert "8 triệu/tháng đạt mức tối thiểu 5 triệu/tháng" in answer
    assert "21 tuổi" not in answer and "10 triệu/tháng" not in answer
    assert "40 tuổi" not in answer and "40 triệu/tháng" not in answer


@pytest.mark.parametrize("claim", [
    "Bố60tuổi và lương30triệu.",
    "Mẹ 60 tuổi và thu nhập 30 triệu.",
    "Vợ 30 tuổi và lương 30 triệu.",
    "Quản lý 45 tuổi và thu nhập 30 triệu.",
])
def test_bare_other_person_subject_never_becomes_the_caller(claim):
    answer = direct_condition_answer([
        user("Tôi muốn thẻ Gold."), user(claim), user(QUESTION),
    ], SOURCE)
    assert "cần xác nhận tuổi hiện tại của người đứng tên" in answer
    assert "cần xác nhận một mức thu nhập riêng" in answer
    assert "60 tuổi đạt" not in answer and "30 triệu/tháng đạt" not in answer


def test_hypothetical_facts_are_not_actual_and_do_not_replace_prior_actual_facts():
    unknown = direct_condition_answer([
        user("Tôi muốn thẻ Gold."),
        user("Nếu tôi 30 tuổi và thu nhập 8 triệu thì sao?"), user(QUESTION),
    ], SOURCE)
    assert "cần xác nhận tuổi hiện tại" in unknown
    assert "cần xác nhận một mức thu nhập riêng" in unknown
    assert "30 tuổi đạt" not in unknown and "8 triệu/tháng đạt" not in unknown

    prior = direct_condition_answer([
        user("Tôi muốn thẻ Gold."),
        user("Hiện tôi 25 tuổi và thu nhập riêng 6 triệu."),
        user("Nếu tôi 30 tuổi và thu nhập 8 triệu thì sao?"), user(QUESTION),
    ], SOURCE)
    assert "25 tuổi đạt" in prior and "6 triệu/tháng đạt" in prior
    assert "30 tuổi đạt" not in prior and "8 triệu/tháng đạt" not in prior

    future = direct_condition_answer([
        user("Tôi muốn thẻ Gold."),
        user("Sang năm tôi 30 tuổi và thu nhập 8 triệu."), user(QUESTION),
    ], SOURCE)
    assert "cần xác nhận tuổi hiện tại" in future
    assert "cần xác nhận một mức thu nhập riêng" in future


def test_actual_self_clause_after_other_person_supplies_both_owned_facts():
    answer = direct_condition_answer([
        user("Tôi muốn thẻ Gold."),
        user("Bố 60 tuổi và lương 30 triệu, còn tôi 30 tuổi và thu nhập riêng 8 triệu."),
        user(QUESTION),
    ], SOURCE)
    assert "30 tuổi đạt" in answer and "8 triệu/tháng đạt" in answer
    assert "60 tuổi đạt" not in answer and "30 triệu/tháng đạt" not in answer


@pytest.mark.parametrize("other_claim", [
    "Mẹ tôi là nhân viên ngân hàng, lương20triệu một tháng.",
    "Con tôi17tuổi, lương20triệu một tháng.",
])
def test_other_person_context_is_kept_until_income_quantity_is_masked(other_claim):
    answer = direct_condition_answer([
        user("Tôi muốn thẻ Gold."), user(other_claim), user(QUESTION),
    ], SOURCE)
    assert "cần xác nhận tuổi hiện tại" in answer
    assert "cần xác nhận một mức thu nhập riêng" in answer
    assert "20 triệu/tháng đạt" not in answer


def test_explicit_self_salary_after_parent_and_prior_self_salary_both_win():
    same_turn = direct_condition_answer([
        user("Tôi muốn thẻ Gold."),
        user("Mẹ tôi là nhân viên ngân hàng, lương20triệu, "
             "còn tôi30tuổi và thu nhập riêng12triệu."),
        user(QUESTION),
    ], SOURCE)
    assert "30 tuổi đạt" in same_turn and "12 triệu/tháng đạt" in same_turn
    assert "20 triệu/tháng đạt" not in same_turn

    later_parent = direct_condition_answer([
        user("Tôi muốn thẻ Gold."), user("Tôi30tuổi, lương12triệu."),
        user("Mẹ tôi là nhân viên ngân hàng, lương20triệu."),
        user(QUESTION),
    ], SOURCE)
    assert "30 tuổi đạt" in later_parent and "12 triệu/tháng đạt" in later_parent
    assert "20 triệu/tháng đạt" not in later_parent


@pytest.mark.parametrize("quoted", [
    "Nguồn cũ nói, thu nhập tối thiểu20triệu mới được mở thẻ.",
    "Ngân hàng nói, thu nhập tối thiểu20triệu một tháng.",
])
def test_old_source_quote_never_becomes_the_callers_income(quoted):
    answer = direct_condition_answer([
        user("Tôi muốn thẻ Gold và tôi30tuổi."),
        user(quoted),
        user(QUESTION),
    ], SOURCE)
    assert "cần xác nhận một mức thu nhập riêng" in answer
    assert "20 triệu/tháng đạt" not in answer


def test_explicit_self_income_after_source_contrast_ends_quoted_scope():
    answer = direct_condition_answer([
        user("Tôi muốn thẻ Gold và tôi30tuổi."),
        user("Nguồn cũ nói, thu nhập tối thiểu20triệu mới được mở thẻ, "
             "còn thu nhập riêng của tôi là12triệu."),
        user(QUESTION),
    ], SOURCE)
    assert "12 triệu/tháng đạt mức tối thiểu 5 triệu/tháng" in answer
    assert "20 triệu/tháng đạt" not in answer


def test_absent_or_conflicting_source_does_not_emit_a_direct_comparison():
    messages = [user("Tôi muốn thẻ Gold."), user("Tôi 30 tuổi, thu nhập 8 triệu."), user(QUESTION)]
    assert not direct_condition_answer(messages, "Không có nguồn")
    conflicting = SOURCE + "\n- Thu nhập tối thiểu 9 triệu/tháng\n- Từ 21 tuổi trở lên"
    assert not direct_condition_answer(messages, conflicting)


def test_thresholds_and_tier_range_are_read_from_a_variable_source():
    source = """THÔNG TIN THAM KHẢO:
1. Thẻ Sapphire: Hạn mức 40 triệu đến 250 triệu
## Điều kiện mở thẻ
- Từ 21 tuổi trở lên
- Thu nhập tối thiểu 7,5 triệu đồng/tháng
"""
    answer = direct_condition_answer([
        user("Tôi chọn thẻ Sapphire."),
        user("Tôi 20 tuổi, thu nhập riêng 8 triệu mỗi tháng."),
        user(QUESTION),
    ], source)
    assert "20 tuổi chưa đạt mức tối thiểu 21 tuổi" in answer
    assert "8 triệu/tháng đạt mức tối thiểu 7.5 triệu/tháng" in answer
    assert "Thẻ Sapphire có dải hạn mức 40-250 triệu" in answer
    assert "tối đa 21 tuổi" not in answer
