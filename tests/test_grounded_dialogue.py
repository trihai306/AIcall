import asyncio
import json

import pytest

from backend.pipeline.grounded_contracts import (
    AcceptedFact,
    DialogueState,
    PolicySnapshot,
    SourceSnippet,
    TurnUnderstanding,
)
from backend.pipeline.grounded_dialogue import (
    GroundedDialogueError,
    apply_understanding,
    understand_turn,
)


class FakeLLM:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = []

    async def generate_structured(self, messages, schema, *, num_predict, timeout):
        self.calls.append(
            {
                "messages": messages,
                "schema": schema,
                "num_predict": num_predict,
                "timeout": timeout,
            }
        )
        if self.error:
            raise self.error
        return self.output


@pytest.fixture
def policy():
    return PolicySnapshot(
        product="loan",
        version="policy-v1",
        snippets=(SourceSnippet(id="loan-rates", text="Nguồn lãi suất sản phẩm."),),
        claims=(),
    )


def result(**overrides):
    base = {
        "intent": "question",
        "product": "loan",
        "topic": "conditions",
        "certainty": "clear",
        "facts": [],
        "source_refs": [],
        "intent_quote": "tư vấn giúp tôi",
    }
    base.update(overrides)
    return base


def run(coro):
    return asyncio.run(coro)


def context_payload(call):
    system = call["messages"][0]["content"]
    encoded = system.split("BEGIN_READ_ONLY_CONTEXT_DATA\n", 1)[1]
    encoded = encoded.split("\nEND_READ_ONLY_CONTEXT_DATA", 1)[0]
    return json.loads(encoded)


def test_structured_contract_uses_stable_indexes_without_duplicating_current(policy):
    history = [
        {"role": "user", "content": "Tôi quan tâm khoản vay."},
        {"role": "assistant", "content": "Anh cần tư vấn gì?"},
        {"role": "user", "content": "tư vấn giúp tôi"},
    ]
    llm = FakeLLM(result())

    understood = run(understand_turn(llm, history[-1]["content"], history, DialogueState(), policy))

    assert understood.intent == "question"
    call = llm.calls[0]
    assert call["schema"]["properties"]["source_refs"]["items"]["enum"] == [
        "loan-rates"
    ]
    assert call["schema"]["properties"]["source_refs"]["maxItems"] == 1
    assert "intent_quote" not in call["schema"]["properties"]
    assert "current_turn" not in call["schema"]["properties"]
    assert {"facts", "source_refs"} <= set(call["schema"]["required"])
    assert "default" not in call["schema"]["properties"]["facts"]
    assert "default" not in call["schema"]["properties"]["source_refs"]
    assert "tính tiền lãi" in call["schema"]["properties"]["intent"]["description"]
    assert "phí thường niên" in call["schema"]["properties"]["topic"]["description"]
    fact_arms = call["schema"]["$defs"]["FactUpdate"]["oneOf"]
    numeric_arm = next(arm for arm in fact_arms if arm["title"] == "NumericFactEvidence")
    channel_arm = next(arm for arm in fact_arms if arm["title"] == "ChannelFactEvidence")
    assert "value" not in numeric_arm["properties"]
    assert "value" not in numeric_arm["required"]
    field_description = numeric_arm["properties"]["field"]["description"]
    assert "term_months=kỳ hạn" in field_description
    assert "elapsed_months=thời gian thực tế đã" in field_description
    assert channel_arm["properties"]["value"]["enum"] == ["online", "counter", ""]
    assert call["num_predict"] > 0 and call["timeout"] > 0
    assert [message["role"] for message in call["messages"]] == ["system", "user"]
    assert call["messages"][-1]["content"] == history[-1]["content"]
    payload = context_payload(call)
    assert payload["current_user_turn"] == 1
    assert [turn["turn"] for turn in payload["past_history"]] == [0, None]
    assert all(
        turn["content"] != history[-1]["content"]
        for turn in payload["past_history"]
    )
    assert payload["policy_context"]["sources"] == [
        {"id": "loan-rates", "text": "Nguồn lãi suất sản phẩm."}
    ]
    assert understood.intent_quote == history[-1]["content"]
    assert understood.current_turn == 1


def test_prompt_matches_quote_only_wire_contract(policy):
    text = "Tôi muốn hỏi thông tin sản phẩm."
    llm = FakeLLM(result())

    run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    prompt = llm.calls[0]["messages"][0]["content"].split(
        "BEGIN_READ_ONLY_CONTEXT_DATA", 1
    )[0]
    assert "Do not generate a numeric value" in prompt
    assert "Normalize a numeric fact to a plain decimal value" not in prompt
    assert "term_months is kỳ hạn đăng ký" in prompt
    assert "elapsed_months is thời" in prompt
    assert "Always return both facts and source_refs arrays" in prompt
    assert "requested product variant" in prompt
    assert "Never map every fee question to annual_fee" in prompt


