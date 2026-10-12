from copy import deepcopy
from decimal import Decimal

from backend.pipeline.grounded_contracts import (
    AcceptedFact,
    DialogueState,
    FactUpdate,
    PolicyClaim,
    PolicySnapshot,
    SourceSnippet,
    TurnUnderstanding,
)
from backend.pipeline.grounded_executor import execute_turn as _execute_turn


def execute_turn(understanding, state, policy, **kwargs):
    """Executor fixture: canonical dialogue reduction has already happened."""
    if understanding.product != "unknown":
        state.product = understanding.product
    if understanding.intent in {"privacy", "security"}:
        state.security_active = True
    product = state.product
    for update in understanding.facts:
        if update.modality != "actual" or update.owner not in {"self", "household"}:
            continue
        if update.field in {"income_monthly", "age"}:
            scope = "*"
            fact_product = (
                update.product if update.product != "unknown" else product
            )
        elif update.product != "unknown":
            scope = update.product
            fact_product = update.product
        elif update.turn == understanding.current_turn:
            scope = product
            fact_product = product
        else:
            continue
        key = (scope, update.field, update.owner)
        current = state.facts.get(key)
        retracted_at = state.retracted_at.get(key, -1)
        if update.operation == "retract":
            if current is None or current.turn <= update.turn:
                state.facts.pop(key, None)
            state.retracted_at[key] = max(retracted_at, update.turn)
            continue
        if update.turn < retracted_at or (
            current is not None and update.turn < current.turn
        ):
            continue
        if current is not None and update.turn == current.turn and update.operation != "correct":
            continue
        state.facts[key] = AcceptedFact(
            field=update.field,
            value=update.value,
            owner=update.owner,
            product=fact_product,
            turn=update.turn,
            quote=update.quote,
        )
        state.retracted_at.pop(key, None)
    accepted = deepcopy(state)
    answer = _execute_turn(understanding, state, policy, **kwargs)
    assert state == accepted, "executor must not mutate dialogue state"
    return answer


def fact(
    field,
    value,
    *,
    owner="self",
    modality="actual",
    operation="assert",
    turn=1,
    product="unknown",
):
    return FactUpdate(
        field=field,
        value=str(value),
        owner=owner,
        modality=modality,
        operation=operation,
        turn=turn,
        quote=f"{field}={value}",
        product=product,
    )


def claim(
    key,
    value,
    unit,
    *,
    term=None,
    tier="",
    quote=None,
    source_ref="",
    qualifier="exact",
):
    return PolicyClaim(
        key=key,
        value=str(value),
        unit=unit,
        term_months=term,
        tier=tier,
        quote=quote or f"{key} {value}",
        source_ref=source_ref,
        qualifier=qualifier,
    )


def understanding(intent, product, *, topic="other", facts=(), refs=()):
    facts = list(facts)
    return TurnUnderstanding(
        intent=intent,
        product=product,
        topic=topic,
        certainty="clear",
        facts=facts,
        source_refs=list(refs),
        intent_quote=intent,
        current_turn=max((item.turn for item in facts), default=0),
    )


def snapshot(*claims, product="savings", version="v1", snippets=()):
    current_snippets = list(snippets)
    known_ids = {snippet.id for snippet in current_snippets}
    proven_claims = []
    for index, policy_claim in enumerate(claims):
        if policy_claim.source_ref:
            proven_claims.append(policy_claim)
            continue
        source_id = f"proof-{index}"
        while source_id in known_ids:
            source_id += "-claim"
        known_ids.add(source_id)
        current_snippets.append(SourceSnippet(source_id, policy_claim.quote))
        proven_claims.append(policy_claim.model_copy(update={"source_ref": source_id}))
    return PolicySnapshot(
        product=product,
        version=version,
        snippets=tuple(current_snippets),
        claims=tuple(proven_claims),
    )


