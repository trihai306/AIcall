"""Con số ngoài dữ kiện vay không được sửa phương án khách đã chốt."""

import pytest

from backend.pipeline.du_kien_khoan_vay import (
    chu_the_thu_nhap_nguoi_khac,
    quantities,
    resolve,
)


TRIEU = 10**6


def users(*contents):
    return [{"role": "user", "content": content} for content in contents]


def established():
    return users("Tôi vay 95 triệu trong 12 tháng, thu nhập 11 triệu")


@pytest.mark.parametrize("retraction", [
    "rút lại số tiền đó.",
    "rut lai so tien do.",
])
def test_retracting_current_amount_invalidates_only_amount(retraction):
    state = resolve(users("Anh vay 250 triệu trong 24 tháng"), retraction)

    assert state.amount.status == "ambiguous"
    assert state.amount.value is None
    assert state.amount_updated
    assert state.term.status == "known"
    assert state.term.value == 24
    assert not state.term_updated


@pytest.mark.parametrize("retraction", [
    "rút lại số tiền đó.",
    "rut lai so tien do.",
])
def test_new_amount_after_retraction_recovers_without_reviving_old_value(retraction):
    history = users("Anh vay 250 triệu trong 24 tháng", retraction)
    pending = resolve(history)
    assert pending.amount.status == "ambiguous" and pending.amount.value is None

    state = resolve(history, "là 300 triệu")
    assert state.amount.status == "known"
    assert state.amount.value == 300 * TRIEU
    assert state.term.value == 24


@pytest.mark.parametrize("sentence", [
    "Đội bóng anh thích vừa thắng ba bàn",
    "Doi bong anh thich vua thang ba ban",
    "Cầu thủ vừa ghi ba bàn trong trận đấu",
    "Cau thu vua ghi ba ban trong tran dau",
    "Con tôi đang học lớp ba",
    "Con toi dang hoc lop ba",
    "Tôi đang có nợ xấu nhóm ba tại CIC",
    "Toi dang co no xau nhom ba tai CIC",
    "Mã hồ sơ của tôi là 123456",
    "Ma ho so cua toi la 123456",
])
def test_non_loan_quantity_roles_do_not_change_established_facts(sentence):
    before = resolve(established())
    after = resolve(established(), sentence)

    assert after.evidence() == before.evidence()
    assert not after.amount_updated
    assert not after.term_updated
    assert not after.income_updated


@pytest.mark.parametrize("sentence", [
    "Con tôi học 3 môn trong 6 tháng",
    "Con tôi học ba môn trong sáu tháng",
    "Con toi hoc 3 mon trong 6 thang",
    "Con toi hoc ba mon trong sau thang",
])
def test_education_count_and_duration_belong_to_the_childs_clause(sentence):
    before = resolve(established())
    after = resolve(established(), sentence)

    assert after.evidence() == before.evidence()
    assert not after.amount_updated
    assert not after.term_updated


def test_education_clause_does_not_hide_later_explicit_loan_correction():
    state = resolve(
        established(),
        "Con tôi học3môn6tháng, còn tôi đổi khoản vay100triệu24tháng",
    )

    assert state.amount.status == "known"
    assert state.amount.value == 100 * TRIEU
    assert state.term.status == "known"
    assert state.term.value == 24
    assert state.amount_updated and state.term_updated
    assert state.income.value == 11 * TRIEU


@pytest.mark.parametrize("sentence", [
    "Học phí của con tôi là 3 triệu mỗi tháng",
    "Hoc phi cua con toi la 3 trieu moi thang",
    "Phí hồ sơ là 3 triệu",
    "Phi ho so la 3 trieu",
    "Ngân hàng yêu cầu thu nhập tối thiểu 20 triệu",
    "Ngan hang yeu cau thu nhap toi thieu 20 trieu",
])
def test_fee_and_quoted_income_thresholds_do_not_replace_customer_facts(sentence):
    before = resolve(established())
    after = resolve(established(), sentence)
    assert after.evidence() == before.evidence()


