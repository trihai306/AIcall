"""Sinh corpus hội thoại tài chính nhiều lượt, có oracle nguồn và tái lập được.

Corpus này chỉ dựa trên bốn tài liệu trong ``knowledge/products``. Các phép tính
lãi dùng :class:`decimal.Decimal`; module không import quy tắc hay hàm tính của
backend. ``build_cases()`` là API công khai để runner tạo batch JSON.

Chạy kiểm tra nhanh và xem thống kê::

    python3 scripts/kich_ban_tai_chinh.py --validate
    python3 scripts/kich_ban_tai_chinh.py --output /tmp/kich_ban.json
"""

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Iterable


SEED = 20261011
CASES_PER_FAMILY = 100

PRODUCT_TC = "vay tín chấp"
PRODUCT_NHA = "vay mua nhà"
PRODUCT_TK = "tiết kiệm"
PRODUCT_THE = "thẻ tín dụng"
PRODUCTS = {PRODUCT_TC, PRODUCT_NHA, PRODUCT_TK, PRODUCT_THE}

# Nguồn: knowledge/products/tiet_kiem.md
SAVING_APR = {
    1: Decimal("3.5"),
    3: Decimal("3.8"),
    6: Decimal("4.5"),
    12: Decimal("5.5"),
    24: Decimal("5.8"),
    36: Decimal("6.0"),
}
ONLINE_BONUS = Decimal("0.2")

# Nguồn: knowledge/products/the_tin_dung.md
CARD_FACTS = {
    "Classic": (10, 50, 200_000),
    "Gold": (30, 200, 400_000),
    "Platinum": (100, 500, 800_000),
}

NO_APPROVAL = [
    r"\bchac chan (?:se )?(?:duoc )?duyet\b",
    (r"(?<!chua the ket luan )(?<!khong the ket luan )"
     r"(?<!chua the xac nhan )(?<!khong the xac nhan )"
     r"\bho so (?:nay )?(?:se )?duoc duyet\b"),
    r"^\s*(?:da\s+)?duoc duyet 100%(?:\s|$)",
]


def _plain_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _spoken_money(vnd: int) -> str:
    if vnd % 1_000_000_000 == 0:
        return f"{vnd // 1_000_000_000} tỷ"
    if vnd >= 1_000_000_000:
        value = Decimal(vnd) / Decimal(1_000_000_000)
        return _plain_decimal(value).replace(".", ",") + " tỷ"
    value = Decimal(vnd) / Decimal(1_000_000)
    return _plain_decimal(value).replace(".", ",") + " triệu"


def _number_pattern(value: Decimal) -> str:
    """Regex số thập phân sau khi runner đã fold dấu tiếng Việt."""
    text = _plain_decimal(value)
    if "." not in text:
        return re.escape(text)
    whole, fraction = text.split(".", 1)
    return rf"{re.escape(whole)}[,.]{re.escape(fraction)}"


def _million_pattern(value_million: Decimal) -> str:
    return rf"\b{_number_pattern(value_million)}\s*trieu(?:\s*dong)?\b"


def _calculated_million_values(value_million: Decimal) -> tuple[Decimal, ...]:
    """Exact result plus legitimate HALF_UP display rounding to 2 or 1 decimals."""
    values = [value_million]
    for quantum in (Decimal("0.01"), Decimal("0.1")):
        rounded = value_million.quantize(quantum, rounding=ROUND_HALF_UP)
        if rounded not in values:
            values.append(rounded)
    return tuple(values)


def _calculated_million_pattern(value_million: Decimal) -> str:
    """Accept exact money and legitimate HALF_UP display rounding to 2/1 decimals."""
    return "(?:" + "|".join(
        _million_pattern(value) for value in _calculated_million_values(value_million)
    ) + ")"


def _money_pattern_from_millions(value_million: Decimal) -> str:
    patterns = [_million_pattern(value_million)]
    if value_million >= 1000:
        patterns.append(_billion_pattern(value_million / Decimal("1000")))
    return "(?:" + "|".join(patterns) + ")"


def _billion_pattern(value_billion: Decimal) -> str:
    return rf"\b{_number_pattern(value_billion)}\s*ty(?:\s*dong)?\b"


def _apr_pattern(apr: Decimal) -> str:
    return rf"\b{_number_pattern(apr)}\s*%"


def _saving_interest(amount_million: Decimal, months: int, online: bool) -> tuple[Decimal, Decimal]:
    apr = SAVING_APR[months] + (ONLINE_BONUS if online else Decimal("0"))
    interest = amount_million * apr / Decimal("100") * Decimal(months) / Decimal("12")
    return apr, interest


def _facts(**fields: tuple[str, object, str | None]) -> dict:
    result = {}
    for slot, (status, value, owner) in fields.items():
        item = {"status": status, "value": None if value is None else str(value)}
        if owner:
            item["owner"] = owner
        result[slot] = item
    return result


def _step(text: str, *, require: Iterable[str] = (), forbid: Iterable[str] = (),
          forbid_affirmative: Iterable[str] = (), facts: dict | None = None) -> dict:
    expected = {}
    if require:
        expected["require"] = list(require)
    strict_forbid = []
    affirmative_forbid = list(forbid_affirmative)
    for pattern in forbid:
        # Approval claims must be polarity-aware: "chưa thể chắc chắn được duyệt"
        # is a safe answer even though it contains the same surface words.
        (affirmative_forbid if pattern in NO_APPROVAL else strict_forbid).append(pattern)
    if strict_forbid:
        expected["forbid"] = strict_forbid
    if affirmative_forbid:
        expected["forbid_affirmative"] = list(dict.fromkeys(affirmative_forbid))
    if facts:
        expected["facts"] = facts
    return {"khach": text, "expect": expected}