@pytest.mark.parametrize("missing_key", ["facts", "source_refs"])
def test_required_wire_arrays_cannot_be_omitted(policy, missing_key):
    text = "Tôi muốn hỏi thông tin sản phẩm."
    output = result()
    output.pop(missing_key)

    with pytest.raises(GroundedDialogueError, match="must include facts and source_refs"):
        run(
            understand_turn(
                FakeLLM(output),
                text,
                [{"role": "user", "content": text}],
                DialogueState(),
                policy,
            )
        )


def test_model_cannot_forge_host_owned_current_user_turn(policy):
    history = [
        {"role": "user", "content": "Tôi đang xem khoản vay."},
        {"role": "assistant", "content": "Anh muốn hỏi gì?"},
        {"role": "user", "content": "tư vấn giúp tôi"},
    ]
    llm = FakeLLM(result(current_turn=999, intent_quote="forged evidence"))

    understood = run(
        understand_turn(
            llm,
            history[-1]["content"],
            history,
            DialogueState(),
            policy,
        )
    )

    assert understood.current_turn == 1
    assert understood.intent_quote == history[-1]["content"]


@pytest.mark.parametrize(
    ("intent", "model_topic", "expected_topic"),
    [
        ("calculate_ltv", "lock_fee", "limit"),
        ("calculate_payment", "documents", "rate"),
        ("calculate_interest", "annual_fee", "rate"),
        ("calculate_interest", "early_withdrawal", "early_withdrawal"),
    ],
)
def test_typed_calculation_has_a_compatible_topic(
    policy,
    intent,
    model_topic,
    expected_topic,
):
    text = "Tôi muốn thực hiện phép tính này."
    llm = FakeLLM(result(intent=intent, topic=model_topic))

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    assert understood.intent == intent
    assert understood.topic == expected_topic


def test_empty_policy_forces_empty_source_refs_schema():
    policy = PolicySnapshot(product="loan", version="empty", snippets=(), claims=())
    text = "tư vấn giúp tôi"
    llm = FakeLLM(result())

    run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    assert llm.calls[0]["schema"]["properties"]["source_refs"]["maxItems"] == 0


def test_compact_history_keeps_original_turn_indexes(policy):
    history = [{"role": "user", "content": f"câu {index}"} for index in range(15)]
    llm = FakeLLM(result(intent_quote="câu 14"))

    run(understand_turn(llm, "câu 14", history, DialogueState(), policy))

    payload = context_payload(llm.calls[0])
    assert len(payload["past_history"]) == 12
    assert payload["past_history"][0]["turn"] == 2
    assert payload["past_history"][-1]["turn"] == 13


def test_paraphrased_correction_is_grounded_and_applied(policy):
    text = "À không, khoản vay là năm trăm triệu, trả trong hai năm."
    history = [{"role": "user", "content": text}]
    llm = FakeLLM(
        result(
            intent="calculate_payment",
            topic="term",
            intent_quote="trả trong hai năm",
            facts=[
                {
                    "field": "amount",
                    "value": "500000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "correct",
                    "turn": 0,
                    "quote": "năm trăm triệu",
                },
                {
                    "field": "term_months",
                    "value": "24",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "hai năm",
                },
            ],
        )
    )

    understood = run(understand_turn(llm, text, history, DialogueState(), policy))
    state = apply_understanding(DialogueState(), understood, history, text)

    assert state.get("amount", product="loan").value == "500000000"
    assert state.get("term_months", product="loan").value == "24"


def test_every_fact_must_quote_exact_user_turn_not_assistant(policy):
    history = [
        {"role": "assistant", "content": "thu nhập bốn triệu"},
        {"role": "user", "content": "tư vấn giúp tôi"},
    ]
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "income_monthly",
                    "value": "4000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "thu nhập bốn triệu",
                }
            ]
        )
    )

    with pytest.raises(GroundedDialogueError, match="exact substring"):
        run(understand_turn(llm, "tư vấn giúp tôi", history, DialogueState(), policy))


def test_numeric_value_cannot_invent_multiplier(policy):
    text = "Tôi cần vay 500 thôi, tư vấn giúp tôi."
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "amount",
                    "value": "500000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "500",
                }
            ]
        )
    )

    with pytest.raises(GroundedDialogueError, match="not supported"):
        run(understand_turn(llm, text, [{"role": "user", "content": text}], DialogueState(), policy))


def test_term_months_requires_an_explicit_time_unit(policy):
    text = "Kỳ hạn 24, tư vấn giúp tôi."
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "term_months",
                    "value": "24",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "24",
                }
            ]
        )
    )

    with pytest.raises(GroundedDialogueError, match="not supported"):
        run(understand_turn(llm, text, [{"role": "user", "content": text}], DialogueState(), policy))


def test_half_scale_is_validated_without_guessing(policy):
    text = "Tôi dự tính vay nửa tỷ, tư vấn giúp tôi."
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "amount",
                    "value": "500000000",
                    "owner": "self",
                    "modality": "hypothetical",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "nửa tỷ",
                }
            ]
        )
    )

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )
    assert understood.facts[0].value == "500000000"