def test_education_context_yields_to_a_later_explicit_self_loan_request():
    state = resolve(established(), "Tôi học xong muốn vay 100 triệu trong 24 tháng")
    assert state.amount.value == 100 * TRIEU
    assert state.term.value == 24
    assert state.amount_updated and state.term_updated


@pytest.mark.parametrize("sentence", [
    "Tôi điều trị trong 6 tháng",
    "Tôi uống thuốc trong 6 tháng",
    "Con tôi điều trị 6 tháng",
    "Tôi thuê nhà trong 6 tháng",
    "Tôi làm dự án trong 6 tháng",
    "Toi dieu tri trong 6 thang",
    "Toi thue nha trong 6 thang",
    "Toi lam du an trong 6 thang",
])
def test_temporal_duration_without_local_loan_role_does_not_replace_term(sentence):
    before = resolve(established())
    after = resolve(established(), sentence)
    assert after.evidence() == before.evidence()
    assert not after.term_updated


@pytest.mark.parametrize("sentence", [
    "6 tháng",
    "trong 6 tháng",
    "trong vòng sáu tháng",
    "trong6tháng",
])
def test_concise_duration_reply_in_active_loan_conversation_updates_term(sentence):
    state = resolve(established(), sentence)
    assert state.term.status == "known"
    assert state.term.value == 6
    assert state.term_updated


@pytest.mark.parametrize("sentence", [
    "khoản vay trả trong 6 tháng",
    "thời hạn trả góp 6 tháng",
    "đổi lại trong 6 tháng",
    "doi lai trong 6 thang",
])
def test_explicit_repayment_or_correction_anchor_owns_duration(sentence):
    state = resolve(established(), sentence)
    assert state.term.status == "known"
    assert state.term.value == 6
    assert state.term_updated


def test_assistant_term_question_allows_concise_temporal_answer():
    history = [{
        "role": "assistant",
        "content": "Anh chị muốn vay trong bao nhiêu tháng ạ?",
    }]
    state = resolve(history, "trong 6 tháng")
    assert state.term.status == "known"
    assert state.term.value == 6


def test_compact_two_financial_fields_still_resolve_in_one_utterance():
    state = resolve(text="Tôi vay95triệu trong12tháng thu nhập11triệu")
    assert state.amount.value == 95 * TRIEU
    assert state.term.value == 12
    assert state.income.value == 11 * TRIEU

    corrected = resolve(established(), "275 trong 24 tháng")
    assert corrected.amount.value == 275 * TRIEU
    assert corrected.term.value == 24


def test_off_domain_clause_does_not_leak_into_later_explicit_loan_clause():
    state = resolve(
        established(),
        "Tôi điều trị trong6tháng, còn tôi đổi khoản vay100triệu24tháng",
    )
    assert state.amount.value == 100 * TRIEU
    assert state.term.value == 24
    assert state.amount_updated and state.term_updated


@pytest.mark.parametrize("sentence", [
    "Tôi vay 95 triệu rồi tôi điều trị 6 tháng",
    "Tôi vay 95 triệu và điều trị 6 tháng",
    "Tôi vay 95 triệu; tôi điều trị 6 tháng",
])
def test_loan_anchor_does_not_cross_into_a_later_off_domain_proposition(sentence):
    state = resolve(text=sentence)
    assert state.amount.value == 95 * TRIEU
    assert state.term.status == "unknown"


def test_explicit_repayment_anchor_survives_a_conjunction_inside_its_clause():
    state = resolve(text="Tôi trả góp cả gốc và lãi trong 24 tháng")
    assert state.term.status == "known"
    assert state.term.value == 24


def test_comma_only_term_continuation_still_belongs_to_same_loan_request():
    state = resolve(text="Tôi vay 95 triệu, trong 12 tháng")
    assert state.amount.value == 95 * TRIEU
    assert state.term.value == 12


@pytest.mark.parametrize("sentence", [
    "Tình hình thật là tôi vừa chậm trả ba tháng",
    "Tinh hinh that la toi vua cham tra ba thang",
    "Khoản vay cũ của tôi quá hạn ba tháng",
    "Khoan vay cu cua toi qua han ba thang",
])
def test_arrears_duration_is_not_a_new_requested_loan_term(sentence):
    state = resolve(established(), sentence)

    assert state.amount.value == 95 * TRIEU
    assert state.term.status == "known"
    assert state.term.value == 12
    assert state.income.value == 11 * TRIEU
    assert not state.term_updated


