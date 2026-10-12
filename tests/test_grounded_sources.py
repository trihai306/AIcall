import asyncio
import hashlib
from decimal import Decimal

import pytest

from backend.pipeline import grounded_sources
from backend.pipeline.grounded_contracts import PolicyClaim, PolicyExtraction
from backend.pipeline.grounded_sources import (
    _CACHE,
    _CACHE_LIMIT,
    _INFLIGHT,
    _clear_policy_cache,
    build_policy,
)
from backend.pipeline.ngu_canh_tai_lieu import toan_van


def async_test(function):
    def run():
        return asyncio.run(function())
    run.__name__ = function.__name__
    return run


class FakeLLM:
    def __init__(self, result=None):
        self.result = result or {"claims": []}
        self.calls = []

    async def generate_structured(self, messages, schema, **kwargs):
        self.calls.append((messages, schema, kwargs))
        return self.result


class SequenceLLM(FakeLLM):
    def __init__(self, results):
        super().__init__()
        self.results = iter(results)

    async def generate_structured(self, messages, schema, **kwargs):
        self.calls.append((messages, schema, kwargs))
        return next(self.results)


class BlockingLLM(FakeLLM):
    def __init__(self, result):
        super().__init__(result)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate_structured(self, messages, schema, **kwargs):
        self.calls.append((messages, schema, kwargs))
        self.started.set()
        await self.release.wait()
        return self.result


@pytest.fixture(autouse=True)
def _empty_policy_cache():
    _clear_policy_cache()
    yield
    _clear_policy_cache()


@async_test
async def test_canonical_policy_changes_are_read_from_current_content():
    source_a = """# Personal Loan - Dynamic Policy
## Product policy
- Interest rate: from 4.25%/year
- Limit: up to 321 million VND
- Term: 7 - 41 months
- Customer age: 23 - 61 years old
- Stable income from 6 million VND/month
"""
    source_b = source_a.replace("4.25", "5.75").replace("321", "456") \
        .replace("7 - 41", "9 - 47").replace("23 - 61", "25 - 63") \
        .replace("income from 6 million", "income from 8 million")

    first = await build_policy("loan", source_a, FakeLLM())
    second = await build_policy("loan", source_b, FakeLLM())

    assert first.unique("apr") is None
    assert second.unique("apr") is None
    assert [(claim.value, claim.qualifier) for claim in first.claims
            if claim.key == "apr"] == [("4.25", "minimum")]
    assert [(claim.value, claim.qualifier) for claim in second.claims
            if claim.key == "apr"] == [("5.75", "minimum")]
    assert first.unique("max_amount") == 321_000_000
    assert second.unique("max_amount") == 456_000_000
    assert second.unique("min_term") == 9
    assert second.unique("max_term") == 47
    assert second.unique("min_age") == 25
    assert second.unique("max_age") == 63
    assert second.unique("min_income") == 8_000_000
    assert first.version != second.version


@async_test
async def test_savings_bonus_minimum_and_rates_change_without_code_change():
    template = """# Savings
## Policy
- Minimum deposit: {minimum} million VND
- {term} month term: interest rate {apr}%/year
- Online interest rate adds {bonus}%/year
- Early withdrawal interest rate {early}%/year
"""
    first = await build_policy(
        "savings", template.format(minimum=3, term=11, apr="4.4", bonus="0.3", early="0.7"),
        FakeLLM(),
    )
    second = await build_policy(
        "savings", template.format(minimum=4, term=13, apr="5.1", bonus="0.6", early="0.9"),
        FakeLLM(),
    )

    assert first.unique("min_amount") == 3_000_000
    assert second.unique("min_amount") == 4_000_000
    assert first.unique("apr", term_months=11) == Decimal("4.4")
    assert second.unique("apr", term_months=13) == Decimal("5.1")
    assert second.unique("online_bonus") == Decimal("0.6")
    assert second.unique("early_rate") == Decimal("0.9")


@async_test
async def test_mortgage_ltv_and_loan_max_are_separate_units():
    source_a = """# Home Loan
## Policy
- Limit: up to 73% of property value, maximum 17 billion VND
- Term: maximum 29 years
"""
    source_b = source_a.replace("73%", "68%").replace("17 billion", "23 billion") \
        .replace("29 years", "31 years")
    first = await build_policy("mortgage", source_a, FakeLLM())
    second = await build_policy("mortgage", source_b, FakeLLM())

    assert first.unique("ltv") == 73
    assert first.unique("max_amount") == 17_000_000_000
    assert first.unique("max_term") == 29 * 12
    assert second.unique("ltv") == 68
    assert second.unique("max_amount") == 23_000_000_000
    assert second.unique("max_term") == 31 * 12