def test_intent_evidence_is_owned_by_host_not_model(policy):
    history = [
        {"role": "user", "content": "dừng tư vấn"},
        {"role": "user", "content": "tư vấn giúp tôi"},
    ]
    llm = FakeLLM(result(intent="stop", intent_quote="dừng tư vấn"))

    understood = run(
        understand_turn(llm, history[-1]["content"], history, DialogueState(), policy)
    )

    assert understood.intent_quote == "tư vấn giúp tôi"


def test_numeric_value_and_normalized_quote_are_canonicalized(policy):
    text = "TÔI   VAY 120 triệu trong hai năm."
    llm = FakeLLM(
        result(
            intent="calculate_payment",
            facts=[
                {
                    "field": "amount",
                    "value": "120.000.000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "tôi vay 120 triệu",
                    "product": "loan",
                }
            ],
        )
    )

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    assert understood.facts[0].value == "120000000"
    assert understood.facts[0].quote == "TÔI   VAY 120 triệu"


def test_model_numeric_value_is_ignored_in_favor_of_quoted_quantity(policy):
    text = "Tôi vay 120 triệu."
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "amount",
                    "value": "130 triệu",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "120 triệu",
                    "product": "loan",
                }
            ]
        )
    )

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    assert understood.facts[0].value == "120000000"


@pytest.mark.parametrize("model_value", ["", "0", "E3200000000"])
def test_malformed_or_empty_model_numeric_value_is_host_derived(policy, model_value):
    text = "Giá trị tài sản là 3,2 tỷ."
    llm = FakeLLM(
        result(
            product="mortgage",
            facts=[
                {
                    "field": "property_value",
                    "value": model_value,
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "3,2 tỷ",
                    "product": "mortgage",
                }
            ],
        )
    )

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    assert understood.facts[0].value == "3200000000"


def test_numeric_wire_fact_can_omit_value(policy):
    text = "Tôi gửi 120 triệu trong sáu tháng."
    llm = FakeLLM(
        result(
            product="savings",
            facts=[
                {
                    "field": "amount",
                    "owner": "self",
                    "modality": "hypothetical",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "120 triệu",
                    "product": "savings",
                },
                {
                    "field": "term_months",
                    "owner": "self",
                    "modality": "hypothetical",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "sáu tháng",
                    "product": "savings",
                },
            ],
        )
    )

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    assert [fact.value for fact in understood.facts] == ["120000000", "6"]


def test_ambiguous_money_quote_cannot_select_one_quantity(policy):
    text = "Giá trị tài sản ba tỷ và khoản vay hai tỷ."
    llm = FakeLLM(
        result(
            product="mortgage",
            facts=[
                {
                    "field": "property_value",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": text,
                    "product": "mortgage",
                }
            ],
        )
    )

    with pytest.raises(GroundedDialogueError, match="exactly one"):
        run(
            understand_turn(
                llm,
                text,
                [{"role": "user", "content": text}],
                DialogueState(),
                policy,
            )
        )


def test_numeric_quote_without_a_quantity_is_rejected(policy):
    policy = PolicySnapshot(
        product="loan",
        version="numeric-policy",
        snippets=(
            SourceSnippet(
                id="published-limit",
                text="Hạn mức sản phẩm tối đa là 500 triệu đồng.",
            ),
        ),
        claims=(),
    )
    text = "Tôi muốn hỏi về khoản vay của tôi."
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "amount",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "khoản vay của tôi",
                    "product": "loan",
                }
            ]
        )
    )

    with pytest.raises(GroundedDialogueError, match="exactly one"):
        run(
            understand_turn(
                llm,
                text,
                [{"role": "user", "content": text}],
                DialogueState(),
                policy,
            )
        )


def test_channel_value_is_derived_from_quote(policy):
    text = "Tôi sẽ đăng ký online."
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "channel",
                    "value": "counter",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "đăng ký online",
                    "product": "loan",
                }
            ]
        )
    )

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    assert understood.facts[0].value == "online"


def test_money_fact_rejects_bare_number_from_unrelated_measurement(policy):
    text = "Chỉ số y tế là 6, tư vấn giúp tôi."
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "income_monthly",
                    "value": "6",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "6",
                    "product": "unknown",
                }
            ]
        )
    )

    with pytest.raises(GroundedDialogueError, match="not supported"):
        run(
            understand_turn(
                llm,
                text,
                [{"role": "user", "content": text}],
                DialogueState(),
                policy,
            )
        )


def test_normalized_quote_recovery_rejects_multiple_matches(policy):
    text = "Vay 120 triệu rồi nhắc lại: VAY   120 triệu."
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "amount",
                    "value": "120 triệu",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "vay 120 triệu",
                    "product": "loan",
                }
            ]
        )
    )

    with pytest.raises(GroundedDialogueError, match="ambiguous matches"):
        run(
            understand_turn(
                llm,
                text,
                [{"role": "user", "content": text}],
                DialogueState(),
                policy,
            )
        )