@pytest.mark.parametrize("sentence", [
    "đổi kỳ hạn sang ba tháng",
    "doi ky han sang ba thang",
])
def test_explicit_term_correction_remains_a_real_update(sentence):
    state = resolve(established(), sentence)
    assert state.amount.value == 95 * TRIEU
    assert state.term.status == "known"
    assert state.term.value == 3
    assert state.term_updated


@pytest.mark.parametrize("sentence", [
    "Tôi muốn trả trong ba năm",
    "Toi muon tra trong ba nam",
])
def test_explicit_new_loan_term_remains_supported(sentence):
    state = resolve(established(), sentence)
    assert state.term.status == "known"
    assert state.term.value == 36
    assert state.term_updated


@pytest.mark.parametrize("sentence", [
    "thu nhập của tôi là ba mươi triệu",
    "thu nhap cua toi la ba muoi trieu",
])
def test_typed_income_still_updates_income_only(sentence):
    state = resolve(established(), sentence)
    assert state.amount.value == 95 * TRIEU
    assert state.term.value == 12
    assert state.income.status == "known"
    assert state.income.value == 30 * TRIEU
    assert state.income_updated


def test_bare_answer_to_assistant_question_keeps_the_questioned_role():
    income_history = established() + [{
        "role": "assistant",
        "content": "Thu nhập hàng tháng của anh chị khoảng bao nhiêu ạ?",
    }]
    income = resolve(income_history, "mười lăm")
    assert income.income.value == 15 * TRIEU
    assert income.amount.value == 95 * TRIEU

    term_history = established() + [{
        "role": "assistant",
        "content": "Anh chị muốn vay trong bao nhiêu tháng ạ?",
    }]
    term = resolve(term_history, "ba mươi sáu")
    assert term.term.status == "missing_unit"
    assert term.term.coefficient == 36
    assert term.amount.value == 95 * TRIEU


def test_true_cancellation_and_numeric_readback_keep_their_existing_meanings():
    cancelled = resolve(established(), "không muốn vay nữa")
    assert cancelled.amount.status == "cancelled"
    assert cancelled.term.status == "cancelled"

    before = resolve(established())
    readback = resolve(established(), "Anh nghe cái gì ba trăm cơ?")
    assert readback.evidence() == before.evidence()


@pytest.mark.parametrize("sentence", [
    "Bố 60 tuổi và lương 30 triệu",
    "Mẹ lương 20 triệu",
    "Vợ lương 18 triệu",
    "Sếp lương 50 triệu",
    "Bo 60 tuoi va luong 30 trieu",
    "Me luong 20 trieu",
    "Vo luong 18 trieu",
    "Sep luong 50 trieu",
    "Anh Nam lương 40 triệu",
])
def test_bare_other_person_income_is_not_owned_by_the_caller(sentence):
    state = resolve(text=sentence)
    assert state.income.status == "unknown"
    assert state.income.value is None
    assert not state.income_updated

    prior = resolve(users("Thu nhập thực tế của tôi là 12 triệu"), sentence)
    assert prior.income.value == 12 * TRIEU
    assert prior.income.owner == "self"


@pytest.mark.parametrize("sentence", [
    "Bố30triệu còn tôi12",
    "Bo30trieu con toi12",
    "Mẹ20triệu còn tôi15triệu",
])
def test_shorthand_family_comparison_keeps_only_callers_income(sentence):
    state = resolve(text=sentence)
    expected = 15 if "15" in sentence else 12
    assert state.income.status == "known"
    assert state.income.value == expected * TRIEU
    assert state.income.owner == "self"


@pytest.mark.parametrize("sentence", [
    "Nếu tôi 30 tuổi và thu nhập 8 triệu thì sao?",
    "Neu toi 30 tuoi va thu nhap 8 trieu thi sao?",
    "Giả sử thu nhập của tôi là 30 triệu thì hồ sơ thế nào?",
])
def test_hypothetical_income_is_not_committed_as_actual_income(sentence):
    state = resolve(text=sentence)
    assert state.income.status == "unknown"
    assert not state.income_updated