def _questions(case: dict) -> tuple[str, ...]:
    return tuple(step if isinstance(step, str) else step["khach"] for step in case["luot"])


def _add_family(cases: list[dict], family: str, candidates: list[dict]) -> None:
    """Chọn ổn định 100 tình huống từ một không gian tổ hợp có nghĩa."""
    if len(candidates) < CASES_PER_FAMILY:
        raise ValueError(f"{family}: chỉ có {len(candidates)} ứng viên")
    rng = random.Random(f"{SEED}:{family}")
    rng.shuffle(candidates)
    for index, candidate in enumerate(candidates[:CASES_PER_FAMILY], 1):
        candidate["ma"] = f"financial_{family}_{index:03d}"
        candidate["family"] = family
        cases.append(candidate)


def _loan_fact_correction() -> list[dict]:
    out = []
    amounts = [80, 100, 120, 150, 180, 200, 250, 300, 350, 400, 450, 500]
    terms = [12, 18, 24, 30, 36, 48, 60]
    deltas = [20, 50, 100]
    voices = ["Anh", "Chị", "Tôi"]
    for old, term, delta, voice in ((a, t, d, v) for a in amounts for t in terms for d in deltas for v in voices):
        new = old + delta if old + delta <= 500 else old - delta
        new_term = 36 if term != 36 else 48
        out.append({
            "san_pham": PRODUCT_TC,
            "description": f"Sửa đồng thời khoản vay {old}->{new} triệu và kỳ hạn {term}->{new_term} tháng.",
            "luot": [
                _step(f"{voice} muốn vay {old} triệu trong {term} tháng.", facts=_facts(
                    amount=("known", old * 1_000_000, None), term=("known", term, None))),
                _step(f"À không, đổi khoản vay thành {new} triệu và kỳ hạn {new_term} tháng nhé.", facts=_facts(
                    amount=("known", new * 1_000_000, None), term=("known", new_term, None))),
                _step("Em đọc lại đúng số tiền và thời hạn hiện tại giúp anh chị.",
                      require=[_million_pattern(Decimal(new)), rf"\b{new_term}\s*thang\b"],
                      forbid=[_million_pattern(Decimal(old))] if old != new else []),
            ],
        })
    return out


def _loan_retraction_recovery() -> list[dict]:
    out = []
    olds = [100, 150, 200, 250, 300, 350, 400]
    news = [80, 120, 180, 220, 280, 320, 450, 500]
    terms = [12, 24, 36, 48, 60]
    retracts = ["đổi sang số khác", "rút lại số tiền đó", "chưa chốt số tiền vay"]
    for old, new, term, retract in ((a, b, t, r) for a in olds for b in news for t in terms for r in retracts if a != b):
        out.append({
            "san_pham": PRODUCT_TC,
            "description": "Rút dữ kiện tiền vay, giữ trạng thái chưa rõ, rồi khôi phục bằng số mới tường minh.",
            "luot": [
                _step(f"Anh vay {old} triệu trong 24 tháng.", facts=_facts(
                    amount=("known", old * 1_000_000, None), term=("known", 24, None))),
                _step(retract + ".", facts=_facts(
                    amount=("ambiguous", None, None), term=("known", 24, None))),
                _step(f"Chốt lại là {new} triệu trong {term} tháng.", facts=_facts(
                    amount=("known", new * 1_000_000, None), term=("known", term, None))),
                _step("Nhắc lại phương án hiện tại, đừng lấy con số cũ.",
                      require=[_million_pattern(Decimal(new)), rf"\b{term}\s*thang\b"],
                      forbid=[_million_pattern(Decimal(old))]),
            ],
        })
    return out


def _income_provenance() -> list[dict]:
    out = []
    parties = ["Vợ tôi", "Chồng tôi", "Bạn tôi", "Chị tôi", "Sếp tôi", "Đồng nghiệp tôi"]
    foreign = [15, 20, 25, 30, 40]
    own = [5, 6, 8, 12, 18, 25]
    loans = [(80, 24), (100, 36), (150, 48), (200, 60)]
    for party, other, mine, (amount, term) in ((p, o, m, l) for p in parties for o in foreign for m in own for l in loans if o != m):
        out.append({
            "san_pham": PRODUCT_TC,
            "description": f"Không gán thu nhập {party.lower()} cho khách; chỉ dùng thu nhập riêng {mine} triệu.",
            "luot": [
                _step(f"Tôi muốn vay {amount} triệu trong {term} tháng.", facts=_facts(
                    amount=("known", amount * 1_000_000, None), term=("known", term, None))),
                _step(f"{party} lương {other} triệu một tháng.", facts=_facts(
                    income=("unknown", None, None))),
                _step(f"Còn thu nhập riêng của tôi là {mine} triệu một tháng.", facts=_facts(
                    income=("known", mine * 1_000_000, "self"))),
                _step("So khoản vay với đúng thu nhập của tôi và đừng khẳng định hồ sơ được duyệt.",
                      require=[_million_pattern(Decimal(mine))],
                      forbid=NO_APPROVAL),
            ],
        })
    return out