def test_annual_income_is_normalized_only_from_explicit_period(policy):
    text = "Thu nhập của tôi là 120 triệu mỗi năm."
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "income_monthly",
                    "value": "10 triệu",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "120 triệu mỗi năm",
                    "product": "unknown",
                }
            ]
        )
    )

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    assert understood.facts[0].value == "10000000"


def test_income_without_annual_period_keeps_quoted_quantity(policy):
    text = "Thu nhập của tôi là 120 triệu."
    llm = FakeLLM(
        result(
            facts=[
                {
                    "field": "income_monthly",
                    "value": "10 triệu",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "120 triệu",
                    "product": "unknown",
                }
            ]
        )
    )

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    assert understood.facts[0].value == "120000000"


def test_cross_clause_parent_income_and_hypothetical_self_amount(policy):
    text = "Bố tôi lương hai mươi triệu; nếu tôi vay ba trăm triệu thì sao?"
    llm = FakeLLM(
        result(
            product="loan",
            intent_quote="thì sao",
            facts=[
                {
                    "field": "income_monthly",
                    "value": "20000000",
                    "owner": "other",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "Bố tôi lương hai mươi triệu",
                },
                {
                    "field": "amount",
                    "value": "300000000",
                    "owner": "self",
                    "modality": "hypothetical",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "tôi vay ba trăm triệu",
                },
            ],
        )
    )

    understood = run(understand_turn(llm, text, [{"role": "user", "content": text}], DialogueState(), policy))
    state = apply_understanding(DialogueState(), understood, [{"role": "user", "content": text}], text)

    assert state.facts == {}
    assert len(understood.facts) == 2  # executor may still use current hypothetical inputs


def test_negated_future_income_does_not_replace_actual_income():
    state = DialogueState(
        product="loan",
        facts={
            ("*", "income_monthly", "self"): AcceptedFact(
                field="income_monthly",
                value="4000000",
                owner="self",
                product="loan",
                turn=0,
                quote="thu nhập bốn triệu",
            )
        },
    )
    text = "Sang năm có thể lên sáu triệu, giờ vẫn bốn triệu."
    history = [
        {"role": "user", "content": "thu nhập bốn triệu"},
        {"role": "user", "content": text},
    ]
    understanding = TurnUnderstanding.model_validate(
        result(
            intent_quote="giờ vẫn bốn triệu",
            facts=[
                {
                    "field": "income_monthly",
                    "value": "6000000",
                    "owner": "self",
                    "modality": "hypothetical",
                    "operation": "assert",
                    "turn": 1,
                    "quote": "có thể lên sáu triệu",
                },
                {
                    "field": "income_monthly",
                    "value": "4000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 1,
                    "quote": "giờ vẫn bốn triệu",
                },
            ],
        )
    )

    apply_understanding(state, understanding, history, text)

    assert state.get("income_monthly").value == "4000000"
    assert state.get("income_monthly").turn == 1


def test_elapsed_duration_is_distinct_from_contracted_term():
    text = "Kỳ hạn hai năm và tôi đã trả được sáu tháng."
    history = [{"role": "user", "content": text}]
    understanding = TurnUnderstanding.model_validate(
        result(
            intent_quote="đã trả được sáu tháng",
            facts=[
                {
                    "field": "term_months",
                    "value": "24",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "Kỳ hạn hai năm",
                    "product": "loan",
                },
                {
                    "field": "elapsed_months",
                    "value": "6",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "đã trả được sáu tháng",
                    "product": "loan",
                },
            ],
        )
    )
    state = DialogueState(product="loan")

    apply_understanding(state, understanding, history, text)

    assert state.get("term_months", product="loan").value == "24"
    assert state.get("elapsed_months", product="loan").value == "6"


def test_conflicting_current_assertions_stay_ambiguous_on_next_turn(policy):
    text = "Tôi đang phân vân vay một trăm triệu hay hai trăm triệu."
    history = [{"role": "user", "content": text}]
    conflict = TurnUnderstanding.model_validate(
        result(
            intent_quote="phân vân",
            facts=[
                {
                    "field": "amount",
                    "value": "100000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "một trăm triệu",
                    "product": "loan",
                },
                {
                    "field": "amount",
                    "value": "200000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "hai trăm triệu",
                    "product": "loan",
                },
            ],
        )
    )
    state = DialogueState(product="loan")
    apply_understanding(state, conflict, history, text)

    key = ("loan", "amount", "self")
    assert state.get("amount", product="loan") is None
    assert state.ambiguous_at[key] == 0

    followup = "Tính đi."
    history.append({"role": "user", "content": followup})
    llm = FakeLLM(
        result(
            intent="calculate_payment",
            intent_quote="Tính đi",
            facts=[],
        )
    )
    understood = run(understand_turn(llm, followup, history, state, policy))
    payload = context_payload(llm.calls[0])
    assert payload["accepted_state"]["ambiguous_at"] == [
        {"scope": "loan", "field": "amount", "owner": "self", "turn": 0}
    ]

    apply_understanding(state, understood, history, followup)
    assert state.get("amount", product="loan") is None
    assert state.ambiguous_at[key] == 0


