"""Deterministic execution of validated, evidence-backed banking turns.

This module deliberately does not inspect the customer's raw words.  It consumes
the typed meaning produced upstream, keeps actual customer facts separate from
policy facts, and only performs arithmetic when every required operand is known.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from backend.pipeline.grounded_contracts import (
    DialogueState,
    FactUpdate,
    GroundedAnswer,
    PolicyClaim,
    PolicySnapshot,
    SourceSnippet,
    TurnUnderstanding,
)


_SAFETY_INTENTS = frozenset(
    {"stop", "defer", "security", "privacy", "identity", "fabrication", "approval"}
)
_PUBLIC_PRODUCT_TOPICS = frozenset(
    {
        "rate",
        "fee",
        "annual_fee",
        "replacement_fee",
        "lock_fee",
        "limit",
        "term",
        "documents",
        "conditions",
        "promotion",
        "early_withdrawal",
        "compound",
        "minimum_payment",
        "scope",
        "channel",
    }
)
_EXPECTED_UNITS = {
    "apr": "percent",
    "online_bonus": "percent",
    "early_rate": "percent",
    "ltv": "percent",
    "min_amount": "vnd",
    "max_amount": "vnd",
    "min_income": "vnd",
    "annual_fee": "vnd",
    "tier_min": "vnd",
    "tier_max": "vnd",
    "min_term": "months",
    "max_term": "months",
    "min_age": "age",
    "max_age": "age",
}
_ALLOWED_QUALIFIERS = {
    "apr": frozenset({"exact"}),
    "online_bonus": frozenset({"exact"}),
    "early_rate": frozenset({"exact"}),
    "annual_fee": frozenset({"exact"}),
    "ltv": frozenset({"exact", "maximum"}),
    "max_amount": frozenset({"exact", "maximum"}),
    "max_term": frozenset({"exact", "maximum"}),
    "max_age": frozenset({"exact", "maximum"}),
    "tier_max": frozenset({"exact", "maximum"}),
    "min_amount": frozenset({"exact", "minimum"}),
    "min_term": frozenset({"exact", "minimum"}),
    "min_age": frozenset({"exact", "minimum"}),
    "min_income": frozenset({"exact", "minimum"}),
    "tier_min": frozenset({"exact", "minimum"}),
}


@dataclass(frozen=True)
class _ResolvedFact:
    value: str | None
    hypothetical: bool = False
    conflict: bool = False


@dataclass(frozen=True)
class _PolicyValue:
    value: Decimal | None
    status: str
    evidence_refs: tuple[str, ...] = ()


def _answer(
    policy: PolicySnapshot,
    text: str,
    reason: str,
    refs: tuple[str, ...] = (),
) -> GroundedAnswer:
    return GroundedAnswer(
        text=text,
        reason=reason,
        source_version=policy.version,
        evidence_refs=refs,
    )


def _selected_sources(
    understanding: TurnUnderstanding, policy: PolicySnapshot
) -> tuple[SourceSnippet, ...]:
    """Return only exact, current source IDs, preserving the model's order."""
    by_id = {snippet.id: snippet for snippet in policy.snippets}
    selected: list[SourceSnippet] = []
    seen: set[str] = set()
    for source_id in understanding.source_refs[:3]:
        if source_id in by_id and source_id not in seen:
            selected.append(by_id[source_id])
            seen.add(source_id)
    return tuple(selected)


def _effective_product(
    understanding: TurnUnderstanding, state: DialogueState, policy: PolicySnapshot
) -> str:
    if understanding.product != "unknown":
        return understanding.product
    if state.product != "unknown":
        return state.product
    return policy.product or "unknown"


def _updates_for(
    understanding: TurnUnderstanding,
    product: str,
    field_name: str,
    owner: str,
    modality: str,
) -> list[FactUpdate]:
    return [
        fact
        for fact in understanding.facts
        if fact.field == field_name
        and fact.owner == owner
        and fact.modality == modality
        and _fact_in_scope(fact, understanding, product)
    ]


def _fact_in_scope(
    fact: FactUpdate, understanding: TurnUnderstanding, product: str
) -> bool:
    if fact.field in {"income_monthly", "age"}:
        return True
    if fact.product != "unknown":
        return fact.product == product
    return fact.turn == understanding.current_turn


def _reduce_updates(updates: list[FactUpdate]) -> _ResolvedFact:
    """Resolve one current-turn slot without silently choosing among assertions."""
    values: dict[str, str] = {}
    for update in sorted(enumerate(updates), key=lambda item: (item[1].turn, item[0])):
        update = update[1]
        if update.operation == "retract":
            values.clear()
        elif update.operation == "correct":
            values = {update.value: update.value}
        else:
            values[update.value] = update.value
    if len(values) > 1:
        return _ResolvedFact(None, conflict=True)
    if not values:
        return _ResolvedFact(None)
    return _ResolvedFact(next(iter(values.values())))


def _resolve_fact(
    understanding: TurnUnderstanding,
    state: DialogueState,
    product: str,
    field_name: str,
    *,
    owner: str = "self",
    allow_hypothetical: bool = False,
    conflicts: set[tuple[str, str]] = frozenset(),
) -> _ResolvedFact:
    if (field_name, owner) in conflicts:
        return _ResolvedFact(None, conflict=True)
    accepted = state.get(field_name, owner=owner, product=product)
    if allow_hypothetical:
        hypothetical_updates = _updates_for(
            understanding, product, field_name, owner, "hypothetical"
        )
        hypothetical_updates = [
            update
            for update in hypothetical_updates
            if update.turn == understanding.current_turn
        ]
        if hypothetical_updates:
            hypothetical = _reduce_updates(hypothetical_updates)
            if hypothetical.conflict:
                return hypothetical
            if hypothetical.value is not None:
                return _ResolvedFact(hypothetical.value, hypothetical=True)
    return _ResolvedFact(accepted.value if accepted else None)


def _current_actual_conflicts(
    understanding: TurnUnderstanding, product: str
) -> set[tuple[str, str]]:
    """Detect an unusable current delta without changing canonical state."""
    grouped: dict[tuple[str, str], list[FactUpdate]] = {}
    for fact in understanding.facts:
        if (
            fact.modality == "actual"
            and fact.operation != "retract"
            and _fact_in_scope(fact, understanding, product)
        ):
            grouped.setdefault((fact.field, fact.owner), []).append(fact)
    return {
        key for key, updates in grouped.items() if _reduce_updates(updates).conflict
    }


