"""Deterministic comparisons for explicit customer facts and retrieved rules.

Only emit a note when both sides are present. This never declares a loan
approved; it only compares the particular condition the customer asked about.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _explicit_card_condition_question(text: str) -> bool:
    """The narrow compound question this deterministic answer owns."""
    t = _plain(text)
    return all((
        re.search(r"\bdoi chieu\b.{0,24}\bdieu kien\b", t),
        re.search(r"\bchac chan\b", t),
        re.search(r"\b(?:cap|mo) the\b", t),
        re.search(r"\bhan muc\b.{0,24}\b(?:cao nhat|toi da)\b", t),
    ))


def _card_rules(source: str):
    """Return unique published minima and per-tier ranges, or ``None``.

    Values come only from the current retrieved source. Repeated identical
    statements are harmless; conflicting statements disable the direct answer.
    """
    ages: set[int] = set()
    incomes: set[Decimal] = set()
    tiers: dict[str, set[tuple[Decimal, Decimal]]] = {}
    display: dict[str, str] = {}
    for line in (source or "").splitlines():
        plain = _plain(line)
        if "tuoi" in plain:
            for raw in re.findall(
                    r"\b(?:tu|toi thieu|it nhat)\s+(?:la\s+)?(\d{1,3})\s*tuoi\b",
                    plain):
                ages.add(int(raw))
        if re.search(r"\b(?:thu nhap|luong)\b", plain):
            for raw in re.findall(
                    r"\b(?:tu|toi thieu|it nhat)\s+(?:la\s+)?"
                    r"(\d+(?:[.,]\d+)?)\s*trieu\b", plain):
                incomes.add(Decimal(raw.replace(",", ".")) * Decimal(1_000_000))
        tier = re.search(
            r"(?i)\bthẻ\s+([^\s:,-]+)\s*:\s*[^\n]*?\bhạn mức\s+"
            r"(\d+(?:[.,]\d+)?)\s*(?:triệu(?:\s*đồng)?\s*)?"
            r"(?:[-–—]|(?:đến|tới))\s*(\d+(?:[.,]\d+)?)\s*triệu\b",
            line,
        )
        if tier:
            key = _plain(tier.group(1))
            low = Decimal(tier.group(2).replace(",", "."))
            high = Decimal(tier.group(3).replace(",", "."))
            tiers.setdefault(key, set()).add((low, high))
            display.setdefault(key, tier.group(1))
    if len(ages) != 1 or len(incomes) != 1 or not tiers:
        return None
    return next(iter(ages)), next(iter(incomes)), tiers, display


def _selected_card_tier(messages: list[dict], tier_keys: set[str]) -> tuple[str, str]:
    """Return ``(status, key)`` using customer turns only and latest choice."""
    for row in reversed(messages):
        if row.get("role") != "user":
            continue
        text = _plain(str(row.get("content") or ""))
        found: list[tuple[int, str]] = []
        for key in tier_keys:
            found += [(m.start(), key) for m in re.finditer(
                rf"\b(?:the\s+)?{re.escape(key)}\b", text)]
        found.sort()
        distinct = {key for _, key in found}
        if len(distinct) == 1:
            return "known", found[-1][1]
        if len(distinct) > 1:
            if re.search(r"\b(?:doi sang|chot|chon)\b", text):
                return "known", found[-1][1]
            return "ambiguous", ""
    return "unknown", ""


_OTHER_PERSON_SUBJECT = re.compile(
    r"^(?:(?:bo|cha|me|vo|chong|con(?: trai| gai)?|anh trai|chi gai|em trai|"
    r"em gai|ban|dong nghiep|sep|quan ly|nguoi yeu)\b)|"
    r"\b(?:bo|cha|me|vo|chong|con(?: trai| gai)?|anh trai|chi gai|em trai|"
    r"em gai|ban|dong nghiep|sep|quan ly|nguoi yeu)(?: cua)?\s+"
    r"(?:toi|minh|anh|chi|em)\b"
)
_NON_ACTUAL_FACT = re.compile(
    r"\b(?:neu|gia su|vi du|sau nay|sang nam|nam sau|thang sau|tuong lai)\b"
)
_QUOTED_FACT_CLAUSE = re.compile(
    r"^\s*(?:theo\s+)?(?:nguon|tai lieu|ngan hang|ho so)\b.{0,80}"
    r"\b(?:noi|bao|yeu cau|quy dinh|can|phai)\b"
)
_EXPLICIT_ACTUAL_OWNER = re.compile(
    r"^\s*(?:toi|em)\b|"
    r"\b(?:thu nhap|luong)(?:\s+(?:rieng|thuc te))(?:\s+cua)?\s+"
    r"(?:toi|minh|anh|chi|em)\b|"
    r"\b(?:thu nhap|luong)\s+cua\s+(?:toi|minh|anh|chi|em)\b|"
    r"^\s*(?:thu nhap|luong)\s+(?:minh|anh|chi|em)\b|"
    r"^\s*(?:tong thu nhap|thu nhap (?:chung|hai vo chong|gia dinh|ho gia dinh))\b"
)
_QUOTED_AGE_RULE = re.compile(
    r"\b(?:dieu kien|yeu cau|quy dinh|ngan hang|tai lieu|nguon)\b.{0,36}$"
)


def _semantic_plain(text: str) -> str:
    """Fold accents and expose word/number boundaries from glued chat text."""
    return re.sub(
        r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", _plain(text), flags=re.I)


def _fact_clauses(text: str) -> list[str]:
    """Split only at boundaries that can introduce a new fact owner/modal state."""
    return [part.strip() for part in re.split(
        r"[,;.!?]+|\b(?:còn|nhưng)\b", text or "", flags=re.I
    ) if part.strip()]


def _non_actual_self_clause(text: str) -> bool:
    plain = _semantic_plain(text).strip()
    return bool(
        _NON_ACTUAL_FACT.search(plain)
        or _QUOTED_FACT_CLAUSE.search(plain)
        or _OTHER_PERSON_SUBJECT.search(plain)
    )


def _actual_fact_clauses(text: str) -> list[str]:
    """Keep source/owner scope while filtering consecutive clauses.

    A comma after ``Nguồn cũ nói`` cannot turn the following published
    threshold into the caller's salary. An explicit caller or household clause
    ends that quoted scope and remains eligible for the typed projection.
    """
    kept: list[str] = []
    quoted_scope = False
    for part in _fact_clauses(text):
        plain = _semantic_plain(part).strip()
        if _QUOTED_FACT_CLAUSE.search(plain):
            quoted_scope = True
            continue
        if quoted_scope:
            if _EXPLICIT_ACTUAL_OWNER.search(plain):
                quoted_scope = False
            else:
                continue
        if not _non_actual_self_clause(part):
            kept.append(part)
    return kept


def _age_state(messages: list[dict]) -> tuple[str, int | None]:
    """Conservative chronological projection of the applicant's actual age."""
    status, value = "unknown", None
    for row in messages:
        if row.get("role") != "user":
            continue
        original = str(row.get("content") or "")
        text = _plain(original)
        retracted = bool(re.search(
            r"\b(?:rut lai|bo|huy|khong dung)\b.{0,30}\b(?:tuoi|thong tin tuoi)\b|"
            r"\b(?:tuoi|thong tin tuoi)\b.{0,30}\b(?:rut lai|bo|huy|khong dung)\b",
            text,
        ))
        actual_clauses = _actual_fact_clauses(original)
        actual_text = " ".join(actual_clauses)
        actual_plain = _plain(actual_text)
        alternatives = re.search(
            r"(?<!\d)(\d{1,3})\s*(?:hay|hoac|/|[-–])\s*"
            r"(\d{1,3})\s*tuoi\b", actual_plain)
        candidates: list[int] = []
        for clause in actual_clauses:
            for match in re.finditer(r"(?<!\d)(\d{1,3})\s*tuổi\b", clause, re.I):
                before = _plain(clause[:match.start()])
                if _QUOTED_AGE_RULE.search(before) or re.search(r"\btu\s*$", before):
                    continue
                if re.search(r"\bkhong phai\s*$", before):
                    continue
                candidates.append(int(match.group(1)))
        if alternatives and not re.search(r"\bkhong phai\b.{0,40}\bma\b", actual_plain):
            status, value = "ambiguous", None
        elif candidates:
            distinct = set(candidates)
            corrected = bool(re.search(
                r"\b(?:a nham|nham|sua lai|doi lai|khong phai)\b", actual_plain))
            if len(distinct) == 1 or corrected:
                status, value = "known", candidates[-1]
            else:
                status, value = "ambiguous", None
        elif retracted or ("khong phai" in text and "tuoi" in text):
            status, value = "unknown", None
    return status, value