@async_test
async def test_mixed_term_units_are_normalized_to_months():
    source = """# Personal Loan
## Policy
- Term: 12 months - 3 years
"""
    policy = await build_policy("loan", source, FakeLLM())

    assert policy.unique("min_term") == 12
    assert policy.unique("max_term") == 36
    assert {claim.unit for claim in policy.claims} == {"months"}


@async_test
async def test_dynamic_card_tiers_are_not_named_in_code():
    source_a = """# Credit Card
## Tiers
1. Card Aurora: Limit 12-44 million VND, annual fee 123,000 VND/year
2. Card Nebula: Limit 55-888 million VND, annual fee 654,000 VND/year
"""
    source_b = source_a.replace("Aurora", "Comet").replace("12-44", "14-49") \
        .replace("123,000", "321,000")
    first = await build_policy("card", source_a, FakeLLM())
    second = await build_policy("card", source_b, FakeLLM())

    assert first.unique("tier_min", tier="Aurora") == 12_000_000
    assert first.unique("tier_max", tier="Aurora") == 44_000_000
    assert first.unique("annual_fee", tier="Aurora") == 123_000
    assert first.unique("tier_max", tier="Nebula") == 888_000_000
    assert first.unique("annual_fee", tier="Nebula") == 654_000
    assert second.unique("tier_min", tier="Aurora") is None
    assert second.unique("tier_min", tier="Comet") == 14_000_000
    assert second.unique("tier_max", tier="Comet") == 49_000_000
    assert second.unique("annual_fee", tier="Comet") == 321_000


@async_test
async def test_card_tier_labels_own_values_across_clause_permutations():
    source = """# Credit Card
## Tiers
1. Thẻ Gold: Phí thường niên 400.000đ/năm, hạn mức 30-200 triệu đồng
2. Thẻ Orbit: Hạn mức 25-90 triệu đồng; hoàn tiền tối đa 1 triệu đồng; phí thường niên 222.000đ/năm
"""
    policy = await build_policy("card", source, FakeLLM())

    assert policy.unique("annual_fee", tier="Gold") == 400_000
    assert policy.unique("tier_min", tier="Gold") == 30_000_000
    assert policy.unique("tier_max", tier="Gold") == 200_000_000
    assert policy.unique("annual_fee", tier="Orbit") == 222_000
    assert policy.unique("tier_min", tier="Orbit") == 25_000_000
    assert policy.unique("tier_max", tier="Orbit") == 90_000_000
    assert not any(claim.value == "1000000" for claim in policy.claims)


@async_test
async def test_conflict_and_deletion_remain_unknown():
    conflicting = """# Personal Loan
## Policy
- Interest rate: 7.1%/year
- Interest rate: 8.2%/year
"""
    deleted = """# Personal Loan
## Policy
- Contact the bank for the current rate.
"""
    first = await build_policy("loan", conflicting, FakeLLM())
    second = await build_policy("loan", deleted, FakeLLM())

    assert first.unique("apr") is None
    assert second.unique("apr") is None


@async_test
async def test_llm_complement_cannot_replace_verified_conflict():
    source = """# Personal Loan
## Policy
- Interest rate: 7.1%/year
- Interest rate: 8.2%/year
"""
    quote = "- Interest rate: 7.1%/year"
    llm = FakeLLM(PolicyExtraction(claims=[
        PolicyClaim(key="apr", value="7.1", unit="percent", quote=quote),
    ]))

    policy = await build_policy("loan", source, llm)

    assert policy.unique("apr") is None
    assert [claim.value for claim in policy.claims if claim.key == "apr"] == ["7.1", "8.2"]
    assert policy.errors == ("rejected_llm_claim:0:apr",)


@async_test
async def test_full_content_hash_invalidates_same_size_change_and_ids_are_versioned():
    llm = FakeLLM()
    source_a = "# Personal Loan\n- Interest rate: 1.2%/year\n"
    source_b = "# Personal Loan\n- Interest rate: 9.8%/year\n"
    first = await build_policy("loan", source_a, llm)
    again = await build_policy("loan", source_a, llm)
    second = await build_policy("loan", source_b, llm)

    assert len(source_a.encode()) == len(source_b.encode())
    assert first is again
    assert first.version == hashlib.sha256(source_a.encode()).hexdigest()
    assert second.version == hashlib.sha256(source_b.encode()).hexdigest()
    assert first.version != second.version
    assert all(snippet.id.startswith(first.version + ":L") for snippet in first.snippets)
    assert {s.id for s in first.snippets}.isdisjoint({s.id for s in second.snippets})
    assert first.evidence_for("apr") == (first.claims[0].source_ref,)
    assert first.claims[0].source_ref in {snippet.id for snippet in first.snippets}


@async_test
async def test_policy_cache_is_bounded():
    for index in range(_CACHE_LIMIT + 7):
        source = f"# Personal Loan\n- Interest rate: {index + 1}%/year\n"
        await build_policy("loan", source, FakeLLM())

    assert len(_CACHE) == _CACHE_LIMIT