def test_interest_tracks_source_mutation_and_online_bonus_is_percentage_points():
    turn = understanding(
        "calculate_interest",
        "savings",
        topic="rate",
        facts=(
            fact("amount", 100_000_000),
            fact("term_months", 6),
            fact("channel", "online"),
        ),
    )
    policy_a = snapshot(
        claim("apr", "4", "percent", term=6),
        claim("online_bonus", "0.5", "percent", term=6),
    )
    policy_b = snapshot(
        claim("apr", "5", "percent", term=6),
        claim("online_bonus", "0.5", "percent", term=6),
        version="v2",
    )
    answer_a = execute_turn(turn, DialogueState(), policy_a)
    answer_b = execute_turn(turn, DialogueState(), policy_b)
    assert "2,25 triệu đồng" in answer_a.text
    assert "2,75 triệu đồng" in answer_b.text
    assert answer_b.source_version == "v2"


def test_online_interest_requires_current_bonus_after_source_deletion_and_accepts_zero():
    turn = understanding(
        "calculate_interest",
        "savings",
        facts=(
            fact("amount", 100_000_000),
            fact("term_months", 6),
            fact("channel", "online"),
        ),
    )
    policy_a = snapshot(
        claim("apr", "4", "percent", term=6),
        claim("online_bonus", "0.5", "percent", term=6),
        version="a",
    )
    policy_b = snapshot(
        claim("apr", "5", "percent", term=6),
        claim("online_bonus", "0.7", "percent", term=6),
        version="b",
    )
    bonus_deleted = snapshot(
        claim("apr", "5", "percent", term=6),
        version="bonus-deleted",
    )
    explicit_zero = snapshot(
        claim("apr", "5", "percent", term=6),
        claim("online_bonus", "0", "percent", term=6),
        version="zero",
    )

    answer_a = execute_turn(turn, DialogueState(), policy_a)
    answer_b = execute_turn(turn, DialogueState(), policy_b)
    deleted = execute_turn(turn, DialogueState(), bonus_deleted)
    zero = execute_turn(turn, DialogueState(), explicit_zero)

    assert "2,25 triệu đồng" in answer_a.text
    assert "2,85 triệu đồng" in answer_b.text
    assert deleted.reason == "online_bonus_missing"
    assert "ước tính là" not in deleted.text
    assert "2,85 triệu đồng" not in deleted.text
    assert zero.reason == "calculated_interest"
    assert "2,5 triệu đồng" in zero.text
    assert zero.source_version == "zero"


def test_online_bonus_conflict_refuses_while_counter_without_bonus_uses_base_rate():
    online = understanding(
        "calculate_interest",
        "savings",
        facts=(
            fact("amount", 100_000_000),
            fact("term_months", 6),
            fact("channel", "online"),
        ),
    )
    conflicting = snapshot(
        claim("apr", "5", "percent", term=6),
        claim("online_bonus", "0.5", "percent", term=6),
        claim("online_bonus", "0.7", "percent", term=6),
    )
    answer = execute_turn(online, DialogueState(), conflicting)
    assert answer.reason == "online_bonus_conflict"
    assert "ước tính là" not in answer.text

    counter = understanding(
        "calculate_interest",
        "savings",
        facts=(
            fact("amount", 100_000_000),
            fact("term_months", 6),
            fact("channel", "counter"),
        ),
    )
    base_only = snapshot(claim("apr", "5", "percent", term=6))
    counter_answer = execute_turn(counter, DialogueState(), base_only)
    assert counter_answer.reason == "calculated_interest"
    assert "2,5 triệu đồng" in counter_answer.text


def test_interest_asks_for_missing_term_and_rejects_conflicting_rate():
    no_term = understanding(
        "calculate_interest", "savings", facts=(fact("amount", 10_000_000),)
    )
    policy = snapshot(claim("apr", "4", "percent", term=6))
    assert execute_turn(no_term, DialogueState(), policy).reason == "missing_term_months"

    conflicting = snapshot(
        claim("apr", "4", "percent", term=6),
        claim("apr", "5", "percent", term=6),
    )
    full = understanding(
        "calculate_interest",
        "savings",
        facts=(fact("amount", 10_000_000), fact("term_months", 6)),
    )
    answer = execute_turn(full, DialogueState(), conflicting)
    assert answer.reason == "apr_conflict"
    assert "ước tính là" not in answer.text