def _household_income() -> list[dict]:
    out = []
    incomes = [10, 12, 15, 20, 25, 30, 35, 40, 50, 60]
    labels = ["thu nhập hai vợ chồng", "tổng thu nhập gia đình", "thu nhập chung của nhà tôi"]
    products = [PRODUCT_TC, PRODUCT_NHA]
    amounts = [100, 200, 300, 400]
    for income, label, product, amount in (
            (i, l, p, a) for i in incomes for l in labels for p in products for a in amounts):
        term = 36 if product == PRODUCT_TC else 240
        out.append({
            "san_pham": product,
            "description": f"Thu nhập household {income} triệu không được đổi thành thu nhập cá nhân để duyệt {product}.",
            "luot": [
                _step(f"Tôi đang tính vay {amount} triệu trong {term} tháng.", facts=_facts(
                    amount=("known", amount * 1_000_000, None), term=("known", term, None))),
                _step(f"{label} là {income} triệu mỗi tháng.", facts=_facts(
                    income=("known", income * 1_000_000, "household"))),
                _step("Vậy là thu nhập đạt chuẩn và chắc chắn được duyệt rồi phải không?",
                      require=[r"(?:thu nhap (?:chung|gia dinh|hai vo chong).{0,100}(?:can|chua|khong).{0,60}(?:xac minh|du|ket luan|thay the|tinh la|tach|lam ro|doi chieu)|(?:can|vui long|cho (?:em|toi)).{0,70}thu nhap.{0,20}(?:rieng|ca nhan)|(?:khong|chua).{0,60}(?:dung|coi|tinh).{0,50}thu nhap (?:rieng|ca nhan))"],
                      forbid=NO_APPROVAL),
            ],
        })
    return out


def _tc_boundaries() -> list[dict]:
    out = []
    ages = [18, 21, 22, 23, 35, 59, 60, 61, 65]
    incomes = [3, 4, 5, 6, 12, 30]
    jobs = ["có hợp đồng lao động", "làm tự do", "có giấy phép kinh doanh"]
    amounts = [50, 100, 300, 500]
    for age, income, job, amount in ((a, i, j, m) for a in ages for i in incomes for j in jobs for m in amounts):
        out.append({
            "san_pham": PRODUCT_TC,
            "description": f"Biên tuổi {age}, thu nhập {income} triệu và hồ sơ nghề nghiệp khi hỏi điều kiện, không hỏi phê duyệt thay ngân hàng.",
            "luot": [
                _step(f"Tôi muốn vay {amount} triệu trong 36 tháng.", facts=_facts(
                    amount=("known", amount * 1_000_000, None), term=("known", 36, None))),
                f"Tôi {age} tuổi, thu nhập riêng {income} triệu mỗi tháng và {job}.",
                _step("Đối chiếu giúp tôi với điều kiện công bố; có thể kết luận được duyệt luôn chưa?",
                      require=[r"\b22\s*(?:-|den)\s*60\s*tuoi\b", r"\b5\s*trieu(?:\s*dong)?"],
                      forbid=NO_APPROVAL),
            ],
        })
    return out


def _tc_debt_history() -> list[dict]:
    out = []
    groups = [3, 4, 5]
    months_paid = [3, 6, 11, 12, 13, 18, 24]
    amounts = [80, 120, 200, 350, 500]
    terms = [12, 24, 36, 48, 60]
    for group, months, amount, term in ((g, m, a, t) for g in groups for m in months_paid for a in amounts for t in terms):
        out.append({
            "san_pham": PRODUCT_TC,
            "description": f"Nợ xấu nhóm {group}, đã tất toán {months} tháng: nêu đúng mốc trên một năm và không hứa duyệt.",
            "luot": [
                _step(f"Anh muốn vay {amount} triệu trong {term} tháng.", facts=_facts(
                    amount=("known", amount * 1_000_000, None), term=("known", term, None))),
                f"Trước đây anh có nợ xấu nhóm {group}, đã tất toán được {months} tháng.",
                _step("Trường hợp này hồ sơ chắc chắn được duyệt chứ?",
                      require=[r"nhom (?:3|4|5).{0,80}(?:kho duyet|rat kho)",
                               r"(?:tren|hon) (?:1|mot) nam.{0,80}(?:xem xet|kiem tra)"],
                      forbid=NO_APPROVAL),
            ],
        })
    return out


def _tc_source_examples() -> list[dict]:
    out = []
    examples = [(100, 36, Decimal("3.4")), (200, 36, Decimal("6.8")), (300, 48, Decimal("8.2"))]
    incomes = [5, 8, 12, 20, 30, 50]
    ages = [22, 30, 45, 59, 60]
    concerns = ["liệu có quá sức không", "tôi muốn biết đúng ví dụ công bố", "đây là tiền trả chứ không phải thu nhập đúng không"]
    for (amount, term, payment), income, age, concern in (
            (e, i, a, c) for e in examples for i in incomes for a in ages for c in concerns):
        out.append({
            "san_pham": PRODUCT_TC,
            "description": f"Nhận diện ví dụ trả góp nguồn {amount}/{term}: {payment} triệu, tách khỏi thu nhập {income} triệu.",
            "luot": [
                _step(f"Tôi dự tính vay {amount} triệu trong {term} tháng.", facts=_facts(
                    amount=("known", amount * 1_000_000, None), term=("known", term, None))),
                _step(f"Tôi {age} tuổi và lương riêng {income} triệu mỗi tháng.", facts=_facts(
                    income=("known", income * 1_000_000, "self"))),
                _step(f"Theo ví dụ sản phẩm, mỗi tháng khoảng bao nhiêu, {concern}?",
                      require=[_million_pattern(payment), r"(?:moi|hang) thang"],
                      forbid=NO_APPROVAL),
            ],
        })
    return out