@async_test
async def test_only_selected_product_block_is_used_not_mixed_faq_tail():
    source = """# Savings
- 9 month term: interest rate 4.6%/year
# Shared FAQ
- Personal loan interest rate: 19.9%/year
- Personal loan limit: maximum 777 million VND
"""
    policy = await build_policy("savings", source, FakeLLM())

    assert policy.unique("apr", term_months=9) == Decimal("4.6")
    assert policy.unique("apr") is None
    assert policy.unique("max_amount") is None
    assert all("19.9" not in snippet.text for snippet in policy.snippets)


@async_test
async def test_unknown_product_cannot_mine_numbers_from_shared_source():
    source = """# Shared FAQ
- Personal loan interest rate: 19.9%/year
- Credit card limit: maximum 777 million VND
"""
    policy = await build_policy("unknown", source, FakeLLM())

    assert policy.claims == ()
    assert policy.snippets == ()
    known_product = await build_policy("loan", source, FakeLLM())
    assert known_product.claims == ()
    assert known_product.snippets == ()


@async_test
async def test_current_four_product_documents_have_clean_claim_summaries():
    policies = {}
    llms = {}
    for family, name in (
        ("loan", "vay tín chấp"),
        ("mortgage", "vay mua nhà"),
        ("savings", "tiết kiệm"),
        ("card", "thẻ tín dụng"),
    ):
        llms[family] = FakeLLM()
        policies[family] = await build_policy(
            family, toan_van(name, fresh=True), llms[family],
        )

    assert {family: len(policy.claims) for family, policy in policies.items()} == {
        "loan": 7, "mortgage": 8, "savings": 13, "card": 12,
    }
    assert all(not llm.calls for llm in llms.values())

    assert {Decimal(c.value) for c in policies["loan"].claims if c.key == "apr"} \
        == {Decimal("7.9")}
    assert {Decimal(c.value) for c in policies["mortgage"].claims if c.key == "apr"} \
        == {Decimal("8"), Decimal("10")}
    assert policies["mortgage"].unique("ltv") == 80
    assert policies["mortgage"].unique("max_amount") == 10_000_000_000
    assert policies["mortgage"].unique("max_term") == 25 * 12

    savings = policies["savings"]
    assert savings.unique("online_bonus") == Decimal("0.2")
    assert savings.unique("early_rate") == Decimal("0.5")
    assert savings.unique("apr", term_months=12) == Decimal("5.5")
    assert savings.unique("min_amount") == 1_000_000

    card = policies["card"]
    assert not [claim for claim in card.claims if claim.key == "apr"]
    assert {claim.tier for claim in card.claims if claim.key == "annual_fee"} \
        == {"Classic", "Gold", "Platinum"}

    expected_age_counts = {"loan": 2, "mortgage": 2, "savings": 1, "card": 1}
    for family, policy in policies.items():
        assert sum(c.key in {"min_age", "max_age"} for c in policy.claims) \
            == expected_age_counts[family]
        assert all(claim.source_ref in {s.id for s in policy.snippets}
                   for claim in policy.claims)
        assert all("vi du" not in claim.quote.casefold()
                   and "cashback" not in claim.quote.casefold()
                   for claim in policy.claims if claim.key == "apr")
        assert all("Câu Hỏi Thường Gặp" not in snippet.text
                   for snippet in policy.snippets)


@async_test
async def test_worked_example_is_not_policy_apr():
    source = """# Personal Loan
## Worked examples
- Example: borrow 100 million VND for 20 months at 15.5%/year
## Policy
- Interest rate is published after appraisal
"""
    policy = await build_policy("loan", source, FakeLLM())
    assert policy.unique("apr") is None


@async_test
async def test_llm_cannot_promote_example_section_to_policy_apr():
    source = """# Personal Loan
## Worked examples
Annual borrowing cost marker => 14.7%
"""
    quote = "Annual borrowing cost marker => 14.7%"
    llm = FakeLLM(PolicyExtraction(claims=[
        PolicyClaim(key="apr", value="14.7", unit="percent", quote=quote),
    ]))

    policy = await build_policy("loan", source, llm)
    assert policy.unique("apr") is None
    assert policy.errors == ("rejected_llm_claim:0:apr",)


@async_test
async def test_llm_cannot_promote_discount_to_base_apr():
    source = """# Personal Loan
## Policy
- Limit: maximum 80 million VND
- Discount: reduced interest rate by 0.5% annually
"""
    quote = "- Discount: reduced interest rate by 0.5% annually"
    llm = FakeLLM(PolicyExtraction(claims=[
        PolicyClaim(key="apr", value="0.5", unit="percent", quote=quote),
    ]))

    policy = await build_policy("loan", source, llm)
    assert policy.unique("apr") is None
    assert not [claim for claim in policy.claims if claim.key == "apr"]
    assert policy.errors == ("rejected_llm_claim:0:apr",)