def test_ambiguous_understanding_invalidates_only_proposed_current_slots():
    old = "Tôi vay một trăm triệu, thu nhập bốn triệu."
    text = "Có thể khoản vay là hai trăm triệu."
    history = [
        {"role": "user", "content": old},
        {"role": "user", "content": text},
    ]
    amount_key = ("loan", "amount", "self")
    income_key = ("*", "income_monthly", "self")
    state = DialogueState(
        product="loan",
        facts={
            amount_key: AcceptedFact(
                field="amount",
                value="100000000",
                owner="self",
                product="loan",
                turn=0,
                quote="một trăm triệu",
            ),
            income_key: AcceptedFact(
                field="income_monthly",
                value="4000000",
                owner="self",
                product="loan",
                turn=0,
                quote="thu nhập bốn triệu",
            ),
        },
    )
    ambiguous = TurnUnderstanding.model_validate(
        result(
            product="mortgage",
            certainty="ambiguous",
            intent_quote="Có thể",
            facts=[
                {
                    "field": "amount",
                    "value": "200000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 1,
                    "quote": "hai trăm triệu",
                    "product": "loan",
                }
            ],
        )
    )

    apply_understanding(state, ambiguous, history, text)

    assert state.product == "loan"
    assert state.get("amount", product="loan") is None
    assert state.ambiguous_at[amount_key] == 1
    assert state.get("income_monthly").value == "4000000"
    assert income_key not in state.ambiguous_at


def test_explicit_correction_clears_ambiguity_and_restores_fact():
    first = "Tôi đang phân vân vay một trăm triệu hay hai trăm triệu."
    correction_text = "Chính xác là hai trăm triệu."
    history = [
        {"role": "user", "content": first},
        {"role": "user", "content": correction_text},
    ]
    key = ("loan", "amount", "self")
    state = DialogueState(product="loan", ambiguous_at={key: 0})
    correction = TurnUnderstanding.model_validate(
        result(
            intent_quote="Chính xác",
            facts=[
                {
                    "field": "amount",
                    "value": "200000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "correct",
                    "turn": 1,
                    "quote": "hai trăm triệu",
                    "product": "loan",
                }
            ],
        )
    )

    apply_understanding(state, correction, history, correction_text)

    assert state.get("amount", product="loan").value == "200000000"
    assert key not in state.ambiguous_at


def test_ordered_current_correction_resolves_prior_assertion_conflict():
    text = (
        "Không phải một trăm triệu hay hai trăm triệu; chính xác là "
        "một trăm năm mươi triệu."
    )
    history = [{"role": "user", "content": text}]
    understanding = TurnUnderstanding.model_validate(
        result(
            intent_quote="chính xác",
            facts=[
                {"field": "amount", "value": "100000000", "owner": "self", "modality": "actual", "operation": "assert", "turn": 0, "quote": "một trăm triệu", "product": "loan"},
                {"field": "amount", "value": "200000000", "owner": "self", "modality": "actual", "operation": "assert", "turn": 0, "quote": "hai trăm triệu", "product": "loan"},
                {"field": "amount", "value": "150000000", "owner": "self", "modality": "actual", "operation": "correct", "turn": 0, "quote": "một trăm năm mươi triệu", "product": "loan"},
            ],
        )
    )
    state = DialogueState(product="loan")

    apply_understanding(state, understanding, history, text)

    assert state.get("amount", product="loan").value == "150000000"
    assert state.ambiguous_at == {}


def test_older_history_cannot_revive_newer_ambiguity():
    first = "Tôi từng nói vay một trăm triệu."
    second = "Con số hiện tại chưa rõ."
    current = "Cứ tư vấn tiếp."
    history = [
        {"role": "user", "content": first},
        {"role": "user", "content": second},
        {"role": "user", "content": current},
    ]
    key = ("loan", "amount", "self")
    state = DialogueState(product="loan", ambiguous_at={key: 1})
    replay = TurnUnderstanding.model_validate(
        result(
            intent_quote="tư vấn tiếp",
            facts=[
                {"field": "amount", "value": "100000000", "owner": "self", "modality": "actual", "operation": "assert", "turn": 0, "quote": "một trăm triệu", "product": "loan"}
            ],
        )
    )

    apply_understanding(state, replay, history, current)

    assert state.get("amount", product="loan") is None
    assert state.ambiguous_at[key] == 1