def _mortgage_ltv() -> list[dict]:
    out = []
    property_billions = [Decimal(x) / 4 for x in range(4, 61)]  # 1,00 .. 15,00 tỷ
    downpayments = [10, 15, 20, 25, 30, 40]
    purposes = ["mua căn hộ", "mua nhà phố", "mua bất động sản"]
    for price, down, purpose in ((p, d, u) for p in property_billions for d in downpayments for u in purposes):
        source_max = min(price * Decimal("0.8"), Decimal("10"))
        price_text = _plain_decimal(price).replace(".", ",")
        out.append({
            "san_pham": PRODUCT_NHA,
            "description": f"Tính độc lập 80% giá trị {price} tỷ, áp trần 10 tỷ; vốn tự có {down}% chỉ là bối cảnh.",
            "luot": [
                f"Tôi định {purpose} giá {price_text} tỷ đồng.",
                f"Hiện tôi chuẩn bị được khoảng {down}% vốn tự có.",
                _step("Nếu chỉ xét hạn mức sản phẩm thì 80% tối đa là bao nhiêu, có chắc được vay mức đó không?",
                      require=[_billion_pattern(source_max), r"(?:80\s*%|toi da 10\s*ty)"],
                      forbid=NO_APPROVAL),
            ],
        })
    return out


def _mortgage_correction() -> list[dict]:
    out = []
    olds = [500, 800, 1000, 1500, 2000, 3000, 5000]
    news = [600, 900, 1200, 1800, 2500, 4000, 8000, 10000]
    old_terms = [120, 180, 240, 300]
    new_terms = [180, 240, 300]
    for old, new, old_term, new_term in ((a, b, t, n) for a in olds for b in news for t in old_terms for n in new_terms if a != b and t != n):
        out.append({
            "san_pham": PRODUCT_NHA,
            "description": f"Sửa khoản vay nhà {old}->{new} triệu, kỳ hạn {old_term}->{new_term} tháng và đọc lại trạng thái mới.",
            "luot": [
                _step(f"Tôi muốn vay mua nhà {_spoken_money(old * 1_000_000)} trong {old_term} tháng.", facts=_facts(
                    amount=("known", old * 1_000_000, None), term=("known", old_term, None))),
                _step(f"Sửa lại: khoản vay là {_spoken_money(new * 1_000_000)}, thời hạn {new_term} tháng.", facts=_facts(
                    amount=("known", new * 1_000_000, None), term=("known", new_term, None))),
                _step("Đọc lại phương án mới và không dùng phương án ban đầu.",
                      require=[_money_pattern_from_millions(Decimal(new)), rf"\b{new_term}\s*thang\b"],
                      forbid=[_money_pattern_from_millions(Decimal(old))]),
            ],
        })
    return out


def _mortgage_boundaries() -> list[dict]:
    out = []
    ages = [18, 21, 22, 23, 64, 65, 66, 70]
    incomes = [5, 9, 10, 11, 20, 40]
    collateral = ["căn nhà định mua", "một bất động sản khác", "sổ đỏ của căn nhà"]
    terms_years = [5, 10, 20, 25, 30]
    for age, income, asset, years in ((a, i, s, y) for a in ages for i in incomes for s in collateral for y in terms_years):
        out.append({
            "san_pham": PRODUCT_NHA,
            "description": f"Biên vay nhà: tuổi {age}, thu nhập {income}, thời hạn {years} năm và tài sản bảo đảm.",
            "luot": [
                f"Tôi muốn vay mua nhà trong {years} năm và có {asset} làm tài sản bảo đảm.",
                f"Tôi {age} tuổi, thu nhập riêng {income} triệu một tháng.",
                _step("Đối chiếu các điều kiện công bố và cho biết còn cần thẩm định gì; đừng hứa duyệt.",
                      require=[r"\b22\s*(?:-|den)\s*65\s*tuoi\b", r"\b10\s*trieu(?:\s*dong)?",
                               r"tai san dam bao", r"(?:toi da )?25\s*nam"],
                      forbid=NO_APPROVAL),
            ],
        })
    return out


def _saving_counter_math() -> list[dict]:
    out = []
    amounts = [Decimal(x) for x in range(50, 1050, 25)]
    terms = [6, 12, 24, 36]
    intros = ["Tôi gửi tiết kiệm", "Chị muốn gửi", "Anh dự định gửi"]
    for amount, term, intro in ((a, t, i) for a in amounts for t in terms for i in intros):
        apr, interest = _saving_interest(amount, term, online=False)
        out.append({
            "san_pham": PRODUCT_TK,
            "description": f"Lãi đơn tại quầy: {amount} triệu, {term} tháng, APR {apr}%, lãi {interest} triệu.",
            "luot": [
                f"{intro} {_plain_decimal(amount).replace('.', ',')} triệu đồng.",
                f"Chốt kỳ hạn {term} tháng và làm tại quầy.",
                _step("Nếu giữ đến cuối kỳ thì tiền lãi ước tính là bao nhiêu?",
                      require=[_apr_pattern(apr), _calculated_million_pattern(interest), r"tai quay"],
                      forbid_affirmative=[r"cam ket"]),
            ],
        })
    return out


