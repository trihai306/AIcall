"""Build immutable, source-grounded product policy snapshots.

The current document is the authority on every call.  Deterministic adapters
cover the product Markdown used by the application; an LLM may only propose
claims when that shape is not recognised.  Proposed claims are accepted only
when their exact quote and normalised quantity can be verified in the selected
product source.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import re
import unicodedata
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.pipeline.grounded_contracts import (
    PolicyClaim,
    PolicySnapshot,
    SourceSnippet,
)


_CACHE_LIMIT = 64
_STRUCTURED_TIMEOUT_S = 13.0
_CACHE: OrderedDict[tuple[str, str], PolicySnapshot] = OrderedDict()
_INFLIGHT: dict[tuple[str, str], tuple[asyncio.AbstractEventLoop,
                                      asyncio.Task[PolicySnapshot]]] = {}

_PRODUCT_ALIASES = {
    "loan": ("vay tin chap", "personal loan", "unsecured loan"),
    "mortgage": ("vay mua nha", "bat dong san", "mortgage", "home loan"),
    "savings": ("tiet kiem", "savings", "deposit"),
    "card": ("the tin dung", "credit card"),
}

# Coverage describes the policy vocabulary expected for each supported product,
# never a rate, threshold, tier name, or answer.  Missing keys remain unknown if
# neither the deterministic adapter nor a verified model proposal can find them.
_EXPECTED_COVERAGE = {
    "loan": frozenset({
        "apr", "max_amount", "min_term", "max_term", "min_age", "max_age",
        "min_income",
    }),
    "mortgage": frozenset({
        "apr", "max_amount", "max_term", "ltv", "min_age", "max_age",
        "min_income",
    }),
    "savings": frozenset({
        "apr", "online_bonus", "early_rate", "min_amount", "min_term",
        "max_term", "min_age",
    }),
    "card": frozenset({
        "max_amount", "min_age", "min_income", "annual_fee", "tier_min",
        "tier_max",
    }),
}

_POLICY_KEY_ORDER = (
    "apr", "online_bonus", "early_rate", "min_amount", "max_amount",
    "min_term", "max_term", "ltv", "min_age", "max_age", "min_income",
    "annual_fee", "tier_min", "tier_max",
)


@dataclass(frozen=True)
class _Line:
    number: int
    text: str
    section: str


@dataclass(frozen=True)
class _Span:
    line: _Line
    start: int
    end: int

    @property
    def text(self) -> str:
        return self.line.text[self.start:self.end]


_PolicyKey = Literal[
    "apr", "online_bonus", "early_rate", "min_amount", "max_amount",
    "min_term", "max_term", "ltv", "min_age", "max_age", "min_income",
    "annual_fee", "tier_min", "tier_max",
]


class _WirePolicyProposal(BaseModel):
    """Untrusted model output selects meaning and verbatim evidence only.

    Extra legacy fields are ignored deliberately.  In particular, a model's
    value, unit, or qualifier can never override quantities derived from the
    verified quote by host code.
    """
    model_config = ConfigDict(extra="forbid")

    key: _PolicyKey
    quote: str = Field(min_length=1)
    tier: str = ""


class _WirePolicyExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[_WirePolicyProposal] = Field(default_factory=list, max_length=64)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").casefold().replace("đ", "d"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _product_key(product: str) -> str:
    value = _plain(product).strip().replace("-", "_").replace(" ", "_")
    aliases = {
        "vay": "loan", "vay_tin_chap": "loan", "personal_loan": "loan",
        "vay_mua_nha": "mortgage", "home_loan": "mortgage",
        "tiet_kiem": "savings", "deposit": "savings",
        "the": "card", "the_tin_dung": "card", "credit_card": "card",
    }
    return aliases.get(value, value)


def _selected_lines(product: str, source_doc: str) -> list[tuple[int, str]]:
    """Select one H1 product block and exclude appended FAQ/product blocks."""
    if _product_key(product) not in _PRODUCT_ALIASES:
        return []
    lines = (source_doc or "").splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r"^#\s+\S", line)]
    if not starts:
        return list(enumerate(lines, 1))

    blocks: list[tuple[int, int, str]] = []
    for pos, start in enumerate(starts):
        end = starts[pos + 1] if pos + 1 < len(starts) else len(lines)
        blocks.append((start, end, _plain(lines[start].lstrip("# "))))

    key = _product_key(product)
    aliases = _PRODUCT_ALIASES.get(key, (_plain(product),))
    chosen = next((b for b in blocks if any(a and a in b[2] for a in aliases)), None)
    # An unfamiliar H1 is not proof that the document belongs to this product.
    # Failing closed keeps an FAQ-only or wrong-product source from becoming
    # numeric policy merely because it happens to be the sole block.
    if chosen is None:
        return []
    start, end, _ = chosen
    return [(i + 1, lines[i]) for i in range(start, end)]


def _policy_lines(selected: list[tuple[int, str]]) -> list[_Line]:
    section = ""
    result: list[_Line] = []
    for number, text in selected:
        stripped = text.strip()
        if stripped.startswith("#"):
            section = _plain(stripped.lstrip("# "))
            continue
        if stripped:
            result.append(_Line(number, text, section))
    return result


def _has_internal_clause_separator(text: str) -> bool:
    if ";" in text:
        return True
    for position, char in enumerate(text):
        if char != ".":
            continue
        between_digits = (position > 0 and position + 1 < len(text)
                          and text[position - 1].isdigit()
                          and text[position + 1].isdigit())
        if not between_digits and text[position + 1:].strip():
            return True
    return False


def _decimal(raw: str, *, grouped_if_three: bool = False) -> Decimal | None:
    value = raw.strip().replace(" ", "")
    if grouped_if_three and re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", value):
        value = value.replace(".", "").replace(",", "")
    elif "." in value and "," in value:
        last_dot, last_comma = value.rfind("."), value.rfind(",")
        decimal_mark = "." if last_dot > last_comma else ","
        group_mark = "," if decimal_mark == "." else "."
        value = value.replace(group_mark, "").replace(decimal_mark, ".")
    else:
        value = value.replace(",", ".")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


_NUMBER = r"\d+(?:[.,]\d+)*"
_MONEY_UNIT = (
    r"tỷ|ty|billion|triệu|trieu|million|nghìn|nghin|thousand|"
    r"vnd|vnđ|đồng|dong|đ"
)


def _money_values(text: str) -> list[Decimal]:
    """Read VND quantities; a range may share the unit printed at its end."""
    result: list[Decimal] = []
    pattern = re.compile(
        rf"(?P<a>{_NUMBER})(?:\s*(?:-|–|—|đến|toi|to)\s*(?P<b>{_NUMBER}))?"
        rf"\s*(?P<u>{_MONEY_UNIT})(?=$|\W)", re.I,
    )
    for match in pattern.finditer(text):
        unit = _plain(match.group("u"))
        factor = (Decimal("1000000000") if unit in {"ty", "billion"}
                  else Decimal("1000000") if unit in {"trieu", "million"}
                  else Decimal("1000") if unit in {"nghin", "thousand"}
                  else Decimal(1))
        for name in ("a", "b"):
            raw = match.group(name)
            if raw is None:
                continue
            number = _decimal(raw, grouped_if_three=factor == 1)
            if number is not None:
                result.append(number * factor)
    return result


def _percent_values(text: str) -> list[Decimal]:
    values: list[Decimal] = []
    plain = _plain(text)
    pattern = re.compile(
        rf"(?P<a>{_NUMBER})(?:\s*(?:-|–|—|den|toi|to)\s*(?P<b>{_NUMBER}))?"
        r"\s*(?:%|(?:diem\s*)?phan\s*tram|diem\s*%)",
        re.I,
    )
    for match in pattern.finditer(plain):
        for name in ("a", "b"):
            raw = match.group(name)
            value = _decimal(raw) if raw else None
            if value is not None:
                values.append(value)
    return values


def _duration_values(text: str) -> list[tuple[Decimal, str]]:
    result: list[tuple[Decimal, str]] = []
    pattern = re.compile(
        rf"(?P<a>{_NUMBER})(?:\s*(?:-|–|—|đến|toi|to)\s*(?P<b>{_NUMBER}))?"
        # A digit can immediately follow the unit in compact tables, for
        # example ``6tháng4,10%``.  It is a valid boundary, while another
        # letter is not.
        r"\s*(?P<u>tháng|thang|months?|năm|nam|years?)(?=$|[^a-z])", re.I,
    )
    for match in pattern.finditer(text):
        unit = ("months" if _plain(match.group("u")) in {"thang", "month", "months"}
                else "years")
        for name in ("a", "b"):
            value = _decimal(match.group(name)) if match.group(name) else None
            if value is not None:
                result.append((value, unit))
    return result


def _age_values(text: str) -> list[Decimal]:
    plain = _plain(text)
    after = re.findall(
        rf"({_NUMBER})(?:\s*(?:-|–|—|den|toi|to)\s*({_NUMBER}))?"
        r"\s*(?:tuoi|years?\s+old|age)\b", plain,
    )
    before = re.findall(
        rf"\b(?:tuoi|age)\s*:?\s*(?:tu|from)?\s*({_NUMBER})"
        rf"(?:\s*(?:-|–|—|den|toi|to)\s*({_NUMBER}))?", plain,
    )
    result: list[Decimal] = []
    for first, second in after + before:
        for raw in (first, second):
            if raw:
                value = _decimal(raw)
                if value is not None and value not in result:
                    result.append(value)
    return result


def _has_promotional_duration(text: str) -> bool:
    return bool(_duration_values(text)) and _contains_alias(
        text, "uu dai", "khuyen mai", "promotion", "promotional", "introductory",
    )


def _source_qualifier(key: str, value: Decimal, quote: str) -> str:
    """Derive whether the quoted value is exact or only a boundary/estimate."""
    plain = _plain(quote)
    if any(word in plain for word in ("khoang", "xap xi", "uoc tinh", "about", "around")):
        return "indicative"
    if key in {"min_amount", "min_term", "min_age", "min_income", "tier_min",
               "max_amount", "max_term", "max_age", "tier_max"}:
        is_minimum = key.startswith("min_") or key == "tier_min"
        if _has_explicit_range(quote):
            return "minimum" if is_minimum else "maximum"
        compact = re.sub(r"\s+", "", plain)
        if is_minimum and (re.search(
                r"\b(?:tu|from|at\s+least|minimum|starting\s+at|starts\s+from)\b",
                plain) or any(word in compact for word in ("toithieu", "trolen"))):
            return "minimum"
        if not is_minimum and (re.search(
                r"\b(?:up\s+to|at\s+most|maximum)\b", plain)
                or any(word in compact for word in ("toida", "lenden"))):
            return "maximum"
        if not is_minimum and re.search(r"\bden\s*\d", plain):
            return "maximum"
        return "exact"
    if key in {"apr", "ltv"}:
        values = _percent_values(quote)
        if len(values) >= 2:
            if value == min(values):
                return "minimum"
            if value == max(values):
                return "maximum"
        if re.search(
                r"\b(?:tu|from|starting at|starts from|at least)\s*:?\s*\d", plain):
            return "minimum"
        if re.search(
                r"\b(?:toi\s*da|len\s*den|maximum|up to|at most)\s*:?\s*\d", plain):
            return "maximum"
    return "exact"


def _claim(key: str, value: Decimal, unit: str, quote: str, *,
           term_months: int | None = None, tier: str = "",
           qualifier: str | None = None) -> PolicyClaim:
    if key in {"min_term", "max_term"} and unit == "years":
        value *= 12
        unit = "months"
    return PolicyClaim(key=key, value=str(value), unit=unit,
                       term_months=term_months, tier=tier, quote=quote,
                       qualifier=qualifier or _source_qualifier(key, value, quote))


def _tier_name(text: str) -> str:
    prefix = text.split(":", 1)[0]
    prefix = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", prefix)
    prefix = re.sub(r"^\s*(?:thẻ|the|card)\s+", "", prefix, flags=re.I)
    return prefix.strip()


def _label_span(text: str, label: str) -> str:
    """Return one labelled clause, independent of clause order and other numbers."""
    plain = _plain(text)
    patterns = {
        "limit": r"\b(?:han muc|limit)\b",
        "annual_fee": r"\b(?:phi thuong nien|annual fee)\b",
    }
    found: list[tuple[int, str]] = []
    for name, pattern in patterns.items():
        matches = list(re.finditer(pattern, plain))
        if len(matches) > 1:
            return ""
        if matches:
            found.append((matches[0].start(), name))
    found.sort()
    for index, (start, name) in enumerate(found):
        if name != label:
            continue
        ends = [found[index + 1][0]] if index + 1 < len(found) else []
        # A clause separator is not a decimal/thousands separator between two
        # digits.  This lets unrelated cashback/cap clauses sit between fields.
        separator = re.search(r"(?<!\d)[,;]|[,;](?!\d)", text[start:])
        if separator:
            ends.append(start + separator.start())
        end = min(ends) if ends else len(text)
        return text[start:end].strip(" ,;:-")
    return ""


def _parse_line(line: _Line) -> list[PolicyClaim]:
    quote = line.text.strip()
    plain, section = _plain(quote), line.section
    if "vi du" in section or "example" in section or re.search(r"\bvi du\b", plain):
        return []

    claims: list[PolicyClaim] = []
    money = _money_values(quote)
    percents = _percent_values(quote)
    durations = _duration_values(quote)
    ages = _age_values(quote)

    is_tier = ":" in quote and bool(re.search(r"\b(?:the|card)\b", plain)) \
        and any(word in plain for word in ("han muc", "limit"))
    tier = _tier_name(quote) if is_tier else ""
    if is_tier:
        # Each value is owned by its labelled clause.  Reading the first/last
        # money values breaks as soon as editors reorder fee and limit clauses.
        limits = _money_values(_label_span(quote, "limit"))
        fees = _money_values(_label_span(quote, "annual_fee"))
        if len(limits) == 2:
            claims.append(_claim("tier_min", min(limits), "vnd", quote, tier=tier))
            claims.append(_claim("tier_max", max(limits), "vnd", quote, tier=tier))
        if len(fees) == 1:
            claims.append(_claim("annual_fee", fees[0], "vnd", quote, tier=tier))
        return claims

    context = f"{plain} {section}"
    if any(word in plain for word in ("lai suat", "interest rate", "apr")) and percents:
        if "online" in context and any(word in plain for word in (
                "cong them", "them", "adds", "additional")):
            claims.extend(_claim("online_bonus", value, "percent", quote)
                          for value in percents)
        elif any(word in plain for word in (
                "rut truoc han", "tat toan truoc han", "early withdrawal")):
            claims.extend(_claim("early_rate", value, "percent", quote)
                          for value in percents)
        elif (not _has_promotional_duration(quote)
              and not any(word in plain for word in (
                "cashback", "hoan tien", "tra gop", "giam", "discount",
                "reduction", "reduced"))
              and any(word in plain for word in (
                  "/nam", "/year", "per year", "annual", "annually", "apr"))):
            term = None
            if any(word in plain for word in ("ky han", "term")) and durations:
                amount, unit = durations[0]
                term = int(amount * (12 if unit == "years" else 1))
            claims.extend(_claim("apr", value, "percent", quote, term_months=term)
                          for value in percents)

    if any(word in plain for word in ("han muc", "limit", "ceiling")):
        if percents and any(word in plain for word in (
                "gia tri", "tai san", "property value", "ltv")):
            claims.extend(_claim("ltv", value, "percent", quote) for value in percents)
        if money and (len(money) == 2 and _has_explicit_range(quote)
                      or _source_qualifier("max_amount", max(money), quote) == "maximum"):
            claims.append(_claim("max_amount", max(money), "vnd", quote))

    if money and any(word in plain for word in ("toi thieu", "minimum")) and any(
            word in plain for word in ("so tien", "tien gui", "khoan gui", "deposit")):
        claims.append(_claim("min_amount", min(money), "vnd", quote))

    if money and any(word in plain for word in ("thu nhap", "income")) and any(
            word in plain for word in ("tu ", "toi thieu", "tro len", "minimum", "from")):
        claims.append(_claim("min_income", min(money), "vnd", quote))

    if durations and any(word in plain for word in ("ky han", "thoi han", "term")) \
            and not percents \
            and not any(word in plain for word in ("lai suat", "interest rate", "apr")):
        values = durations
        if len(values) >= 2:
            months = [value * (12 if unit == "years" else 1)
                      for value, unit in values]
            claims.append(_claim("min_term", min(months), "months", quote))
            claims.append(_claim("max_term", max(months), "months", quote))
        elif any(word in plain for word in ("toi da", "len den", "maximum", "up to")):
            claims.append(_claim("max_term", values[-1][0], values[-1][1], quote))
        elif any(word in plain for word in ("toi thieu", "minimum")):
            claims.append(_claim("min_term", values[0][0], values[0][1], quote))

    if ages:
        if len(ages) >= 2:
            claims.append(_claim("min_age", ages[0], "age", quote))
            claims.append(_claim("max_age", ages[1], "age", quote))
        elif any(word in plain for word in ("tro len", "toi thieu", "minimum", "from")):
            claims.append(_claim("min_age", ages[0], "age", quote))
        elif any(word in plain for word in ("toi da", "maximum", "up to")):
            claims.append(_claim("max_age", ages[0], "age", quote))

    if any(word in plain for word in ("phi thuong nien", "annual fee")) and money:
        claims.append(_claim("annual_fee", money[-1], "vnd", quote))
    return claims


def _dedupe(claims: Iterable[PolicyClaim]) -> tuple[PolicyClaim, ...]:
    result: list[PolicyClaim] = []
    seen: set[tuple] = set()
    for claim in claims:
        identity = (claim.key, claim.value, claim.unit, claim.term_months,
                    claim.tier.casefold(), claim.quote, claim.qualifier)
        if identity not in seen:
            seen.add(identity)
            result.append(claim)
    return tuple(result)


def _quote_location(quote: str, selected: list[tuple[int, str]]) \
        -> tuple[_Line, int, int] | None:
    """Locate one exact, contiguous quote within a policy line.

    A repeated substring is ambiguous evidence, even when both occurrences are
    on the same line.  Headings cannot become quantitative evidence.
    """
    if not quote:
        return None
    matches: list[tuple[_Line, int, int]] = []
    for line in _policy_lines(selected):
        start = 0
        while True:
            position = line.text.find(quote, start)
            if position < 0:
                break
            matches.append((line, position, position + len(quote)))
            if len(matches) > 1:
                return None
            start = position + 1
    return matches[0] if len(matches) == 1 else None


def _source_clause_spans(selected: list[tuple[int, str]]) -> tuple[_Span, ...]:
    """Decompose current source into exact, non-crossing semantic clauses."""
    spans: list[_Span] = []
    seen: set[tuple[int, int, int]] = set()

    def add(line: _Line, raw_start: int, raw_end: int) -> None:
        while raw_start < raw_end and line.text[raw_start].isspace():
            raw_start += 1
        while raw_end > raw_start and (line.text[raw_end - 1].isspace()
                                       or line.text[raw_end - 1] in ";,."):
            raw_end -= 1
        identity = (line.number, raw_start, raw_end)
        if raw_end <= raw_start or raw_end - raw_start > 600 or identity in seen:
            return
        seen.add(identity)
        spans.append(_Span(line, raw_start, raw_end))

    for line in _policy_lines(selected):
        boundaries: list[int] = []
        for position, char in enumerate(line.text):
            between_digits = (position > 0 and position + 1 < len(line.text)
                              and line.text[position - 1].isdigit()
                              and line.text[position + 1].isdigit())
            if char == ";" or (char in ".," and not between_digits):
                boundaries.append(position)
        starts = [0] + [position + 1 for position in boundaries]
        ends = boundaries + [len(line.text)]
        for raw_start, raw_end in zip(starts, ends):
            add(line, raw_start, raw_end)
            colon = line.text.find(":", raw_start, raw_end)
            if colon >= 0:
                prefix = _plain(line.text[raw_start:colon])
                compact = re.sub(r"\s+", "", prefix)
                field_prefixes = (
                    "lai suat", "interestrate", "apr", "ky han", "term",
                    "han muc", "gioi han", "limit", "income", "thu nhap",
                    "age", "tuoi", "annualfee", "phi nam", "phi thuong nien",
                )
                if not any(re.sub(r"\s+", "", label) in compact
                           for label in field_prefixes):
                    add(line, colon + 1, raw_end)
        if len(spans) >= 384:
            break
    return tuple(spans[:384])


def _source_quote_candidates(selected: list[tuple[int, str]]) -> tuple[str, ...]:
    """Return bounded exact fragments the model is allowed to select."""
    candidates: list[str] = []
    seen: set[str] = set()
    for span in _source_clause_spans(selected):
        if span.text not in seen:
            seen.add(span.text)
            candidates.append(span.text)
    return tuple(candidates)


def _wire_schema(candidates: tuple[str, ...], missing_keys: frozenset[str]) -> dict:
    schema = deepcopy(_WirePolicyExtraction.model_json_schema())

    def constrain(node) -> None:
        if not isinstance(node, dict):
            return
        properties = node.get("properties")
        if isinstance(properties, dict) and "key" in properties and "quote" in properties:
            properties["key"]["enum"] = sorted(missing_keys)
            properties["quote"]["enum"] = list(candidates)
        for value in node.values():
            if isinstance(value, dict):
                constrain(value)
            elif isinstance(value, list):
                for item in value:
                    constrain(item)

    constrain(schema)
    return schema


def _contains_alias(text: str, *aliases: str) -> bool:
    plain = _plain(text)
    compact = re.sub(r"\s+", "", plain)
    return any(_plain(alias) in plain or re.sub(r"\s+", "", _plain(alias)) in compact
               for alias in aliases)


def _semantics_match(claim: PolicyClaim, section: str, parent_line: str) -> bool:
    plain = _plain(claim.quote)
    parent_plain = _plain(parent_line)
    safety_context = f"{parent_plain} {_plain(section)}"
    if _contains_alias(safety_context, "vi du", "example"):
        return False
    # The quoted span must itself identify the field.  Context outside it can
    # veto examples/promotions/currency mixing, but cannot lend an unrelated
    # number a semantic role.
    anchors = {
        "apr": ("lai suat", "interest rate", "apr", "borrowing rate",
                "borrowing cost", "chi phi vay", "ky han", "term"),
        "online_bonus": ("cong them", "cong", "adds", "additional", "bonus"),
        "early_rate": ("rut truoc han", "tat toan truoc han", "early withdrawal"),
        "min_amount": ("toi thieu", "minimum"),
        "max_amount": ("han muc", "gioi han", "limit", "ceiling"),
        "min_term": ("ky han", "thoi han", "term"),
        "max_term": ("ky han", "thoi han", "term"),
        "ltv": ("gia tri", "tai san", "property value", "ltv"),
        "min_age": ("tuoi", "age", "years old"),
        "max_age": ("tuoi", "age", "years old"),
        "min_income": ("thu nhap", "income"),
        "annual_fee": ("phi thuong nien", "phi nam", "annual fee", "phi"),
        "tier_min": ("han muc", "gioi han", "limit"),
        "tier_max": ("han muc", "gioi han", "limit"),
    }[claim.key]
    if not _contains_alias(claim.quote, *anchors):
        return False
    if claim.key == "online_bonus" and not _contains_alias(claim.quote, "online"):
        return False
    if claim.key == "min_amount" and _contains_alias(
            claim.quote, "thu nhap", "income", "gia tri nha", "property value",
            "phi", "fee", "han muc", "gioi han", "limit"):
        return False
    if claim.key == "annual_fee" and not _contains_alias(
            claim.quote, "phi thuong nien", "phi nam", "annual fee") \
            and (not claim.tier or not _contains_alias(claim.quote, "phi")):
        return False
    if claim.key == "apr" and (
            _contains_alias(claim.quote, "rut truoc han", "tat toan truoc han",
                            "early withdrawal", "cong them", "adds", "additional",
                            "bonus")
            or _contains_alias(safety_context, "cashback", "hoan tien", "giam",
                               "discount", "reduction", "reduced")):
        return False
    if claim.key == "apr" and _has_promotional_duration(safety_context) \
            and not _contains_alias(claim.quote, "ky han", "term"):
        return False
    if claim.key == "apr" and not _contains_alias(
            claim.quote, "/nam", "/year", "per year", "annual", "annually", "apr"):
        return False
    if claim.unit == "vnd" and re.search(
            r"\b(?:usd|eur|gbp|jpy|dollar|euro)\b", safety_context):
        return False
    if claim.term_months is not None:
        terms = [int(value * (12 if unit == "years" else 1))
                 for value, unit in _duration_values(claim.quote)]
        # A narrow term/rate quote owns exactly one term.  This prevents a
        # proposal from arbitrarily pairing one rate with another nearby term.
        if len(terms) != 1 or claim.term_months != terms[0]:
            return False
    elif claim.key == "apr" and _duration_values(claim.quote):
        return False
    if claim.key == "apr" and len(_percent_values(claim.quote)) != 1:
        return False
    if claim.tier and not _contains_alias(parent_line, claim.tier):
        return False
    return True


def _has_explicit_range(quote: str) -> bool:
    return bool(re.search(
        rf"{_NUMBER}\s*(?:(?:{_MONEY_UNIT})|%|thang|months?|nam|years?|tuoi)?"
        rf"\s*(?:-|–|—|den|to)\s*{_NUMBER}", _plain(quote), re.I,
    ))


def _has_bound_meaning(key: str, quote: str, values: list[Decimal]) -> bool:
    """Require source wording, rather than the model key, to own a bound."""
    if key not in {"min_amount", "max_amount", "min_term", "max_term",
                   "min_age", "max_age", "min_income", "tier_min", "tier_max"}:
        return True
    if len(values) == 2 and _has_explicit_range(quote):
        return True
    if len(values) != 1:
        return False
    expected = "minimum" if key.startswith("min_") or key == "tier_min" \
        else "maximum"
    return _source_qualifier(key, values[0], quote) == expected


def _tier_from_context(parent_line: str, start: int, end: int) -> str:
    """Find the single card owner whose colon-led clause contains the quote."""
    colons = [position for position, char in enumerate(parent_line) if char == ":"]
    inside = [position for position in colons if start <= position < end]
    colon = inside[0] if len(inside) == 1 else max(
        (position for position in colons if position < start), default=-1,
    )
    if colon < 0:
        return ""
    boundary = -1
    for position in range(colon - 1, -1, -1):
        char = parent_line[position]
        between_digits = (position > 0 and position + 1 < len(parent_line)
                          and parent_line[position - 1].isdigit()
                          and parent_line[position + 1].isdigit())
        if char == ";" or (char == "." and not between_digits):
            boundary = position
            break
    owner = _tier_name(parent_line[boundary + 1:colon] + ":")
    owner = re.sub(r"^(?:\s*\[[^\]]+\]\s*)+", "", owner).strip()
    owner = re.sub(r"^(?:the|card)\s+", "", owner, flags=re.I).strip()
    # A field label followed by a colon is not a dynamic tier name.
    if not owner or _contains_alias(
            owner, "lai suat", "interest rate", "ky han", "term", "han muc",
            "limit", "phi thuong nien", "phi nam", "annual fee", "tuoi", "age",
            "thu nhap", "income", "toi thieu", "minimum", "toi da", "maximum"):
        return ""
    return owner


def _tier_from_self_label(quote: str, key: str) -> str:
    """Read a dynamic tier name only when the same clause labels its field."""
    patterns = []
    if key == "annual_fee":
        patterns.extend((
            rf"(?:phí\s+thường\s+niên|phí\s+năm|annual\s+fee|phí)\s+"
            rf"(?P<tier>[^\d:;,]+?)\s*(?={_NUMBER})",
        ))
    else:
        patterns.extend((
            r"(?P<tier>[^\d:;,]+?)\s+(?:có\s+)?(?:hạn\s+mức|giới\s+hạn|limit)\b",
            rf"(?:hạn\s+mức|giới\s+hạn|limit)\s+(?P<tier>[^\d:;,]+?)\s*(?={_NUMBER})",
        ))
    for pattern in patterns:
        match = re.search(pattern, quote, re.I)
        if not match:
            continue
        owner = _tier_name(match.group("tier") + ":")
        owner = re.sub(r"^(?:\s*\[[^\]]+\]\s*)+", "", owner).strip()
        owner = re.sub(r"^(?:the|thẻ|card)\s+", "", owner, flags=re.I).strip()
        if (owner and re.search(r"[A-Za-zÀ-ỹ]", owner)
                and _plain(owner) not in {
                    "nam", "thuong nien", "annual fee", "toi da", "maximum",
                    "up to", "at most", "den", "toi thieu", "minimum",
                    "at least", "from",
                }):
            return owner
    return ""


def _tier_owns_card_limit(product: str, key: str, quote: str, line: _Line,
                          start: int, end: int) -> bool:
    """Keep a dynamically named card limit out of product-wide ceilings."""
    return bool(
        product == "card" and key == "max_amount"
        and (_tier_from_context(line.text, start, end)
             or _tier_from_self_label(quote, "tier_max"))
    )


def _derived_claims(product: str, proposal: _WirePolicyProposal, line: _Line,
                    start: int, end: int) -> list[PolicyClaim]:
    """Derive quantities and dimensions from source, never model fields."""
    key, quote = proposal.key, proposal.quote
    if _tier_owns_card_limit(product, key, quote, line, start, end):
        return []
    values: list[Decimal]
    unit: str

    if key in {"apr", "online_bonus", "early_rate", "ltv"}:
        values = _percent_values(quote)
        unit = "percent"
        if len(values) != 1:
            return []
    elif key in {"min_amount", "max_amount", "min_income", "annual_fee",
                 "tier_min", "tier_max"}:
        values = _money_values(quote)
        unit = "vnd"
    elif key in {"min_age", "max_age"}:
        values = _age_values(quote)
        unit = "age"
    else:
        durations = _duration_values(quote)
        values = [value * (12 if source_unit == "years" else 1)
                  for value, source_unit in durations]
        unit = "months"

    if not values:
        return []
    if not _has_bound_meaning(key, quote, values):
        return []
    if len(values) == 1:
        value = values[0]
    elif (len(values) == 2 and _has_explicit_range(quote)
          and key in {"min_amount", "max_amount", "min_term", "max_term",
                      "min_age", "max_age", "tier_min", "tier_max"}):
        value = min(values) if key.startswith("min_") or key == "tier_min" \
            else max(values)
    else:
        return []

    term_months = None
    if key == "apr":
        terms = [int(amount * (12 if source_unit == "years" else 1))
                 for amount, source_unit in _duration_values(quote)]
        owns_term = _contains_alias(quote, "ky han", "term")
        if owns_term and len(terms) > 1:
            return []
        term_months = terms[0] if owns_term and terms else None

    owner = ""
    if key in {"tier_min", "tier_max", "annual_fee"}:
        owner = (_tier_from_context(line.text, start, end)
                 or _tier_from_self_label(quote, key))
        if proposal.tier:
            named_in_quote = bool(re.search(
                rf"(?<!\w){re.escape(_plain(proposal.tier))}(?!\w)", _plain(quote), re.I,
            ))
            if owner and _plain(proposal.tier) != _plain(owner):
                return []
            if not owner and not named_in_quote:
                return []
            owner = owner or proposal.tier.strip()
        if key in {"tier_min", "tier_max"} and not owner:
            return []

    claim = _claim(
        key, value, unit, quote, term_months=term_months, tier=owner,
        qualifier=_source_qualifier(key, value, quote),
    )
    return [claim] if _semantics_match(claim, line.section, line.text) else []


def _claim_signature(claim: PolicyClaim) -> tuple:
    return (claim.key, claim.value, claim.unit, claim.term_months,
            claim.tier.casefold(), claim.qualifier)


def _host_clause_claims(product: str, selected: list[tuple[int, str]],
                        version: str) -> tuple[list[PolicyClaim], list[SourceSnippet]]:
    """Compile explicit typed clauses without depending on model key selection."""
    allowed = _EXPECTED_COVERAGE.get(product, frozenset())
    claims: list[PolicyClaim] = []
    snippets: list[SourceSnippet] = []
    seen_claims: set[tuple] = set()
    seen_snippets: set[str] = set()
    spans = sorted(_source_clause_spans(selected), key=lambda span: len(span.text))
    for span in spans:
        for key in _POLICY_KEY_ORDER:
            if key not in allowed:
                continue
            proposal = _WirePolicyProposal(key=key, quote=span.text)
            for claim in _derived_claims(
                    product, proposal, span.line, span.start, span.end):
                signature = _claim_signature(claim)
                if signature in seen_claims:
                    continue
                source_ref = (f"{version}:L{span.line.number}"
                              if span.start == 0 and span.end == len(span.line.text)
                              else f"{version}:L{span.line.number}:C{span.start}-{span.end}")
                claims.append(claim.model_copy(update={"source_ref": source_ref}))
                seen_claims.add(signature)
                if ":C" in source_ref and source_ref not in seen_snippets:
                    snippets.append(SourceSnippet(id=source_ref, text=span.text))
                    seen_snippets.add(source_ref)
    return claims, snippets


def _validated_llm_claims(product: str, extraction: _WirePolicyExtraction,
                          selected: list[tuple[int, str]],
                          version: str, allowed_keys: frozenset[str]) \
        -> tuple[list[PolicyClaim], list[SourceSnippet], list[str]]:
    accepted: list[PolicyClaim] = []
    supplemental: list[SourceSnippet] = []
    errors: list[str] = []
    candidates = set(_source_quote_candidates(selected))
    for index, proposal in enumerate(extraction.claims):
        location = (_quote_location(proposal.quote, selected)
                    if proposal.key in allowed_keys and proposal.quote in candidates
                    else None)
        line, start, end = location if location else (_Line(0, "", ""), 0, 0)
        source_ref = (f"{version}:L{line.number}" if proposal.quote == line.text
                      else f"{version}:L{line.number}:C{start}-{end}")
        derived = _derived_claims(
            product, proposal, line, start, end,
        ) if location else []
        if derived:
            accepted.extend(claim.model_copy(update={"source_ref": source_ref})
                            for claim in derived)
            if source_ref.endswith(f":C{start}-{end}"):
                supplemental.append(SourceSnippet(id=source_ref, text=proposal.quote))
        else:
            errors.append(f"rejected_llm_claim:{index}:{proposal.key}")
    return accepted, supplemental, errors


async def _fallback_extract(llm, selected: list[tuple[int, str]],
                            missing_keys: frozenset[str]) -> _WirePolicyExtraction:
    numbered = "\n".join(f"L{number}: {text}" for number, text in selected)
    candidates = _source_quote_candidates(selected)
    messages = [
        {
            "role": "system",
            "content": (
                "Classify explicit product-policy source fragments. Return only key, "
                "quote, and an optional tier label. Select quote exactly from the schema "
                "enum; prefer the smallest self-labelled fragment containing the number, "
                "unit, and associated term or tier. Never emit or calculate value, unit, "
                "qualifier, or term_months. Set tier to the exact dynamic card name when "
                "the fragment names a card tier. Never join non-contiguous text. Do not approve "
                "eligibility, or use worked examples as policy APR. Keep conflicting "
                "source fragments as separate proposals. The "
                "L<number>: locator is not part of the quote. "
                "Only propose these currently missing keys: "
                + ", ".join(sorted(missing_keys)) + "."
            ),
        },
        {"role": "user", "content": numbered},
    ]
    result = llm.generate_structured(
        messages, _wire_schema(candidates, missing_keys), num_predict=768, timeout=12.0,
    )
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, _WirePolicyExtraction):
        return result
    if isinstance(result, BaseModel):
        result = result.model_dump()
    # Some model backends return fields from an older cached grammar.  Strip
    # them before validation so even syntactically plausible model quantities
    # never enter the trusted contract.  The advertised schema itself forbids
    # such fields.
    if isinstance(result, dict) and isinstance(result.get("claims"), list):
        cleaned = []
        for raw_claim in result["claims"]:
            if not isinstance(raw_claim, dict):
                cleaned.append(raw_claim)
                continue
            proposal = {name: raw_claim[name] for name in ("key", "quote", "tier")
                        if name in raw_claim}
            cleaned.append(proposal)
        result = {"claims": cleaned}
    return _WirePolicyExtraction.model_validate(result)


def _cache_get(key: tuple[str, str]) -> PolicySnapshot | None:
    value = _CACHE.get(key)
    if value is not None:
        _CACHE.move_to_end(key)
    return value


def _cache_put(key: tuple[str, str], value: PolicySnapshot) -> None:
    _CACHE[key] = value
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_LIMIT:
        _CACHE.popitem(last=False)


def _clear_policy_cache() -> None:
    """Test hook; production invalidation is content-addressed."""
    _CACHE.clear()


async def _compile_policy(canonical_product: str, raw: str, version: str, llm) \
        -> PolicySnapshot:
    """Compile and cache one immutable content version."""
    selected = _selected_lines(canonical_product, raw)
    snippets = list(
        SourceSnippet(id=f"{version}:L{number}", text=text)
        for number, text in selected if text.strip()
    )
    product_keys = _EXPECTED_COVERAGE.get(canonical_product, frozenset())
    parsed = [
        claim.model_copy(update={"source_ref": f"{version}:L{line.number}"})
        for line in _policy_lines(selected) for claim in _parse_line(line)
        if not _has_internal_clause_separator(line.text)
        if claim.key in product_keys
        if not _tier_owns_card_limit(
            canonical_product, claim.key, claim.quote, line, 0, len(line.text),
        )
    ]
    host_claims, host_snippets = _host_clause_claims(
        canonical_product, selected, version,
    )
    known_signatures = {_claim_signature(claim) for claim in parsed}
    for claim in host_claims:
        if _claim_signature(claim) not in known_signatures:
            parsed.append(claim)
            known_signatures.add(_claim_signature(claim))
    known_snippet_ids = {snippet.id for snippet in snippets}
    for snippet in host_snippets:
        if snippet.id not in known_snippet_ids:
            snippets.append(snippet)
            known_snippet_ids.add(snippet.id)
    errors: list[str] = []

    covered = frozenset(claim.key for claim in parsed)
    missing = product_keys - covered
    # A format can change one field while canonical fields still parse.  Ask for
    # only missing keys once per content-addressed snapshot; cache hits never call
    # the model again.  Empty or rejected proposals leave those fields unknown.
    if missing and llm is not None and any(re.search(r"\d", line)
                                           for _, line in selected):
        try:
            extraction = await asyncio.wait_for(
                _fallback_extract(llm, selected, missing),
                timeout=_STRUCTURED_TIMEOUT_S,
            )
            proposed, narrow_snippets, rejected = _validated_llm_claims(
                canonical_product, extraction, selected, version, missing,
            )
            for claim in proposed:
                if claim.key in covered:
                    rejected.append(f"ignored_llm_claim:{claim.key}:already_grounded")
                    continue
                parsed.append(claim)
            known_snippet_ids = {snippet.id for snippet in snippets}
            for snippet in narrow_snippets:
                if snippet.id not in known_snippet_ids:
                    snippets.append(snippet)
                    known_snippet_ids.add(snippet.id)
            errors.extend(rejected)
        except Exception as exc:
            errors.append(f"llm_extraction_failed:{type(exc).__name__}")

    snapshot = PolicySnapshot(
        product=canonical_product,
        version=version,
        snippets=tuple(snippets),
        claims=_dedupe(parsed),
        errors=tuple(errors),
    )
    _cache_put((canonical_product, version), snapshot)
    return snapshot


async def build_policy(product: str, source_doc: str, llm) -> PolicySnapshot:
    """Return a policy snapshot derived from this call's current source text.

    Concurrent readers of the same product and content share one compiler task.
    Shielding keeps cancellation of one caller from cancelling the compiler for
    every other reader; the structured generation timeout bounds that task.
    """
    raw = source_doc or ""
    version = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    canonical_product = _product_key(product)
    cache_key = (canonical_product, version)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    loop = asyncio.get_running_loop()
    existing = _INFLIGHT.get(cache_key)
    if existing is not None and existing[0] is loop and not existing[1].done():
        return await asyncio.shield(existing[1])
    if existing is not None and existing[0] is not loop and not existing[1].done():
        raise RuntimeError("Policy compilation is active on another event loop")

    # A task from another event loop must never be awaited here.  Production has
    # one application loop; this guard also makes repeated asyncio.run test loops
    # safe if a prior loop was interrupted before its callback ran.
    task = loop.create_task(_compile_policy(canonical_product, raw, version, llm))
    _INFLIGHT[cache_key] = (loop, task)

    def forget(done: asyncio.Task[PolicySnapshot]) -> None:
        current = _INFLIGHT.get(cache_key)
        if current is not None and current[1] is done:
            _INFLIGHT.pop(cache_key, None)

    task.add_done_callback(forget)
    return await asyncio.shield(task)


__all__ = ["build_policy"]