def test_product_specific_amounts_and_channels_do_not_bleed():
    state = DialogueState(product="loan")
    loan_text = "Khoản vay một trăm triệu, đăng ký online."
    loan = TurnUnderstanding.model_validate(
        result(
            intent_quote="Khoản vay",
            facts=[
                {"field": "amount", "value": "100000000", "owner": "self", "modality": "actual", "operation": "assert", "turn": 0, "quote": "một trăm triệu"},
                {"field": "channel", "value": "online", "owner": "self", "modality": "actual", "operation": "assert", "turn": 0, "quote": "đăng ký online"},
            ],
        )
    )
    apply_understanding(state, loan, [{"role": "user", "content": loan_text}], loan_text)

    mortgage_text = "Nhà này tôi vay hai tỷ tại quầy."
    mortgage = TurnUnderstanding.model_validate(
        result(
            product="mortgage",
            intent_quote="Nhà này",
            facts=[
                {"field": "amount", "value": "2000000000", "owner": "self", "modality": "actual", "operation": "assert", "turn": 1, "quote": "hai tỷ"},
                {"field": "channel", "value": "counter", "owner": "self", "modality": "actual", "operation": "assert", "turn": 1, "quote": "tại quầy"},
            ],
        )
    )
    history = [
        {"role": "user", "content": loan_text},
        {"role": "user", "content": mortgage_text},
    ]
    apply_understanding(state, mortgage, history, mortgage_text)

    assert state.product == "mortgage"
    assert state.get("amount", product="loan").value == "100000000"
    assert state.get("channel", product="loan").value == "online"
    assert state.get("amount", product="mortgage").value == "2000000000"
    assert state.get("channel", product="mortgage").value == "counter"


def test_current_mixed_product_claims_keep_independent_amount_scopes():
    text = (
        "Tôi gửi tiết kiệm một trăm năm mươi triệu, còn khoản vay là "
        "hai trăm triệu."
    )
    history = [{"role": "user", "content": text}]
    understanding = TurnUnderstanding.model_validate(
        result(
            product="savings",
            intent_quote="Tôi gửi tiết kiệm",
            facts=[
                {
                    "field": "amount",
                    "value": "150000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "tiết kiệm một trăm năm mươi triệu",
                    "product": "savings",
                },
                {
                    "field": "amount",
                    "value": "200000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "khoản vay là hai trăm triệu",
                    "product": "loan",
                },
            ],
        )
    )
    state = DialogueState(product="loan")

    apply_understanding(state, understanding, history, text)

    assert state.product == "savings"
    assert state.get("amount", product="savings").value == "150000000"
    assert state.get("amount", product="loan").value == "200000000"


def test_historical_productless_amount_cannot_migrate_on_product_switch():
    old_text = "Tôi cần vay một trăm triệu."
    text = "Giờ tôi muốn hỏi về tiết kiệm."
    history = [
        {"role": "user", "content": old_text},
        {"role": "user", "content": text},
    ]
    understanding = TurnUnderstanding.model_validate(
        result(
            product="savings",
            intent_quote="hỏi về tiết kiệm",
            facts=[
                {
                    "field": "amount",
                    "value": "100000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "một trăm triệu",
                    "product": "unknown",
                }
            ],
        )
    )
    state = DialogueState(product="loan")

    with pytest.raises(GroundedDialogueError, match="missing its product scope"):
        apply_understanding(state, understanding, history, text)

    assert state.get("amount", product="savings") is None
    assert state.product == "loan"


def test_understander_rejects_historical_productless_amount(policy):
    old_text = "Tôi cần vay một trăm triệu."
    text = "Giờ tôi muốn hỏi về tiết kiệm."
    history = [
        {"role": "user", "content": old_text},
        {"role": "user", "content": text},
    ]
    llm = FakeLLM(
        result(
            product="savings",
            intent_quote="hỏi về tiết kiệm",
            facts=[
                {
                    "field": "amount",
                    "value": "100000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "một trăm triệu",
                    "product": "unknown",
                }
            ],
        )
    )

    with pytest.raises(GroundedDialogueError, match="missing its product scope"):
        run(understand_turn(llm, text, history, DialogueState(product="loan"), policy))


def test_retracted_newer_fact_cannot_be_revived_by_old_claim():
    text0 = "Tôi vay một trăm triệu."
    text1 = "Bỏ số một trăm triệu trước đi."
    history = [{"role": "user", "content": text0}, {"role": "user", "content": text1}]
    state = DialogueState(
        product="loan",
        facts={
            ("loan", "amount", "self"): AcceptedFact(
                field="amount", value="100000000", owner="self", product="loan", turn=0, quote="một trăm triệu"
            )
        },
    )
    retract = TurnUnderstanding.model_validate(
        result(
            intent_quote="Bỏ số",
            facts=[
                {"field": "amount", "value": "100000000", "owner": "self", "modality": "actual", "operation": "retract", "turn": 1, "quote": "một trăm triệu"}
            ],
        )
    )
    apply_understanding(state, retract, history, text1)
    old = TurnUnderstanding.model_validate(
        result(
            intent_quote="Bỏ số",
            facts=[
                {"field": "amount", "value": "100000000", "owner": "self", "modality": "actual", "operation": "assert", "turn": 0, "quote": "một trăm triệu", "product": "loan"}
            ],
        )
    )
    apply_understanding(state, old, history, text1)

    assert state.get("amount", product="loan") is None
    assert state.retracted_at[("loan", "amount", "self")] == 1