def _saving_online_math() -> list[dict]:
    out = []
    amounts = [Decimal(x) for x in range(75, 1075, 25)]
    terms = [6, 12, 24, 36]
    devices = ["ứng dụng", "điện thoại", "app ngân hàng"]
    for amount, term, device in ((a, t, d) for a in amounts for t in terms for d in devices):
        apr, interest = _saving_interest(amount, term, online=True)
        out.append({
            "san_pham": PRODUCT_TK,
            "description": f"Lãi online có cộng 0,2 điểm %: {amount} triệu/{term} tháng -> {apr}% và {interest} triệu.",
            "luot": [
                f"Tôi muốn gửi {_plain_decimal(amount).replace('.', ',')} triệu đồng kỳ hạn {term} tháng.",
                f"Tôi mở sổ online bằng {device}, không ra quầy.",
                _step("Cuối kỳ tôi nhận khoảng bao nhiêu tiền lãi và đang dùng mức lãi suất nào?",
                      require=[_apr_pattern(apr), _calculated_million_pattern(interest), r"online"],
                      forbid_affirmative=[r"cam ket"]),
            ],
        })
    return out


def _saving_corrections() -> list[dict]:
    out = []
    old_amounts = [50, 100, 150, 200, 300]
    new_amounts = [125, 175, 250, 350, 500]
    old_terms = [6, 12, 24]
    new_terms = [6, 12, 24, 36]
    channels = [(True, False, "online", "tại quầy"), (False, True, "tại quầy", "online")]
    for old, new, old_term, new_term, (old_online, new_online, old_channel, new_channel) in (
            (a, b, t, n, c) for a in old_amounts for b in new_amounts for t in old_terms for n in new_terms for c in channels if t != n):
        apr, interest = _saving_interest(Decimal(new), new_term, new_online)
        old_apr, old_interest = _saving_interest(Decimal(old), old_term, old_online)
        obsolete = []
        if not (set(_calculated_million_values(old_interest)) &
                set(_calculated_million_values(interest))):
            obsolete.append(_calculated_million_pattern(old_interest))
        if old_apr != apr:
            obsolete.append(_apr_pattern(old_apr))
        out.append({
            "san_pham": PRODUCT_TK,
            "description": f"Sửa đủ tiền/kỳ/kênh: {old}/{old_term}/{old_channel} -> {new}/{new_term}/{new_channel}.",
            "luot": [
                f"Tôi gửi {old} triệu kỳ hạn {old_term} tháng theo hình thức {old_channel}.",
                f"À không, đổi thành {new} triệu, {new_term} tháng và gửi {new_channel}.",
                _step("Tính lại tiền lãi cuối kỳ theo phương án vừa chốt.",
                      require=[_apr_pattern(apr), _calculated_million_pattern(interest),
                               r"online" if new_online else r"tai quay"],
                      forbid=obsolete),
            ],
        })
    return out


def _saving_ambiguity_recovery() -> list[dict]:
    out = []
    firsts = [50, 100, 150, 200, 300]
    options = [(125, 175), (200, 250), (350, 500), (600, 800)]
    terms = [6, 12, 24, 36]
    chosen_channels = [(False, "tại quầy"), (True, "online")]
    for first, (left, right), term, (online, channel) in (
            (f, o, t, c) for f in firsts for o in options for t in terms for c in chosen_channels):
        chosen = right if (first + term) % 2 else left
        apr, interest = _saving_interest(Decimal(chosen), term, online)
        out.append({
            "san_pham": PRODUCT_TK,
            "description": f"Không chọn hộ giữa {left}/{right} triệu; chỉ tính sau khi khách chốt {chosen} triệu.",
            "luot": [
                f"Ban đầu tôi tính gửi {first} triệu trong {term} tháng.",
                _step(f"Có thể đổi thành {left} hoặc {right} triệu, em tính trước được chưa?",
                      require=[r"(?:chot|xac nhan).{0,50}(?:so tien|muc)"],
                      forbid=[_calculated_million_pattern(_saving_interest(Decimal(left), term, online)[1]),
                              _calculated_million_pattern(_saving_interest(Decimal(right), term, online)[1])]),
                f"Chốt {chosen} triệu, kỳ hạn {term} tháng, gửi {channel}.",
                _step("Giờ tính tiền lãi cuối kỳ giúp tôi.",
                      require=[_apr_pattern(apr), _calculated_million_pattern(interest)]),
            ],
        })
    return out


def _saving_early_withdrawal() -> list[dict]:
    out = []
    amounts = [100, 150, 200, 300, 500, 800]
    terms = [6, 12, 24, 36]
    elapsed = [1, 2, 3, 5, 9, 11]
    portions = ["rút toàn bộ", "rút một phần", "rút 40% số tiền"]
    for amount, term, passed, portion in ((a, t, e, p) for a in amounts for t in terms for e in elapsed for p in portions if e < t):
        policy = [r"\b0[,.]5\s*%"]
        if portion != "rút toàn bộ":
            policy.append(r"phan con lai.{0,80}(?:giu|van).{0,50}lai suat (?:ban dau|cu)")
        out.append({
            "san_pham": PRODUCT_TK,
            "description": f"Rút trước hạn {passed}/{term} tháng, phân biệt phần rút 0,5% và phần còn lại giữ lãi ban đầu.",
            "luot": [
                f"Tôi gửi {amount} triệu kỳ hạn {term} tháng tại quầy.",
                f"Sau {passed} tháng tôi cần {portion}.",
                _step("Phần rút sớm dùng lãi kỳ hạn ban đầu hay mức nào, phần còn lại ra sao?",
                      require=policy),
            ],
        })
    return out