@async_test
async def test_monthly_rate_is_not_relabelled_as_apr():
    source = """# Personal Loan
## Policy
- Interest rate: 1.2%/month
"""
    policy = await build_policy("loan", source, FakeLLM())
    assert policy.unique("apr") is None


@async_test
async def test_host_derives_number_unit_and_qualifier_from_exact_clause():
    source = """# Personal Loan
## Commercial terms
Annual borrowing cost marker => 6.35%
"""
    policy = await build_policy("loan", source, None)

    assert policy.unique("apr") == Decimal("6.35")
    assert len(policy.claims) == 1
    assert policy.errors == ()
    assert policy.evidence_for("apr") == (policy.claims[0].source_ref,)
    assert policy.claims[0].source_ref != "forged:source"


@async_test
async def test_host_derives_source_qualifier_without_model_output():
    source = """# Personal Loan
## Commercial terms
Annual borrowing cost starts from 7.9%
"""
    quote = "Annual borrowing cost starts from 7.9%"
    policy = await build_policy("loan", source, None)

    assert policy.unique("apr") is None
    assert [(claim.value, claim.qualifier) for claim in policy.claims] \
        == [("7.9", "minimum")]
    assert policy.errors == ()


@async_test
async def test_canonical_apr_without_spacing_preserves_minimum_qualifier():
    source = """# Vay Tín Chấp
## Chính sách
- Lãi suất:từ7.9%/năm
"""
    policy = await build_policy("loan", source, FakeLLM())

    apr = [claim for claim in policy.claims if claim.key == "apr"]
    assert [(claim.value, claim.qualifier) for claim in apr] == [("7.9", "minimum")]
    assert policy.unique("apr") is None


@async_test
async def test_llm_complements_partial_format_once_per_content_version():
    source_a = """# Savings
## Policy
- Minimum deposit: 3 million VND
Annual borrowing cost marker => 6.35%
"""
    source_b = source_a.replace("3 million", "4 million").replace("6.35", "7.45")
    llm = FakeLLM()

    first = await build_policy("savings", source_a, llm)
    cached = await build_policy("savings", source_a, llm)
    second = await build_policy("savings", source_b, llm)

    assert first is cached
    assert first.unique("min_amount") == 3_000_000
    assert first.unique("apr") == Decimal("6.35")
    assert second.unique("min_amount") == 4_000_000
    assert second.unique("apr") == Decimal("7.45")
    assert first.version != second.version
    assert len(source_a.encode()) == len(source_b.encode())
    assert len(llm.calls) == 2
    assert "apr" not in llm.calls[0][0][0]["content"]
    assert first.errors == ()


@async_test
async def test_llm_fallback_rejects_foreign_currency_relabelled_as_vnd():
    source = """# Personal Loan
## Commercial terms
Ceiling marker => maximum 25,000 USD
"""
    quote = "Ceiling marker => maximum 25,000 USD"
    llm = FakeLLM({"claims": [{
        "key": "max_amount", "value": "25000", "unit": "vnd",
        "term_months": None, "tier": "", "quote": quote,
    }]})
    policy = await build_policy("loan", source, llm)

    assert policy.unique("max_amount") is None
    assert policy.errors == ("rejected_llm_claim:0:max_amount",)


@async_test
async def test_malformed_llm_result_fails_closed():
    source = "# Personal Loan\nUnfamiliar numeric policy layout: value 42 units\n"
    llm = FakeLLM({"claims": [{"invented": "field"}]})
    policy = await build_policy("loan", source, llm)

    assert policy.claims == ()
    assert policy.errors == ("llm_extraction_failed:ValidationError",)


@async_test
async def test_singleflight_shares_inference_and_survives_one_waiter_cancellation():
    source = """# Personal Loan
## Commercial terms
Annual borrowing cost 6.4%
"""
    quote = "Annual borrowing cost 6.4%"
    llm = BlockingLLM(PolicyExtraction(claims=[
        PolicyClaim(key="apr", value="6.4", unit="percent", quote=quote),
    ]))

    cancelled = asyncio.create_task(build_policy("loan", source, llm))
    await llm.started.wait()
    readers = [asyncio.create_task(build_policy("loan", source, llm))
               for _ in range(7)]
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    llm.release.set()
    snapshots = await asyncio.gather(*readers)
    cached = await build_policy("loan", source, llm)

    assert len(llm.calls) == 1
    assert all(snapshot is snapshots[0] for snapshot in snapshots)
    assert cached is snapshots[0]
    assert cached.unique("apr") == Decimal("6.4")
    assert not _INFLIGHT


