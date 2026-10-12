"""Shared contracts: language understanding is separate from facts and arithmetic.

The model proposes evidence-backed meanings, never a customer-facing answer or
a financial decision. Values from customer speech and product policy have
different types and provenance.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Product = Literal["loan", "mortgage", "savings", "card", "unknown"]
Owner = Literal["self", "household", "other", "source"]
FactField = Literal["amount", "term_months", "elapsed_months", "income_monthly", "age",
                    "property_value", "channel", "card_tier", "withdrawal_amount", "currency"]
Intent = Literal["stop", "defer", "greeting", "identity", "privacy",
                 "security", "off_topic", "fabrication", "approval",
                 "acknowledge", "readback", "question", "calculate_interest",
                 "calculate_payment", "calculate_ltv", "eligibility",
                 "customer_record", "unknown"]
Topic = Literal["rate", "fee", "annual_fee", "replacement_fee", "lock_fee",
                "limit", "term", "documents", "conditions", "promotion",
                "early_withdrawal", "compound", "minimum_payment", "scope",
                "channel", "other"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactUpdate(StrictModel):
    field: FactField
    value: str
    owner: Owner
    modality: Literal["actual", "hypothetical", "negated", "quoted"]
    operation: Literal["assert", "correct", "retract"]
    turn: int = Field(ge=0)
    quote: str = Field(min_length=1)
    product: Product = "unknown"


class TurnUnderstanding(StrictModel):
    intent: Intent
    product: Product
    topic: Topic
    certainty: Literal["clear", "ambiguous"]
    facts: list[FactUpdate] = Field(default_factory=list, max_length=24)
    source_refs: list[str] = Field(default_factory=list, max_length=3)
    # A current utterance supporting the intent; model instructions in user
    # speech or a document cannot grant action/approval authority.
    intent_quote: str
    # Replaced by the host's user-turn ordinal after parsing model output.
    current_turn: int = Field(default=0, ge=0)


class PolicyClaim(StrictModel):
    key: Literal["apr", "online_bonus", "early_rate", "min_amount", "max_amount",
                 "min_term", "max_term", "ltv", "min_age", "max_age", "min_income",
                 "annual_fee", "tier_min", "tier_max"]
    value: str
    unit: Literal["vnd", "percent", "months", "years", "age"]
    term_months: int | None = None
    tier: str = ""
    quote: str
    source_ref: str = ""
    qualifier: Literal["exact", "minimum", "maximum", "indicative"] = "exact"


class PolicyExtraction(StrictModel):
    claims: list[PolicyClaim] = Field(default_factory=list, max_length=64)


@dataclass(frozen=True)
class SourceSnippet:
    id: str
    text: str


@dataclass(frozen=True)
class PolicySnapshot:
    product: str
    version: str
    snippets: tuple[SourceSnippet, ...]
    claims: tuple[PolicyClaim, ...]
    errors: tuple[str, ...] = ()

    def unique(self, key: str, *, term_months: int | None = None,
               tier: str = "") -> Decimal | None:
        """Conflicting, absent, or non-finite policy values remain unknown."""
        values = set()
        for claim in self.claims:
            if (claim.key != key or claim.term_months != term_months
                    or claim.tier.casefold() != tier.casefold()):
                continue
            if key == "apr" and claim.qualifier != "exact":
                return None
            try:
                value = Decimal(claim.value)
            except Exception:
                continue
            if value.is_finite():
                values.add(value)
        return next(iter(values)) if len(values) == 1 else None

    def evidence_for(self, key: str, *, term_months: int | None = None,
                     tier: str = "") -> tuple[str, ...]:
        if self.unique(key, term_months=term_months, tier=tier) is None:
            return ()
        known = {snippet.id for snippet in self.snippets}
        return tuple(dict.fromkeys(
            claim.source_ref for claim in self.claims
            if claim.key == key and claim.term_months == term_months
            and claim.tier.casefold() == tier.casefold()
            and claim.source_ref in known))


@dataclass(frozen=True)
class AcceptedFact:
    field: str
    value: str
    owner: str
    product: str
    turn: int
    quote: str


@dataclass
class DialogueState:
    product: str = "unknown"
    # Keys are (product scope, field, owner); personal facts have scope '*'.
    facts: dict[tuple[str, str, str], AcceptedFact] = field(default_factory=dict)
    retracted_at: dict[tuple[str, str, str], int] = field(default_factory=dict)
    security_active: bool = False
    ambiguous_at: dict[tuple[str, str, str], int] = field(default_factory=dict)

    def get(self, name: str, owner: str = "self", product: str | None = None):
        scope = "*" if name in {"income_monthly", "age"} else (product or self.product)
        key = (scope, name, owner)
        return None if key in self.ambiguous_at else self.facts.get(key)

    def evidence(self) -> dict:
        result = {}
        for field_name, slot in (("amount", "amount"), ("term_months", "term"),
                                 ("income_monthly", "income")):
            fact = self.get(field_name)
            key = ("*" if field_name == "income_monthly" else self.product, field_name, "self")
            result[slot] = ({"status": "known", "value": fact.value,
                             "raw": fact.quote, "turn": fact.turn,
                             **({"owner": fact.owner} if slot == "income" else {})}
                            if fact else {"status": ("ambiguous" if key in self.ambiguous_at else "unknown"), "value": None,
                                          "raw": "", "turn": -1})
        return result


@dataclass(frozen=True)
class GroundedAnswer:
    text: str
    reason: str
    source_version: str
    evidence_refs: tuple[str, ...] = ()