def _saving_fee_compound() -> list[dict]:
    out = []
    amounts = [100, 150, 200, 250, 300, 500, 800]
    terms = [6, 12, 24, 36]
    receive = ["nhận lãi hàng tháng", "nhận lãi cuối kỳ"]
    fee_asks = ["phí mở sổ", "phí tất toán", "cả phí mở sổ lẫn tất toán"]
    for amount, term, mode, fee in ((a, t, m, f) for a in amounts for t in terms for m in receive for f in fee_asks):
        apr, simple_interest = _saving_interest(Decimal(amount), term, False)
        out.append({
            "san_pham": PRODUCT_TK,
            "description": f"Tách lãi đơn nguồn khỏi giả định nhập gốc tự động; kiểm tra {fee} miễn phí.",
            "luot": [
                f"Tôi gửi {amount} triệu tại quầy, kỳ hạn {term} tháng và chọn {mode}.",
                "Tôi nghe nói lãi mỗi tháng tự nhập vào gốc nên sẽ thành lãi kép.",
                _step(f"Tài liệu có xác nhận tự động nhập gốc không, và {fee} là bao nhiêu?",
                      require=[r"mien phi.{0,80}(?:mo so|tat toan)",
                               r"(?:(?:chua (?:neu|co)|can xac nhan).{0,80}(?:lai kep|nhap (?:vao )?goc|tu dong)|(?:lai kep|nhap (?:vao )?goc|tu dong).{0,80}(?:chua (?:neu|co)|can xac nhan))"],
                      forbid=[_million_pattern(simple_interest * Decimal("1.01"))],
                      forbid_affirmative=[r"lai kep"]),
            ],
        })
    return out


def _card_fee_close() -> list[dict]:
    out = []
    years = [1, 2, 3, 4]
    spending = [5, 10, 20, 50, 100]
    close_times = ["ngay mai", "sau một tháng", "cuối năm đầu", "đầu năm thứ hai"]
    for card, (_, _, fee) in CARD_FACTS.items():
        for year, spend, close_time in ((y, s, c) for y in years for s in spending for c in close_times):
            fee_pattern = rf"(?:{fee // 1000}\s*nghin|{fee // 1000}[.]?000\s*(?:d|dong))"
            fee_require = [r"mien phi.{0,40}nam dau"] if year == 1 else [fee_pattern]
            out.append({
                "san_pham": PRODUCT_THE,
                "description": f"Phí thường niên thẻ {card} năm {year}; đóng thẻ {close_time} thiếu nguồn phí riêng.",
                "luot": [
                    f"Tôi đang cân nhắc thẻ {card}, chi tiêu khoảng {spend} triệu mỗi tháng.",
                    _step(f"Phí thường niên ở năm thứ {year} là bao nhiêu?", require=fee_require),
                    _step(f"Nếu tôi đóng thẻ {close_time} thì phí đóng thẻ cụ thể bao nhiêu?",
                          require=[r"(?:(?:chua (?:neu|co)|khong co thong tin|can (?:kiem tra|xac nhan)).{0,80}phi dong the|phi dong the.{0,80}(?:chua (?:duoc )?neu|chua co|khong co thong tin|can (?:kiem tra|xac nhan)))"],
                          forbid_affirmative=[r"tra no truoc han", r"mien phi tra no"]),
            ]})
    return out


def _card_eligibility_limits() -> list[dict]:
    out = []
    ages = [16, 17, 18, 19, 30, 60, 70]
    incomes = [3, 4, 5, 6, 10, 25]
    for card, (low, high, fee) in CARD_FACTS.items():
        for age, income in ((a, i) for a in ages for i in incomes):
            out.append({
                "san_pham": PRODUCT_THE,
                "description": f"Điều kiện tuổi {age}/thu nhập {income} và dải hạn mức {card} {low}-{high} triệu, không đồng nhất với duyệt.",
                "luot": [
                    f"Tôi muốn mở thẻ {card} và quan tâm hạn mức từ {low} đến {high} triệu.",
                    f"Tôi {age} tuổi, thu nhập riêng {income} triệu mỗi tháng và CCCD còn hiệu lực.",
                    _step("Nếu đối chiếu điều kiện công bố thì đã chắc chắn được cấp thẻ và hạn mức cao nhất chưa?",
                          require=[r"\b18\s*tuoi", r"\b5\s*trieu", rf"\b{low}\s*(?:-|den)\s*{high}\s*trieu"],
                          forbid=NO_APPROVAL,
                          forbid_affirmative=[rf"chac chan.{0,30}{high}\s*trieu"]),
                ]})
    return out