@async_test
async def test_singleflight_timeout_preserves_host_grounded_rate():
    source = """# Personal Loan
## Commercial terms
Annual borrowing cost 6.4%
"""
    llm = BlockingLLM({"claims": []})
    previous = grounded_sources._STRUCTURED_TIMEOUT_S
    grounded_sources._STRUCTURED_TIMEOUT_S = 0.01
    try:
        snapshots = await asyncio.gather(*(
            build_policy("loan", source, llm) for _ in range(6)
        ))
    finally:
        grounded_sources._STRUCTURED_TIMEOUT_S = previous

    assert len(llm.calls) == 1
    assert all(snapshot is snapshots[0] for snapshot in snapshots)
    assert snapshots[0].unique("apr") == Decimal("6.4")
    assert snapshots[0].errors == ("llm_extraction_failed:TimeoutError",)
    assert not _INFLIGHT


@async_test
async def test_host_clauses_ground_compact_savings_fields_without_llm():
    source = """# Savings
## Policy
Kỳ hạn6tháng4,10%/năm;onlinecộng0,15điểmphầntrăm;tốithiểu2triệu.
"""
    policy = await build_policy("savings", source, None)

    assert policy.unique("apr", term_months=6) == Decimal("4.10")
    assert policy.unique("online_bonus") == Decimal("0.15")
    assert policy.unique("min_amount") == 2_000_000
    assert policy.errors == ()
    narrow = {snippet.id: snippet.text for snippet in policy.snippets if ":C" in snippet.id}
    assert set(narrow.values()) == {
        "Kỳ hạn6tháng4,10%/năm",
        "onlinecộng0,15điểmphầntrăm",
        "tốithiểu2triệu",
    }
    for claim in policy.claims:
        assert narrow[claim.source_ref] == claim.quote


@async_test
async def test_host_clauses_keep_card_labels_independent_of_clause_order():
    source = """# Credit Card
## Tiers
Aurora:hạnmức250-900triệu,phínăm555.000đ/năm.
"""
    policy = await build_policy("card", source, None)

    assert policy.unique("tier_min", tier="Aurora") == 250_000_000
    assert policy.unique("tier_max", tier="Aurora") == 900_000_000
    assert policy.unique("annual_fee", tier="Aurora") == 555_000
    assert policy.errors == ()
    assert all(next(snippet for snippet in policy.snippets
                    if snippet.id == claim.source_ref).text == claim.quote
               for claim in policy.claims)


@async_test
async def test_host_clauses_ground_compact_mortgage_constraints():
    source = """# Home Loan
## Policy
Tốiđa65%giátrịnhà.Tuổi25-58.Thunhậptoithiểu18triệu/tháng.
"""
    policy = await build_policy("mortgage", source, None)

    assert policy.unique("ltv") == 65
    assert policy.unique("min_age") == 25
    assert policy.unique("max_age") == 58
    assert policy.unique("min_income") == 18_000_000
    assert policy.errors == ()


@async_test
async def test_host_clauses_keep_each_rate_and_reject_bad_model_proposals():
    source = """# Savings
## Policy
Kỳ hạn6tháng4,10%/năm;Kỳ hạn12tháng5,20%/năm.
Mứctốithiểu3triệu;Mứctốithiểu3triệu.
"""
    llm = FakeLLM(PolicyExtraction(claims=[
        PolicyClaim(key="apr", value="4.10", unit="percent", term_months=12,
                    quote="Kỳ hạn6tháng4,10%/năm"),
        PolicyClaim(key="apr", value="4.10", unit="percent", term_months=6,
                    quote="Kỳ hạn6tháng4,10%/năm!"),
        PolicyClaim(key="min_amount", value="3000000", unit="vnd",
                    quote="Mứctốithiểu3triệu", qualifier="minimum"),
        PolicyClaim(key="apr", value="4.10", unit="percent", term_months=6,
                    quote="Kỳ hạn6tháng4,10%/năm;Kỳ hạn12tháng5,20%/năm"),
    ]))

    policy = await build_policy("savings", source, llm)

    assert policy.unique("apr", term_months=6) == Decimal("4.10")
    assert policy.unique("apr", term_months=12) == Decimal("5.20")
    assert policy.unique("min_amount") == 3_000_000
    assert len(policy.claims) == 3
    assert policy.errors == (
        "rejected_llm_claim:0:apr",
        "rejected_llm_claim:1:apr",
        "rejected_llm_claim:2:min_amount",
        "rejected_llm_claim:3:apr",
    )


@async_test
async def test_narrow_quote_cannot_hide_example_or_discount_parent_context():
    source = """# Personal Loan
## Policy
Ví dụ: Kỳ hạn6tháng4,10%/năm.
Giảm giá: Lãi suất6,20%/năm.
"""
    llm = FakeLLM(PolicyExtraction(claims=[
        PolicyClaim(key="apr", value="4.10", unit="percent", term_months=6,
                    quote="Kỳ hạn6tháng4,10%/năm"),
        PolicyClaim(key="apr", value="6.20", unit="percent",
                    quote="Lãi suất6,20%/năm"),
    ]))

    policy = await build_policy("loan", source, llm)

    assert policy.unique("apr") is None
    assert policy.claims == ()
    assert policy.errors == (
        "rejected_llm_claim:0:apr",
        "rejected_llm_claim:1:apr",
    )