def _has_current_hypothetical(
    understanding: TurnUnderstanding, product: str, fields: set[str]
) -> bool:
    return any(
        fact.modality == "hypothetical"
        and fact.turn == understanding.current_turn
        and fact.field in fields
        and _fact_in_scope(fact, understanding, product)
        for fact in understanding.facts
    )


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _positive_decimal(fact: _ResolvedFact) -> Decimal | None:
    value = _decimal(fact.value)
    return value if value is not None and value > 0 else None


def _positive_months(fact: _ResolvedFact) -> int | None:
    value = _positive_decimal(fact)
    if value is None or value != value.to_integral_value():
        return None
    return int(value)


def _nonnegative_months(fact: _ResolvedFact) -> int | None:
    value = _decimal(fact.value)
    if value is None or value < 0 or value != value.to_integral_value():
        return None
    return int(value)


def _matching_claims(
    policy: PolicySnapshot,
    key: str,
    *,
    term_months: int | None,
    tier: str,
) -> list[PolicyClaim]:
    expected_unit = _EXPECTED_UNITS.get(key)
    return [
        claim
        for claim in policy.claims
        if claim.key == key
        and claim.term_months == term_months
        and claim.tier.casefold() == tier.casefold()
        and (expected_unit is None or claim.unit == expected_unit)
    ]


def _policy_value(
    policy: PolicySnapshot,
    key: str,
    *,
    term_months: int | None = None,
    tier: str = "",
    fallback_generic: bool = False,
) -> _PolicyValue:
    claims = _matching_claims(
        policy, key, term_months=term_months, tier=tier
    )
    selected_term = term_months
    if not claims and fallback_generic and term_months is not None:
        selected_term = None
        claims = _matching_claims(policy, key, term_months=None, tier=tier)
    if not claims:
        return _PolicyValue(None, "missing")

    allowed_qualifiers = _ALLOWED_QUALIFIERS.get(key, frozenset({"exact"}))
    disallowed = [
        claim for claim in claims if claim.qualifier not in allowed_qualifiers
    ]
    if disallowed:
        qualifiers = {claim.qualifier for claim in claims}
        values = {
            value
            for claim in claims
            if (value := _decimal(claim.value)) is not None
        }
        if len(qualifiers) != 1 or len(values) != 1:
            return _PolicyValue(None, "conflict")
        bound = next(iter(values))
        if bound < 0:
            return _PolicyValue(None, "invalid")
        known_snippets = {snippet.id: snippet for snippet in policy.snippets}
        verified_refs = tuple(
            dict.fromkeys(
                claim.source_ref
                for claim in claims
                if claim.source_ref in known_snippets
                and claim.quote.strip()
                == known_snippets[claim.source_ref].text.strip()
                and _decimal(claim.value) == bound
            )
        )
        if not verified_refs:
            return _PolicyValue(None, "unproven")
        return _PolicyValue(bound, next(iter(qualifiers)), verified_refs)

    # ``unique`` is the contract's authority for conflict and finite-value checks.
    value = policy.unique(key, term_months=selected_term, tier=tier)
    if value is None:
        return _PolicyValue(None, "conflict")
    if value < 0 or (key == "ltv" and value > 100):
        return _PolicyValue(None, "invalid")
    known_snippets = {snippet.id: snippet for snippet in policy.snippets}
    contract_refs = set(
        policy.evidence_for(key, term_months=selected_term, tier=tier)
    )
    verified_refs = tuple(
        dict.fromkeys(
            claim.source_ref
            for claim in claims
            if claim.source_ref in contract_refs
            and claim.source_ref in known_snippets
            and claim.quote.strip() == known_snippets[claim.source_ref].text.strip()
            and _decimal(claim.value) == value
        )
    )
    if not verified_refs:
        return _PolicyValue(None, "unproven")
    return _PolicyValue(
        value,
        "known",
        verified_refs,
    )


def _has_applicable_claim(
    policy: PolicySnapshot, key: str, term_months: int | None
) -> bool:
    return any(
        claim.key == key and claim.term_months in {term_months, None}
        for claim in policy.claims
    )


def _fmt(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    raw = format(absolute, "f")
    integer, dot, fraction = raw.partition(".")
    grouped = f"{int(integer):,}".replace(",", ".")
    fraction = fraction.rstrip("0")
    return sign + grouped + (("," + fraction) if dot and fraction else "")


def _fmt_money(value: Decimal) -> str:
    rounded = value.to_integral_value(rounding=ROUND_HALF_UP)
    absolute = abs(rounded)
    units = (
        (Decimal("1000000000"), "tỷ đồng"),
        (Decimal("1000000"), "triệu đồng"),
        (Decimal("1000"), "nghìn đồng"),
    )
    for scale, label in units:
        if absolute >= scale:
            scaled = rounded / scale
            return f"{_fmt(scaled)} {label}"
    return f"{_fmt(rounded)} đồng"


def _refs(sources: tuple[SourceSnippet, ...]) -> tuple[str, ...]:
    return tuple(source.id for source in sources)


def _policy_refs(*values: _PolicyValue) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            source_id
            for value in values
            for source_id in value.evidence_refs
        )
    )


def _rate_bound_phrase(rate: _PolicyValue) -> str:
    if rate.value is None:
        return ""
    label = {
        "minimum": "mức tối thiểu",
        "maximum": "mức tối đa",
        "indicative": "mức tham khảo",
    }.get(rate.status, "mức chưa xác định")
    return f"{label} {_fmt(rate.value)}%/năm"


def _source_intro(sources: tuple[SourceSnippet, ...]) -> str:
    return "Theo thông tin sản phẩm được công bố trong nguồn hiện tại:\n" + "\n".join(
        source.text for source in sources[:2]
    )


def _selected_policy_source_answer(
    policy: PolicySnapshot, sources: tuple[SourceSnippet, ...]
) -> GroundedAnswer:
    selected = sources[:2]
    return _answer(
        policy,
        _source_intro(selected),
        "selected_source_answer",
        _refs(selected),
    )


def _policy_status_blocks_selected_source(value: _PolicyValue) -> bool:
    return value.status in {"conflict", "unproven", "invalid"}


def _field_label(field_name: str) -> str:
    return {
        "amount": "số tiền",
        "term_months": "kỳ hạn",
        "elapsed_months": "thời gian gửi thực tế",
        "income_monthly": "thu nhập hằng tháng",
        "age": "tuổi",
        "property_value": "giá trị tài sản",
        "channel": "kênh thực hiện",
        "card_tier": "hạng thẻ",
        "withdrawal_amount": "số tiền rút",
        "currency": "loại tiền",
    }.get(field_name, field_name)