def _without_non_actual_fact_claims(messages: list[dict], quantities, other_owner) -> list[dict]:
    """Mask non-caller quantities before removing non-actual clauses.

    Ownership must be decided against the untouched turn. Otherwise removing
    ``Mẹ tôi là nhân viên ngân hàng`` leaves the following ``lương 20
    triệu`` clause orphaned and the typed reducer reasonably treats it as the
    caller's own salary.
    """
    cleaned: list[dict] = []
    for row in messages:
        if row.get("role") != "user":
            cleaned.append(row)
            continue
        original = str(row.get("content") or "")
        masked = list(original)
        for q in quantities(original):
            if q.kind in ("bare", "money") and other_owner(original, q):
                masked[q.start:q.end] = " " * (q.end - q.start)
        kept = _actual_fact_clauses("".join(masked))
        cleaned.append({**row, "content": " ".join(kept)})
    return cleaned


def _income_state(messages: list[dict]):
    # Reuse the canonical typed/provenance-aware reducer; do not maintain a
    # second raw-number history in this precheck.
    from backend.pipeline.du_kien_khoan_vay import (
        chu_the_thu_nhap_nguoi_khac,
        quantities,
        resolve,
    )

    state = resolve(_without_non_actual_fact_claims(
        messages, quantities, chu_the_thu_nhap_nguoi_khac)).income
    latest_retraction = -1
    for index, row in enumerate(messages):
        if row.get("role") != "user":
            continue
        text = _plain(str(row.get("content") or ""))
        if re.search(
                r"\b(?:rut lai|bo|huy|khong dung)\b.{0,30}\b(?:thu nhap|luong)\b|"
                r"\b(?:thu nhap|luong)\b.{0,30}\b(?:rut lai|bo|huy|khong dung)\b",
                text):
            latest_retraction = index
    if latest_retraction > state.turn:
        return "unknown", None, ""
    return state.status, state.value, state.owner