@async_test
async def test_compact_source_mutations_drive_all_host_derived_values():
    savings_a = "# Savings\n[TEST ONLY A] Kỳ hạn 6 tháng 4,10%/năm; online cộng 0,15 điểm phần trăm; tối thiểu 2 triệu.\n"
    savings_b = "# Savings\n[TEST ONLY B] Tối thiểu 5 triệu. Gửi online cộng 0,40 điểm %. Lãi kỳ hạn 6 tháng là 5,35%/năm.\n"
    card_a = "# Credit Card\nAurora:hạnmức250-900triệu,phínăm555.000đ/năm.\n"
    card_b = "# Credit Card\nNebula:hạnmức300-800triệu,phínăm666.000đ/năm.\n"
    mortgage_a = "# Home Loan\n[TEST ONLY A] Tối đa 65% giá trị nhà. Tuổi 25-58. Thu nhập tối thiểu 18 triệu/tháng.\n"
    mortgage_b = "# Home Loan\n[TEST ONLY B] Thu nhập từ 14,5 triệu; tuổi từ 23 đến 63; tỷ lệ cho vay tối đa 72,5% giá trị.\n"
    llm = SequenceLLM([
        {"claims": [
            {"key": "apr", "quote": "[TEST ONLY A] Kỳ hạn 6 tháng 4,10%/năm"},
            {"key": "online_bonus", "quote": "online cộng 0,15 điểm phần trăm"},
            {"key": "min_amount", "quote": "tối thiểu 2 triệu"},
        ]},
        {"claims": [
            {"key": "min_amount", "quote": "[TEST ONLY B] Tối thiểu 5 triệu"},
            {"key": "online_bonus", "quote": "Gửi online cộng 0,40 điểm %"},
            {"key": "apr", "quote": "Lãi kỳ hạn 6 tháng là 5,35%/năm"},
        ]},
        {"claims": [
            {"key": "tier_min", "quote": "hạnmức250-900triệu"},
            {"key": "tier_max", "quote": "hạnmức250-900triệu"},
            {"key": "annual_fee", "quote": "phínăm555.000đ/năm"},
        ]},
        {"claims": [
            {"key": "tier_min", "quote": "hạnmức300-800triệu"},
            {"key": "tier_max", "quote": "hạnmức300-800triệu"},
            {"key": "annual_fee", "quote": "phínăm666.000đ/năm"},
        ]},
        {"claims": [
            {"key": "ltv", "quote": "[TEST ONLY A] Tối đa 65% giá trị nhà"},
            {"key": "min_income", "quote": "Thu nhập tối thiểu 18 triệu/tháng"},
        ]},
        {"claims": [
            {"key": "min_income", "quote": "[TEST ONLY B] Thu nhập từ 14,5 triệu"},
            {"key": "ltv", "quote": "tỷ lệ cho vay tối đa 72,5% giá trị"},
        ]},
    ])

    sa = await build_policy("savings", savings_a, llm)
    sb = await build_policy("savings", savings_b, llm)
    ca = await build_policy("card", card_a, llm)
    cb = await build_policy("card", card_b, llm)
    ma = await build_policy("mortgage", mortgage_a, llm)
    mb = await build_policy("mortgage", mortgage_b, llm)

    assert (sa.unique("apr", term_months=6), sa.unique("online_bonus"),
            sa.unique("min_amount")) == (Decimal("4.10"), Decimal("0.15"), 2_000_000)
    assert (sb.unique("apr", term_months=6), sb.unique("online_bonus"),
            sb.unique("min_amount")) == (Decimal("5.35"), Decimal("0.40"), 5_000_000)
    assert (ca.unique("tier_min", tier="Aurora"),
            ca.unique("tier_max", tier="Aurora"),
            ca.unique("annual_fee", tier="Aurora")) == (
                250_000_000, 900_000_000, 555_000)
    assert (cb.unique("tier_min", tier="Nebula"),
            cb.unique("tier_max", tier="Nebula"),
            cb.unique("annual_fee", tier="Nebula")) == (
                300_000_000, 800_000_000, 666_000)
    assert (ma.unique("ltv"), ma.unique("min_age"), ma.unique("max_age"),
            ma.unique("min_income")) == (65, 25, 58, 18_000_000)
    assert (mb.unique("ltv"), mb.unique("min_age"), mb.unique("max_age"),
            mb.unique("min_income")) == (Decimal("72.5"), 23, 63, 14_500_000)
    assert all(first.version != second.version for first, second in (
        (sa, sb), (ca, cb), (ma, mb),
    ))
    assert len(llm.calls) == 6