def test_history_interruption_purges_orphaned_facts_and_retractions():
    state = DialogueState(
        product="loan",
        facts={
            ("loan", "amount", "self"): AcceptedFact(
                field="amount",
                value="100000000",
                owner="self",
                product="loan",
                turn=0,
                quote="một trăm triệu",
            )
        },
        retracted_at={("loan", "term_months", "self"): 3},
        ambiguous_at={("loan", "amount", "self"): 4},
    )
    text = "Tôi muốn hỏi lại từ đầu."
    history = [{"role": "user", "content": text}]
    understanding = TurnUnderstanding.model_validate(
        result(intent_quote="hỏi lại từ đầu")
    )

    apply_understanding(state, understanding, history, text)

    assert state.facts == {}
    assert state.retracted_at == {}
    assert state.ambiguous_at == {}


def test_replacement_latest_user_turn_can_replace_its_old_tombstone():
    state = DialogueState(
        product="loan",
        retracted_at={("loan", "amount", "self"): 0},
    )
    text = "Thay vào đó tôi vay hai trăm triệu."
    history = [{"role": "user", "content": text}]
    understanding = TurnUnderstanding.model_validate(
        result(
            intent_quote="Thay vào đó",
            facts=[
                {
                    "field": "amount",
                    "value": "200000000",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "hai trăm triệu",
                }
            ],
        )
    )

    apply_understanding(state, understanding, history, text)

    assert state.get("amount", product="loan").value == "200000000"
    assert state.retracted_at == {}


def test_retraction_without_repeated_categorical_value_is_valid():
    text = "Bỏ kênh đăng ký trước đó đi."
    history = [{"role": "user", "content": text}]
    state = DialogueState(
        product="loan",
        facts={
            ("loan", "channel", "self"): AcceptedFact(
                field="channel",
                value="online",
                owner="self",
                product="loan",
                turn=0,
                quote="đăng ký online",
            )
        },
    )
    understanding = TurnUnderstanding.model_validate(
        result(
            intent_quote="Bỏ kênh",
            facts=[
                {
                    "field": "channel",
                    "value": "",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "retract",
                    "turn": 0,
                    "quote": "Bỏ kênh đăng ký trước đó đi",
                }
            ],
        )
    )

    apply_understanding(state, understanding, history, text)

    assert state.get("channel", product="loan") is None
    assert state.retracted_at[("loan", "channel", "self")] == 0


def test_stale_state_evidence_is_omitted_from_model_context(policy):
    state = DialogueState(
        product="loan",
        facts={
            ("loan", "amount", "self"): AcceptedFact(
                field="amount",
                value="100000000",
                owner="self",
                product="loan",
                turn=0,
                quote="một trăm triệu",
            )
        },
    )
    text = "Tôi muốn hỏi lại từ đầu."
    llm = FakeLLM(result(intent_quote="hỏi lại từ đầu"))

    run(understand_turn(llm, text, [{"role": "user", "content": text}], state, policy))

    payload = context_payload(llm.calls[0])
    assert payload["accepted_state"]["facts"] == []


def test_card_tier_channel_currency_and_sources_require_literal_evidence(policy):
    text = "Tôi chọn hạng Platinum và làm online bằng USD."
    good = result(
        product="card",
        intent_quote="Tôi chọn",
        source_refs=["loan-rates"],
        facts=[
            {"field": "card_tier", "value": "Platinum", "owner": "self", "modality": "actual", "operation": "assert", "turn": 0, "quote": "hạng Platinum"},
            {"field": "channel", "value": "online", "owner": "self", "modality": "actual", "operation": "assert", "turn": 0, "quote": "làm online"},
            {"field": "currency", "value": "USD", "owner": "self", "modality": "actual", "operation": "assert", "turn": 0, "quote": "bằng USD"},
        ],
    )
    run(understand_turn(FakeLLM(good), text, [{"role": "user", "content": text}], DialogueState(), policy))

    bad = dict(good)
    bad["facts"] = [dict(good["facts"][0], value="Diamond")]
    with pytest.raises(GroundedDialogueError, match="tier"):
        run(understand_turn(FakeLLM(bad), text, [{"role": "user", "content": text}], DialogueState(), policy))

    bad_source = dict(good, source_refs=["invented-source"])
    with pytest.raises(GroundedDialogueError, match="unknown policy source"):
        run(understand_turn(FakeLLM(bad_source), text, [{"role": "user", "content": text}], DialogueState(), policy))