def _display_fact(field_name: str, value: str) -> str:
    number = _decimal(value)
    if field_name in {"amount", "income_monthly", "property_value", "withdrawal_amount"}:
        return _fmt_money(number) if number is not None else value
    if field_name in {"term_months", "elapsed_months"}:
        return f"{_fmt(number)} tháng" if number is not None else value
    if field_name == "age":
        return f"{_fmt(number)} tuổi" if number is not None else value
    return value


def _owner_context(owner: str) -> str:
    return {
        "self": "của anh/chị",
        "household": "của hộ gia đình",
        "other": "của người khác",
        "source": "theo nguồn được dẫn",
    }[owner]


def _current_delta_description(fact: FactUpdate) -> str:
    label = f"{_field_label(fact.field)} {_owner_context(fact.owner)}"
    if fact.product != "unknown":
        label += f" cho sản phẩm {fact.product}"
    if fact.operation == "retract":
        statement = f"rút lại {label}"
    else:
        value = _display_fact(fact.field, fact.value)
        verb = "sửa" if fact.operation == "correct" else "ghi nhận"
        connector = " thành" if fact.operation == "correct" else ""
        statement = f"{verb} {label}{connector} {value}"
    if fact.modality == "actual":
        return statement
    modality = {
        "hypothetical": "giả định",
        "negated": "thông tin đã phủ định",
        "quoted": "thông tin được trích dẫn",
    }[fact.modality]
    return f"{modality}: {statement} (không lưu là dữ kiện thực tế)"


def _known_currency_is_unsupported(currency: _ResolvedFact) -> bool:
    if currency.value is None:
        return False
    normalized = currency.value.strip().casefold()
    return normalized not in {"vnd", "vnđ", "đồng", "dong"}


def _safety_answer(
    understanding: TurnUnderstanding,
    policy: PolicySnapshot,
    *,
    organization: str,
    agent_name: str,
) -> GroundedAnswer:
    intent = understanding.intent
    if intent == "stop":
        text = "Dạ, em dừng trao đổi tại đây ạ."
    elif intent == "defer":
        text = "Dạ, mình có thể tiếp tục trao đổi khi anh/chị thuận tiện ạ."
    elif intent == "security":
        text = (
            "Nếu thẻ bị mất hoặc có giao dịch đáng ngờ, anh/chị hãy khóa thẻ "
            "trên ứng dụng chính thức và dùng kênh hỗ trợ chính thức của đơn vị phát "
            "hành. Không cung cấp OTP, PIN hoặc mật khẩu cho bất kỳ ai."
        )
    elif intent == "privacy":
        text = (
            "Anh/chị không cần cung cấp OTP, PIN, mật khẩu, mã bảo mật thẻ hoặc "
            "toàn bộ thông tin đăng nhập trong cuộc trao đổi này."
        )
    elif intent == "identity":
        identity = f" tên {agent_name.strip()}" if agent_name.strip() else ""
        if organization.strip():
            text = (
                f"Theo cấu hình của hệ thống này, em là trợ lý AI{identity}, hỗ "
                f"trợ nội dung mang nhãn {organization.strip()}. Các nhãn cấu hình "
                "này không tự xác thực danh tính bên gọi hoặc quan hệ với tổ chức "
                "đó; anh/chị nên tự kiểm tra qua kênh chính thức."
            )
        else:
            text = (
                f"Theo cấu hình của hệ thống này, em là trợ lý AI{identity}. Em "
                "chưa có thông tin tổ chức đã xác thực để khẳng định về đơn vị liên hệ."
            )
    elif intent == "approval":
        text = (
            "Em chưa thể xác nhận hồ sơ được phê duyệt. Kết quả còn phụ thuộc vào "
            "thẩm định và thông báo chính thức."
        )
    else:
        text = (
            "Em không có dữ liệu đã xác thực để khẳng định thông tin đó hoặc nói "
            "rằng một thao tác đã được thực hiện."
        )
    return _answer(policy, text, f"safety_{intent}")


def _missing_or_conflict(
    policy: PolicySnapshot, *, field: str, conflict: bool, refs: tuple[str, ...]
) -> GroundedAnswer:
    if conflict:
        return _answer(
            policy,
            f"Em đang có nhiều giá trị khác nhau cho {_field_label(field)}; "
            "anh/chị vui lòng xác nhận một giá trị.",
            f"conflicting_{field}",
            refs,
        )
    return _answer(
        policy,
        f"Em còn thiếu {_field_label(field)}; anh/chị vui lòng cung cấp thông tin này.",
        f"missing_{field}",
        refs,
    )