def test_hypothetical_income_preserves_prior_actual_and_later_actual_can_update():
    history = users("Thu nhập thực tế của tôi là 12 triệu")
    hypothetical = "Nếu tôi 30 tuổi và thu nhập 30 triệu thì sao?"
    after_hypothetical = resolve(history, hypothetical)
    assert after_hypothetical.income.value == 12 * TRIEU
    assert after_hypothetical.income.raw == "12 triệu"
    assert not after_hypothetical.income_updated

    history.append({"role": "user", "content": hypothetical})
    latest = resolve(history, "Hiện thu nhập thực tế của tôi vẫn là 12 triệu")
    assert latest.income.value == 12 * TRIEU
    assert latest.income.owner == "self"
    assert latest.income.turn == 2 and latest.income_updated


@pytest.mark.parametrize("sentence", [
    "Anh lương 20 triệu",
    "Chị có thu nhập 20 triệu",
    "Tổng thu nhập gia đình 40 triệu",
    "Ngân hàng yêu cầu thu nhập tối thiểu 20 triệu",
])
def test_income_subject_positive_controls_keep_existing_provenance(sentence):
    state = resolve(text=sentence)
    if sentence.startswith("Tổng"):
        assert state.income.value == 40 * TRIEU
        assert state.income.owner == "household"
    elif sentence.startswith("Ngân hàng"):
        assert state.income.status == "unknown"
    else:
        assert state.income.value == 20 * TRIEU
        assert state.income.owner == "self"


def test_annual_income_unit_correction_does_not_change_principal_or_loan_term():
    history = users("Thu nhập tôi 30 triệu một tháng, muốn vay 60 triệu")
    state = resolve(
        history,
        "Tôi nói nhầm đơn vị: 30 triệu một năm, không phải một tháng",
    )

    assert state.amount.value == 60 * TRIEU
    assert state.term.status == "unknown"
    assert not state.amount_updated and not state.term_updated
    assert state.income.status == "ambiguous"
    assert state.income.value is None
    assert state.income.owner == "self"
    assert state.income_updated


def test_repayment_quote_and_discourse_vay_homograph_do_not_replace_principal():
    history = users("Tôi thấy ví dụ vay 100 triệu 36 tháng trả 3,4 triệu mỗi tháng")
    state = resolve(
        history,
        "Vậy hồ sơ của tôi cũng chắc chắn trả đúng 3,4 triệu và được duyệt phải không?",
    )

    assert state.amount.value == 100 * TRIEU
    assert state.term.value == 36
    assert not state.amount_updated and not state.term_updated


def test_discourse_vay_does_not_hide_a_later_real_loan_anchor():
    state = resolve(established(), "Vậy tôi muốn vay 80 triệu trong 18 tháng")
    assert state.amount.value == 80 * TRIEU
    assert state.term.value == 18
    assert state.amount_updated and state.term_updated


@pytest.mark.parametrize("sentence", [
    "Thu nhập của riêng tôi chưa ổn định, căn nhà 2,5 tỷ.",
    "Thu nhap cua rieng toi chua on dinh, can nha 2.5 ty.",
    "Thu nhập của riêng tôi chưa ổn định, căn hộ 3 tỷ.",
    "Thu nhập của riêng tôi chưa ổn định, miếng đất 4 tỷ.",
])
def test_bare_property_value_cannot_inherit_income_from_previous_clause(sentence):
    state = resolve(text=sentence)
    assert state.income.status == "unknown"
    assert state.amount.status == "unknown"
    assert not state.income_updated and not state.amount_updated

    prior = resolve(users("Thu nhập thực tế của tôi là 12 triệu"), sentence)
    assert prior.income.status == "known"
    assert prior.income.value == 12 * TRIEU
    assert prior.income.owner == "self"
    assert prior.amount.status == "unknown"
    assert not prior.income_updated and not prior.amount_updated