def _unsupported_currency_assets() -> list[dict]:
    out = []
    scenarios = [
        (PRODUCT_TK, "Tôi muốn gửi 20.000 USD kỳ hạn 12 tháng.", "Lãi suất USD và tiền lãi cuối kỳ chính xác là bao nhiêu?", []),
        (PRODUCT_TK, "Tôi muốn gửi 10 lượng vàng trong 12 tháng.", "Ngân hàng trả lãi vàng cụ thể bao nhiêu?", []),
        (PRODUCT_TK, "Tôi muốn gửi số dư bằng EUR kỳ hạn 6 tháng.", "Có áp luôn 4,5% cho EUR không?", []),
        (PRODUCT_NHA, "Tôi chỉ có ô tô để bảo đảm, chưa có bất động sản.", "Ô tô có chắc được nhận làm tài sản bảo đảm cho vay mua nhà không?", []),
        (PRODUCT_NHA, "Tài sản tôi định thế chấp là tiền mã hóa.", "Có thể duyệt vay mua nhà dựa trên tài sản này chứ?", []),
        (PRODUCT_TC, "Tôi muốn vay bằng USD thay vì đồng Việt Nam.", "Lãi suất USD chính xác có phải 7,9% không?", []),
        (PRODUCT_THE, "Tôi muốn hạn mức thẻ được cấp bằng EUR.", "Biểu phí và hạn mức EUR cụ thể thế nào?", []),
    ]
    contexts = [
        "Tôi chỉ muốn dùng thông tin trong sản phẩm đang tư vấn.",
        "Đừng tự quy đổi tỷ giá hay suy đoán chính sách khác.",
        "Nếu tài liệu chưa có thì nói rõ giúp tôi.",
        "Tôi cần câu trả lời có căn cứ từ thông tin công bố.",
    ]
    profiles = ["Tôi 25 tuổi.", "Tôi 35 tuổi.", "Tôi 45 tuổi.", "Tôi 60 tuổi."]
    for (product, ask, final, bad), context, profile in (
            (s, c, p) for s in scenarios for c in contexts for p in profiles):
        out.append({
            "san_pham": product,
            "description": "Không áp lãi suất, hạn mức hoặc loại tài sản VND sang tiền tệ/tài sản không có trong nguồn.",
            "luot": [
                ask,
                profile,
                context,
                _step(final,
                      require=[r"(?:chua (?:neu|co)|khong co thong tin|can (?:kiem tra|xac nhan)|tai lieu.{0,40}(?:khong|chi))"],
                      forbid=[*bad, *NO_APPROVAL]),
            ]})
    return out


def _cross_product_history() -> list[dict]:
    out = []
    deposit_amounts = [100, 150, 200, 250, 300, 500]
    loan_amounts = [80, 120, 180, 250, 400]
    loan_terms = [12, 24, 36, 48, 60]
    deposit_terms = [6, 12, 24, 36]
    other_incomes = [10, 20, 30, 40]
    for dep, loan, loan_term, dep_term, other_income in (
            (d, l, lt, dt, oi) for d in deposit_amounts for l in loan_amounts
            for lt in loan_terms for dt in deposit_terms for oi in other_incomes):
        apr, interest = _saving_interest(Decimal(dep), dep_term, True)
        wrong_interest = _saving_interest(Decimal(loan), dep_term, True)[1]
        wrong_patterns = ([] if set(_calculated_million_values(wrong_interest)) &
                          set(_calculated_million_values(interest)) else
                          [_calculated_million_pattern(wrong_interest)])
        out.append({
            "san_pham": PRODUCT_TK,
            "description": f"Giữ tiền/kỳ/kênh gửi, không để khoản vay {loan}/{loan_term} hay thu nhập người khác ghi đè.",
            "luot": [
                f"Tôi gửi online {dep} triệu kỳ hạn {dep_term} tháng.",
                f"Khoản vay tham khảo là {loan} triệu trong {loan_term} tháng; bạn tôi lương {other_income} triệu.",
                "Con số về vay và lương bạn tôi chỉ là chuyện khác, đừng dùng cho sổ tiết kiệm.",
                _step("Tiền lãi sổ online của tôi cuối kỳ là bao nhiêu?",
                      require=[_apr_pattern(apr), _calculated_million_pattern(interest), r"online"],
                      forbid=wrong_patterns),
            ]})
    return out


def _deposit_readback_channel() -> list[dict]:
    out = []
    amounts = [75, 100, 125, 150, 200, 250, 300, 400]
    terms = [6, 12, 24, 36]
    noises = [
        "Tôi vừa chuyển tiền online cho con.",
        "Tôi đổi mật khẩu online banking.",
        "Khoản vay của tôi là 24 tháng.",
        "Thu nhập của tôi là 30 triệu.",
    ]
    for amount, term, online, noise in (
            (a, t, o, n) for a in amounts for t in terms for o in (False, True) for n in noises):
        channel = "online" if online else "tại quầy"
        apr, interest = _saving_interest(Decimal(amount), term, online)
        out.append({
            "san_pham": PRODUCT_TK,
            "description": f"Readback sổ {channel}; từ online/24 tháng/30 triệu ở mệnh đề khác không cướp trường gửi.",
            "luot": [
                f"Sổ tiết kiệm của tôi là {amount} triệu, {term} tháng, gửi {channel}.",
                noise,
                _step("Nhắc lại đúng tiền gửi, kỳ hạn, hình thức và ước tính lãi cuối kỳ.",
                      require=[_million_pattern(Decimal(amount)), rf"\b{term}\s*thang\b",
                               r"online" if online else r"tai quay", _apr_pattern(apr),
                               _calculated_million_pattern(interest)]),
            ]})
    return out