def test_public_question_card_tier_is_ephemeral_across_next_turn():
    policy = PolicySnapshot(
        product="card",
        version="card-policy",
        snippets=(SourceSnippet(id="card-fees", text="Biểu phí thẻ công khai."),),
        claims=(),
    )
    text = "Phí thường niên thẻ Gold là bao nhiêu?"
    history = [{"role": "user", "content": text}]
    llm = FakeLLM(
        result(
            intent="question",
            product="card",
            topic="annual_fee",
            source_refs=["card-fees"],
            facts=[
                {
                    "field": "card_tier",
                    "value": "Gold",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "thẻ Gold",
                    "product": "card",
                }
            ],
        )
    )

    understood = run(
        understand_turn(llm, text, history, DialogueState(), policy)
    )
    assert understood.facts[0].value == "Gold"
    assert understood.facts[0].modality == "hypothetical"

    state = apply_understanding(DialogueState(), understood, history, text)
    assert state.get("card_tier", product="card") is None

    followup = "Nhắc lại thông tin vừa tra cứu."
    history.append({"role": "user", "content": followup})
    readback_llm = FakeLLM(
        result(
            intent="readback",
            product="card",
            topic="annual_fee",
            facts=[],
            source_refs=[],
        )
    )
    readback = run(
        understand_turn(readback_llm, followup, history, state, policy)
    )
    payload = context_payload(readback_llm.calls[0])
    assert payload["accepted_state"]["facts"] == []
    apply_understanding(state, readback, history, followup)
    assert state.get("card_tier", product="card") is None


def test_direct_apply_cannot_persist_historical_tier_from_public_question():
    prior = "Tôi đang xem hạng Gold."
    text = "Cho tôi hỏi biểu phí thẻ."
    history = [
        {"role": "user", "content": prior},
        {"role": "user", "content": text},
    ]
    understanding = TurnUnderstanding.model_validate(
        result(
            intent="question",
            product="card",
            topic="fee",
            intent_quote="hỏi biểu phí thẻ",
            facts=[
                {
                    "field": "card_tier",
                    "value": "Gold",
                    "owner": "self",
                    "modality": "actual",
                    "operation": "assert",
                    "turn": 0,
                    "quote": "hạng Gold",
                    "product": "card",
                }
            ],
        )
    )
    state = DialogueState(product="card")

    apply_understanding(state, understanding, history, text)

    assert state.get("card_tier", product="card") is None


def test_generic_policy_question_can_select_a_visible_source(policy):
    text = "Lãi suất của khoản vay thế nào?"
    llm = FakeLLM(
        result(
            topic="rate",
            intent_quote="Lãi suất",
            source_refs=["loan-rates"],
        )
    )

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    payload = context_payload(llm.calls[0])
    assert understood.source_refs == ["loan-rates"]
    assert payload["policy_context"]["sources"][0]["text"] == policy.snippets[0].text


def test_policy_compiler_errors_are_not_model_context():
    diagnostic = "internal compiler could not parse a policy row"
    policy = PolicySnapshot(
        product="loan",
        version="policy-with-diagnostic",
        snippets=(SourceSnippet(id="public-source", text="Thông tin sản phẩm."),),
        claims=(),
        errors=(diagnostic,),
    )
    text = "Tôi muốn hỏi thông tin sản phẩm."
    llm = FakeLLM(result(source_refs=["public-source"]))

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(),
            policy,
        )
    )

    payload = context_payload(llm.calls[0])
    assert "errors" not in payload["policy_context"]
    assert diagnostic not in llm.calls[0]["messages"][0]["content"]
    assert understood.intent_quote == text
    assert understood.current_turn == 0


def test_public_card_fee_question_has_policy_contract_without_record_facts():
    policy = PolicySnapshot(
        product="card",
        version="card-policy",
        snippets=(
            SourceSnippet(
                id="card-fees",
                text="Quy định công khai về phí thường niên theo hạng thẻ.",
            ),
        ),
        claims=(),
    )
    text = "Tra giúp tôi chính sách phí thường niên của thẻ đang dùng."
    llm = FakeLLM(
        result(
            intent="question",
            product="card",
            topic="annual_fee",
            intent_quote="phí thường niên",
            facts=[],
            source_refs=["card-fees"],
        )
    )

    understood = run(
        understand_turn(
            llm,
            text,
            [{"role": "user", "content": text}],
            DialogueState(product="card"),
            policy,
        )
    )

    assert understood.intent == "question"
    assert understood.topic == "annual_fee"
    assert understood.facts == []
    assert understood.source_refs == ["card-fees"]


def test_schema_or_generation_failure_has_no_fallback(policy):
    text = "tư vấn giúp tôi"
    history = [{"role": "user", "content": text}]
    with pytest.raises(GroundedDialogueError, match="schema"):
        run(understand_turn(FakeLLM({"intent": "question"}), text, history, DialogueState(), policy))
    with pytest.raises(GroundedDialogueError, match="failed"):
        run(understand_turn(FakeLLM(error=RuntimeError("offline")), text, history, DialogueState(), policy))


def test_unrelated_identifier_is_not_coerced_into_financial_fact(policy):
    text = "Đội bóng 500 thắng rồi, còn khoản vay thì tư vấn giúp tôi."
    llm = FakeLLM(result())

    understood = run(understand_turn(llm, text, [{"role": "user", "content": text}], DialogueState(), policy))

    assert understood.facts == []