def _rate_for_term(
    understanding: TurnUnderstanding,
    state: DialogueState,
    policy: PolicySnapshot,
    product: str,
    conflicts: set[tuple[str, str]],
) -> tuple[_PolicyValue, _PolicyValue, int | None, _ResolvedFact, GroundedAnswer | None]:
    term_fact = _resolve_fact(
        understanding,
        state,
        product,
        "term_months",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    term = _positive_months(term_fact)
    if term_fact.conflict:
        return _PolicyValue(None, "missing"), _PolicyValue(None, "missing"), None, term_fact, _missing_or_conflict(
            policy, field="term_months", conflict=True, refs=()
        )
    if product == "savings" and term is None:
        return _PolicyValue(None, "missing"), _PolicyValue(None, "missing"), None, term_fact, _missing_or_conflict(
            policy, field="term_months", conflict=False, refs=()
        )
    rate = _policy_value(
        policy,
        "apr",
        term_months=term,
        fallback_generic=product != "savings",
    )
    if (
        term is None
        and rate.status == "missing"
        and any(claim.key == "apr" and claim.term_months is not None for claim in policy.claims)
    ):
        return rate, _PolicyValue(None, "missing"), term, term_fact, _missing_or_conflict(
            policy, field="term_months", conflict=False, refs=()
        )
    bonus = _PolicyValue(None, "missing")
    if rate.status != "known":
        return rate, bonus, term, term_fact, None
    has_bonus_claim = _has_applicable_claim(policy, "online_bonus", term)
    channel = _resolve_fact(
        understanding,
        state,
        product,
        "channel",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    if channel.conflict:
        return rate, bonus, term, term_fact, _missing_or_conflict(
            policy,
            field="channel",
            conflict=True,
            refs=(),
        )
    if has_bonus_claim and channel.value is None:
        return rate, bonus, term, term_fact, _missing_or_conflict(
            policy,
            field="channel",
            conflict=False,
            refs=(),
        )
    if channel.value is not None and channel.value.strip().casefold() == "online":
        bonus = _policy_value(
            policy,
            "online_bonus",
            term_months=term,
            fallback_generic=True,
        )
        if bonus.status != "known":
            return (
                rate,
                bonus,
                term,
                term_fact,
                _answer(
                    policy,
                    "Nguồn hiện tại chưa cho một mức cộng lãi online duy nhất, nên em chưa thể tính chính xác.",
                    f"online_bonus_{bonus.status}",
                ),
            )
    return rate, bonus, term, term_fact, None


def _calculate_early_withdrawal(
    understanding: TurnUnderstanding,
    state: DialogueState,
    policy: PolicySnapshot,
    product: str,
    conflicts: set[tuple[str, str]],
    sources: tuple[SourceSnippet, ...],
    deposit_fact: _ResolvedFact,
    deposit_amount: Decimal,
) -> GroundedAnswer:
    refs = _refs(sources)
    withdrawal_fact = _resolve_fact(
        understanding,
        state,
        product,
        "withdrawal_amount",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    withdrawal = _positive_decimal(withdrawal_fact)
    if withdrawal_fact.conflict or withdrawal is None:
        return _missing_or_conflict(
            policy,
            field="withdrawal_amount",
            conflict=withdrawal_fact.conflict,
            refs=refs,
        )
    if withdrawal > deposit_amount:
        return _answer(
            policy,
            "Số tiền rút đang lớn hơn số tiền gửi đã xác nhận; anh/chị vui lòng kiểm tra lại hai số tiền.",
            "withdrawal_exceeds_deposit",
            refs,
        )

    elapsed_fact = _resolve_fact(
        understanding,
        state,
        product,
        "elapsed_months",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    elapsed = _nonnegative_months(elapsed_fact)
    if elapsed_fact.conflict or elapsed is None:
        return _missing_or_conflict(
            policy,
            field="elapsed_months",
            conflict=elapsed_fact.conflict,
            refs=refs,
        )

    early_rate = _policy_value(policy, "early_rate")
    if early_rate.status != "known" or early_rate.value is None:
        if early_rate.status in {"minimum", "maximum", "indicative"}:
            text = (
                f"Nguồn hiện tại chỉ nêu {_rate_bound_phrase(early_rate)} cho rút "
                "trước hạn, không phải mức áp dụng chính xác, nên em chưa thể tính "
                "tiền lãi rút sớm."
            )
        else:
            text = (
                "Nguồn hiện tại chưa cho một mức lãi rút trước hạn chính xác và "
                "được chứng minh, nên em chưa thể tính tiền lãi."
            )
        return _answer(
            policy,
            text,
            f"early_rate_{early_rate.status}",
            early_rate.evidence_refs,
        )

    withdrawn_interest = (
        withdrawal * early_rate.value * Decimal(elapsed) / Decimal("1200")
    )
    conditional = (
        deposit_fact.hypothetical
        or withdrawal_fact.hypothetical
        or elapsed_fact.hypothetical
        or _has_current_hypothetical(understanding, product, {"currency"})
    )
    lead = "Nếu dùng các giả định vừa nêu, " if conditional else "Theo các dữ kiện hiện có, "
    text = (
        f"{lead}phần rút sớm {_fmt_money(withdrawal)} có tiền lãi ước tính "
        f"{_fmt_money(withdrawn_interest)} cho {elapsed} tháng, với lãi suất rút "
        f"sớm {_fmt(early_rate.value)}%/năm."
    )
    used_values = [early_rate]
    remainder = deposit_amount - withdrawal
    reason = "calculated_early_withdrawal"
    if remainder > 0:
        rate, bonus, _, _, issue = _rate_for_term(
            understanding, state, policy, product, conflicts
        )
        if issue or rate.status != "known" or rate.value is None:
            text += (
                f" Phần còn lại {_fmt_money(remainder)} chưa được tính lãi vì cần "
                "kỳ hạn hợp đồng, kênh gửi và mức lãi chính xác tương ứng."
            )
            reason = "calculated_withdrawn_portion_only"
        else:
            effective_rate = rate.value + (bonus.value or Decimal("0"))
            remainder_interest = (
                remainder * effective_rate * Decimal(elapsed) / Decimal("1200")
            )
            text += (
                f" Phần còn lại {_fmt_money(remainder)} có lãi tích lũy ước tính "
                f"{_fmt_money(remainder_interest)} trong đúng {elapsed} tháng, với "
                f"lãi suất {_fmt(effective_rate)}%/năm."
            )
            used_values.extend((rate, bonus))
    return _answer(policy, text, reason, _policy_refs(*used_values))


def _calculate_interest(
    understanding: TurnUnderstanding,
    state: DialogueState,
    policy: PolicySnapshot,
    product: str,
    conflicts: set[tuple[str, str]],
    sources: tuple[SourceSnippet, ...],
) -> GroundedAnswer:
    refs = _refs(sources)
    if product != "savings":
        return _answer(
            policy,
            "Em chưa có phương pháp tính lãi phù hợp cho sản phẩm này từ nguồn hiện tại.",
            "interest_product_unsupported",
            refs,
        )
    amount_fact = _resolve_fact(
        understanding,
        state,
        product,
        "amount",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    amount = _positive_decimal(amount_fact)
    if amount_fact.conflict or amount is None:
        return _missing_or_conflict(
            policy,
            field="amount",
            conflict=amount_fact.conflict,
            refs=refs,
        )
    currency = _resolve_fact(
        understanding,
        state,
        product,
        "currency",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    if currency.conflict:
        return _missing_or_conflict(policy, field="currency", conflict=True, refs=refs)
    if _known_currency_is_unsupported(currency):
        return _answer(
            policy,
            "Em không thể áp dụng lãi suất VND cho loại tiền đã nêu. Cần nguồn lãi suất đúng loại tiền để tính.",
            "unsupported_currency_for_vnd_rate",
            refs,
        )

    if understanding.topic == "early_withdrawal":
        return _calculate_early_withdrawal(
            understanding,
            state,
            policy,
            product,
            conflicts,
            sources,
            amount_fact,
            amount,
        )

    rate, bonus, term, term_fact, issue = _rate_for_term(
        understanding, state, policy, product, conflicts
    )
    if issue:
        return _answer(policy, issue.text, issue.reason, refs)
    if term is None:
        return _missing_or_conflict(
            policy, field="term_months", conflict=term_fact.conflict, refs=refs
        )
    if rate.status != "known" or rate.value is None:
        if rate.status in {"minimum", "maximum", "indicative"}:
            text = (
                f"Nguồn hiện tại chỉ nêu {_rate_bound_phrase(rate)}, không phải "
                "mức áp dụng chính xác, nên em chưa thể tính tiền lãi."
            )
        else:
            text = (
                "Nguồn hiện tại chưa cho một mức lãi suất duy nhất cho kỳ hạn "
                "này, nên em chưa thể tính tiền lãi."
            )
        return _answer(
            policy,
            text,
            f"apr_{rate.status}",
            rate.evidence_refs or refs,
        )
    effective_rate = rate.value + (bonus.value or Decimal("0"))
    interest = amount * effective_rate * Decimal(term) / Decimal("1200")
    conditional = (
        amount_fact.hypothetical
        or term_fact.hypothetical
        or _has_current_hypothetical(
            understanding, product, {"channel", "currency"}
        )
    )
    lead = "Nếu dùng các giả định vừa nêu, " if conditional else "Theo các dữ kiện hiện có, "
    text = (
        f"{lead}tiền lãi ước tính là {_fmt_money(interest)} cho {term} tháng, "
        f"với lãi suất {_fmt(effective_rate)}%/năm."
    )
    return _answer(
        policy,
        text,
        "calculated_interest",
        _policy_refs(rate, bonus),
    )


def _calculate_payment(
    understanding: TurnUnderstanding,
    state: DialogueState,
    policy: PolicySnapshot,
    product: str,
    conflicts: set[tuple[str, str]],
    sources: tuple[SourceSnippet, ...],
) -> GroundedAnswer:
    refs = _refs(sources)
    if product not in {"loan", "mortgage"}:
        return _answer(
            policy,
            "Em chưa có phương pháp tính khoản trả giảm dần phù hợp cho sản phẩm này từ nguồn hiện tại.",
            "payment_product_unsupported",
            refs,
        )
    amount_fact = _resolve_fact(
        understanding,
        state,
        product,
        "amount",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    term_fact = _resolve_fact(
        understanding,
        state,
        product,
        "term_months",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    amount = _positive_decimal(amount_fact)
    term = _positive_months(term_fact)
    if amount_fact.conflict or amount is None:
        return _missing_or_conflict(
            policy, field="amount", conflict=amount_fact.conflict, refs=refs
        )
    if term_fact.conflict or term is None:
        return _missing_or_conflict(
            policy, field="term_months", conflict=term_fact.conflict, refs=refs
        )
    currency = _resolve_fact(
        understanding,
        state,
        product,
        "currency",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    if currency.conflict:
        return _missing_or_conflict(policy, field="currency", conflict=True, refs=refs)
    if _known_currency_is_unsupported(currency):
        return _answer(
            policy,
            "Em không thể áp dụng lãi suất VND cho loại tiền đã nêu. Cần nguồn lãi suất đúng loại tiền để tính.",
            "unsupported_currency_for_vnd_rate",
            refs,
        )
    rate = _policy_value(policy, "apr", term_months=term, fallback_generic=True)
    if rate.status != "known" or rate.value is None:
        if rate.status in {"minimum", "maximum", "indicative"}:
            implication = {
                "minimum": "Khoản thực tế có thể cao hơn mức tính từ sàn này.",
                "maximum": "Khoản thực tế có thể thấp hơn mức tính từ trần này.",
                "indicative": "Mức áp dụng thực tế vẫn chưa được xác định.",
            }[rate.status]
            text = (
                f"Nguồn hiện tại chỉ nêu {_rate_bound_phrase(rate)}, không phải "
                f"lãi suất áp dụng chính xác. Em chưa thể tính khoản trả. {implication}"
            )
        else:
            text = (
                "Nguồn hiện tại chưa cho một mức lãi suất duy nhất, nên em chưa "
                "thể ước tính khoản trả."
            )
        return _answer(
            policy,
            text,
            f"apr_{rate.status}",
            rate.evidence_refs or refs,
        )
    principal = amount / Decimal(term)
    first_interest = amount * rate.value / Decimal("1200")
    first_payment = principal + first_interest
    conditional = (
        amount_fact.hypothetical
        or term_fact.hypothetical
        or _has_current_hypothetical(understanding, product, {"currency"})
    )
    lead = "Nếu dùng các giả định vừa nêu, " if conditional else "Theo các dữ kiện hiện có, "
    text = (
        f"{lead}đây là mô phỏng theo giả định gốc được chia đều trong {term} "
        "tháng. Khoản trả tháng đầu ước tính khoảng "
        f"{_fmt_money(first_payment)} với lãi suất {_fmt(rate.value)}%/năm; "
        "các tháng sau giảm dần. Đây là ước tính, "
        "chưa phải lịch trả nợ chính thức."
    )
    return _answer(
        policy,
        text,
        "calculated_declining_first_payment",
        _policy_refs(rate),
    )


def _calculate_ltv(
    understanding: TurnUnderstanding,
    state: DialogueState,
    policy: PolicySnapshot,
    product: str,
    conflicts: set[tuple[str, str]],
    sources: tuple[SourceSnippet, ...],
) -> GroundedAnswer:
    refs = _refs(sources)
    if product != "mortgage":
        return _answer(
            policy,
            "Em chưa có cơ sở áp dụng tỷ lệ tài sản bảo đảm cho sản phẩm này.",
            "ltv_product_unsupported",
            refs,
        )
    property_fact = _resolve_fact(
        understanding,
        state,
        product,
        "property_value",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    property_value = _positive_decimal(property_fact)
    if property_fact.conflict or property_value is None:
        return _missing_or_conflict(
            policy,
            field="property_value",
            conflict=property_fact.conflict,
            refs=refs,
        )
    currency = _resolve_fact(
        understanding,
        state,
        product,
        "currency",
        allow_hypothetical=True,
        conflicts=conflicts,
    )
    if currency.conflict:
        return _missing_or_conflict(policy, field="currency", conflict=True, refs=refs)
    if _known_currency_is_unsupported(currency):
        return _answer(
            policy,
            "Em không thể áp dụng hạn mức VND cho giá trị tài sản bằng loại tiền đã nêu.",
            "unsupported_currency_for_vnd_limit",
            refs,
        )
    ltv = _policy_value(policy, "ltv")
    cap = _policy_value(policy, "max_amount")
    if ltv.status != "known" or ltv.value is None:
        return _answer(
            policy,
            "Nguồn hiện tại chưa cho một tỷ lệ tài sản bảo đảm duy nhất và được chứng minh, nên em chưa thể tính hạn mức tham khảo.",
            f"ltv_policy_{ltv.status}",
            ltv.evidence_refs,
        )
    ltv_amount = property_value * ltv.value / Decimal("100")
    conditional = property_fact.hypothetical or _has_current_hypothetical(
        understanding, product, {"currency"}
    )
    lead = "Nếu giá trị tài sản là mức giả định này, " if conditional else "Theo giá trị tài sản đã cung cấp, "
    if cap.status == "missing":
        text = (
            f"{lead}riêng theo tỷ lệ {_fmt(ltv.value)}% trong nguồn, số tiền tính "
            f"theo tỷ lệ là {_fmt_money(ltv_amount)}. Trần vay tuyệt đối chưa có "
            "trong nguồn, nên đây chưa phải hạn mức tối đa tổng thể. Giá trị thực "
            "tế còn phụ thuộc thẩm định; đây không phải xác nhận phê duyệt."
        )
        return _answer(
            policy,
            text,
            "calculated_ltv_ratio_only",
            _policy_refs(ltv),
        )
    if cap.status != "known" or cap.value is None:
        return _answer(
            policy,
            "Trần vay tuyệt đối trong nguồn hiện tại không có một giá trị duy nhất và được chứng minh, nên em chưa thể tính hạn mức tham khảo.",
            f"ltv_cap_{cap.status}",
            cap.evidence_refs,
        )
    estimate = min(ltv_amount, cap.value)
    text = (
        f"{lead}hạn mức tham khảo theo tỷ lệ {_fmt(ltv.value)}% và trần nguồn là "
        f"{_fmt_money(estimate)}. Giá trị thực tế còn phụ thuộc thẩm định; đây không "
        "phải xác nhận phê duyệt."
    )
    return _answer(
        policy,
        text,
        "calculated_ltv_cap",
        _policy_refs(ltv, cap),
    )


def _eligibility(
    understanding: TurnUnderstanding,
    state: DialogueState,
    policy: PolicySnapshot,
    product: str,
    conflicts: set[tuple[str, str]],
    sources: tuple[SourceSnippet, ...],
) -> GroundedAnswer:
    refs = _refs(sources)
    age_fact = _resolve_fact(
        understanding,
        state,
        product,
        "age",
        owner="self",
        allow_hypothetical=False,
        conflicts=conflicts,
    )
    income_fact = _resolve_fact(
        understanding,
        state,
        product,
        "income_monthly",
        owner="self",
        allow_hypothetical=False,
        conflicts=conflicts,
    )
    if age_fact.conflict:
        return _missing_or_conflict(policy, field="age", conflict=True, refs=refs)
    if income_fact.conflict:
        return _missing_or_conflict(
            policy, field="income_monthly", conflict=True, refs=refs
        )
    age = _positive_decimal(age_fact)
    income = _positive_decimal(income_fact)
    if age is None and income is None:
        return _answer(
            policy,
            "Em cần tuổi và thu nhập hằng tháng của chính người đăng ký để đối chiếu điều kiện nguồn.",
            "missing_self_eligibility_facts",
            refs,
        )

    min_age = _policy_value(policy, "min_age")
    max_age = _policy_value(policy, "max_age")
    min_income = _policy_value(policy, "min_income")
    if (
        min_age.value is not None
        and max_age.value is not None
        and min_age.value > max_age.value
    ):
        return _answer(
            policy,
            "Các giới hạn tuổi trong nguồn hiện tại không nhất quán, nên em chưa thể đối chiếu điều kiện.",
            "eligibility_age_range_invalid",
            refs,
        )
    comparisons: list[str] = []
    used_policy_values: list[_PolicyValue] = []
    unknown_source = False
    if age is not None:
        age_bounds = [bound for bound in (min_age, max_age) if bound.status == "known"]
        if not age_bounds:
            unknown_source = True
        else:
            if min_age.status != "known" or max_age.status != "known":
                unknown_source = True
            age_ok = (
                (min_age.value is None or age >= min_age.value)
                and (max_age.value is None or age <= max_age.value)
            )
            comparisons.append(
                f"tuổi đã nêu {'phù hợp' if age_ok else 'chưa phù hợp'} với giới hạn tuổi trong nguồn"
            )
            used_policy_values.extend(age_bounds)
    if income is not None:
        if min_income.status != "known" or min_income.value is None:
            unknown_source = True
        else:
            comparisons.append(
                "thu nhập của chính người đăng ký "
                + ("đạt" if income >= min_income.value else "chưa đạt")
                + f" mức tối thiểu {_fmt_money(min_income.value)} trong nguồn"
            )
            used_policy_values.append(min_income)
    if not comparisons:
        return _answer(
            policy,
            "Nguồn hiện tại chưa có đủ điều kiện tương ứng để đối chiếu các dữ kiện cá nhân đã cung cấp.",
            "eligibility_source_missing",
            refs,
        )
    text = "Đối chiếu sơ bộ: " + "; ".join(comparisons) + "."
    if age is None:
        text += " Cần thêm tuổi của chính người đăng ký để đối chiếu phần còn lại."
    if income is None:
        text += (
            " Cần thêm thu nhập hằng tháng của chính người đăng ký; thu nhập hộ "
            "gia đình không được tự chuyển thành thu nhập cá nhân."
        )
    if unknown_source:
        text += " Một phần điều kiện còn chưa có nguồn xác định."
    text += " Kết quả này không phải phê duyệt; hồ sơ vẫn cần thẩm định chính thức."
    return _answer(
        policy,
        text,
        "eligibility_compared_known_self_facts",
        _policy_refs(*used_policy_values),
    )


def _acknowledge_or_readback(
    understanding: TurnUnderstanding,
    state: DialogueState,
    policy: PolicySnapshot,
    product: str,
    conflicts: set[tuple[str, str]],
) -> GroundedAnswer:
    if conflicts:
        field_name, _ = sorted(conflicts)[0]
        return _missing_or_conflict(
            policy, field=field_name, conflict=True, refs=()
        )
    if understanding.intent == "acknowledge":
        current = [
            _current_delta_description(fact)
            for fact in understanding.facts
            if fact.turn == understanding.current_turn
        ]
        if current:
            text = "Em đã ghi nhận nội dung vừa nêu: " + "; ".join(current) + "."
        else:
            text = "Em đã ghi nhận ạ."
        reason = "acknowledge_current_delta"
    else:
        current = []
        for (scope, field_name, owner), fact in state.facts.items():
            key = (scope, field_name, owner)
            if key in state.ambiguous_at:
                continue
            if owner not in {"self", "household"} or scope not in {"*", product}:
                continue
            label = _field_label(field_name)
            if owner == "household":
                label += " của hộ gia đình"
            current.append(f"{label} {_display_fact(field_name, fact.value)}")
        current.sort()
        if current:
            text = "Thông tin hiện có: " + "; ".join(current) + "."
        else:
            text = "Hiện chưa có dữ kiện thực tế đã được ghi nhận để đọc lại."
        reason = "readback_current_state"
    if product == "savings" and state.get("term_months", product=product) is None:
        text += " Anh/chị vui lòng cho biết thêm kỳ hạn gửi."
        reason = (
            "acknowledge_missing_savings_term"
            if understanding.intent == "acknowledge"
            else "readback_missing_savings_term"
        )
    return _answer(policy, text, reason)


def _question(
    understanding: TurnUnderstanding,
    state: DialogueState,
    policy: PolicySnapshot,
    product: str,
    conflicts: set[tuple[str, str]],
    sources: tuple[SourceSnippet, ...],
) -> GroundedAnswer:
    refs = _refs(sources)
    if understanding.topic == "minimum_payment" and product == "card":
        if sources:
            return _selected_policy_source_answer(policy, sources)
        text = (
            "Khoản thanh toán tối thiểu là số tiền ít nhất cần trả cho kỳ sao kê để "
            "tránh bị ghi nhận là chưa thanh toán theo yêu cầu. Số cụ thể phải xem "
            "trên sao kê và quy định hiện hành của thẻ; em không tự đặt một tỷ lệ."
        )
        return _answer(policy, text, "minimum_payment_concept", refs)

    if understanding.topic == "rate":
        rate, bonus, term, term_fact, issue = _rate_for_term(
            understanding, state, policy, product, conflicts
        )
        hypothetical_operand = term_fact.hypothetical or _has_current_hypothetical(
            understanding, product, {"channel"}
        )
        blocking_issue = issue is not None and (
            issue.reason.startswith("conflicting_")
            or issue.reason.endswith(("_conflict", "_unproven", "_invalid"))
        )
        if issue and (hypothetical_operand or blocking_issue):
            return _answer(policy, issue.text, issue.reason, refs)
        if _policy_status_blocks_selected_source(rate) or _policy_status_blocks_selected_source(
            bonus
        ):
            return _answer(
                policy,
                "Nguồn hiện tại chưa cho một mức lãi suất duy nhất và được chứng minh phù hợp với dữ kiện đã nêu.",
                f"apr_{rate.status}" if rate.status != "known" else f"online_bonus_{bonus.status}",
                _policy_refs(rate, bonus),
            )
        if sources and not hypothetical_operand:
            return _selected_policy_source_answer(policy, sources)
        if issue:
            return _answer(policy, issue.text, issue.reason, refs)
        if rate.status == "known" and rate.value is not None:
            effective = rate.value + (bonus.value or Decimal("0"))
            term_text = f" cho kỳ hạn {term} tháng" if term is not None else ""
            lead = (
                "Nếu dùng phương án giả định vừa nêu, lãi suất"
                if _has_current_hypothetical(
                    understanding, product, {"term_months", "channel"}
                )
                else "Lãi suất"
            )
            text = (
                f"{lead} theo nguồn hiện tại{term_text} là "
                f"{_fmt(effective)}%/năm."
            )
            if bonus.value is not None:
                text += (
                    f" Mức này gồm {_fmt(bonus.value)} điểm phần trăm cộng thêm "
                    "cho kênh online."
                )
            return _answer(
                policy,
                text,
                "sourced_rate",
                _policy_refs(rate, bonus),
            )
        if rate.status in {"minimum", "maximum", "indicative"}:
            return _answer(
                policy,
                f"Theo nguồn hiện tại, lãi suất được nêu là "
                f"{_rate_bound_phrase(rate)}; đây không phải mức áp dụng chính xác.",
                f"sourced_rate_{rate.status}",
                rate.evidence_refs,
            )
        return _answer(
            policy,
            "Nguồn hiện tại chưa cho một mức lãi suất duy nhất phù hợp với dữ kiện đã nêu.",
            f"apr_{rate.status}",
            refs,
        )

    if understanding.topic == "annual_fee" and product == "card":
        tier = _resolve_fact(
            understanding,
            state,
            product,
            "card_tier",
            allow_hypothetical=True,
            conflicts=conflicts,
        )
        if tier.conflict:
            return _missing_or_conflict(
                policy, field="card_tier", conflict=True, refs=refs
            )
        fee = _policy_value(policy, "annual_fee", tier=tier.value or "")
        if _policy_status_blocks_selected_source(fee):
            return _answer(
                policy,
                "Nguồn hiện tại chưa cho một mức phí thường niên duy nhất và được chứng minh cho hạng thẻ này.",
                f"annual_fee_{fee.status}",
                fee.evidence_refs,
            )
        if sources and not tier.hypothetical:
            return _selected_policy_source_answer(policy, sources)
        if tier.value is None and fee.status != "known" and any(
            claim.key == "annual_fee" and claim.tier for claim in policy.claims
        ):
            return _missing_or_conflict(
                policy, field="card_tier", conflict=False, refs=refs
            )
        if fee.status == "known" and fee.value is not None:
            tier_text = f" cho hạng {tier.value}" if tier.value else ""
            lead = (
                "Nếu chọn hạng thẻ giả định này, phí thường niên"
                if tier.hypothetical
                else "Phí thường niên"
            )
            return _answer(
                policy,
                f"{lead} theo nguồn{tier_text} là {_fmt_money(fee.value)}.",
                "sourced_annual_fee",
                fee.evidence_refs,
            )
        return _answer(
            policy,
            "Nguồn hiện tại chưa cho một mức phí thường niên duy nhất cho hạng thẻ này.",
            f"annual_fee_{fee.status}",
            refs,
        )

    if understanding.topic == "limit" and product == "card":
        tier = _resolve_fact(
            understanding,
            state,
            product,
            "card_tier",
            allow_hypothetical=True,
            conflicts=conflicts,
        )
        if tier.conflict or tier.value is None:
            return _missing_or_conflict(
                policy, field="card_tier", conflict=tier.conflict, refs=refs
            )
        lower = _policy_value(policy, "tier_min", tier=tier.value)
        upper = _policy_value(policy, "tier_max", tier=tier.value)
        if (
            lower.status == "known"
            and upper.status == "known"
            and lower.value is not None
            and upper.value is not None
            and lower.value <= upper.value
        ):
            lead = (
                "Nếu chọn hạng thẻ giả định này, khoảng hạn mức"
                if tier.hypothetical
                else "Khoảng hạn mức"
            )
            return _answer(
                policy,
                f"{lead} theo nguồn cho hạng {tier.value} là từ "
                f"{_fmt_money(lower.value)} đến {_fmt_money(upper.value)}.",
                "sourced_tier_range",
                _policy_refs(lower, upper),
            )

    if understanding.topic == "limit" and product != "card":
        lower = _policy_value(policy, "min_amount")
        upper = _policy_value(policy, "max_amount")
        if (
            lower.status == "known"
            and upper.status == "known"
            and lower.value is not None
            and upper.value is not None
            and lower.value <= upper.value
        ):
            return _answer(
                policy,
                f"Khoảng số tiền theo nguồn hiện tại là từ {_fmt_money(lower.value)} "
                f"đến {_fmt_money(upper.value)}.",
                "sourced_amount_range",
                _policy_refs(lower, upper),
            )

    if understanding.topic == "term":
        lower = _policy_value(policy, "min_term")
        upper = _policy_value(policy, "max_term")
        if (
            lower.status == "known"
            and upper.status == "known"
            and lower.value is not None
            and upper.value is not None
            and lower.value <= upper.value
        ):
            return _answer(
                policy,
                f"Khoảng kỳ hạn theo nguồn hiện tại là từ {_fmt(lower.value)} đến "
                f"{_fmt(upper.value)} tháng.",
                "sourced_term_range",
                _policy_refs(lower, upper),
            )

    if understanding.topic == "early_withdrawal" and product == "savings":
        early_rate = _policy_value(policy, "early_rate")
        if early_rate.status == "known" and early_rate.value is not None:
            return _answer(
                policy,
                f"Mức lãi rút trước hạn theo nguồn hiện tại là "
                f"{_fmt(early_rate.value)}%/năm; số tiền thực tế còn phụ thuộc thời "
                "gian gửi thực tế.",
                "sourced_early_rate",
                early_rate.evidence_refs,
            )

    if sources:
        return _selected_policy_source_answer(policy, sources)
    return _answer(
        policy,
        "Nguồn hiện tại chưa có phần thông tin được chọn để trả lời chính xác; em chưa thể suy đoán thêm.",
        "selected_source_missing",
    )


def _customer_record_answer(
    understanding: TurnUnderstanding,
    state: DialogueState,
    policy: PolicySnapshot,
    product: str,
    conflicts: set[tuple[str, str]],
    sources: tuple[SourceSnippet, ...],
) -> GroundedAnswer:
    if understanding.topic in _PUBLIC_PRODUCT_TOPICS:
        public = _question(
            understanding, state, policy, product, conflicts, sources
        )
        supported = public.reason.startswith("sourced_") or public.reason in {
            "selected_source_answer",
            "minimum_payment_concept",
        }
        if supported and public.evidence_refs:
            text = (
                public.text
                + " Đây là thông tin sản phẩm được công bố chung. Em chưa có dữ "
                "liệu hồ sơ riêng đã xác thực để xác nhận khoản thực tế đã thu "
                "hoặc áp dụng, số dư hay trạng thái tài khoản của anh/chị."
            )
            return _answer(
                policy,
                text,
                "customer_record_public_partial",
                public.evidence_refs,
            )
    return _answer(
        policy,
        "Em chưa có dữ liệu hồ sơ khách hàng đã xác thực trong lượt này, nên "
        "không thể xác nhận số dư, trạng thái hồ sơ, nguồn tiền hoặc một thao tác "
        "trên tài khoản.",
        "customer_record_unavailable",
    )


def execute_turn(
    understanding: TurnUnderstanding,
    state: DialogueState,
    policy: PolicySnapshot,
    *,
    organization: str = "",
    agent_name: str = "",
) -> GroundedAnswer:
    """Execute one validated turn and always return a conservative answer."""
    if understanding.intent in _SAFETY_INTENTS:
        return _safety_answer(
            understanding,
            policy,
            organization=organization,
            agent_name=agent_name,
        )

    if understanding.certainty == "ambiguous":
        sources = _selected_sources(understanding, policy)
        return _answer(
            policy,
            "Em chưa hiểu đủ rõ yêu cầu hoặc dữ kiện vừa nêu; anh/chị vui lòng xác nhận lại.",
            "ambiguous_understanding",
            _refs(sources),
        )

    product = _effective_product(understanding, state, policy)
    conflicts = _current_actual_conflicts(understanding, product)
    sources = _selected_sources(understanding, policy)

    if understanding.intent == "greeting":
        return _answer(policy, "Dạ, em có thể hỗ trợ thông tin gì cho anh/chị ạ?", "greeting")
    if understanding.intent == "off_topic":
        return _answer(
            policy,
            "Em chỉ có thông tin trong phạm vi tư vấn tài chính đang được cung cấp; em chưa có nguồn phù hợp cho câu hỏi này.",
            "off_topic_without_invention",
        )
    if understanding.intent in {"acknowledge", "readback"}:
        return _acknowledge_or_readback(
            understanding, state, policy, product, conflicts
        )
    if (
        policy.product not in {"", "unknown", product}
        and understanding.intent
        in {
            "question",
            "calculate_interest",
            "calculate_payment",
            "calculate_ltv",
            "eligibility",
            "customer_record",
        }
    ):
        return _answer(
            policy,
            "Nguồn hiện tại thuộc sản phẩm khác, nên em chưa thể dùng nguồn này để trả lời yêu cầu.",
            "policy_product_mismatch",
        )
    if understanding.intent == "customer_record":
        return _customer_record_answer(
            understanding, state, policy, product, conflicts, sources
        )
    if understanding.intent == "calculate_interest":
        return _calculate_interest(
            understanding, state, policy, product, conflicts, sources
        )
    if understanding.intent == "calculate_payment":
        return _calculate_payment(
            understanding, state, policy, product, conflicts, sources
        )
    if understanding.intent == "calculate_ltv":
        return _calculate_ltv(
            understanding, state, policy, product, conflicts, sources
        )
    if understanding.intent == "eligibility":
        return _eligibility(
            understanding, state, policy, product, conflicts, sources
        )
    if understanding.intent == "question":
        return _question(
            understanding, state, policy, product, conflicts, sources
        )
    return _answer(
        policy,
        "Em chưa có đủ dữ kiện và nguồn phù hợp để trả lời chính xác; anh/chị vui lòng nói rõ nội dung cần hỗ trợ.",
        "unknown_or_ambiguous_intent",
        _refs(sources),
    )


__all__ = ["execute_turn"]