@async_test
async def test_multi_card_parent_requires_the_matching_dynamic_owner():
    source = """# Credit Card
Aurora:hạnmức20-40triệu;Nebula:hạnmức50-90triệu.
"""
    policy = await build_policy("card", source, None)

    assert policy.unique("tier_max", tier="Aurora") == 40_000_000
    assert policy.unique("tier_max", tier="Nebula") == 90_000_000
    assert policy.errors == ()


@async_test
async def test_gate_style_metadata_and_reordered_tier_phrases_remain_data_driven():
    source_a = """# Credit Card
[TEST ONLY A] Aurora: hạn mức 250-900 triệu, phí năm 555.000đ. Gold: phí 333.000đ, hạn mức 45-180 triệu. Classic: 111.000đ, 12-48 triệu.
"""
    source_b = """# Credit Card
[TEST ONLY B] Gold giới hạn từ 45 đến 180 triệu; phí năm Gold 333.000đ. Phí Aurora 555.000đ; Aurora có giới hạn 250-900 triệu.
"""
    first = await build_policy("card", source_a, None)
    second = await build_policy("card", source_b, None)

    for policy in (first, second):
        assert policy.unique("tier_min", tier="Aurora") == 250_000_000
        assert policy.unique("tier_max", tier="Aurora") == 900_000_000
        assert policy.unique("annual_fee", tier="Aurora") == 555_000
        assert policy.unique("tier_min", tier="Gold") == 45_000_000
        assert policy.unique("tier_max", tier="Gold") == 180_000_000
        assert policy.unique("annual_fee", tier="Gold") == 333_000
    assert first.unique("annual_fee", tier="Classic") is None
    assert first.errors == ()
    assert second.errors == ()


@async_test
async def test_wire_bound_keys_reject_unlabelled_single_values():
    source = """# Personal Loan
Income 20 million VND/month
Age 30 years old
Term 12 months
"""
    llm = FakeLLM({"claims": [
        {"key": "min_income", "quote": "Income 20 million VND/month"},
        {"key": "min_age", "quote": "Age 30 years old"},
        {"key": "max_age", "quote": "Age 30 years old"},
        {"key": "min_term", "quote": "Term 12 months"},
        {"key": "max_term", "quote": "Term 12 months"},
    ]})

    policy = await build_policy("loan", source, llm)

    assert policy.claims == ()
    assert policy.errors == (
        "rejected_llm_claim:0:min_income",
        "rejected_llm_claim:1:min_age",
        "rejected_llm_claim:2:max_age",
        "rejected_llm_claim:3:min_term",
        "rejected_llm_claim:4:max_term",
    )


@async_test
async def test_wire_bound_keys_accept_explicit_source_boundaries():
    source = """# Personal Loan
Income at least 20 million VND/month
Age at least 30 years old
Term at least 12 months
Term at most 48 months
"""
    policy = await build_policy("loan", source, None)

    assert policy.unique("min_income") == 20_000_000
    assert policy.unique("min_age") == 30
    assert policy.unique("min_term") == 12
    assert policy.unique("max_term") == 48
    assert {claim.qualifier for claim in policy.claims} == {"minimum", "maximum"}
    assert policy.errors == ()


@async_test
async def test_wire_schema_and_host_reject_out_of_scope_product_key():
    source = """# Personal Loan
Annual fee 700,000 VND
"""
    llm = FakeLLM({"claims": [{
        "key": "annual_fee", "quote": "Annual fee 700,000 VND",
        "value": "700000", "unit": "vnd", "term_months": 99,
    }]})

    policy = await build_policy("loan", source, llm)

    assert policy.claims == ()
    assert policy.errors == ("rejected_llm_claim:0:annual_fee",)
    schema = llm.calls[0][1]
    proposal_schema = schema["$defs"]["_WirePolicyProposal"]
    assert set(proposal_schema["properties"]) == {"key", "quote", "tier"}
    assert "annual_fee" not in proposal_schema["properties"]["key"]["enum"]
    assert proposal_schema["additionalProperties"] is False