def test_hypothetical_is_ephemeral_and_quoted_example_is_not_customer_amount():
    state = DialogueState()
    policy = snapshot(claim("apr", "6", "percent", term=12))
    hypothetical = understanding(
        "calculate_interest",
        "savings",
        facts=(
            fact("amount", 20_000_000, modality="hypothetical"),
            fact("term_months", 12, modality="hypothetical"),
        ),
    )
    answer = execute_turn(hypothetical, state, policy)
    assert "Nếu dùng các giả định" in answer.text
    assert state.get("amount", product="savings") is None
    quoted = understanding(
        "calculate_interest",
        "savings",
        facts=(
            fact("amount", 50_000_000, modality="quoted"),
            fact("term_months", 12),
        ),
    )
    assert execute_turn(quoted, DialogueState(), policy).reason == "missing_amount"


def test_ltv_uses_lower_of_ratio_and_dynamic_cap_without_approval():
    policy = snapshot(
        claim("ltv", "70", "percent", quote="Tỷ lệ tối đa 70%"),
        claim("max_amount", "2000000000", "vnd", quote="Trần 2 tỷ"),
        product="mortgage",
    )
    turn = understanding(
        "calculate_ltv",
        "mortgage",
        facts=(fact("property_value", 4_000_000_000),),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert "2 tỷ đồng" in answer.text
    assert "không phải xác nhận phê duyệt" in answer.text
    assert "Căn cứ nguồn" not in answer.text


def test_ltv_without_absolute_cap_returns_only_proven_ratio_component():
    turn = understanding(
        "calculate_ltv",
        "mortgage",
        facts=(fact("property_value", 3_200_000_000),),
    )
    ratio = claim("ltv", "65", "percent", quote="Tỷ lệ tối đa theo nguồn là 65%.")
    with_cap = execute_turn(
        turn,
        DialogueState(),
        snapshot(
            ratio,
            claim("max_amount", "1800000000", "vnd", quote="Trần là 1,8 tỷ."),
            product="mortgage",
        ),
    )
    ratio_only = execute_turn(
        turn,
        DialogueState(),
        snapshot(ratio, product="mortgage"),
    )
    assert with_cap.reason == "calculated_ltv_cap"
    assert "1,8 tỷ đồng" in with_cap.text
    assert ratio_only.reason == "calculated_ltv_ratio_only"
    assert "riêng theo tỷ lệ 65%" in ratio_only.text
    assert "2,08 tỷ đồng" in ratio_only.text
    assert "Trần vay tuyệt đối chưa có trong nguồn" in ratio_only.text
    assert "chưa phải hạn mức tối đa tổng thể" in ratio_only.text
    assert "không phải xác nhận phê duyệt" in ratio_only.text
    assert ratio_only.evidence_refs


def test_ltv_conflicting_caps_refuse_instead_of_returning_ratio_component():
    policy = snapshot(
        claim("ltv", "65", "percent", quote="Tỷ lệ tối đa theo nguồn là 65%."),
        claim("max_amount", "1800000000", "vnd", quote="Trần A."),
        claim("max_amount", "1900000000", "vnd", quote="Trần B."),
        product="mortgage",
    )
    turn = understanding(
        "calculate_ltv",
        "mortgage",
        facts=(fact("property_value", 3_200_000_000),),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert answer.reason == "ltv_cap_conflict"
    assert "2,08 tỷ đồng" not in answer.text
    assert "hạn mức tham khảo" in answer.text


def test_declining_first_payment_uses_actual_amount_term_and_source_apr():
    policy = snapshot(claim("apr", "12", "percent"), product="loan")
    turn = understanding(
        "calculate_payment",
        "loan",
        facts=(fact("amount", 120_000_000), fact("term_months", 12)),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert "11,2 triệu đồng" in answer.text
    assert "tháng đầu" in answer.text and "giảm dần" in answer.text
    assert "giả định gốc được chia đều" in answer.text


def test_eligibility_never_converts_household_income_to_self_income():
    policy = snapshot(
        claim("min_age", "22", "age"),
        claim("max_age", "60", "age"),
        claim("min_income", "10000000", "vnd"),
        product="loan",
    )
    household_only = understanding(
        "eligibility",
        "loan",
        facts=(
            fact("age", 30),
            fact("income_monthly", 30_000_000, owner="household"),
        ),
    )
    answer = execute_turn(household_only, DialogueState(), policy)
    assert "thu nhập" not in answer.text or "thu nhập của chính" not in answer.text
    assert "không phải phê duyệt" in answer.text

    self_income = understanding(
        "eligibility",
        "loan",
        facts=(fact("income_monthly", 12_000_000),),
    )
    answer = execute_turn(self_income, DialogueState(), policy)
    assert "thu nhập của chính người đăng ký đạt" in answer.text


def test_negated_income_does_not_become_eligibility_fact():
    policy = snapshot(claim("min_income", "10000000", "vnd"), product="loan")
    turn = understanding(
        "eligibility",
        "loan",
        facts=(fact("income_monthly", 20_000_000, modality="negated"),),
    )
    state = DialogueState()
    answer = execute_turn(turn, state, policy)
    assert answer.reason == "missing_self_eligibility_facts"
    assert state.get("income_monthly") is None


def test_readback_preserves_prior_facts_and_requests_savings_term():
    state = DialogueState()
    policy = snapshot()
    execute_turn(
        understanding("acknowledge", "savings", facts=(fact("amount", 80_000_000),)),
        state,
        policy,
    )
    answer = execute_turn(
        understanding("readback", "savings"), state, policy
    )
    assert "80 triệu đồng" in answer.text
    assert "kỳ hạn gửi" in answer.text


def test_generic_question_uses_only_exact_selected_current_sources():
    snippets = (
        SourceSnippet("fee", "Biểu phí hiện hành từ nguồn A."),
        SourceSnippet("docs", "Danh sách hồ sơ từ nguồn B."),
    )
    policy = snapshot(product="loan", snippets=snippets)
    turn = understanding(
        "question", "loan", topic="documents", refs=("docs", "missing", "fee")
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert "Danh sách hồ sơ từ nguồn B." in answer.text
    assert "Biểu phí hiện hành từ nguồn A." in answer.text
    assert answer.evidence_refs == ("docs", "fee")


def test_crypto_currency_cannot_receive_vnd_rate():
    policy = snapshot(claim("apr", "6", "percent", term=12))
    turn = understanding(
        "calculate_interest",
        "savings",
        facts=(
            fact("amount", 2),
            fact("term_months", 12),
            fact("currency", "BTC"),
        ),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert answer.reason == "unsupported_currency_for_vnd_rate"
    assert "VND" in answer.text


def test_security_and_identity_do_not_invent_calls_numbers_or_actions():
    policy = snapshot()
    security = execute_turn(
        understanding("security", "card"), DialogueState(), policy
    )
    assert "OTP" in security.text
    assert "gọi lại" not in security.text
    assert not any(character.isdigit() for character in security.text)

    identity = execute_turn(
        understanding("identity", "unknown"),
        DialogueState(),
        policy,
        organization="",
        agent_name="Mai",
    )
    assert "Mai" in identity.text
    assert "ngân hàng" not in identity.text.casefold()


def test_minimum_payment_has_no_fabricated_fixed_percentage():
    answer = execute_turn(
        understanding("question", "card", topic="minimum_payment"),
        DialogueState(),
        snapshot(product="card"),
    )
    assert "tối thiểu" in answer.text
    assert "%" not in answer.text


def test_policy_unique_is_the_conflict_authority():
    policy = snapshot(
        claim("annual_fee", "100000", "vnd", tier="Dynamic"),
        claim("annual_fee", Decimal("100000.0"), "vnd", tier="Dynamic"),
        product="card",
    )
    turn = understanding(
        "question",
        "card",
        topic="annual_fee",
        facts=(fact("card_tier", "Dynamic"),),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert "100 nghìn đồng" in answer.text


def test_calculation_returns_claim_proof_ids_without_turn_selected_refs():
    snippets = (SourceSnippet("rate-proof", "Kỳ hạn nguồn."),)
    policy = snapshot(
        claim(
            "apr",
            "6",
            "percent",
            term=12,
            quote="Kỳ hạn nguồn.",
            source_ref="rate-proof",
        ),
        snippets=snippets,
    )
    turn = understanding(
        "calculate_interest",
        "savings",
        facts=(fact("amount", 100_000_000), fact("term_months", 12)),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert answer.evidence_refs == ("rate-proof",)


def test_customer_record_never_claims_unavailable_account_state():
    answer = execute_turn(
        understanding("customer_record", "unknown"),
        DialogueState(),
        snapshot(),
    )
    assert answer.reason == "customer_record_unavailable"
    assert "chưa có dữ liệu" in answer.text
    assert "không thể xác nhận" in answer.text


def test_customer_record_returns_proven_public_fee_with_private_record_unknown():
    policy = snapshot(
        claim("annual_fee", "420000", "vnd", tier="Hạng thử nghiệm"),
        product="card",
    )
    turn = understanding(
        "customer_record",
        "card",
        topic="annual_fee",
        facts=(fact("card_tier", "Hạng thử nghiệm"),),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert answer.reason == "customer_record_public_partial"
    assert "420 nghìn đồng" in answer.text
    assert "thông tin sản phẩm được công bố chung" in answer.text
    assert "chưa có dữ liệu hồ sơ riêng đã xác thực" in answer.text
    assert "khoản thực tế đã thu hoặc áp dụng" in answer.text
    assert answer.evidence_refs


def test_selected_conditional_fee_source_precedes_base_fee_and_tracks_text_change():
    base = SourceSnippet("base-fee", "Phí thường niên công bố là 400 nghìn đồng.")
    waiver_a = SourceSnippet(
        "conditional-fee", "Khách hàng đáp ứng điều kiện được miễn phí năm đầu."
    )
    waiver_b = SourceSnippet(
        "conditional-fee", "Khách hàng đáp ứng điều kiện mới được giảm một nửa phí năm đầu."
    )
    base_claim = claim(
        "annual_fee",
        "400000",
        "vnd",
        tier="Dynamic",
        quote=base.text,
        source_ref=base.id,
    )
    turn = understanding(
        "customer_record",
        "card",
        topic="annual_fee",
        facts=(fact("card_tier", "Dynamic"),),
        refs=("conditional-fee",),
    )
    policy_a = snapshot(base_claim, product="card", snippets=(base, waiver_a))
    policy_b = snapshot(
        base_claim,
        product="card",
        version="v2",
        snippets=(base, waiver_b),
    )
    answer_a = execute_turn(turn, DialogueState(), policy_a)
    answer_b = execute_turn(turn, DialogueState(), policy_b)
    assert answer_a.reason == "customer_record_public_partial"
    assert waiver_a.text in answer_a.text
    assert base.text not in answer_a.text
    assert waiver_b.text in answer_b.text
    assert waiver_a.text not in answer_b.text
    assert answer_b.source_version == "v2"
    assert answer_b.evidence_refs == ("conditional-fee",)


def test_selected_source_does_not_choose_one_conflicting_fee_as_authoritative():
    fee_a = SourceSnippet("fee-a", "Phí công bố theo dòng A.")
    fee_b = SourceSnippet("fee-b", "Phí công bố theo dòng B.")
    policy = snapshot(
        claim(
            "annual_fee", "400000", "vnd", tier="Dynamic",
            quote=fee_a.text, source_ref=fee_a.id,
        ),
        claim(
            "annual_fee", "500000", "vnd", tier="Dynamic",
            quote=fee_b.text, source_ref=fee_b.id,
        ),
        product="card",
        snippets=(fee_a, fee_b),
    )
    turn = understanding(
        "question",
        "card",
        topic="annual_fee",
        facts=(fact("card_tier", "Dynamic"),),
        refs=("fee-a",),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert answer.reason == "annual_fee_conflict"
    assert fee_a.text not in answer.text
    assert answer.evidence_refs == ()


def test_acknowledgement_uses_current_other_owner_delta_without_old_state_repetition():
    state = DialogueState(product="loan")
    state.facts[("loan", "amount", "self")] = AcceptedFact(
        field="amount",
        value="90000000",
        owner="self",
        product="loan",
        turn=8,
        quote="newer",
    )
    turn = understanding(
        "acknowledge",
        "loan",
        facts=(
            fact("amount", 10_000_000, turn=2),
            fact("income_monthly", 50_000_000, owner="other", turn=9),
        ),
    )
    answer = execute_turn(turn, state, snapshot(product="loan"))
    assert "thu nhập hằng tháng của người khác 50 triệu đồng" in answer.text
    assert "90 triệu đồng" not in answer.text
    assert "thu nhập hằng tháng của anh/chị 50 triệu đồng" not in answer.text
    assert state.get("amount", product="loan").value == "90000000"
    assert state.get("income_monthly", owner="other") is None


def test_acknowledgement_distinguishes_quoted_and_hypothetical_deltas():
    state = DialogueState(product="loan")
    state.facts[("loan", "amount", "self")] = AcceptedFact(
        field="amount",
        value="70000000",
        owner="self",
        product="loan",
        turn=1,
        quote="prior amount",
    )
    turn = understanding(
        "acknowledge",
        "loan",
        facts=(
            fact("income_monthly", 32_000_000, owner="other", turn=4),
            fact("term_months", 18, modality="hypothetical", turn=4),
            fact("amount", 90_000_000, modality="quoted", turn=4),
        ),
    )
    answer = execute_turn(turn, state, snapshot(product="loan"))
    assert "thu nhập hằng tháng của người khác 32 triệu đồng" in answer.text
    assert "giả định" in answer.text
    assert "thông tin được trích dẫn" in answer.text
    assert "không lưu là dữ kiện thực tế" in answer.text
    assert "70 triệu đồng" not in answer.text


def test_dynamic_ranges_and_early_rate_use_claim_evidence():
    snippets = (
        SourceSnippet("min", "Mức thấp nhất từ nguồn."),
        SourceSnippet("max", "Mức cao nhất từ nguồn."),
        SourceSnippet("early", "Lãi rút sớm từ nguồn."),
    )
    policy = snapshot(
        claim(
            "min_amount", "25000000", "vnd",
            quote="Mức thấp nhất từ nguồn.", source_ref="min",
        ),
        claim(
            "max_amount", "375000000", "vnd",
            quote="Mức cao nhất từ nguồn.", source_ref="max",
        ),
        claim(
            "early_rate", "0.25", "percent",
            quote="Lãi rút sớm từ nguồn.", source_ref="early",
        ),
        product="savings",
        snippets=snippets,
    )
    amount_range = execute_turn(
        understanding("question", "savings", topic="limit"),
        DialogueState(),
        policy,
    )
    assert "25 triệu đồng" in amount_range.text
    assert "375 triệu đồng" in amount_range.text
    assert amount_range.evidence_refs == ("min", "max")

    early = execute_turn(
        understanding("question", "savings", topic="early_withdrawal"),
        DialogueState(),
        policy,
    )
    assert "0,25%" in early.text
    assert early.evidence_refs == ("early",)


def test_privacy_activates_security_state_without_accepting_turn_facts():
    state = DialogueState()
    answer = execute_turn(
        understanding(
            "privacy", "loan", facts=(fact("amount", 999_000_000),)
        ),
        state,
        snapshot(product="loan"),
    )
    assert answer.reason == "safety_privacy"
    assert state.security_active is True
    assert state.get("amount", product="loan").value == "999000000"


def test_stale_fact_in_turn_cannot_drive_calculation_over_newer_state():
    state = DialogueState(product="savings")
    state.facts[("savings", "amount", "self")] = AcceptedFact(
        field="amount",
        value="200000000",
        owner="self",
        product="savings",
        turn=9,
        quote="new amount",
    )
    policy = snapshot(claim("apr", "6", "percent", term=12))
    turn = understanding(
        "calculate_interest",
        "savings",
        facts=(fact("amount", 100_000_000, turn=2), fact("term_months", 12, turn=10)),
    )
    answer = execute_turn(turn, state, policy)
    assert "12 triệu đồng" in answer.text


def test_ambiguous_turn_does_not_mutate_state_or_calculate():
    turn = TurnUnderstanding(
        intent="calculate_interest",
        product="savings",
        topic="rate",
        certainty="ambiguous",
        facts=[fact("amount", 100_000_000), fact("term_months", 12)],
        source_refs=[],
        intent_quote="ambiguous",
    )
    state = DialogueState()
    answer = execute_turn(
        turn, state, snapshot(claim("apr", "6", "percent", term=12))
    )
    assert answer.reason == "ambiguous_understanding"


def test_policy_for_different_product_is_never_used():
    turn = understanding(
        "calculate_payment",
        "loan",
        facts=(fact("amount", 100_000_000), fact("term_months", 12)),
    )
    answer = execute_turn(
        turn,
        DialogueState(),
        snapshot(claim("apr", "6", "percent"), product="savings"),
    )
    assert answer.reason == "policy_product_mismatch"
    assert "ước tính khoảng" not in answer.text


def test_readback_labels_household_fact_without_turning_it_into_self_income():
    turn = understanding(
        "readback",
        "loan",
        facts=(fact("income_monthly", 28_000_000, owner="household"),),
    )
    answer = execute_turn(turn, DialogueState(), snapshot(product="loan"))
    assert "thu nhập hằng tháng của hộ gia đình 28 triệu đồng" in answer.text
    assert "thu nhập hằng tháng 28 triệu đồng" not in answer.text


def test_unproven_policy_claim_cannot_drive_arithmetic():
    policy = PolicySnapshot(
        product="savings",
        version="unproven",
        snippets=(SourceSnippet("source", "Một dòng nguồn khác."),),
        claims=(claim("apr", "6", "percent", term=12, source_ref="source"),),
    )
    turn = understanding(
        "calculate_interest",
        "savings",
        facts=(fact("amount", 100_000_000), fact("term_months", 12)),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert answer.reason == "apr_unproven"
    assert "ước tính là" not in answer.text
    assert answer.evidence_refs == ()


def test_historical_hypothetical_is_not_reused_as_current_scenario():
    turn = understanding(
        "calculate_interest",
        "savings",
        facts=(
            fact("amount", 100_000_000, modality="hypothetical", turn=2),
            fact("term_months", 12, turn=5),
        ),
    ).model_copy(update={"current_turn": 5})
    answer = execute_turn(
        turn,
        DialogueState(),
        snapshot(claim("apr", "6", "percent", term=12)),
    )
    assert answer.reason == "missing_amount"


def test_mixed_product_deltas_do_not_conflict_or_bleed_into_current_calculation():
    turn = understanding(
        "calculate_interest",
        "savings",
        facts=(
            fact("amount", 150_000_000, product="savings"),
            fact("amount", 200_000_000, product="loan"),
            fact("term_months", 12, product="savings"),
        ),
    )
    state = DialogueState()
    answer = execute_turn(
        turn,
        state,
        snapshot(claim("apr", "6", "percent", term=12)),
    )
    assert answer.reason == "calculated_interest"
    assert "9 triệu đồng" in answer.text
    assert state.get("amount", product="savings").value == "150000000"
    assert state.get("amount", product="loan").value == "200000000"


def test_other_product_hypothetical_does_not_override_current_product_fact():
    turn = understanding(
        "calculate_interest",
        "savings",
        facts=(
            fact("amount", 150_000_000, product="savings"),
            fact(
                "amount",
                200_000_000,
                product="loan",
                modality="hypothetical",
            ),
            fact("term_months", 12, product="savings"),
        ),
    )
    answer = execute_turn(
        turn,
        DialogueState(),
        snapshot(claim("apr", "6", "percent", term=12)),
    )
    assert answer.reason == "calculated_interest"
    assert "9 triệu đồng" in answer.text
    assert "giả định" not in answer.text


def test_partial_early_withdrawal_uses_withdrawn_principal_and_elapsed_time():
    policy = snapshot(
        claim("early_rate", "0.5", "percent"),
        claim("apr", "6", "percent", term=12),
    )
    turn = understanding(
        "calculate_interest",
        "savings",
        topic="early_withdrawal",
        facts=(
            fact("amount", 100_000_000),
            fact("withdrawal_amount", 20_000_000),
            fact("elapsed_months", 3),
            fact("term_months", 12),
        ),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert answer.reason == "calculated_early_withdrawal"
    assert "phần rút sớm 20 triệu đồng" in answer.text
    assert "25 nghìn đồng" in answer.text
    assert "125 nghìn đồng" not in answer.text
    assert "Phần còn lại 80 triệu đồng" in answer.text
    assert "1,2 triệu đồng" in answer.text


def test_early_withdrawal_requires_elapsed_duration_and_valid_partial_amount():
    policy = snapshot(claim("early_rate", "0.5", "percent"))
    missing_elapsed = understanding(
        "calculate_interest",
        "savings",
        topic="early_withdrawal",
        facts=(
            fact("amount", 100_000_000),
            fact("withdrawal_amount", 20_000_000),
            fact("term_months", 12),
        ),
    )
    answer = execute_turn(missing_elapsed, DialogueState(), policy)
    assert answer.reason == "missing_elapsed_months"
    assert "ước tính" not in answer.text

    excessive = understanding(
        "calculate_interest",
        "savings",
        topic="early_withdrawal",
        facts=(
            fact("amount", 100_000_000),
            fact("withdrawal_amount", 120_000_000),
            fact("elapsed_months", 3),
        ),
    )
    assert (
        execute_turn(excessive, DialogueState(), policy).reason
        == "withdrawal_exceeds_deposit"
    )


def test_floor_apr_is_explained_but_never_used_for_exact_payment():
    policy = snapshot(
        claim("apr", "7.9", "percent", qualifier="minimum"),
        product="loan",
    )
    turn = understanding(
        "calculate_payment",
        "loan",
        facts=(fact("amount", 120_000_000), fact("term_months", 12)),
    )
    answer = execute_turn(turn, DialogueState(), policy)
    assert answer.reason == "apr_minimum"
    assert "mức tối thiểu 7,9%/năm" in answer.text
    assert "chưa thể tính khoản trả" in answer.text
    assert "tháng đầu ước tính" not in answer.text
    assert answer.evidence_refs


def test_ambiguous_canonical_state_slot_cannot_drive_calculation_or_readback():
    state = DialogueState(product="savings")
    amount_key = ("savings", "amount", "self")
    state.facts[amount_key] = AcceptedFact(
        field="amount",
        value="100000000",
        owner="self",
        product="savings",
        turn=1,
        quote="amount",
    )
    state.facts[("savings", "term_months", "self")] = AcceptedFact(
        field="term_months",
        value="12",
        owner="self",
        product="savings",
        turn=1,
        quote="term",
    )
    state.ambiguous_at[amount_key] = 2
    policy = snapshot(claim("apr", "6", "percent", term=12))
    calculation = execute_turn(
        understanding("calculate_interest", "savings"), state, policy
    )
    assert calculation.reason == "missing_amount"
    assert "6 triệu đồng" not in calculation.text
    readback = execute_turn(understanding("readback", "savings"), state, policy)
    assert "100 triệu đồng" not in readback.text


def test_configured_identity_labels_are_not_claimed_as_verified_affiliation():
    answer = execute_turn(
        understanding("identity", "unknown"),
        DialogueState(),
        snapshot(),
        organization="Nhãn tổ chức thử nghiệm",
        agent_name="Mai",
    )
    assert "Theo cấu hình" in answer.text
    assert "Mai" in answer.text and "Nhãn tổ chức thử nghiệm" in answer.text
    assert "không tự xác thực" in answer.text