def _fmt_number(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if value % 1 else str(int(value))


def _card_condition_answer(messages: list[dict], source: str, prefix: str) -> str:
    rules = _card_rules(source)
    if not rules:
        return ""
    minimum_age, minimum_income, tiers, display = rules
    tier_status, tier = _selected_card_tier(messages, set(tiers))
    if tier_status == "known" and len(tiers[tier]) != 1:
        return ""

    age_status, age = _age_state(messages)
    income_status, income, owner = _income_state(messages)
    facts: list[str] = []
    if age_status == "known" and age is not None:
        relation = "đạt" if age >= minimum_age else "chưa đạt"
        facts.append(f"{age} tuổi {relation} mức tối thiểu {minimum_age} tuổi")
    else:
        facts.append(f"cần xác nhận tuổi hiện tại của người đứng tên (tối thiểu {minimum_age} tuổi)")

    income_min_m = minimum_income / Decimal(1_000_000)
    if income_status == "known" and income is not None and owner == "self":
        income_m = income / Decimal(1_000_000)
        relation = "đạt" if income >= minimum_income else "chưa đạt"
        facts.append(
            f"thu nhập riêng {_fmt_number(income_m)} triệu/tháng {relation} "
            f"mức tối thiểu {_fmt_number(income_min_m)} triệu/tháng"
        )
    elif income_status == "known" and owner == "household":
        facts.append(
            f"thu nhập hộ gia đình chưa thay cho thu nhập riêng; cần xác nhận "
            f"thu nhập riêng so với mức {_fmt_number(income_min_m)} triệu/tháng"
        )
    else:
        facts.append(
            f"cần xác nhận một mức thu nhập riêng so với mức tối thiểu "
            f"{_fmt_number(income_min_m)} triệu/tháng"
        )

    if tier_status == "known":
        low, high = next(iter(tiers[tier]))
        tier_fact = (f"Thẻ {display[tier]} có dải hạn mức "
                     f"{_fmt_number(low)}-{_fmt_number(high)} triệu")
    else:
        tier_fact = "Cần xác nhận một loại thẻ cụ thể để đối chiếu dải hạn mức"
    compared = "; ".join(facts)
    return (f"{prefix}theo điều kiện công bố, {compared}. {tier_fact}, nhưng chưa thể "
            "khẳng định được cấp thẻ hay được hạn mức cao nhất vì còn cần thẩm định hồ sơ.")


def banking_fact_precheck(messages: list[dict], system_prompt: str) -> str:
    source = system_prompt.split("THÔNG TIN THAM KHẢO:", 1)[-1]
    if source == system_prompt:
        return ""
    users = [str(m.get("content") or "") for m in messages if m.get("role") == "user"]
    if not users:
        return ""
    latest = users[-1]
    history = " ".join(users)
    notes: list[str] = []

    if re.search(r"(?i)tuổi|đủ điều kiện|vay được|mở thẻ", latest):
        recent_ages = re.findall(r"(?<!\d)(\d{1,2})\s*tuổi\b", latest, re.I)
        ages = recent_ages or re.findall(r"(?<!\d)(\d{1,2})\s*tuổi\b", history, re.I)
        minimums = {int(n) for n in re.findall(
            r"(?i)\btừ\s+(\d{2})\s*(?:[-–]\s*\d{2}\s*)?tuổi\b", source
        )}
        ranges = {(int(a), int(b)) for a, b in re.findall(
            r"(?i)\btừ\s+(\d{2})\s*[-–]\s*(\d{2})\s*tuổi\b", source
        )}
        if ages and (recent_ages or len(set(ages)) == 1) and len(minimums) == 1:
            age, minimum = int(ages[-1]), next(iter(minimums))
            if age < minimum:
                notes.append(
                    f"Khách {age} tuổi < mức tối thiểu {minimum} tuổi trong nguồn: "
                    "CHƯA đạt riêng điều kiện tuổi. Không được nói là đã đạt."
                )
            elif len(ranges) == 1:
                lower, upper = next(iter(ranges))
                if lower == minimum and age > upper:
                    notes.append(
                        f"Khách {age} tuổi > mức tối đa {upper} tuổi trong nguồn: "
                        "CHƯA đạt riêng điều kiện tuổi. Không được nói là đã đạt."
                    )

    if re.search(r"(?i)nợ xấu|tất toán|trả hết nợ", latest) and re.search(
        r"(?i)tất toán\s+trên\s+(?:1|một)\s+năm", source
    ):
        settled = r"(?:tất toán|trả hết(?: nợ xấu| nợ)?)"
        month_matches = re.findall(rf"(?i){settled}[^.!?\n]{{0,35}}?(\d{{1,2}})\s*tháng", history)
        month_matches += re.findall(rf"(?i)(\d{{1,2}})\s*tháng[^.!?\n]{{0,35}}?{settled}", history)
        if month_matches and len(set(month_matches)) == 1:
            months = int(month_matches[-1])
            if months <= 12:
                notes.append(
                    f"Khách đã tất toán {months} tháng <= 12 tháng: CHƯA qua "
                    "mốc trên 1 năm để có thể xem xét. Không nói đã qua mốc."
                )
            else:
                notes.append(
                    f"Khách đã tất toán {months} tháng > 12 tháng: chỉ CÓ THỂ "
                    "xem xét; không khẳng định được duyệt."
                )

    if re.search(r"(?i)chưa có tài sản (?:bảo đảm|đảm bảo)", history) and re.search(
        r"(?i)có tài sản (?:bảo đảm|đảm bảo)", source
    ) and re.search(r"(?i)đủ điều kiện|vay được|kết luận", latest):
        notes.append(
            "Khách đã nói CHƯA có tài sản bảo đảm, còn nguồn yêu cầu có: "
            "CHƯA đạt điều kiện tài sản; đừng hỏi lại như thể chưa biết."
        )

    return "\n".join(notes)


def direct_condition_answer(messages: list[dict], system_prompt: str,
                            prefill: str = "") -> str:
    """Answer only an explicit numeric-condition question with checked facts."""
    users = [str(m.get("content") or "") for m in messages if m.get("role") == "user"]
    if not users:
        return ""
    latest = users[-1]
    note = banking_fact_precheck(messages, system_prompt)
    prefix = "" if prefill.strip() else ("Vâng, " if re.search(r"(?i)miền Bắc", " ".join(users)) else "Dạ, ")
    source = system_prompt.split("THÔNG TIN THAM KHẢO:", 1)[-1]

    if source != system_prompt and _explicit_card_condition_question(latest):
        answer = _card_condition_answer(messages, source, prefix)
        if answer:
            return answer

    age = re.search(r"Khách (\d+) tuổi < mức tối thiểu (\d+) tuổi", note)
    if age and re.search(r"(?i)riêng tuổi|điều kiện tuổi|tuổi.*(đạt|đủ|được)", latest):
        return (f"{prefix}{age.group(1)} tuổi chưa đạt điều kiện tuổi ạ; "
                f"tài liệu yêu cầu từ {age.group(2)} tuổi.")

    above = re.search(r"Khách (\d+) tuổi > mức tối đa (\d+) tuổi", note)
    if above and re.search(r"(?i)riêng tuổi|điều kiện tuổi|tuổi.*(đạt|đủ|được)", latest):
        return (f"{prefix}{above.group(1)} tuổi chưa đạt điều kiện tuổi ạ; "
                f"tài liệu giới hạn đến {above.group(2)} tuổi.")

    debt = re.search(r"Khách đã tất toán (\d+) tháng <= 12 tháng", note)
    if debt and re.search(r"(?i)đã qua mốc|trên (?:1|một) năm|được xem xét|thuộc diện", latest):
        return (f"{prefix}{debt.group(1)} tháng chưa qua mốc trên 1 năm trong "
                "tài liệu, nên chưa thuộc trường hợp có thể xem xét theo điều kiện này ạ.")

    debt_above = re.search(r"Khách đã tất toán (\d+) tháng > 12 tháng", note)
    if debt_above and re.search(r"(?i)được xem xét|được vay|duyệt|chắc|trên (?:1|một) năm", latest):
        return (f"{prefix}{debt_above.group(1)} tháng đã qua mốc trên 1 năm ạ; "
                "hồ sơ có thể được xem xét, nhưng chưa thể khẳng định được duyệt.")

    if "CHƯA đạt điều kiện tài sản" in note and re.search(
        r"(?i)có thể kết luận|đủ điều kiện|vay được", latest
    ):
        return (f"{prefix}chưa thể kết luận đủ điều kiện ạ; tài liệu yêu cầu "
                "có tài sản bảo đảm, còn anh/chị vừa nói mình chưa có.")

    card = re.search(r"(?i)thẻ\s+(Classic|Gold|Platinum)", latest)
    if card and re.search(r"(?i)năm thứ (?:2|hai)|từ năm thứ hai", latest) and re.search(
        r"(?i)miễn phí thường niên năm đầu", source
    ):
        fees = re.findall(
            rf"(?im)^\s*\d+\.\s*Thẻ\s+{re.escape(card.group(1))}:"
            r"[^\n]*?phí thường niên\s+([\d.]+)\s*đ/năm", source
        )
        if len(fees) == 1:
            return (f"{prefix}năm đầu được miễn phí; từ năm thứ hai, phí thường niên "
                    f"thẻ {card.group(1)} là {fees[0]}đ/năm ạ.")

    if re.search(r"(?i)gửi online|gửi trực tuyến", latest) and re.search(
        r"(?i)bao nhiêu|cộng lên|thành bao nhiêu", latest
    ):
        term = re.search(r"(?i)(\d{1,2})\s*tháng", latest)
        bonus = re.search(r"(?i)lãi suất cộng thêm\s+(\d+(?:[.,]\d+)?)%/năm", source)
        if term and bonus:
            rates = re.findall(
                rf"(?i)kỳ hạn\s+{re.escape(term.group(1))}\s+tháng:\s*lãi suất\s+(\d+(?:[.,]\d+)?)%/năm",
                source,
            )
            if len(rates) == 1:
                base = Decimal(rates[0].replace(",", "."))
                extra = Decimal(bonus.group(1).replace(",", "."))
                total = format(base + extra, "f")
                return (f"{prefix}gửi online kỳ hạn {term.group(1)} tháng là "
                        f"{total}%/năm, gồm mức tại quầy {rates[0]}% cộng thêm {bonus.group(1)}% ạ.")

    if re.search(r"(?i)trả trước hạn|trả nợ trước hạn", latest):
        years = re.search(r"(?i)sau\s+(\d{1,2})\s+năm", latest)
        free_after = re.search(r"(?i)miễn phí trả nợ trước hạn sau\s+(\d{1,2})\s+năm", source)
        if years and free_after and int(years.group(1)) > int(free_after.group(1)):
            return (f"{prefix}trả trước hạn sau {years.group(1)} năm thuộc diện miễn phí ạ; "
                    f"tài liệu miễn phí sau {free_after.group(1)} năm.")
    return ""