@pytest.mark.parametrize("sentence", [
    "Tôi cần vay 2,5 tỷ để mua nhà",
    "Toi can vay 2.5 ty de mua nha",
    "Thu nhập tôi 12 triệu, tôi cần vay 2,5 tỷ để mua nhà",
    "Căn nhà tôi mua cần vay 2,5 tỷ",
])
def test_property_context_keeps_explicit_loan_amount_anchor(sentence):
    state = resolve(text=sentence)
    assert state.amount.status == "known"
    assert state.amount.value == 2_500 * TRIEU
    assert state.amount_updated

    if "12" in sentence:
        assert state.income.value == 12 * TRIEU
        assert state.income.owner == "self"


@pytest.mark.parametrize("asset_clause", [
    "xe máy 50 triệu",
    "xe may 50 trieu",
    "máy móc 500 triệu",
    "may moc 500 trieu",
    "máy công nghiệp 700 triệu",
])
def test_machine_asset_value_is_not_an_asr_loan_anchor_or_income(asset_clause):
    sentence = f"Thu nhập chưa ổn định, {asset_clause}."
    state = resolve(text=sentence)
    assert state.income.status == "unknown"
    assert state.amount.status == "unknown"
    assert not state.income_updated and not state.amount_updated

    prior = resolve(users("Thu nhập thực tế của tôi 12 triệu"), sentence)
    assert prior.income.status == "known"
    assert prior.income.value == 12 * TRIEU
    assert prior.income.owner == "self"
    assert prior.amount.status == "unknown"
    assert not prior.income_updated and not prior.amount_updated


@pytest.mark.parametrize("sentence", [
    "Tôi cần vay 50 triệu mua xe máy",
    "Toi can vay 50 trieu mua xe may",
    "Tôi cần may 50 triệu mua xe máy",
    "Máy móc này tôi cần vay 500 triệu để mua",
])
def test_machine_asset_context_preserves_explicit_or_clear_asr_loan_request(sentence):
    state = resolve(text=sentence)
    expected = 500 if "500" in sentence else 50
    assert state.amount.status == "known"
    assert state.amount.value == expected * TRIEU
    assert state.amount_updated


@pytest.mark.parametrize("sentence", [
    "Mẹ tôi là nhân viên ngân hàng, lương 20 triệu một tháng.",
    "Người thân tôi làm ngân hàng, thu nhập 20 triệu.",
    "Bố tôi làm thợ xây, lương 20 triệu.",
    "Mẹ tôi làm giáo viên... lương 20 triệu.",
    "Anh Nam làm ở ngân hàng, có thu nhập 20 triệu.",
    "Chị Lan làm ở công ty may, lương 20 triệu.",
    "Mẹ tôi làm giáo viên và lương 20 triệu.",
])
def test_adjacent_salary_clause_inherits_clear_other_person_subject(sentence):
    state = resolve(text=sentence)
    assert state.income.status == "unknown"
    assert not state.income_updated

    prior = resolve(users("Thu nhập thực tế của tôi 12 triệu"), sentence)
    assert prior.income.status == "known"
    assert prior.income.value == 12 * TRIEU
    assert prior.income.owner == "self"
    assert not prior.income_updated


@pytest.mark.parametrize("sentence, expected, owner", [
    ("Mẹ tôi làm giáo viên, còn tôi lương 12 triệu.", 12, "self"),
    ("Mẹ tôi làm giáo viên, thu nhập riêng của tôi 14 triệu.", 14, "self"),
    ("Mẹ tôi làm giáo viên, tổng thu nhập gia đình 40 triệu.", 40, "household"),
])
def test_local_self_or_household_subject_resets_adjacent_other_person(
        sentence, expected, owner):
    state = resolve(text=sentence)
    assert state.income.status == "known"
    assert state.income.value == expected * TRIEU
    assert state.income.owner == owner
    assert state.income_updated


