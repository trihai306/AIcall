"""Typed, evidence-backed projection of loan facts from chronological turns.

Three distinct states matter: no update, a resolved update, and an unresolved
replacement. The last one MUST invalidate the old value. Never search backwards
past a correction to resurrect a stale amount. No product limit, assistant
claim, model prompt or particular loan amount is used to infer customer facts.

The projection is rebuilt from the persisted history, so reconnects and removal
of interrupted turns cannot leave a second, mutable memory out of sync. This is
a conservative Vietnamese number grammar, not an ASR correction dictionary.
Unsupported/ambiguous expressions request clarification instead of guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re
import unicodedata


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


_DIGIT = dict(zip("không một hai ba bốn năm sáu bảy tám chín".split(), range(10)))
_DIGIT.update({"mốt": 1, "tư": 4, "lăm": 5})
_SCALE = {"nghìn": 1000, "ngàn": 1000, "triệu": 10**6, "tr": 10**6,
          "tỷ": 10**9, "tỉ": 10**9}
_WORDS = set(_DIGIT) | {"trăm", "mươi", "mười", "chục", "linh", "lẻ", "phẩy", "nửa"}
_CURRENCY = {"đồng", "vnd", "vnđ", "đ"}
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+|[^\w\s]", re.UNICODE)


def _small(words: list[str], duration: bool = False) -> Decimal | None:
    """Strict coefficient grammar: adjacent digits are not added together.

    Ngoại lệ duy nhất, chỉ cho KỲ HẠN (`duration`): cặp chữ số nói tắt kiểu
    "hai bốn", "ba sáu", "bốn tám" - cách người Việt đọc 24/36/48 tháng qua
    điện thoại. Cuộc gọi 7db3f780 (13-09-2026) khách nói "vay một trăm triệu
    trong ba sáu tháng", bộ đọc coi là mơ hồ rồi AI hỏi lại "vay bao nhiêu
    tháng" sáu lượt liền. Chỉ nhận chữ số đầu từ 2 và chữ số sau CHẴN: "hai ba
    tháng" có thể là "2-3 tháng", "năm năm" thì không ai nói 55 tháng - hai
    dạng đó vẫn để mơ hồ để hỏi lại. Tiền KHÔNG áp: "ba sáu triệu" hiếm hơn
    "ba, sáu triệu" nhiều.
    """
    if not words:
        return None
    if words == ["nửa"]:
        return Decimal("0.5")
    if duration and len(words) == 2 and words[0] in _DIGIT and words[1] in _DIGIT:
        a, b = _DIGIT[words[0]], _DIGIT[words[1]]
        if 2 <= a <= 9 and b in (2, 4, 6, 8):
            return Decimal(10 * a + b)
    if len(words) == 1 and words[0][0].isdigit():
        raw = words[0]
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+|\d{1,3}(?:,\d{3}){2,}", raw):
            raw = raw.replace(".", "").replace(",", "")
        else:
            raw = raw.replace(",", ".")
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None
    if "phẩy" in words:
        i = words.index("phẩy")
        whole = _small(words[:i])
        digits = words[i + 1:]
        if whole is None or not digits or any(w not in _DIGIT for w in digits):
            return None
        return whole + Decimal("0." + "".join(str(_DIGIT[w]) for w in digits))
    total = 0
    if len(words) >= 2 and words[0] in _DIGIT and words[1] == "trăm":
        total = _DIGIT[words[0]] * 100
        words = words[2:]
        if words and words[0] in ("linh", "lẻ"):
            words = words[1:]
    if not words:
        return Decimal(total)
    if words[0] == "mười":
        total += 10
        words = words[1:]
    elif len(words) >= 2 and words[0] in _DIGIT and words[1] in ("mươi", "chục"):
        total += _DIGIT[words[0]] * 10
        words = words[2:]
    if not words:
        return Decimal(total)
    if len(words) == 1 and words[0] in _DIGIT:
        return Decimal(total + _DIGIT[words[0]])
    return None


def _number(words: list[str], duration: bool = False) -> tuple[Decimal | None, bool]:
    """Coefficients + descending scales; also supports 'một tỷ rưỡi'."""
    total, previous_scale, part = Decimal(0), float("inf"), []
    has_scale = False
    for w in words:
        if w == "rưỡi":
            if not has_scale or part:
                return None, has_scale
            total += Decimal(previous_scale) / 2
            continue
        if w in _SCALE:
            scale = _SCALE[w]
            coefficient = _small(part)
            if coefficient is None or scale >= previous_scale:
                return None, True
            total += coefficient * scale
            previous_scale, part, has_scale = scale, [], True
        else:
            part.append(w)
    if part:
        # 'một triệu hai' has an unspecified scale, not 1,000,002 dong.
        if has_scale:
            return None, True
        return _small(part, duration), False
    return (total, True) if has_scale else (None, False)


@dataclass(frozen=True)
class Quantity:
    raw: str
    start: int
    end: int
    value: Decimal | None
    kind: str                    # money, duration (months), bare, other


def quantities(text: str) -> list[Quantity]:
    text = unicodedata.normalize("NFC", text.lower())
    tokens = list(_TOKEN.finditer(text))
    result: list[Quantity] = []
    i = 0
    while i < len(tokens):
        w = tokens[i].group()
        if w not in _DIGIT and w not in {"mười", "nửa"} | set(_SCALE) and not w[0].isdigit():
            i += 1
            continue
        j = i + 1
        while j < len(tokens) and (tokens[j].group() in _WORDS | set(_SCALE) | {"rưỡi"}
                                  or tokens[j].group()[0].isdigit()):
            if tokens[j].group() == "không" and j + 1 < len(tokens) and tokens[j + 1].group() == "phải":
                break  # negation starts another clause, not a trailing zero
            j += 1
        words = [m.group() for m in tokens[i:j]]
        following = tokens[j].group() if j < len(tokens) else ""
        scales = [k for k, word in enumerate(words) if word in _SCALE]
        if scales and scales[-1] < len(words) - 1 and (
                following == "tháng" or words[-1] == "năm"):
            # '18 triệu một tháng' is money followed by frequency, not a
            # mixed-scale monetary value or one malformed duration.
            j = i + scales[-1] + 1
            words, following = words[:scales[-1] + 1], ""
        kind = "bare"
        multiplier = 1
        if following in ("tháng", "năm"):
            kind, multiplier = "duration", 12 if following == "năm" else 1
            j += 1
        elif following in _CURRENCY:
            kind = "money"
            j += 1
        elif following == "%" or following in ("tuổi", "ngày", "giờ", "phút"):
            kind = "other"
            j += 1
        # 'năm' is both a digit and the year unit. A terminal 'năm' after a
        # valid coefficient is a year only when no other explicit unit follows.
        elif len(words) > 1 and words[-1] == "năm" and _small(words[:-1]) is not None:
            words, kind, multiplier = words[:-1], "duration", 12
        value, scaled = _number(words, duration=(kind == "duration"))
        if scaled and kind == "bare":
            kind = "money"
        if value is not None:
            value *= multiplier
            if re.search(r"(?:\bâm|[-−])\s*$", text[:tokens[i].start()]):
                value = -abs(value)
        # 'năm' can be five or a calendar year. Calendar phrases are not
        # amounts, but 'vay năm' is an unresolved numeric update: dropping it
        # would incorrectly resurrect the previous principal.
        if words == ["năm"] and kind == "bare" and following in (
                "nay", "ngoái", "tới", "sau", "trước", "đó", "này", "mới", "vừa", "rồi"):
            kind = "other"
        # Standalone 'không' without a unit is a negation, not numeric zero.
        if not (words == ["không"] and kind == "bare"):
            result.append(Quantity(text[tokens[i].start():tokens[j - 1].end()],
                                   tokens[i].start(), tokens[j - 1].end(), value, kind))
        i = j
    return result


@dataclass(frozen=True)
class Fact:
    status: str = "unknown"       # unknown, known, missing_unit, ambiguous, cancelled
    value: Decimal | None = None  # only known values may drive calculations
    raw: str = ""
    turn: int = -1
    coefficient: Decimal | None = None

    def evidence(self) -> dict:
        return {"status": self.status, "value": str(self.value) if self.value is not None else None,
                "raw": self.raw, "turn": self.turn}


@dataclass
class LoanState:
    amount: Fact = field(default_factory=Fact)
    term: Fact = field(default_factory=Fact)
    income: Fact = field(default_factory=Fact)
    amount_updated: bool = False
    term_updated: bool = False
    unit_confirmed: bool = False
    request: str = ""

    def evidence(self) -> dict:
        return {"amount": self.amount.evidence(), "term": self.term.evidence(),
                "income": self.income.evidence()}


# These are semantic roles, not lists of observed bad transcriptions or amounts.
_ANCHORS = re.compile(
    r"\b(?P<income>thu nhap|luong|doanh thu|tien cong)\b|"
    r"\b(?P<identifier>dien thoai|can cuoc|cccd|cmnd|ma so|so tai khoan)\b|"
    r"\b(?P<employment>lam viec|lam cong ty|cong tac|sao ke)\b|"
    r"\b(?P<payoff>tat toan|tra truoc|tra som)\b|"
    r"\b(?P<payment>tien lai|tien phi|moi thang dong|moi thang tra|tra moi thang)\b|"
    r"\b(?P<existing>khoan vay cu|hop dong|du no)\b|"
    r"\b(?P<limit>han muc(?: vay)?|vay toi da|tran san pham)\b|"
    r"\b(?P<term>ky han|thoi han|trong vong|trong)\b|"
    r"\b(?P<amount>vay|may|nhu cau|so tien)\b|"
    r"\b(?P<correction>doi|sua|chot|chi lay|la|ma|con|nham|(?:anh|chi|toi|em) (?:noi|bao))\b")
_CORRECTION = re.compile(r"\b(doi|sua|a nham|y (?:anh|toi|chi) la|chot|(?:anh|chi|toi|em) (?:noi|bao))\b")
_CANCEL = re.compile(r"\b(khong (?:muon |can )?vay nua|huy (?:khoan )?vay|thoi khong vay)\b")
_CALC = re.compile(r"\b(?:moi thang|hang thang|mot thang|tien lai)\b.{0,40}\bbao nhieu\b|\b(?:tra|dong) bao nhieu\b")
_ONLY_NUMBER = re.compile(r"^(?:(?:a|da|vang|o|the|anh|chi|toi|em|la|chi|muon|xin|lay|thoi|nhe|chu)\s*)*$")
_ALTERNATIVE = re.compile(r"\s*(?:hay|hoac(?: la)?|den|toi|[-/])\s*")


def is_readback(text: str) -> bool:
    """Asking what was said is a read, not a correction to a fact."""
    normal = fold(text)
    return bool(re.search(r"\bnhac lai\b", normal) or re.search(
        r"\b(?:da (?:noi|cung cap)|(?:anh|chi|toi|em) noi)\b.{0,60}\b(?:bao nhieu|la gi)\b",
        normal))


def _role(text: str, q: Quantity, established: bool) -> str | None:
    prefix = fold(text[:q.start])
    anchors = list(_ANCHORS.finditer(prefix))
    role = anchors[-1].lastgroup if anchors else None
    if role == "term" and anchors[-1].group() in ("trong", "trong vong"):
        # A temporal preposition does not change the owner of a duration:
        # 'old contract ... within 48 months' and 'early payoff within six
        # months' are not new loan terms.
        owners = [a.lastgroup for a in anchors[:-1] if a.lastgroup not in ("term", "correction")]
        if owners and owners[-1] in ("income", "employment", "identifier", "payment", "payoff", "existing", "limit"):
            role = owners[-1]
    if role == "correction":
        preceding = [a.lastgroup for a in anchors[:-1] if a.lastgroup != "correction"]
        role = preceding[-1] if preceding else ("amount" if established else None)
    if role == "term" and q.kind == "bare":
        return "term"
    if role == "term" and q.kind != "duration":
        role = None
    if q.kind == "duration":
        if role in ("amount", "term"):
            return "term"
        if role in ("income", "employment", "identifier", "payment", "payoff", "existing", "limit"):
            return None
        rest = fold(text[:q.start] + " " + text[q.end:])
        # "ba sáu tháng thì mỗi tháng bao nhiêu": kỳ hạn đứng một mình đầu câu
        # hỏi tính - phần còn lại chính là câu hỏi tính, không phải câu khác.
        if established and (_ONLY_NUMBER.fullmatch(rest.strip(" .,!?:"))
                            or _CALC.search(rest)):
            return "term"
        return None
    if q.kind == "other":
        return None
    if role in ("amount", "income"):
        return role
    # Numeric answers to an ongoing loan discussion, not numbers in arbitrary
    # sentences, IDs, employment or quoted product descriptions.
    rest = fold(text[:q.start] + " " + text[q.end:]).strip(" .,!?:")
    if role is None and (established or q.kind == "money") and _ONLY_NUMBER.fullmatch(rest):
        return "amount"
    if (established or q.kind == "money") and _ONLY_NUMBER.fullmatch(prefix.strip()) and re.match(
            r"\s*(?:[,;\-/]|(?:chu )?khong phai\b|(?:trong|ky han|hay|hoac|den|toi)\b)",
            fold(text[q.end:])):
        return "amount"
    return None


def _negated(text: str, q: Quantity) -> bool:
    prefix = fold(text[:q.start])
    return bool(re.search(r"\b(?:khong phai|chu khong(?: phai)?|khong (?:muon )?vay)\s*$", prefix))


def _fact(q: Quantity, turn: int) -> Fact:
    if q.value is None or q.value <= 0:
        return Fact("ambiguous", raw=q.raw, turn=turn)
    if q.kind == "bare":
        return Fact("missing_unit", raw=q.raw, turn=turn, coefficient=q.value)
    if q.kind == "duration" and q.value != q.value.to_integral():
        return Fact("ambiguous", raw=q.raw, turn=turn)
    return Fact("known", q.value, q.raw, turn)


def _apply(state: LoanState, text: str, turn: int) -> None:
    state.amount_updated = state.term_updated = state.unit_confirmed = False
    normal = fold(text).strip(" .,!?:")
    if is_readback(text):
        return
    # Yêu cầu tính ("mỗi tháng bao nhiêu") chỉ TREO trong lúc còn thiếu dữ
    # kiện: khách bổ sung kỳ hạn ở lượt sau thì lượt đó tính luôn. Đã đủ cả
    # hai mà lượt mới không hỏi tính nữa thì thôi treo - không thì "anh vay 300
    # triệu được không" ở lượt sau lại bị đem ra tính trả góp.
    if (state.request == "calculation" and state.amount.value is not None
            and state.term.value is not None and not _CALC.search(normal)):
        state.request = ""
    if _CANCEL.search(normal):
        state.amount = state.term = Fact("cancelled", raw=text, turn=turn)
        state.amount_updated = state.term_updated = True
        state.request = ""
        return
    # Confirm a missing unit by an explicit unit response, not an unrelated
    # 'yes' and never a bank/product number that only the assistant supplied.
    unit_match = re.fullmatch(
        r"\s*(?:(?:dạ|vâng|là)\s+)*(nghìn|ngàn|triệu|tr|tỷ|tỉ|đồng|vnd|vnđ|đ|tháng|năm)"
        r"(?:\s+đồng)?(?:\s+(?:ạ|nhé|nha|thôi))*\s*[.!?,]*\s*", text.lower())
    unit = unit_match.group(1) if unit_match else ""
    if state.amount.status == "missing_unit" and unit in set(_SCALE) | _CURRENCY:
        scale = _SCALE.get(unit, 1)
        state.amount = Fact("known", state.amount.coefficient * scale,
                            state.amount.raw + " " + unit, turn)
        state.amount_updated = True
        state.unit_confirmed = True
        return
    if state.term.status == "missing_unit" and unit in ("tháng", "năm"):
        value = state.term.coefficient * (12 if unit == "năm" else 1)
        state.term = _fact(Quantity(state.term.raw + " " + unit, 0, len(text), value, "duration"), turn)
        state.term_updated = True
        state.unit_confirmed = True
        return
    established = state.amount.status != "unknown" or state.term.status != "unknown"
    candidates: dict[str, list[Quantity]] = {"amount": [], "term": [], "income": []}
    negated_roles: set[str] = set()
    previous: tuple[Quantity, str | None] | None = None
    for q in quantities(text):
        role = _role(text, q, established)
        if role is None and previous and previous[1] and _ALTERNATIVE.fullmatch(
                fold(text[previous[0].end:q.start])):
            role = previous[1]
        previous = q, role
        # A negated amount in an established discussion still clears the old
        # fact even when 'không phải' lacks another explicit loan keyword.
        if _negated(text, q):
            if role:
                negated_roles.add(role)
            elif established and re.fullmatch(r"\s*(?:chu )?khong phai\s*", fold(text[:q.start])):
                negated_roles.add("term" if q.kind == "duration" else "amount")
            continue
        if role:
            candidates[role].append(q)
    for name, choices in candidates.items():
        if not choices:
            continue
        distinct = {(q.value, q.kind) for q in choices}
        # Two different numbers require either an explicit correction between
        # them or a clarification. 'A hay B' must not become an arbitrary B.
        correction = (len(choices) > 1 and _CORRECTION.search(
            fold(text[choices[-2].end:choices[-1].start])))
        fact = (_fact(choices[-1], turn) if len(distinct) == 1 or correction
                else Fact("ambiguous", raw=" / ".join(q.raw for q in choices), turn=turn))
        setattr(state, name, fact)
        if name in ("amount", "term"):
            setattr(state, name + "_updated", True)
    for name in negated_roles:
        if not candidates[name]:
            setattr(state, name, Fact("ambiguous", raw=text, turn=turn))
            if name in ("amount", "term"):
                setattr(state, name + "_updated", True)
    if established and _CORRECTION.search(normal) and not any(candidates.values()):
        # Unknown replacements invalidate their own slot, not always principal.
        owners = [a.lastgroup for a in _ANCHORS.finditer(normal) if a.lastgroup != "correction"]
        target = owners[-1] if owners else "amount"
        if target in candidates:
            setattr(state, target, Fact("ambiguous", raw=text, turn=turn))
            if target in ("amount", "term"):
                setattr(state, target + "_updated", True)
    if _CALC.search(normal) and (state.amount_updated or state.term_updated
                                or not re.search(r"\b(?:luong|thu nhap)\b", normal)):
        state.request = "calculation"


def resolve(history: list[dict] | None = None, text: str | None = None) -> LoanState:
    """Pure chronological reducer. Ignores all assistant quantities.

    Callers may pass a history already containing the current user turn. Only
    the trailing duplicate is suppressed; repeated older corrections matter.
    """
    entries = list(history or [])
    if text is not None and not (entries and entries[-1].get("role") == "user"
                                and entries[-1].get("content") == text):
        entries.append({"role": "user", "content": text})
    state = LoanState()
    for i, row in enumerate(entries):
        if row.get("role") == "user":
            _apply(state, unicodedata.normalize("NFC", row.get("content") or ""), i)
    return state