@async_test
async def test_gate_v4_four_product_fixtures_compile_with_no_llm():
    sources = {
        "loan": """# Personal Loan
Lãi suất từ 7,25%/năm; hạn mức tối đa 280 triệu; kỳ hạn 9-42 tháng; tuổi 23-61; thu nhập tối thiểu 8 triệu/tháng.
""",
        "savings": """# Savings
[TEST ONLY A] Kỳ hạn 6 tháng 4,10%/năm; online cộng 0,15 điểm phần trăm; tối thiểu 2 triệu.
""",
        "mortgage": """# Home Loan
[TEST ONLY A] Tối đa 65% giá trị nhà. Tuổi 25-58. Thu nhập tối thiểu 18 triệu/tháng.
""",
        "card": """# Credit Card
[TEST ONLY A] Aurora: hạn mức 250-900 triệu, phí năm 555.000đ. Gold: phí 333.000đ, hạn mức 45-180 triệu. Classic: 111.000đ, 12-48 triệu.
""",
    }

    loan = await build_policy("loan", sources["loan"], None)
    savings = await build_policy("savings", sources["savings"], None)
    mortgage = await build_policy("mortgage", sources["mortgage"], None)
    card = await build_policy("card", sources["card"], None)

    assert [(claim.value, claim.qualifier) for claim in loan.claims
            if claim.key == "apr"] == [("7.25", "minimum")]
    assert loan.unique("max_amount") == 280_000_000
    assert loan.unique("min_term") == 9
    assert loan.unique("max_term") == 42
    assert loan.unique("min_age") == 23
    assert loan.unique("max_age") == 61
    assert loan.unique("min_income") == 8_000_000
    assert savings.unique("apr", term_months=6) == Decimal("4.10")
    assert savings.unique("online_bonus") == Decimal("0.15")
    assert savings.unique("min_amount") == 2_000_000
    assert mortgage.unique("ltv") == 65
    assert mortgage.unique("min_age") == 25
    assert mortgage.unique("max_age") == 58
    assert mortgage.unique("min_income") == 18_000_000
    assert card.unique("tier_min", tier="Aurora") == 250_000_000
    assert card.unique("tier_max", tier="Aurora") == 900_000_000
    assert card.unique("annual_fee", tier="Aurora") == 555_000
    assert card.unique("annual_fee", tier="Classic") is None
    assert all(policy.errors == () for policy in (loan, savings, mortgage, card))


@async_test
async def test_savings_minimum_money_rejects_competing_income_semantics():
    source = """# Savings
Thu nhập tối thiểu 18 triệu/tháng; giá trị nhà tối thiểu 2 tỷ đồng.
"""

    policy = await build_policy("savings", source, None)

    assert policy.unique("min_amount") is None
    assert not policy.claims


@async_test
async def test_promotional_duration_rate_is_not_a_global_apr():
    promotional = await build_policy(
        "savings",
        "# Savings\nƯu đãi 6 tháng: lãi suất 4,10%/năm.\n",
        None,
    )
    ordinary = await build_policy(
        "savings",
        "# Savings\nLãi suất 4,10%/năm.\n",
        None,
    )
    floor = await build_policy(
        "savings",
        "# Savings\nLãi suất từ 4,10%/năm.\n",
        None,
    )

    assert not [claim for claim in promotional.claims if claim.key == "apr"]
    assert ordinary.unique("apr") == Decimal("4.10")
    assert [(claim.value, claim.qualifier) for claim in floor.claims
            if claim.key == "apr"] == [("4.10", "minimum")]
    assert floor.unique("apr") is None


@async_test
async def test_self_labelled_card_limit_has_tier_ownership_only():
    policy = await build_policy(
        "card",
        "# Credit Card\nAurora có giới hạn 250-900 triệu.\n",
        None,
    )

    assert policy.unique("tier_min", tier="Aurora") == 250_000_000
    assert policy.unique("tier_max", tier="Aurora") == 900_000_000
    assert not [claim for claim in policy.claims if claim.key == "max_amount"]


@async_test
async def test_llm_cannot_relabel_self_labelled_tier_limit_as_global():
    quote = "Aurora có giới hạn 250-900 triệu"
    source = f"# Credit Card\n{quote}.\n"
    llm = FakeLLM({"claims": [{"key": "max_amount", "quote": quote}]})

    fallback = await build_policy("card", source, llm)
    assert len(llm.calls) == 1
    assert fallback.unique("tier_min", tier="Aurora") == 250_000_000
    assert fallback.unique("tier_max", tier="Aurora") == 900_000_000
    assert not [claim for claim in fallback.claims if claim.key == "max_amount"]
    assert fallback.errors == ("rejected_llm_claim:0:max_amount",)

    _clear_policy_cache()
    host = await build_policy("card", source, None)
    signature = lambda policy: {
        (claim.key, claim.value, claim.unit, claim.term_months,
         claim.tier, claim.qualifier)
        for claim in policy.claims
    }
    assert signature(fallback) == signature(host)


@async_test
async def test_product_wide_maxima_remain_unowned():
    card = await build_policy(
        "card", "# Credit Card\nHạn mức tối đa 900 triệu đồng.\n", None,
    )
    loan = await build_policy(
        "loan", "# Personal Loan\nHạn mức tối đa 280 triệu đồng.\n", None,
    )
    mortgage = await build_policy(
        "mortgage", "# Home Loan\nHạn mức tối đa 4 tỷ đồng.\n", None,
    )

    assert card.unique("max_amount") == 900_000_000
    assert loan.unique("max_amount") == 280_000_000
    assert mortgage.unique("max_amount") == 4_000_000_000