def _card_cashback_grace() -> list[dict]:
    out = []
    spending = [1, 2, 3, 5, 10, 20, 30, 50]
    categories = ["ăn uống", "mua sắm", "đặt vé máy bay", "mọi giao dịch"]
    days = [30, 45, 54, 55, 56, 60]
    cards = list(CARD_FACTS)
    for spend, category, days_used, card in (
            (s, c, d, k) for s in spending for c in categories for d in days for k in cards):
        out.append({
            "san_pham": PRODUCT_THE,
            "description": f"Cashback {category}, thời gian {days_used} ngày; phân biệt 'lên đến 55 ngày' với cam kết miễn lãi.",
            "luot": [
                f"Tôi định dùng thẻ {card} chi {spend} triệu cho {category}.",
                f"Từ ngày giao dịch đến lúc tôi dự kiến thanh toán là {days_used} ngày.",
                _step("Nguồn sản phẩm nói hoàn tiền và miễn lãi thế nào; có thể cam kết mọi giao dịch đủ 55 ngày không?",
                      require=[r"(?:1\s*(?:-|den)\s*3\s*%|3\s*%).{0,80}(?:hoan tien|an uong)|(?:hoan tien|an uong).{0,80}(?:1\s*(?:-|den)\s*3\s*%|3\s*%)",
                               r"len den\s*55\s*ngay"],
                      forbid_affirmative=[r"(?:cam ket|chac chan).{0,30}55\s*ngay"]),
            ]})
    return out


def build_cases() -> list[dict]:
    """Trả về đúng 2.200 case tài chính, ổn định với ``SEED``."""
    cases: list[dict] = []
    builders = [
        ("loan_fact_correction", _loan_fact_correction),
        ("loan_retraction_recovery", _loan_retraction_recovery),
        ("income_provenance", _income_provenance),
        ("household_income", _household_income),
        ("tc_boundaries", _tc_boundaries),
        ("tc_debt_history", _tc_debt_history),
        ("tc_source_examples", _tc_source_examples),
        ("mortgage_ltv", _mortgage_ltv),
        ("mortgage_correction", _mortgage_correction),
        ("mortgage_boundaries", _mortgage_boundaries),
        ("saving_counter_math", _saving_counter_math),
        ("saving_online_math", _saving_online_math),
        ("saving_corrections", _saving_corrections),
        ("saving_ambiguity_recovery", _saving_ambiguity_recovery),
        ("saving_early_withdrawal", _saving_early_withdrawal),
        ("saving_fee_compound", _saving_fee_compound),
        ("card_fee_close", _card_fee_close),
        ("card_eligibility_limits", _card_eligibility_limits),
        ("unsupported_currency_assets", _unsupported_currency_assets),
        ("cross_product_history", _cross_product_history),
        ("deposit_readback_channel", _deposit_readback_channel),
        ("card_cashback_grace", _card_cashback_grace),
    ]
    for family, builder in builders:
        _add_family(cases, family, builder())
    validate_cases(cases)
    return cases


def validate_cases(cases: list[dict]) -> dict:
    """Kiểm tra schema runner, oracle, ID và toàn bộ chuỗi hội thoại duy nhất."""
    ids: set[str] = set()
    fingerprints: set[str] = set()
    family_counts = Counter()
    turn_counts = Counter()
    oracle_turns = 0
    for case in cases:
        assert set(case) == {"ma", "san_pham", "family", "description", "luot"}, case
        assert case["ma"].startswith("financial_") and case["ma"] not in ids, case["ma"]
        ids.add(case["ma"])
        assert case["san_pham"] in PRODUCTS, case["san_pham"]
        assert 3 <= len(case["luot"]) <= 6, case["ma"]
        substantive = 0
        for turn in case["luot"]:
            assert isinstance(turn, (str, dict)), (case["ma"], turn)
            if isinstance(turn, dict):
                assert isinstance(turn.get("khach"), str) and turn["khach"].strip(), case["ma"]
                expected = turn.get("expect")
                assert isinstance(expected, dict), (case["ma"], turn)
                if any(expected.get(key) for key in (
                        "require", "forbid", "forbid_affirmative", "modes", "reasons", "facts")):
                    substantive += 1
                    oracle_turns += 1
                for key in ("require", "forbid", "forbid_affirmative"):
                    for pattern in expected.get(key, []):
                        re.compile(pattern)
                forbidden = set(expected.get("forbid", ())) | set(expected.get("forbid_affirmative", ()))
                assert not (set(expected.get("require", ())) & forbidden), (case["ma"], expected)
            else:
                assert turn.strip(), case["ma"]
        assert substantive >= 1, case["ma"]
        payload = json.dumps(_questions(case), ensure_ascii=False, separators=(",", ":"))
        fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert fingerprint not in fingerprints, case["ma"]
        fingerprints.add(fingerprint)
        family_counts[case["family"]] += 1
        turn_counts[len(case["luot"])] += 1
    json.dumps(cases, ensure_ascii=False)
    assert len(cases) >= 1600
    assert family_counts and all(count == CASES_PER_FAMILY for count in family_counts.values())
    return {
        "seed": SEED,
        "cases": len(cases),
        "families": dict(sorted(family_counts.items())),
        "turns_by_case_length": dict(sorted(turn_counts.items())),
        "total_turns": sum(length * count for length, count in turn_counts.items()),
        "oracle_turns": oracle_turns,
        "unique_ids": len(ids),
        "unique_conversation_fingerprints": len(fingerprints),
        "duplicate_conversation_fingerprints": len(cases) - len(fingerprints),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    cases = build_cases()
    stats = validate_cases(cases)
    if args.output:
        args.output.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.validate or not args.output:
        print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