@pytest.mark.parametrize("sentence", [
    "Nhân viên ngân hàng nói thu nhập tối thiểu 5 triệu mới được vay.",
    "Nhân viên ngân hàng nói, thu nhập tối thiểu 5 triệu mới được vay.",
    "Nếu mẹ tôi đổi việc, thu nhập 20 triệu thì sao?",
])
def test_source_or_hypothetical_income_continuation_is_not_actual_salary(sentence):
    state = resolve(text=sentence)
    assert state.income.status == "unknown"
    assert not state.income_updated


@pytest.mark.parametrize("sentence", [
    "Con tôi lương 20 triệu một tháng.",
    "con tôi lương20triệu một tháng.",
    "Con tôi 17 tuổi, lương 20 triệu một tháng.",
    "Con tôi làm ở cửa hàng, thu nhập 20 triệu.",
    "Thu nhập của con tôi 20 triệu.",
])
def test_child_subject_is_not_folded_into_the_contrast_linker(sentence):
    income_quantity = next(q for q in quantities(sentence) if q.kind == "money")
    assert chu_the_thu_nhap_nguoi_khac(sentence, income_quantity)

    state = resolve(text=sentence)
    assert state.income.status == "unknown"
    assert not state.income_updated

    prior = resolve(users("Thu nhập thực tế của tôi 12 triệu"), sentence)
    assert prior.income.status == "known"
    assert prior.income.value == 12 * TRIEU
    assert prior.income.owner == "self"
    assert not prior.income_updated


@pytest.mark.parametrize("sentence", [
    "Vợ tôi lương 30 triệu, còn tôi 12 triệu.",
    "Vo toi luong30trieu con toi12trieu.",
    "Con tôi 17 tuổi, còn tôi lương 12 triệu.",
    "Con tôi làm ở cửa hàng, thu nhập riêng của tôi 14 triệu.",
])
def test_child_subject_does_not_override_later_explicit_caller_income(sentence):
    state = resolve(text=sentence)
    expected = 14 if "14" in sentence else 12
    assert state.income.status == "known"
    assert state.income.value == expected * TRIEU
    assert state.income.owner == "self"
    assert state.income_updated


def test_rejected_future_income_never_falls_through_to_loan_principal():
    history = users(
        "Lương cố định của tôi là 4 triệu mỗi tháng.",
        "Nếu quý sau có thưởng thêm 2 triệu thì mới thành 6 triệu, hiện giờ chưa có.",
    )
    state = resolve(
        history,
        "Vậy đừng coi 6 triệu là thu nhập hiện tại của tôi nhé.",
    )

    assert state.income.status == "known"
    assert state.income.value == 4 * TRIEU
    assert state.income.owner == "self"
    assert state.amount.status == "unknown"
    assert not state.income_updated and not state.amount_updated


@pytest.mark.parametrize("rejection", [
    "Đừng coi 6 triệu là thu nhập hiện tại của tôi.",
    "Dung coi 6 trieu la thu nhap hien tai cua toi.",
    "Không tính 6 triệu vào thu nhập hiện tại.",
    "Khong tinh 6 trieu vao thu nhap hien tai.",
    "Không ghi nhận thu nhập hiện tại của tôi là 6 triệu.",
])
def test_income_rejection_preserves_actual_income_and_no_principal(rejection):
    state = resolve(users("Thu nhập thực tế của tôi là 4 triệu"), rejection)
    assert state.income.value == 4 * TRIEU
    assert state.income.owner == "self"
    assert state.amount.status == "unknown"
    assert not state.income_updated and not state.amount_updated


def test_income_rejection_does_not_hide_explicit_new_loan_or_actual_income():
    history = users("Thu nhập thực tế của tôi là 4 triệu")
    loan = resolve(
        history,
        "Vậy đừng coi 6 triệu là thu nhập; tôi muốn vay 100 triệu.",
    )
    assert loan.income.value == 4 * TRIEU
    assert not loan.income_updated
    assert loan.amount.value == 100 * TRIEU
    assert loan.amount_updated

    actual = resolve(
        history,
        "Đừng ghi 6 triệu là thu nhập; thực tế lương tôi là 5 triệu.",
    )
    assert actual.income.value == 5 * TRIEU
    assert actual.income.owner == "self"
    assert actual.income_updated
    assert actual.amount.status == "unknown"
