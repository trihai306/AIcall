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
import contextlib
import contextvars
import re
import unicodedata


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


_DIGIT = dict(zip("không một hai ba bốn năm sáu bảy tám chín".split(), range(10)))
_DIGIT.update({"mốt": 1, "tư": 4, "lăm": 5})
_SCALE = {"nghìn": 1000, "ngàn": 1000, "triệu": 10**6, "tr": 10**6,
          "tỷ": 10**9, "tỉ": 10**9}
# Cách nói miệng của đơn vị tiền ("trăm củ", "hai trăm chai", "ba tỏi hai") và
# "triệu" nói ngọng. Bộ thử nói như người thường 10-10-2026: cả bốn đều bị hỏi
# lại "kèm đơn vị triệu hoặc tỷ" hoặc rơi xuống mô hình (nó bịa "Ba Đình II").
_SCALE.update({"củ": 10**6, "chai": 10**6, "chiệu": 10**6, "tỏi": 10**9})
_WORDS = set(_DIGIT) | {"trăm", "mươi", "mười", "chục", "linh", "lẻ", "phẩy", "nửa"}
# Chỉ là chữ số HÀNG ĐƠN VỊ của số ghép ("hai tư", "bốn lăm", "hai mốt"), không
# bao giờ mở đầu một con số: "tư vấn" từng bị đọc thành số 4 rồi AI hỏi "anh chị
# vừa nói tư, số tiền này tính theo triệu hay tỷ".
_DON_VI_LE = ("mốt", "tư", "lăm")
# Đứng trước "trăm / chục / triệu..." thì cụm đó là lời HỎI hoặc nói phỏng chừng
# ("mấy trăm triệu", "bao nhiêu triệu", "bảy mươi phần trăm"), không phải con số.
_MO_HO_TRUOC = frozenset({"mấy", "vài", "nhiều", "dăm", "hàng", "nhiêu", "phần", "bao"})
# "năm" đứng một mình sau các chữ này là NĂM (thời gian), không phải số 5: "cố
# định mấy năm" từng thành "anh chị vừa nói năm, triệu hay tỷ".
_TRUOC_NAM_LA_THOI_GIAN = frozenset({
    "mấy", "nhiêu", "vài", "nhiều", "hàng", "hằng", "mỗi", "cả", "từng", "các",
    "những", "đầu", "cuối", "quanh", "sang", "theo", "nửa", "trong", "sau", "trước"})
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
    if words[0] in ("trăm", "chục"):
        # "trăm rưỡi", "trăm hai", "chục triệu": ngầm có "một" đứng trước.
        words = ["một"] + words
    if len(words) == 2 and words[0] in _DIGIT and words[1] in _DIGIT:
        a, b = _DIGIT[words[0]], _DIGIT[words[1]]
        # "lăm / mốt / tư" chỉ có thể là hàng đơn vị: "bốn lăm tháng" là 45
        # tháng, "hai lăm triệu" là 25 triệu - không có cách hiểu nào khác, nhận
        # cho cả tiền lẫn kỳ hạn. Cặp chữ số thường ("ba sáu") thì chỉ kỳ hạn.
        if 2 <= a <= 9 and words[0] not in _DON_VI_LE and (
                words[1] in _DON_VI_LE or (duration and b in (2, 4, 6, 8))):
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
    # Ngay sau "X trăm" mà không có "linh/lẻ": chữ số kế là hàng CHỤC theo cách
    # nói miệng - "ba trăm tư" = 340, "hai trăm hai" = 220. 202 thì luôn được
    # nói "hai trăm linh/lẻ hai".
    sau_tram = False
    if len(words) >= 2 and words[0] in _DIGIT and words[1] == "trăm":
        total = _DIGIT[words[0]] * 100
        words = words[2:]
        sau_tram = True
        if words and words[0] in ("linh", "lẻ"):
            words = words[1:]
            sau_tram = False
    if not words:
        return Decimal(total)
    if words[0] == "mười":
        total += 10
        words = words[1:]
        sau_tram = False
    elif len(words) >= 2 and words[0] in _DIGIT and words[1] in ("mươi", "chục"):
        total += _DIGIT[words[0]] * 10
        words = words[2:]
        sau_tram = False
    if not words:
        return Decimal(total)
    if len(words) == 1 and words[0] in _DIGIT:
        chu_so = _DIGIT[words[0]]
        return Decimal(total + (chu_so * 10 if sau_tram and chu_so else chu_so))
    return None


def _number(words: list[str], duration: bool = False) -> tuple[Decimal | None, bool]:
    """Coefficients + descending scales, kèm các cách nói miệng:

      "một tỷ rưỡi" = 1,5 tỷ          "ba trăm rưỡi" = 350       "hai chục rưỡi" = 25
      "một tỷ hai"  = 1,2 tỷ          "hai triệu ba" = 2,3 triệu
      "một tỷ hai trăm" = 1,2 tỷ      (đơn vị con ngầm hiểu là bậc kế dưới)
    """
    total, previous_scale, part = Decimal(0), float("inf"), []
    has_scale = False
    them = Decimal(0)                 # phần "rưỡi" khi CHƯA có đơn vị
    for w in words:
        if w == "rưỡi":
            if has_scale and not part:
                total += Decimal(previous_scale) / 2
                continue
            if has_scale or not part or them:
                return None, has_scale
            if part[-1] == "trăm":
                them = Decimal(50)
            elif part[-1] == "chục":
                them = Decimal(5)
            elif len(part) == 1 and part[0] in _DIGIT and part[0] not in _DON_VI_LE:
                them = Decimal("0.5")
            else:
                return None, has_scale
            continue
        if them:
            return None, has_scale    # sau "rưỡi" không còn chữ số hay đơn vị
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
        if has_scale:
            # Đuôi sau đơn vị, không kèm đơn vị riêng. Một chữ số = phần mười
            # của đơn vị vừa nói; "X trăm ..." = bậc đơn vị kế dưới.
            if len(part) == 1 and _DIGIT.get(part[0]):
                return total + Decimal(_DIGIT[part[0]]) * Decimal(previous_scale) / 10, True
            if "trăm" in part and previous_scale >= 1000:
                con = _small(part)
                if con is not None and con < 1000:
                    return total + con * Decimal(previous_scale) / 1000, True
            return None, True
        value = _small(part, duration)
        return (value + them if value is not None else None), False
    return (total, True) if has_scale else (None, False)


@dataclass(frozen=True)
class Quantity:
    raw: str
    start: int
    end: int
    value: Decimal | None
    kind: str                    # money, duration (months), bare, other


_LONG_TIEN = re.compile(
    r"\b((?:\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mươi|trăm|chục|rưỡi|lăm|tư|mốt|mấy|vài)"
    r"\s+)(củ|chai|chiệu|tỏi)\b", re.IGNORECASE)


def doc_lai_tien_long(text: str) -> str:
    """ "trăm củ" -> "trăm triệu", "ba tỏi hai" -> "ba tỷ hai": chữ chuẩn cho mô hình đọc.

    Tầng luật tự hiểu các chữ này (`_SCALE`), còn mô hình và bộ chọn kho thì
    không: bộ thử 10-10-2026 "mua căn chung cư ba tỏi hai" được đáp "căn chung
    cư Ba Đình II ạ?". Chỉ đổi khi chữ lóng đứng ngay sau một con số.
    """
    return _LONG_TIEN.sub(
        lambda m: m.group(1) + ("tỷ" if m.group(2).lower() == "tỏi" else "triệu"), text or "")


def _tach_doi(words: list[str]) -> tuple[int, Decimal, Decimal, Decimal] | None:
    """Hai con số LIỀN NHAU nói phỏng chừng: "mười lăm mười sáu", "chín mười triệu".

    Trả `(vị trí cắt, số đầu, số sau, đơn vị)` khi hai nửa đều đọc được và là hai
    số liên tiếp; không thì None (cả cụm vẫn là một con số không đọc được).
    """
    don_vi = Decimal(1)
    loi = words
    if words and words[-1] in _SCALE and not any(w in _SCALE for w in words[:-1]):
        don_vi, loi = Decimal(_SCALE[words[-1]]), words[:-1]
    if any(w in _SCALE or w == "rưỡi" for w in loi):
        return None
    for k in range(1, len(loi)):
        dau, sau = _small(loi[:k]), _small(loi[k:])
        if dau is not None and sau is not None and dau >= 1 and sau == dau + 1:
            return k, dau, sau, don_vi
    return None


_ASCII_SO = {
    "mot": "một", "bon": "bốn", "nam": "năm", "sau": "sáu",
    "bay": "bảy", "tam": "tám", "chin": "chín", "muoi": "mười",
    "tram": "trăm", "chuc": "chục", "trieu": "triệu", "ty": "tỷ",
    "ti": "tỉ", "nghin": "nghìn", "ngan": "ngàn", "thang": "tháng",
}
_ASCII_DON_VI_THOI_GIAN = frozenset({"thang"})
_ASCII_THANG_SO = frozenset({"trieu", "ty", "ti", "nghin", "ngan"})
_ASCII_CHI_THOI_GIAN = frozenset({"nay", "này", "toi", "tới", "sau"})


def _token_co_the_la_so(word: str) -> bool:
    return bool(word[:1].isdigit() or word in _DIGIT or word in _ASCII_SO
                or word in {"mười", "mươi", "trăm", "chục", "linh", "lẻ", "rưỡi"})


def chuan_hoa_so_khong_dau(text: str) -> str:
    """Restore accents only inside a local ASCII numeric expression.

    The returned NFC lowercase text has exactly the same length as the input,
    so offsets still address the original utterance. Ordinary prose stays
    untouched: ``sau khi``, ``trong nam nay`` and ``qua ngan hang`` are not
    turned into six, five, or a thousand.
    """
    source = unicodedata.normalize("NFC", (text or "").lower())
    tokens = list(_TOKEN.finditer(source))
    words = [token.group() for token in tokens]
    replacements: dict[int, str] = {}
    for i, word in enumerate(words):
        replacement = _ASCII_SO.get(word)
        if not replacement:
            continue
        before = words[i - 1] if i else ""
        after = words[i + 1] if i + 1 < len(words) else ""
        if word == "muoi":
            # ASCII mất phân biệt "mười" và "mươi": sau chữ số hàng chục
            # (hai muoi, ba muoi...) phải là "mươi"; ở đầu cụm vẫn là "mười".
            chu_so_truoc = _DIGIT.get(_ASCII_SO.get(before, before))
            if chu_so_truoc is not None and 2 <= chu_so_truoc <= 9:
                replacement = "mươi"
        if word == "sau":
            # "sau thang" is six months, while "năm sau" and "sau một
            # năm" or "sau thang nay/toi/sau" use the ordinary preposition /
            # adverb and must stay intact.
            chi_thoi_gian = (after == "thang" and i + 2 < len(words)
                             and words[i + 2] in _ASCII_CHI_THOI_GIAN)
            numeric_context = (not chi_thoi_gian and after in (
                _ASCII_DON_VI_THOI_GIAN | _ASCII_THANG_SO | {"muoi", "tram", "chuc"}))
        elif word in _ASCII_DON_VI_THOI_GIAN:
            chi_thoi_gian = (before == "sau" and after in _ASCII_CHI_THOI_GIAN)
            numeric_context = not chi_thoi_gian and _token_co_the_la_so(before)
        elif word in _ASCII_THANG_SO:
            numeric_context = _token_co_the_la_so(before) or _token_co_the_la_so(after)
        else:
            numeric_context = (_token_co_the_la_so(before) or _token_co_the_la_so(after)
                               or after in _ASCII_DON_VI_THOI_GIAN)
        if numeric_context:
            replacements[i] = replacement
    if not replacements:
        return source
    pieces: list[str] = []
    cursor = 0
    for i, token in enumerate(tokens):
        pieces.append(source[cursor:token.start()])
        pieces.append(replacements.get(i, token.group()))
        cursor = token.end()
    pieces.append(source[cursor:])
    normalized = "".join(pieces)
    assert len(normalized) == len(source)
    return normalized


def quantities(text: str) -> list[Quantity]:
    raw_text = unicodedata.normalize("NFC", text.lower())
    text = chuan_hoa_so_khong_dau(raw_text)
    tokens = list(_TOKEN.finditer(text))
    result: list[Quantity] = []
    i = 0
    while i < len(tokens):
        w = tokens[i].group()
        truoc = tokens[i - 1].group() if i else ""
        sau = tokens[i + 1].group() if i + 1 < len(tokens) else ""
        an_mot = False                # "trăm rưỡi", "tỷ hai": ngầm "một" đứng trước
        if w in ("trăm", "chục"):
            hop = sau == "rưỡi" or sau in _SCALE or (
                w == "trăm" and (bool(_DIGIT.get(sau)) or sau in ("linh", "lẻ")))
            if truoc in _MO_HO_TRUOC or not hop:
                i += 1
                continue
            an_mot = True
        elif w in _SCALE:
            if truoc in ("nhiêu", "mấy", "phần"):
                i += 1                # "bao nhiêu triệu", "mấy tỷ": lời hỏi
                continue
            an_mot = (sau == "rưỡi" or bool(_DIGIT.get(sau))) and truoc not in _MO_HO_TRUOC
        elif (w not in _DIGIT and w not in {"mười", "nửa"} and not w[0].isdigit()) \
                or w in _DON_VI_LE:
            i += 1
            continue
        elif w == "không" and (sau in _DIGIT or sau in ("mười", "trăm", "chục")):
            # "à KHÔNG hai trăm triệu": lời gạt đi trước con số, không phải chữ số
            # 0 dính vào nó. Chỉ giữ khi là dãy chữ số rời (đọc số điện thoại).
            sau_nua = tokens[i + 2].group() if i + 2 < len(tokens) else ""
            if not (sau in _DIGIT and sau_nua in _DIGIT):
                i += 1
                continue
        j = i + 1
        while j < len(tokens) and (tokens[j].group() in _WORDS | set(_SCALE) | {"rưỡi"}
                                  or tokens[j].group()[0].isdigit()):
            if tokens[j].group() == "không" and j + 1 < len(tokens) and tokens[j + 1].group() == "phải":
                break  # negation starts another clause, not a trailing zero
            # "vay bốn trăm triệu KHÔNG": chữ "không" kết câu là lời HỎI, không
            # phải chữ số 0 dính vào con số. Chỉ là chữ số khi còn con số theo sau
            # ("hai không năm"). Gặp 7 lần trong các cuộc gọi thật đã lưu, lần nào
            # AI cũng đòi "nhắc lại giúp em số tiền".
            if tokens[j].group() == "không":
                ke = tokens[j + 1].group() if j + 1 < len(tokens) else ""
                if not (ke in _WORDS or ke in _SCALE or ke[:1].isdigit()) or ke == "không":
                    break
            j += 1
        words = [m.group() for m in tokens[i:j]]
        following = tokens[j].group() if j < len(tokens) else ""
        # "lương hai chục MỘT THÁNG", "mười lăm MỘT THÁNG": "một tháng" là tần
        # suất, không phải chữ số cuối của con số ("hai chục một" không ai nói
        # cho 21). Từng bị đọc thành kỳ hạn 21 tháng.
        if (following == "tháng" and len(words) >= 2 and words[-1] == "một"
                and not any(x in _SCALE for x in words)
                and (words[-2] == "chục" or (_small(words) is None
                                            and _small(words[:-1]) is not None))):
            j -= 1
            words, following = words[:-1], ""
        scales = [k for k, word in enumerate(words) if word in _SCALE]
        if scales and scales[-1] < len(words) - 1 and (
                following in ("tháng", "tuổi", "ngày", "giờ", "phút") or words[-1] == "năm"):
            # '18 triệu một tháng' is money followed by frequency, not a
            # mixed-scale monetary value or one malformed duration.
            j = i + scales[-1] + 1
            words, following = words[:scales[-1] + 1], ""
        if an_mot:
            words = ["một"] + words
        # "năm rưỡi", "hai năm rưỡi": một năm rưỡi / hai năm rưỡi (kỳ hạn).
        if (len(words) >= 2 and words[-1] == "rưỡi" and words[-2] == "năm"
                and not scales and following not in _SCALE):
            he_so = _small(words[:-2]) if len(words) > 2 else Decimal(1)
            if he_so is not None:
                result.append(Quantity(raw_text[tokens[i].start():tokens[j - 1].end()],
                                       tokens[i].start(), tokens[j - 1].end(),
                                       (he_so + Decimal("0.5")) * 12, "duration"))
                i = j
                continue
        kind = "bare"
        multiplier = 1
        if (words == ["một"] and following == "tháng" and not an_mot
                and truoc in ("ít", "nhẹ", "nhiều", "nhiêu", "hơn")):
            # "muốn trả ÍT MỘT THÁNG", "đóng bao nhiêu một tháng": "một tháng" là
            # tần suất (mỗi tháng), không phải kỳ hạn 1 tháng. Từng làm "vay bảy
            # mươi hai tháng ... trả ít một tháng" thành hai kỳ hạn và AI hỏi lại
            # "bao nhiêu tháng hoặc năm" (bộ thử 304 lượt).
            kind = "other"
            j += 1
        elif following in ("tháng", "năm"):
            kind, multiplier = "duration", 12 if following == "năm" else 1
            j += 1
        elif following in _CURRENCY:
            kind = "money"
            j += 1
        elif following == "%" or following in ("tuổi", "ngày", "giờ", "phút"):
            kind = "other"
            j += 1
        elif (fold(following) in _DANH_TU_DEM_BO_DAU
              and len(words) == 1
              and (words[0] in _DIGIT or words[0][:1].isdigit())
              and not an_mot):
            kind = "other"
        elif following == "phần":
            # "bảy mươi phần trăm" là tỷ lệ, từng bị hỏi "bảy mươi, triệu hay tỷ".
            # Tai máy hay cắt cụt còn "bảy phẩy chín phần": vẫn là tỷ lệ.
            kind = "other"
            j += 2 if j + 1 < len(tokens) and tokens[j + 1].group() == "trăm" else 1
        # 'năm' is both a digit and the year unit. A terminal 'năm' after a
        # valid coefficient is a year only when no other explicit unit follows.
        elif len(words) > 1 and words[-1] == "năm" and _small(words[:-1]) is not None:
            words, kind, multiplier = words[:-1], "duration", 12
        value, scaled = _number(words, duration=(kind == "duration"))
        # Kỳ hạn không đọc được hoặc dài phi lý (trên 50 năm): thử coi phần ĐẦU là
        # số tiền, phần đuôi mới là kỳ hạn - "vậy hai trăm ba năm thì tháng trả
        # bao nhiêu" từng ra kỳ hạn 230 năm.
        if kind == "duration" and not scaled and not an_mot and (
                value is None or value * multiplier > 600):
            k_cat = next((k for k in range(len(words) - 1, 0, -1)
                          if (lambda dau, duoi: dau is not None and duoi is not None
                              and dau >= 10 and duoi * multiplier <= 600)(
                              _small(words[:k]), _small(words[k:], duration=True))), None)
            if k_cat:
                giua = tokens[i + k_cat - 1].end()
                result.append(Quantity(raw_text[tokens[i].start():giua], tokens[i].start(),
                                       giua, _small(words[:k_cat]), "bare"))
                dau_ky = tokens[i + k_cat].start()
                result.append(Quantity(raw_text[dau_ky:tokens[j - 1].end()], dau_ky,
                                       tokens[j - 1].end(),
                                       _small(words[k_cat:], duration=True) * multiplier,
                                       "duration"))
                i = j
                continue
        if scaled and kind == "bare":
            kind = "money"
        if value is not None:
            value *= multiplier
            if re.search(r"(?:\bâm|[-−])\s*$", text[:tokens[i].start()]):
                value = -abs(value)
        # 'năm' can be five or a calendar year. Calendar phrases are not
        # amounts, but 'vay năm' is an unresolved numeric update: dropping it
        # would incorrectly resurrect the previous principal.
        if words == ["năm"] and kind == "bare" and (following in (
                "nay", "ngoái", "tới", "sau", "trước", "đó", "này", "mới", "vừa", "rồi", "đầu")
                or truoc in _TRUOC_NAM_LA_THOI_GIAN):
            i = j
            continue
        doi = _tach_doi(words) if value is None and kind in ("bare", "money") else None
        if doi:
            k, dau, sau_so, don_vi = doi
            loai = "money" if don_vi != 1 or kind == "money" else "bare"
            k_tok = k - (1 if an_mot else 0)
            if 0 < k_tok < j - i:
                giua = tokens[i + k_tok - 1].end()
                result.append(Quantity(raw_text[tokens[i].start():giua], tokens[i].start(),
                                       giua, dau * don_vi, loai))
                result.append(Quantity(raw_text[tokens[i + k_tok].start():tokens[j - 1].end()],
                                       tokens[i + k_tok].start(), tokens[j - 1].end(),
                                       sau_so * don_vi, loai))
                i = j
                continue
        # Standalone 'không' without a unit is a negation, not numeric zero.
        if not (words == ["không"] and kind == "bare"):
            result.append(Quantity(raw_text[tokens[i].start():tokens[j - 1].end()],
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
    # Khách nêu một KHOẢNG kỳ hạn ("4-5 tháng", "vài tháng"): (ngắn, dài) theo
    # tháng. Vẫn là `ambiguous` - không đem tính trả góp - nhưng đủ để đáp khoảng
    # đó có nằm trong thời hạn của sản phẩm hay không.
    khoang: tuple[Decimal, Decimal] | None = None
    # Chỉ dùng cho thu nhập: "self" là riêng người gọi, "household" là tổng /
    # nhiều người trong hộ. Dữ kiện khác và thu nhập chưa rõ chủ thể để trống.
    owner: str = ""

    def evidence(self) -> dict:
        data = {"status": self.status, "value": str(self.value) if self.value is not None else None,
                "raw": self.raw, "turn": self.turn}
        if self.owner:
            data["owner"] = self.owner
        return data


@dataclass
class LoanState:
    amount: Fact = field(default_factory=Fact)
    term: Fact = field(default_factory=Fact)
    income: Fact = field(default_factory=Fact)
    amount_updated: bool = False
    term_updated: bool = False
    # Lượt này khách vừa nêu THU NHẬP (kể cả đáp cụt "mười lăm" cho câu AI hỏi).
    income_updated: bool = False
    unit_confirmed: bool = False
    # Lượt này khách GẬT với thời hạn AI vừa đề nghị - xem `_DE_NGHI_KY_HAN`.
    nhan_de_nghi: bool = False
    request: str = ""

    def evidence(self) -> dict:
        return {"amount": self.amount.evidence(), "term": self.term.evidence(),
                "income": self.income.evidence()}


# ---- Khoảng kỳ hạn -----------------------------------------------------------
# "4-5 tháng", "4 đến 5 tháng", "bốn năm tháng", "ba bốn năm", "vài tháng".
# Đo 09-10-2026 trên backend thật: "vay 4-5 tháng được không" bị đọc "4" thành
# SỐ TIỀN thiếu đơn vị ("tính theo triệu hay tỷ"), "năm sáu tháng" thành 56
# tháng, còn "khoảng 4 5 tháng" rơi xuống mô hình và nó đáp "nằm trong khung".
# KHÔNG có "lăm", "tư", "mốt": đó là chữ số HÀNG ĐƠN VỊ của một số ghép ("bốn lăm"
# = 45, "hai tư" = 24), không bao giờ là một con số đứng riêng. Từng để "lăm": 5
# ở đây và "vay bốn lăm tháng được không" bị đáp "vay 4 đến 5 tháng thì chưa
# được" (bộ thử nói như người thường 10-10-2026).
_CHU_SO_KY_HAN = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5,
                  "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10}
_NOI_RO = r"(?:\s*[-–—/]\s*|\s*,\s+|\s+(?:đến|tới|hay|hoặc)\s+)"
_MOT_CHU = "(?:" + "|".join(_CHU_SO_KY_HAN) + ")"
_KHOANG_SO = re.compile(
    r"(?<![\w.,])(\d{1,2})(" + _NOI_RO + r"|\s+)(\d{1,2})\s*(tháng|năm)(?!\w)")
_KHOANG_CHU = re.compile(
    r"(?<!\w)(" + _MOT_CHU + r")(" + _NOI_RO + r"|\s+)(" + _MOT_CHU + r")\s+(tháng|năm)(?!\w)")
_KHOANG_VAI = re.compile(r"(?<!\w)(?:vài ba|dăm ba|đôi ba|vài|dăm)\s+tháng(?!\w)")
# Đứng ngay sau một con số khác thì không phải khoảng: "một năm sáu tháng" là
# 18 tháng chứ không phải "năm, sáu tháng".
_SAU_CON_SO = re.compile(r"(?:\d|" + _MOT_CHU + r"|mươi|trăm|rưỡi|lăm|tư|mốt)\s*$")


def khoang_ky_han(text: str) -> tuple[int, int, Decimal, Decimal, str] | None:
    """`(đầu, cuối, ngắn, dài, cách đọc)` của khoảng kỳ hạn trong câu; ngắn/dài theo tháng.

    Hai số đứng liền KHÔNG có từ nối ("4 5 tháng", "bốn năm tháng") chỉ là
    khoảng khi chúng liên tiếp nhau - "hai bốn tháng" là 24 tháng.
    """
    text = unicodedata.normalize("NFC", (text or "").lower())
    for mau, doi in ((_KHOANG_SO, int), (_KHOANG_CHU, _CHU_SO_KY_HAN.get)):
        for m in mau.finditer(text):
            a, b = doi(m.group(1)), doi(m.group(3))
            noi_ro = bool(m.group(2).strip())
            if not a or not b or a >= b or (not noi_ro and b != a + 1):
                continue
            if _SAU_CON_SO.search(text[:m.start()]):
                continue
            he_so = 12 if m.group(4) == "năm" else 1
            return (m.start(), m.end(), Decimal(a * he_so), Decimal(b * he_so),
                    f"{a} đến {b} {m.group(4)}")
    m = _KHOANG_VAI.search(text)
    if m:
        return m.start(), m.end(), Decimal(2), Decimal(9), m.group(0)
    return None


# These are semantic roles, not lists of observed bad transcriptions or amounts.
_ANCHORS = re.compile(
    r"\b(?P<income>thu nhap|luong|doanh thu|tien cong)\b|"
    r"\b(?P<identifier>dien thoai|can cuoc|cccd|cmnd|ma so|ma ho so|so ho so|"
    r"ma khach hang|ma giao dich|so tai khoan|bien so)\b|"
    # Con số có vai rõ ràng ngoài ba dữ kiện đang thu thập. Nhánh này đứng
    # trước ``correction`` để "đội bóng" không bị bỏ dấu thành "doi" = đổi.
    r"\b(?P<nonloan>doi bong|tran dau|ti so|ty so|ghi ban|hoc lop|sinh vien|"
    r"nam hoc|khoa hoc|no xau|nhom no|cham tra|tre han|qua han|cic)\b|"
    r"\b(?P<employment>lam viec|lam (?:o |tai |cho |ben )?(?:cong ty|co quan|xuong|nha may)|"
    r"di lam|lam duoc|vao lam|tham nien|cong tac|sao ke)\b|"
    r"\b(?P<payoff>tat toan|tra truoc|tra som)\b|"
    r"\b(?P<payment>tien lai|tien phi|phi|khoan tra|so tien tra|tra dung|tra khoang|"
    r"tra tam|moi thang dong|moi thang tra|tra moi thang)\b|"
    r"\b(?P<existing>khoan vay cu|hop dong|du no)\b|"
    r"\b(?P<limit>han muc(?: vay)?|vay toi da|tran san pham)\b|"
    r"\b(?P<term>ky han|thoi han|trong vong|trong|tra gop|tra dan|gop trong|"
    r"tra(?=\s+trong\b|\s*$))\b|"
    # "may" là "vay" bị nghe nhầm - nhưng "công ty may", "thợ may" thì không.
    r"\b(?P<amount>vay|(?<!cong ty )(?<!nha )(?<!xuong )(?<!tho )(?<!nganh )(?<!nghe )may|"
    r"nhu cau|so tien)\b|"
    r"\b(?P<correction>doi|sua|chot|chi lay|la|ma|con|nham|(?:anh|chi|toi|em) (?:noi|bao))\b")
_CORRECTION = re.compile(r"\b(doi|sua|a nham|y (?:anh|toi|chi) la|chot|(?:anh|chi|toi|em) (?:noi|bao))\b")
# Cùng các chữ đó nhưng CÓ DẤU. `fold` bỏ dấu nên "dồi" (rồi, nói ngọng), "đợi",
# "đôi", "đời" đều thành "doi" = "đổi": khách nói "ừ thế là được dồi anh cảm ơn"
# thì số tiền đã chốt bị coi là đang sửa và AI đòi "nhắc lại giúp em số tiền"
# (bộ thử 10-10-2026). Câu có dấu thì phải khớp đúng chữ có dấu.
# Không có "anh nói / em bảo": đứng một mình (không kèm con số mới) thì "em nói
# nhanh lên", "anh bảo để anh xem đã" không phải lời sửa số tiền.
# "đổi / sửa" phải đi với chữ chỉ việc sửa dữ kiện ("đổi sang", "sửa lại", "đổi kỳ
# hạn"): "vay để sửa nhà", "đổi xe" là MỤC ĐÍCH vay - từng xoá số tiền đã chốt rồi
# AI đòi "nhắc lại giúp em một số tiền" (bộ thử 304 lượt, "cô muốn vay để sửa nhà").
_CORRECTION_CO_DAU = re.compile(
    r"\b((?:đổi|sửa) (?:lại|sang|thành|qua|số|khoản|kỳ hạn|thời hạn|thu nhập|lương)|à nhầm|"
    r"ý (?:anh|tôi|chị) là|chốt lại|(?:anh|chị|tôi) (?:nói|bảo) (?:là|lại))\b")
# "muốn DAY hai trăm triệu": "vay" giọng miền Nam bị ghi thành "day".
_DAY_LA_VAY = re.compile(r"\b(muon|can|dinh|xin|duoc|cho) day\b")
# Một chữ số đứng trước danh từ đếm người/vật là SỐ LƯỢNG, không phải tiền:
# "thu nhập HAI vợ chồng chị là bốn mươi triệu" từng thành hai mức thu nhập.
_DANH_TU_DEM = frozenset({"vợ", "người", "đứa", "lần", "bên", "con", "cái", "căn", "chiếc",
                          "khoản", "nơi", "chỗ", "loại", "sổ", "thẻ", "ông", "bà", "bạn",
                          # Đơn vị đếm kết quả/học tập: con số mang vai số lượng,
                          # không phải câu trả lời cụt cho một dữ kiện khoản vay.
                          "bàn", "điểm", "môn", "trận", "đội",
                          # "vay MỘT SỐ tiền", "một ít", "một chút": "một" là từ chỉ lượng
                          # phỏng chừng - từng thành "anh chị vừa nói một, triệu hay tỷ".
                          "số", "ít", "chút", "tí", "món", "lúc", "vài",
                          # "nói lại MỘT LƯỢT": câu này xuất hiện 38 lần trong các
                          # cuộc gọi thật đã lưu và lần nào cũng bị đọc ra số 1.
                          "lượt", "lần", "thể", "mạch", "hơi", "câu", "ý"})
_DANH_TU_DEM_BO_DAU = frozenset(fold(word) for word in _DANH_TU_DEM)
_CO_DAU = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]")
# Khách TỰ SỬA giữa câu: "ba trăm à không hai trăm triệu", "ba năm à mà thôi bốn
# năm". Chỉ xét ở KHOẢNG GIỮA hai con số cùng vai, không xét cả câu - "mà thôi để
# anh nghĩ đã" không phải lời sửa con số nào.
_TU_SUA = re.compile(r"\b(?:a (?:ma )?khong|a nham|nham|a quen|(?:a )?(?:ma )?thoi|y la)\b")


def _co_y_sua(text: str) -> bool:
    """Câu có lời SỬA dữ kiện ("đổi", "sửa", "chốt"...) - xét cả dấu nếu câu có dấu."""
    goc = unicodedata.normalize("NFC", (text or "").lower())
    if _CO_DAU.search(goc):
        return bool(_CORRECTION_CO_DAU.search(goc))
    # Với câu ASCII, che đúng cụm ``sua|doi + danh từ mục đích`` trước khi tìm
    # lời sửa. Nếu không, "sua bep" còn có thể xoá khoản vay cũ dù con số phía
    # sau đã được loại khỏi vai thu nhập/số tiền trong `_role`.
    return bool(_CORRECTION.search(_prefix_neo(goc)))
_CANCEL = re.compile(r"\b(khong (?:muon |can )?vay nua|huy (?:khoan )?vay|thoi khong vay)\b")
_SUA_DON_VI_THU_NHAP_NAM = re.compile(
    r"\b(?:noi )?(?:nham|sai)\s+(?:mat )?don vi\b.{0,60}"
    r"\b(?:mot nam|hang nam|moi nam|theo nam)\b")
_CALC = re.compile(r"\b(?:moi thang|hang thang|mot thang|tien lai)\b.{0,40}\bbao nhieu\b|\b(?:tra|dong) bao nhieu\b")
# "khoảng / tầm / chắc" là từ rào đón trước con số trả lời cụt: thiếu chúng thì
# "khoảng 300 triệu", "tầm hai năm" đáp cho câu AI vừa hỏi bị bỏ qua hẳn.
# ... và tiếng ngập ngừng / tiểu từ quanh con số: "ừ thì ba năm đi", "ờ thì tầm
# tầm ờ khoảng ờ hai trăm gì đấy" (bộ thử 10-10-2026: cả hai đều không được ghi).
_ONLY_NUMBER = re.compile(
    r"^(?:(?:a|da|vang|o|u|um|uh|the|anh|chi|toi|em|la|chi|muon|xin|lay|thoi|nhe|nha|chu|"
    r"khoang|tam|chung|chac|can|di|thi|gi|day|do|ay|dau|vay|cho|ne|phai|dang)\s*)*$")
# AI vừa HỎI số tiền / thời hạn: câu đáp cụt của khách là đáp cho đúng ý đó, dù
# trước đó chưa có dữ kiện nào. Chỉ nhìn AI hỏi GÌ, không lấy con số nào của AI.
_AI_HOI_TIEN = re.compile(r"\b(?:vay|gui|can)\b.{0,24}\bbao nhieu\b|\bso tien\b.{0,30}\?")
_AI_HOI_KY_HAN = re.compile(r"\b(?:bao lau|may thang|bao nhieu thang|may nam|thoi han)\b")
# "Thu nhập hàng tháng của anh chị khoảng bao nhiêu ạ?" (câu dẫn dắt của `dan_dat`).
_AI_HOI_THU_NHAP = re.compile(
    r"\b(?:thu nhap|luong)\b.{0,40}\b(?:bao nhieu|khoang nao|the nao|ra sao)\b")
# Rút lại một con số vừa nói hoặc nói thẳng là chưa chốt tiền. Đây là trạng
# thái dữ kiện mơ hồ có chủ ý, không phải "không có cập nhật" để rồi số cũ sống
# lại hoặc mô hình tự coi số đầu câu là khoản vay đã chốt.
_CHUA_CHOT_TIEN = re.compile(r"\bchua (?:quyet dinh|chot|xac dinh)\b.{0,24}\bso tien\b")
_RUT_LAI_TIEN = re.compile(
    r"\b(?:a )?khoan\b.{0,30}\b(?:khong|thoi)\b.{0,30}\bmay (?:tram|trieu|ty)\b|"
    r"\bchua (?:quyet dinh|chot|xac dinh)\b.{0,24}\bso tien\b|"
    # Rút lại chính GIÁ TRỊ vừa nêu: xoá độ chắc chắn của số tiền nhưng không
    # biến thành huỷ cả nhu cầu vay và cũng không đụng tới kỳ hạn đã chốt.
    r"\b(?:rut|bo|thu hoi) lai\b.{0,24}\b(?:so tien|muc tien|con so)\b")


def _suy_don_vi() -> bool:
    """Công tắc `config.suy_don_vi_trieu`: tắt thì luôn hỏi lại "triệu hay tỷ"."""
    try:
        from backend.config import settings
        return bool(getattr(settings, "suy_don_vi_trieu", True))
    except Exception:  # noqa: BLE001 - môi trường không nạp được cấu hình
        return True


# Hạn mức tối đa (đồng) của sản phẩm đang tư vấn - do nơi gọi đặt quanh `resolve`
# (xem `voi_tran_san_pham`). None = chưa biết sản phẩm.
_TRAN = contextvars.ContextVar("tran_san_pham", default=None)
# Thời hạn vay DÀI NHẤT (tháng) của sản phẩm đó, để suy "tháng hay năm".
_KY_HAN_DAI = contextvars.ContextVar("ky_han_dai_nhat", default=None)


@contextlib.contextmanager
def voi_tran_san_pham(tran: float | None, ky_han_dai: int | None = None):
    """Mọi `resolve` gọi bên trong khối này suy đơn vị theo hạn mức và thời hạn của sản phẩm."""
    token = _TRAN.set(float(tran) if tran else None)
    token_ky = _KY_HAN_DAI.set(int(ky_han_dai) if ky_han_dai else None)
    try:
        yield
    finally:
        _TRAN.reset(token)
        _KY_HAN_DAI.reset(token_ky)


def ky_han_suy_ra(he_so: Decimal, raw: str = "") -> int | None:
    """Số THÁNG của một kỳ hạn nói không kèm "tháng/năm" ("mười hai", "ba mươi sáu"), hoặc None.

    Chỉ suy khi hiểu là NĂM thì dài phi lý so với sản phẩm (quá 1,5 lần thời hạn
    dài nhất) còn hiểu là tháng thì hợp: vay tín chấp dài nhất 60 tháng nên "mười
    hai" không thể là 12 năm. "ba" (3 tháng hay 3 năm) thì vẫn hỏi lại.
    """
    dai = _KY_HAN_DAI.get()
    if not _suy_don_vi() or not dai or he_so is None or he_so != he_so.to_integral():
        return None
    # "hai lăm": người nói ngọng l/n dùng đúng chữ này cho "hai NĂM". 25 tháng là
    # kỳ hạn hiếm, 2 năm thì rất thường - không đoán, để hỏi lại như trước.
    if he_so == 25 and fold(raw).strip() == "hai lam":
        return None
    if 1 <= he_so <= Decimal(dai) * 3 / 2 and he_so * 12 > Decimal(dai) * 3 / 2:
        return int(he_so)
    return None


def don_vi_suy_ra(he_so: Decimal, raw: str = "") -> int | None:
    """Đơn vị (10**6 hay 10**9) của một số tiền vay nói KHÔNG kèm đơn vị, hoặc None.

    Suy theo HẠN MỨC của sản phẩm đang tư vấn, và chỉ khi đúng MỘT đơn vị cho ra
    con số hợp lý; không thì None để AI hỏi lại. Câu trả lời luôn đọc lại con số
    kèm đơn vị ("Dạ 200 triệu đồng thì...") nên khách sửa được nếu suy sai.

      sản phẩm tính bằng triệu (vay tín chấp, trần 500 triệu) hoặc chưa biết:
          10-999  -> triệu          ("vay bốn trăm")
          1-9     -> hỏi lại
      sản phẩm tính bằng tỷ (vay mua nhà, trần 10 tỷ):
          1 tới 3 lần trần -> tỷ    ("vay hai" = 2 tỷ, "vay mười lăm" = 15 tỷ: vượt trần)
          100-999 -> triệu          ("vay năm trăm")
          còn lại -> hỏi lại        ("vay năm mươi": 50 triệu hay 50 tỷ đều lạ)

    Vì sao không "cứ hiểu là triệu": với vay mua nhà "vay hai" mà ra 2 triệu là
    sai hẳn. Vì sao không "cứ hỏi lại": đo trên các cuộc gọi thật đã lưu
    (10-10-2026), khách nêu số tiền 100 lần thì 12 lần không kèm đơn vị, cả 12
    đều là triệu, và mỗi lần AI hỏi lại tốn 13-16 giây.
    """
    if not _suy_don_vi() or he_so is None:
        return None
    tran = _TRAN.get()
    if tran is None or tran < 10**9:
        return 10**6 if 10 <= he_so < 1000 else None
    # "vay năm": "năm" còn là NĂM (thời gian) - để hỏi lại.
    ty = 1 <= he_so and he_so * 10**9 <= 3 * Decimal(tran) and raw.strip() != "năm"
    trieu = 100 <= he_so < 1000
    if ty != trieu:
        return 10**9 if ty else 10**6
    return None


_ALTERNATIVE = re.compile(r"\s*(?:hay|hoac(?: la)?|den|toi|[-/])\s*")


# NGOẠI LỆ DUY NHẤT của luật "không lấy con số do AI nói": AI hỏi thẳng "Anh chị
# vay 12 tháng được không ạ?" (câu của luật kỳ hạn ngoài khung) và khách gật mà
# không nêu con số nào. Lời gật đó là khách tự xác nhận thời hạn. Thiếu nó, kỳ
# hạn cũ (4 tháng) vẫn nằm trong sổ và lượt sau AI lại báo "4 tháng chưa được".
_DE_NGHI_KY_HAN = re.compile(r"\bvay (\d+) (tháng|năm) được không\b[^?]*\?\s*$")
_GAT_LOI = re.compile(r"\b(u+|uh|um|ok\w*|o ke|duoc|vang|dong y|nhat tri|chot|the di|vay di)\b")
_CHI_GAT = re.compile(
    r"^(?:(?:u+|uh|um|o|a|da|vang|ok\w*|o ke|duoc|dong y|nhat tri|chot|cung|the|vay|thi|di|"
    r"nhe|nha|em|anh|chi|roi|thoi|luon)\s*)+$")

# Câu hỏi lại có nhắc đúng một con số vừa nghe loáng thoáng: "anh nghe ... cái
# gì ba trăm cơ?". Con số vẫn phải được `quantities()` đọc bình thường để các
# tầng khác có thể hiện lại nguyên văn, nhưng tuyệt đối không được ghi thành dữ
# kiện khoản vay. Đòi cả từ hỏi ("gì") lẫn tiểu từ hỏi ở cuối để không nuốt lời
# nêu/sửa rõ ràng như "anh muốn vay ba trăm" hay "à không anh vay ba trăm cơ".
_HOI_LAI_CON_SO = re.compile(
    r"\b(?:(?:nghe|hieu)\b.{0,36}\bgi|cai gi)\b.{0,48}\b(?:co|the|a|vay)\s*$")


def is_readback(text: str) -> bool:
    """Asking what was said is a read, not a correction to any loan fact.

    This predicate is intentionally context-free. A true result owns the whole
    user turn: callers may still parse/display its quantities, but must not use
    them to update amount, term, or income.
    """
    normal = fold(text).strip(" .,!?:")
    return bool(re.search(r"\bnhac lai\b", normal) or re.search(
        r"\b(?:da (?:noi|cung cap)|(?:anh|chi|toi|em) noi)\b.{0,60}\b(?:bao nhieu|la gi)\b",
        normal) or (quantities(text) and _HOI_LAI_CON_SO.search(normal)))


# Bỏ dấu thì "mấy/máy/mày/mây" thành ``may`` và "vậy/vầy" thành ``vay`` -
# đều trùng neo số tiền dù chỉ là đại từ/trợ từ trong câu.
_TRUNG_MAY = re.compile(r"\b(?:mấy|máy|mày|mây|vậy|vầy)\b", re.IGNORECASE)
_CON_LA_CON_CAI = re.compile(
    r"\bcon\b(?=\s+(?:toi|anh|chi|em|co|chu|bac)\b)")
# "SỬA bếp thì hết tầm tám chục triệu", "ĐỔI xe cần hai trăm": sửa/đổi MỘT THỨ là
# mục đích vay. Dùng cùng biểu diễn bỏ dấu cho lời có dấu và không dấu, nhưng chỉ
# che ``sua|doi`` khi ngay sau nó là đúng ngữ pháp danh từ mục đích. Vì vậy
# ``sua lai 15 trieu`` vẫn là lời sửa dữ kiện. Đây chỉ là bản sao prefix dùng tìm
# neo ngữ nghĩa; offset Quantity vẫn trỏ vào nguyên văn của khách.
_SUA_SANG_CHUA_LA_MUC_DICH = re.compile(r"\bsửa\s+(?=sang\b|chữa\b)")
_SUA_LA_MUC_DICH = re.compile(
    r"\b(?:sua|doi)\s+(?=(?:lai\s+)?(?:(?:cai|can|con|chiec)\s+)?"
    r"(?:nha|bep|xe|mai|phong|cua|san|tuong|tran|be|dien|nuoc|quan|vuon|chuong|do|"
    r"noi that|tivi|tu|laptop|viec|nghe)\b)")


def _prefix_neo(text: str) -> str:
    """Prefix đã chuẩn hoá chỉ để phân loại neo; không dùng làm offset."""
    goc = unicodedata.normalize("NFC", (text or "").lower())
    semantic = fold(_SUA_SANG_CHUA_LA_MUC_DICH.sub("_ ", goc))
    return _SUA_LA_MUC_DICH.sub("_ ", semantic)


_SAU_CHU_LAI = re.compile(r"\blãi(?:\s+suất)?(?:\s+(?:là|từ|khoảng|tầm|có|chỉ|đấy|đó))*\s*$")
_NGU_CANH_GIAO_DUC = re.compile(
    r"\b(?:hoc|hoc tap|hoc phi|mon hoc|lop hoc|hoc sinh|sinh vien|dao tao)\b")
_NEO_DU_KIEN_TU_KHACH = re.compile(
    r"\b(?:vay|nhu cau|so tien(?: vay)?|khoan vay|ky han|thoi han|"
    r"thu nhap|luong|doanh thu|tien cong)\b|"
    r"\b(?:doi|sua|chot)\s+(?:lai|sang|thanh|qua|so|khoan|ky han|thoi han|"
    r"thu nhap|luong)\b")
_TU_CHOI_GAN_THU_NHAP = re.compile(
    r"\b(?:dung|khong)\s+(?:coi|xem|tinh|ghi(?: nhan)?|lay)\b")
_NEO_THU_NHAP = re.compile(r"\b(?:luong|thu nhap)\b")


def _la_muc_thu_nhap_bi_tu_choi(text: str, q: Quantity) -> bool:
    """Con số được nhắc để nói rõ KHÔNG ghi nhận làm thu nhập hiện tại."""
    if q.kind not in ("bare", "money"):
        return False
    clause, local_start = _menh_de_chua_so(text, q)
    local_end = local_start + (q.end - q.start)
    before = re.sub(
        r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", clause[:local_start])
    after = re.sub(
        r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", clause[local_end:])
    rejection = list(_TU_CHOI_GAN_THU_NHAP.finditer(before))
    if not rejection:
        return False
    tail = before[rejection[-1].end():]
    # ``đừng coi 6 triệu là thu nhập`` / ``không tính 6 triệu vào lương``.
    if len(tail) <= 48 and re.match(
            r"^.{0,40}\b(?:la|vao|lam)?\s*(?:muc\s+)?(?:luong|thu nhap)\b",
            after):
        return True
    # ``không ghi nhận thu nhập hiện tại của tôi là 6 triệu``.
    return len(tail) <= 64 and bool(_NEO_THU_NHAP.search(tail))


def _so_thuoc_ngu_canh_giao_duc(text: str, q: Quantity) -> bool:
    """Con số thuộc mệnh đề học tập, trừ khi khách đã chuyển sang neo vay rõ ràng.

    So vị trí neo trong chính mệnh đề chứa số để ``học ... 6 tháng`` không thành
    kỳ hạn vay, nhưng ``học xong muốn vay 100 triệu`` vẫn là nhu cầu của khách.
    Ranh giới mệnh đề cũng ngăn chủ thể ``con tôi`` lan sang phần ``còn tôi đổi
    khoản vay...`` ở sau.
    """
    clause, local_start = _menh_de_chua_so(text, q)
    before = re.sub(
        r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", clause[:local_start])
    education = list(_NGU_CANH_GIAO_DUC.finditer(before))
    if not education:
        return False
    loan = list(_NEO_DU_KIEN_TU_KHACH.finditer(before))
    return not loan or education[-1].start() > loan[-1].start()


def _role(text: str, q: Quantity, established: bool, ai_hoi: str = "",
          correction_target: str | None = None) -> str | None:
    """Vai của một con số trong câu. `established`: cuộc đã có số tiền/kỳ hạn;
    `ai_hoi`: AI vừa hỏi "amount", "term" hay "income" (câu đáp cụt là đáp cho ý đó)."""
    # "lãi bảy phẩy chín", "lãi suất là sáu rưỡi": con số đi liền sau chữ LÃI là lãi
    # suất, không phải tiền vay. Xét trên chữ CÓ DẤU - bỏ dấu thì "lại" (sửa lại
    # 200 triệu) cũng thành "lai".
    if q.kind == "bare" and _SAU_CHU_LAI.search(text[:q.start].lower()):
        return None
    if _la_muc_thu_nhap_bi_tu_choi(text, q):
        return None
    if _so_thuoc_ngu_canh_giao_duc(text, q):
        return None
    if q.kind == "money":
        clause, local_start = _menh_de_chua_so(text, q)
        local_before = re.sub(
            r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", clause[:local_start])
        # Dùng đoạn gốc có dấu cho cùng bước che ``máy/mấy/vậy`` như prefix
        # chính. Nếu fold trước, ``xe máy`` thành ``xe may`` và ``may`` bị hiểu
        # nhầm là ASR của ``vay``. Với văn bản ASCII, che riêng danh từ máy móc
        # nhưng giữ ``may`` trong ``cần may 50 triệu`` làm neo vay theo ASR.
        original_clause_start = q.start - local_start
        local_anchor_prefix = _prefix_neo(
            _TRUNG_MAY.sub("_", text[original_clause_start:q.start]))
        local_anchor_prefix = _MAY_MOC_ASCII.sub("_", local_anchor_prefix)
        local_anchor_prefix = re.sub(
            r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", local_anchor_prefix)
        local_asset_anchors = list(_ANCHORS.finditer(local_anchor_prefix))
        local_has_financial_owner = any(
            anchor.lastgroup in ("amount", "income") for anchor in local_asset_anchors)
        local_has_purchase_need = bool(re.search(
            r"\b(?:muon|can|dinh|tinh)\b.{0,32}\b(?:mua|sam)\b", local_before))
        if (_GIA_TRI_TAI_SAN.search(local_before)
                or (_DANH_TU_TAI_SAN.search(local_before)
                    and not local_has_financial_owner
                    and not local_has_purchase_need)):
            # Giá tài sản có thể được nói gọn chỉ bằng danh từ + số tiền
            # (``căn nhà 2,5 tỷ``). Khi mệnh đề này không có neo vay/thu nhập
            # riêng, không cho neo thu nhập ở mệnh đề trước sở hữu con số đó.
            return None
    prefix = _DAY_LA_VAY.sub(r"\1 vay", _CON_LA_CON_CAI.sub(
        "_", _prefix_neo(_TRUNG_MAY.sub("_", text[:q.start]))))
    # ASR/chat text sometimes glues words and digits ("vay200trieu24thang").
    # Virtual boundaries are only for semantic anchors; Quantity offsets remain
    # tied to the untouched utterance.
    prefix = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", prefix)
    clause, local_start = _menh_de_chua_so(text, q)
    local_prefix = _DAY_LA_VAY.sub(
        r"\1 vay", _CON_LA_CON_CAI.sub(
            "_", _prefix_neo(_TRUNG_MAY.sub("_", clause[:local_start]))))
    local_prefix = re.sub(
        r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", local_prefix)
    if q.kind == "duration":
        # Một liên từ có thể mở vị ngữ mới mà không lặp chủ ngữ: ``tôi vay 95
        # triệu và điều trị 6 tháng``. Chỉ mang neo từ phần trước qua liên từ
        # khi phần đó đã nói rõ kỳ hạn/trả góp; neo số tiền đơn thuần không sở
        # hữu mọi duration ở vị ngữ sau.
        breaks = list(re.finditer(r"\b(?:va|roi|sau do)\b", local_prefix))
        if breaks:
            before_break = local_prefix[:breaks[-1].start()]
            explicit_term_before = any(
                a.lastgroup == "term" and a.group() not in ("trong", "trong vong")
                for a in _ANCHORS.finditer(before_break))
            if not explicit_term_before:
                local_prefix = local_prefix[breaks[-1].end():]
    da_co = established            # lời sửa chỉ có nghĩa khi ĐÃ có dữ kiện để sửa
    established = established or bool(ai_hoi)
    # Kỳ hạn phải được sở hữu bởi chính mệnh đề chứa nó. Nếu dùng toàn bộ prefix,
    # "tôi vay 95 triệu; tôi điều trị 6 tháng" sẽ nhập neo ``vay`` của mệnh đề
    # trước và biến thời gian điều trị thành kỳ hạn mới.
    anchors = list(_ANCHORS.finditer(local_prefix if q.kind == "duration" else prefix))
    role = anchors[-1].lastgroup if anchors else None
    if q.kind in ("bare", "money") and _la_thu_nhap_viet_tat_theo_chu_the(
            text, q, ai_hoi):
        return "income"
    if role == "term" and anchors[-1].group() in ("trong", "trong vong"):
        # ``trong / trong vòng`` chỉ nối một thời lượng với vai đã rõ trong cùng
        # mệnh đề; bản thân giới từ thời gian không tạo ra kỳ hạn khoản vay.
        owners = [a.lastgroup for a in anchors[:-1] if a.lastgroup not in ("term", "correction")]
        explicit_term = any(
            a.lastgroup == "term" and a.group() not in ("trong", "trong vong")
            for a in anchors[:-1])
        if owners:
            role = "term" if owners[-1] == "amount" else owners[-1]
        elif explicit_term or _co_y_sua(local_prefix):
            role = "term"
        else:
            role = None
    if role == "correction":
        preceding = [a.lastgroup for a in anchors[:-1] if a.lastgroup != "correction"]
        role = preceding[-1] if preceding else (correction_target or ("amount" if da_co else None))
    if role == "term" and q.kind == "bare":
        return "term"
    if role == "term" and q.kind != "duration":
        role = None
    if q.kind == "duration":
        if role in ("amount", "term"):
            return "term"
        if role in (
                "income", "employment", "identifier", "nonloan", "payment", "payoff",
                "existing", "limit"):
            return None
        local_end = local_start + (q.end - q.start)
        rest = (clause[:local_start] + " " + clause[local_end:]).strip(" .,!?:")
        rest_without_temporal = re.sub(r"\b(?:trong vong|trong)\b", " ", rest)
        # Hai trường tài chính viết gọn: ``275 trong 24 tháng``. Sau khi bỏ
        # mọi quantity và giới từ thời gian, mệnh đề không còn nội dung khác;
        # vì vậy duration thứ hai vẫn thuộc phương án vay đang sửa.
        clause_quantities = quantities(clause)
        has_earlier_quantity = any(
            item.end <= local_start and item.kind in ("bare", "money")
            for item in clause_quantities)
        compact_rest = clause
        for item in sorted(clause_quantities, key=lambda item: -item.start):
            compact_rest = compact_rest[:item.start] + " " + compact_rest[item.end:]
        compact_rest = re.sub(
            r"\b(?:trong vong|trong)\b", " ", compact_rest).strip(" .,!?:")
        compact_financial_fields = (has_earlier_quantity
                                    and bool(_ONLY_NUMBER.fullmatch(compact_rest)))
        # "không, anh chỉ cần 4 tháng thôi": chữ "không" ĐẦU CÂU là gạt lời AI
        # vừa đề nghị rồi nêu lại kỳ hạn của mình ("không phải / không cần /
        # không vay" thì là phủ định chính con số, để nguyên).
        rest = re.sub(r"^\s*khong\b(?!\s+(?:phai|can|muon|vay)\b)[\s,.]*", "", rest)
        rest_without_temporal = re.sub(r"\b(?:trong vong|trong)\b", " ", rest)
        # "ba sáu tháng thì mỗi tháng bao nhiêu": kỳ hạn đứng một mình đầu câu
        # hỏi tính - phần còn lại chính là câu hỏi tính, không phải câu khác.
        earlier_loan_anchor = any(
            a.lastgroup == "amount" or (
                a.lastgroup == "term" and a.group() not in ("trong", "trong vong"))
            for a in _ANCHORS.finditer(prefix))
        if has_earlier_quantity and _CALC.search(fold(text)):
            return "term"
        if (established or earlier_loan_anchor) and (
                _ONLY_NUMBER.fullmatch(rest_without_temporal.strip(" .,!?:"))
                or compact_financial_fields or _CALC.search(rest)):
            return "term"
        if _CHUA_CHOT_TIEN.search(rest):
            return "term"
        return None
    if q.kind == "other":
        return None
    if (role is None and q.kind in ("bare", "money")
            and _CALC.search(fold(text[q.end:]))
            and any(item.start >= q.end and item.kind == "duration"
                    for item in quantities(text))):
        return "amount"
    if role in ("amount", "income"):
        return role
    # Numeric answers to an ongoing loan discussion, not numbers in arbitrary
    # sentences, IDs, employment or quoted product descriptions.
    rest = fold(text[:q.start] + " " + text[q.end:]).strip(" .,!?:")
    # "à không, chắc phải trăm rưỡi": mở đầu bằng lời tự sửa rồi nêu con số mới.
    # Phải có chữ "à" - "không cần 4 tháng" là phủ định chính con số.
    tu_sua = re.match(r"^a (?:ma )?(?:khong|nham|quen)\b[\s,.]*", rest)
    if tu_sua:
        rest = rest[tu_sua.end():]
    if role is None and (established or q.kind == "money") and _ONLY_NUMBER.fullmatch(rest):
        # AI vừa hỏi THỜI HẠN mà khách đáp cụt một con số trần ("ba mươi sáu"):
        # đó là thời hạn thiếu đơn vị, không phải số tiền. Trừ khi khách mở đầu
        # bằng lời tự sửa ("à không, chắc phải trăm rưỡi" - sửa số tiền vừa nói)
        # hoặc con số quá lớn để là số tháng.
        if (ai_hoi == "term" and q.kind == "bare" and not tu_sua
                and q.value is not None and q.value <= 72):
            return "term"
        # AI vừa hỏi THU NHẬP mà khách đáp cụt "mười lăm" / "tầm hai chục triệu":
        # đó là thu nhập. Không có nhánh này con số đè lên số tiền vay đã chốt
        # ("vay ba trăm triệu" ... "mười lăm" -> "Dạ 15 triệu thì trong hạn mức").
        if ai_hoi == "income" and q.kind in ("bare", "money") and not tu_sua:
            return "income"
        return "amount"
    if (established or q.kind == "money") and _ONLY_NUMBER.fullmatch(prefix.strip()) and re.match(
            r"\s*(?:(?:di|thoi|nhe|nha|a)\s+)?"
            r"(?:[,;\-/]|(?:chu )?khong phai\b|(?:trong|tra|gop|ky han|hay|hoac|den|toi)\b)",
            fold(text[q.end:])):
        return "amount"
    # "chị muốn mua xe máy KHOẢNG năm mươi triệu": nêu nhu cầu kèm một khoản tiền
    # ước chừng ở cuối câu là nêu số tiền cần. Không áp cho mua nhà/đất - giá nhà
    # không phải số tiền vay.
    if (q.kind == "money" and re.search(r"\b(?:muon|can|dinh|tinh)\b", prefix)
            and re.search(r"\b(?:khoang|tam|chung|het|mat)\s*$", prefix)
            and not re.search(r"\b(?:nha|can ho|chung cu|dat|biet thu|bat dong san)\b", prefix)
            and not fold(text[q.end:]).strip(" .,!?")):
        return "amount"
    return None


def _negated(text: str, q: Quantity) -> bool:
    prefix = fold(text[:q.start])
    suffix = fold(text[q.end:])
    return bool(
        re.search(r"\b(?:khong phai|chu khong(?: phai)?|khong (?:muon )?vay)\s*$", prefix)
        or re.search(r"\b(?:khong noi|dau co noi)(?: vay)?\s*$", prefix)
        or (re.search(r"\bco noi(?: vay)?\s*$", prefix)
            and re.match(r"\s*dau\b", suffix))
    )


_RANH_GIOI_MENH_DE = re.compile(
    r"[;!?]|(?<!\d)[,.]|[,.](?!\d)|\bnhung\b|"
    r"\bva\b(?=\s+(?:anh|chi|toi|em|ban|vo|chong|me|bo|dong nghiep)\b)")
_RANH_GIOI_CON_CO_DAU = re.compile(r"\bcòn\b", re.IGNORECASE)
_RANH_GIOI_CON_ASCII = re.compile(
    r"\bcon\b(?=\s+(?:toi|anh|chi|em)(?=\s|\d)\s*(?:\d|"
    r"mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi|tram))")
_CO_SO_TRUOC_CON_ASCII = re.compile(
    r"\d|\b(?:mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi|chuc|tram|"
    r"nghin|trieu|ty)\b")
_THU_NHAP_HO_GIA_DINH = re.compile(
    r"\b(?:thu nhap|luong)?\s*(?:cua )?(?:hai |ca )?vo chong\b|"
    r"\b(?:(?:tong )?thu nhap(?: (?:chung|tong))?) (?:cua )?"
    r"(?:gia dinh|ca nha|nha (?:toi|anh|chi|em))\b")
_HO_GIA_DINH_NGUOI_KHAC = re.compile(
    r"\bvo chong (?:ban|ho|nguoi (?:than|quen)|dong nghiep|anh trai|chi gai|em trai|em gai)\b")
_CHU_THE_THU_NHAP_KHAC = re.compile(
    r"\b(?:vo|chong|ban|ban trai|ban gai|nguoi yeu|me|bo|ba|con|anh trai|chi gai|"
    r"em trai|em gai|dong nghiep|sep|quan ly|nhan vien|doi tac|khach hang|nguoi than)"
    r"(?:\s+cua)?\s+(?:toi|anh|chi|em|co|chu|bac)\b|"
    # `anh/chị` đứng độc lập có thể là cách xưng hô với chính người gọi. Chỉ
    # coi là thân nhân khi theo sau là sở hữu ngôi thứ nhất rõ ràng (`chị tôi`).
    r"\b(?:anh|chi)\s+(?:toi|em)\b|"
    r"\b(?:anh|chi)\s+cua\s+(?:toi|em|co|chu|bac)\b")
_CHU_THE_THU_NHAP_KHAC_DAU_MENH_DE = re.compile(
    r"^\s*(?:(?:rieng|ve phia)\s+)?(?:vo|chong|me|bo|ba|con|anh trai|chi gai|"
    r"em trai|em gai|dong nghiep|sep|quan ly|nhan vien|doi tac|khach hang|nguoi than)\b|"
    r"^\s*(?:luong|thu nhap)(?: cua)?\s+(?:vo|chong|me|bo|ba|con|anh trai|chi gai|"
    r"em trai|em gai|dong nghiep|sep|quan ly|nhan vien|doi tac|khach hang|nguoi than)\b")
# Danh xưng + tên riêng là người được nhắc tới; ``anh/chị lương...`` không có
# tên xen giữa nên vẫn là cách xưng hô với chính người gọi.
_TEN_NGUOI_KHAC_DAU_MENH_DE = re.compile(
    r"^\s*(?:rieng\s+)?(?:anh|chi|co|chu|bac)\s+"
    r"(?!(?:co|dang|duoc|khong|la|lam|hien|luong|thu nhap|muon|can|vay|xin|"
    r"noi|bao|hoi|nghe|thay|biet|tinh|du tinh)\b)"
    r"[a-z]+(?:\s+[a-z]+)?\b.{0,80}\b(?:luong|thu nhap)\b")
_DIEU_KIEN_THU_NHAP_GIA_DINH = re.compile(
    r"\b(?:neu(?: nhu)?|gia su|vi du(?: nhu)?|truong hop)\b")
_DIEU_KIEN_THU_NHAP_TRICH_DAN = re.compile(
    r"\b(?:nghe\s+(?:(?:ho|nguoi ta|ai do)\s+)?(?:noi|bao)|"
    r"(?:ho|nguoi ta|ai do)\s+(?:noi|bao|yeu cau))\b.{0,70}\b(?:luong|thu nhap)\b|"
    r"\b(?:ngan hang|ben em|ho so)\b.{0,45}\b(?:noi|bao|yeu cau|can|quy dinh)\b"
    r".{0,35}\b(?:luong|thu nhap)\b|"
    r"\b(?:nhan vien|tu van vien)\b.{0,35}\b(?:noi|bao|yeu cau)\b.{0,35}"
    r"\b(?:luong|thu nhap)\b|"
    r"\b(?:quy dinh|dieu kien)\b.{0,55}\b(?:luong|thu nhap)\b")
_DIEU_KIEN_THU_NHAP_SAU_SO = re.compile(
    r"\b(?:thi\s+)?moi\s+(?:duoc|co the|cho)\s+(?:vay|duyet)\b|"
    r"\b(?:toi thieu|it nhat)\b")
_GIA_TRI_TAI_SAN = re.compile(
    r"\b(?:gia|gia tri|tri gia)(?:\s+(?:la|khoang|tam|chung|het|den))?\s*$")
_DANH_TU_TAI_SAN = re.compile(
    r"\b(?:can nha|ngoi nha|nha dat|can ho|chung cu|biet thu|"
    r"lo dat|mieng dat|thua dat|bat dong san|tai san|"
    r"o to|xe hoi|xe may|may moc|may cong nghiep|may san xuat|"
    r"vang|bitcoin|tien ma hoa)\b")
_MAY_MOC_ASCII = re.compile(
    r"\b(?:xe\s+may|may\s+(?:moc|cong nghiep|san xuat))\b")


def _cac_ranh_gioi_menh_de(text: str) -> list[tuple[int, int]]:
    """Clause boundaries with accent-aware handling of ``con``/``còn``.

    Folding is safe for ordinary boundaries but would turn noun ``Con``
    (child) into linker ``còn``. Accented ``còn`` is always a boundary; ASCII
    ``con`` is one only in a compact numeric contrast such as
    ``vo30trieu con toi12trieu``.
    """
    normal = fold(text)
    boundaries = {
        (match.start(), match.end())
        for match in _RANH_GIOI_MENH_DE.finditer(normal)
    }
    original = unicodedata.normalize("NFC", (text or "").lower())
    boundaries.update(
        (match.start(), match.end())
        for match in _RANH_GIOI_CON_CO_DAU.finditer(original)
    )
    for match in _RANH_GIOI_CON_ASCII.finditer(normal):
        if _CO_SO_TRUOC_CON_ASCII.search(normal[:match.start()]):
            boundaries.add((match.start(), match.end()))
    return sorted(boundaries)


def _menh_de_chua_so(text: str, q: Quantity) -> tuple[str, int]:
    """Return the local clause and quantity offset inside it."""
    normal = fold(text)
    start, end = 0, len(normal)
    for boundary_start, boundary_end in _cac_ranh_gioi_menh_de(text):
        if boundary_end <= q.start:
            start = boundary_end
        elif boundary_start >= q.end:
            end = boundary_start
            break
    return normal[start:end], q.start - start


def _menh_de_lien_truoc(text: str, q: Quantity) -> str:
    """Mệnh đề có nội dung ngay trước mệnh đề chứa ``q``.

    Bỏ qua các dấu liên tiếp để ``... lương 20 triệu`` vẫn kế thừa đúng chủ
    thể ở trước dấu ba chấm, nhưng không đi lùi qua thêm một mệnh đề có nội
    dung khác.
    """
    normal = fold(text)
    _, local_start = _menh_de_chua_so(text, q)
    current_start = q.start - local_start
    separators = [
        boundary for boundary in _cac_ranh_gioi_menh_de(text)
        if boundary[1] <= current_start
    ]
    if not separators:
        return ""
    previous_end = separators[-1][0]
    while previous_end and normal[previous_end - 1] in " \t\r\n.,;:!?":
        previous_end -= 1
    previous_start = 0
    for _, boundary_end in _cac_ranh_gioi_menh_de(text):
        if boundary_end > previous_end:
            break
        previous_start = boundary_end
    return normal[previous_start:previous_end].strip()


_CHU_THE_TU_XUNG_DAU_MENH_DE = re.compile(r"^\s*(?:toi|em)\b")
_CHU_THE_NGUOI_GOI_DAU_MENH_DE = re.compile(r"^\s*(?:toi|em|anh|chi)\b")
_THU_NHAP_TU_XUNG_TRONG_MENH_DE = re.compile(
    r"\b(?:luong|thu nhap)(?:\s+(?:rieng|thuc te))?(?:\s+cua)?\s+(?:toi|em|anh|chi)\b")
_CHU_THE_KHAC_SAU_RANH_GIOI = re.compile(
    r"(?:^|\b(?:con|nhung)\b)\s*(?:vo|chong|me|bo|ba|con|anh trai|chi gai|"
    r"em trai|em gai|dong nghiep|sep|quan ly|nhan vien|doi tac|khach hang|nguoi than)\b")
_CHU_THE_TU_XUNG_SAU_RANH_GIOI = re.compile(
    r"(?:^|\b(?:con|nhung)\b)\s*(?:toi|em)\b")
_NEO_KHOAN_VAY_RO_RANG = re.compile(
    r"\b(?:vay|nhu cau|so tien(?: vay)?|khoan vay|ky han|thoi han|tra gop|tra dan)\b")


def _nguon_hoac_gia_dinh_thu_nhap_lien_ke(
        text: str, q: Quantity, semantic_clause: str) -> bool:
    """Nguồn/giả định ở mệnh đề ngay trước vẫn chi phối câu thu nhập nối tiếp."""
    previous = _menh_de_lien_truoc(text, q)
    if not previous:
        return False
    continuation = f"{previous} {semantic_clause}".strip()
    return bool(
        _DIEU_KIEN_THU_NHAP_GIA_DINH.search(previous)
        or _DIEU_KIEN_THU_NHAP_TRICH_DAN.search(continuation))


def chu_the_thu_nhap_nguoi_khac(text: str, q: Quantity) -> bool:
    """True khi ``q`` là thu nhập của một người khác được nêu rõ.

    Chủ thể có thể nằm trong chính mệnh đề thu nhập hoặc trong mệnh đề việc làm
    ngay trước nó (``Mẹ tôi làm giáo viên, lương 20 triệu``). Chủ thể tự xưng,
    tổng thu nhập hộ, giả định và con số trích dẫn từ nguồn chính sách luôn trả
    False để nơi gọi không đánh đồng chúng với thu nhập của người thân.
    """
    clause, local_start = _menh_de_chua_so(text, q)
    before = clause[:local_start]
    semantic_clause = re.sub(
        r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", clause)
    semantic_before = re.sub(
        r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", before)
    local_end = local_start + (q.end - q.start)
    semantic_after = re.sub(
        r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", clause[local_end:])

    if (_THU_NHAP_HO_GIA_DINH.search(semantic_clause)
            or _DIEU_KIEN_THU_NHAP_GIA_DINH.search(semantic_before)
            or _DIEU_KIEN_THU_NHAP_TRICH_DAN.search(semantic_before)
            or _DIEU_KIEN_THU_NHAP_SAU_SO.search(semantic_after)
            or _HO_GIA_DINH_NGUOI_KHAC.search(semantic_before)):
        return False

    caller_age_lead = re.search(
        r"^\s*(?:anh|chi)\b.{0,36}\btuoi\b", semantic_before)
    named_other = (_TEN_NGUOI_KHAC_DAU_MENH_DE.search(semantic_before)
                   if not caller_age_lead else None)
    other_positions = [
        match.start() for pattern in (
            _CHU_THE_THU_NHAP_KHAC_DAU_MENH_DE,
            _CHU_THE_THU_NHAP_KHAC,
        ) for match in pattern.finditer(semantic_before)
    ]
    if named_other:
        other_positions.append(named_other.start())
    if (re.search(r"\bcua\s+", semantic_after)
            and _CHU_THE_THU_NHAP_KHAC.search(semantic_after)):
        other_positions.append(len(semantic_before))

    self_positions = [
        match.start()
        for match in _THU_NHAP_TU_XUNG_TRONG_MENH_DE.finditer(semantic_before)
    ]
    caller_at_start = _CHU_THE_NGUOI_GOI_DAU_MENH_DE.search(semantic_before)
    if caller_at_start and not named_other:
        self_positions.append(caller_at_start.start())
    # Trong câu có nhiều mức lương, chủ thể gần con số nhất sở hữu con số đó:
    # ``lương anh 30, vợ anh 20`` giữ 30 là của người gọi và bỏ 20 của vợ.
    last_other = max(other_positions, default=-1)
    last_self = max(self_positions, default=-1)
    if last_other > last_self:
        return True
    if last_self >= 0:
        return False

    previous = _menh_de_lien_truoc(text, q)
    if not previous:
        return False
    # Điều kiện/trích dẫn ở mệnh đề chủ thể chi phối chính câu thu nhập kế tiếp,
    # nhưng các mệnh đề xa hơn không được phép lan quyền sở hữu tới đây.
    if _nguon_hoac_gia_dinh_thu_nhap_lien_ke(text, q, semantic_clause):
        return False
    continuation = f"{previous} {semantic_clause}".strip()
    named_other = _TEN_NGUOI_KHAC_DAU_MENH_DE.search(continuation)
    previous_caller_age = re.search(
        r"^\s*(?:anh|chi)\b.{0,60}\btuoi\b", previous)
    return bool(
        _CHU_THE_THU_NHAP_KHAC_DAU_MENH_DE.search(previous)
        or _CHU_THE_THU_NHAP_KHAC.search(previous)
        or named_other and not previous_caller_age)


def _la_thu_nhap_viet_tat_theo_chu_the(text: str, q: Quantity, ai_hoi: str) -> bool:
    """Nhận câu đáp thu nhập rút gọn theo chủ thể, không đoán câu tiền vay.

    ``Bố 30 triệu còn tôi 12`` là hai mức thu nhập khi AI vừa hỏi thu nhập hoặc
    khi chính cấu trúc đối chiếu người thân/người gọi đã định vai. Một neo khoản
    vay rõ ràng trong câu luôn thắng suy luận viết tắt này.
    """
    normal = re.sub(
        r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", fold(text))
    if _NEO_KHOAN_VAY_RO_RANG.search(normal):
        return False
    clause, _ = _menh_de_chua_so(text, q)
    semantic_clause = re.sub(
        r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", clause)
    direct_subject = (_CHU_THE_THU_NHAP_KHAC_DAU_MENH_DE.search(semantic_clause)
                      or _CHU_THE_TU_XUNG_DAU_MENH_DE.search(semantic_clause))
    if not direct_subject:
        return False
    if ai_hoi == "income":
        return True
    return bool(_CHU_THE_KHAC_SAU_RANH_GIOI.search(normal)
                and _CHU_THE_TU_XUNG_SAU_RANH_GIOI.search(normal))


def _income_owner(text: str, q: Quantity) -> str:
    """Provenance for one income quantity: self, household, or ignored (empty)."""
    clause, local_start = _menh_de_chua_so(text, q)
    before = clause[:local_start]
    # Match semantic words in compact chat/ASR text (`lương3.4triệu`) without
    # touching the original text or quantity offsets.
    semantic_clause = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", clause)
    semantic_before = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", before)
    local_end = local_start + (q.end - q.start)
    semantic_after = re.sub(
        r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", clause[local_end:])
    # A quoted eligibility threshold stays quoted even if it happens to name
    # a couple. Household ownership is local to this quantity's clause, so it
    # cannot leak onto a later personal-income clause.
    if (_DIEU_KIEN_THU_NHAP_GIA_DINH.search(semantic_before)
            or _DIEU_KIEN_THU_NHAP_TRICH_DAN.search(semantic_before)
            or _DIEU_KIEN_THU_NHAP_SAU_SO.search(semantic_after)
            or _HO_GIA_DINH_NGUOI_KHAC.search(semantic_before)
            or _nguon_hoac_gia_dinh_thu_nhap_lien_ke(
                text, q, semantic_clause)):
        return ""
    # Two separately qualified salaries ("lương anh 30, vợ anh 20") are not
    # an aggregate: the caller's amount remains self-owned and the spouse's is
    # ignored below. Only explicit aggregate wording establishes household.
    if _THU_NHAP_HO_GIA_DINH.search(semantic_clause):
        return "household"
    if chu_the_thu_nhap_nguoi_khac(text, q):
        return ""
    # A local first-person marker wins in mixed multi-clause utterances. With
    # no stated subject, a direct "lương 20 triệu" is conventionally the
    # caller's own answer.
    return "self"


def _xac_nhan_lai_so_cu(text: str, q: Quantity, old: Fact) -> bool:
    """A bare "vẫn 200" may retain the unit of the established old amount."""
    if old.status != "known" or old.value is None or q.kind != "bare" or q.value is None:
        return False
    if not re.search(r"\b(?:van|giu nguyen|cu la)\s*$", fold(text[:q.start])):
        return False
    if not re.fullmatch(r"\s*(?:(?:ma|thoi|nhe|nha|a)\s*)*[.!?,]*\s*", fold(text[q.end:])):
        return False
    return any(old.value == q.value * scale for scale in (Decimal(10**6), Decimal(10**9)))


def _fact(q: Quantity, turn: int, owner: str = "") -> Fact:
    if q.value is None or q.value <= 0:
        return Fact("ambiguous", raw=q.raw, turn=turn, owner=owner)
    if q.kind == "bare":
        return Fact("missing_unit", raw=q.raw, turn=turn, coefficient=q.value, owner=owner)
    if q.kind == "duration" and q.value != q.value.to_integral():
        return Fact("ambiguous", raw=q.raw, turn=turn, owner=owner)
    return Fact("known", q.value, q.raw, turn, owner=owner)


# Lượt TRƯỚC của khách bỏ lửng ngay sau chữ dẫn vào kỳ hạn ("...ba trăm triệu trong
# vòng" - máy tưởng khách nói xong): con số trần ở lượt này là phần còn lại của
# chính câu đó, tức kỳ hạn. Cuộc gọi thật e2ef1be5: "mười hai" từng bị hỏi "triệu
# hay tỷ".
_BO_LUNG_KY_HAN = re.compile(r"\b(?:trong vong|trong|ky han|thoi han|tra gop|tra dan|tra)\s*$")


_CHI_TIENG_DEM = re.compile(
    r"^(?:(?:a|da|vang|o|u|um|uh|khoang|tam|chung|chac|gi|day|do|ay|ne|thi|the)\s*)*$")


def ai_vua_hoi(ai_truoc: str) -> str:
    """Câu hỏi CUỐI của AI hỏi ý gì: "term", "income", "amount" hoặc "" (không hỏi ý nào)."""
    if "?" not in (ai_truoc or ""):
        return ""
    cuoi = fold(re.split(r"[.!]\s+", ai_truoc.strip())[-1])
    return ("term" if _AI_HOI_KY_HAN.search(cuoi) else
            "income" if _AI_HOI_THU_NHAP.search(cuoi) else
            "amount" if _AI_HOI_TIEN.search(cuoi + "?") else "")


def _so_tran_tro_troi(text: str, q: Quantity) -> bool:
    """Câu chỉ có một con số trần NHỎ với vài tiếng đệm ("hai mươi", "tầm hai mươi gì đấy").

    Có "vay / lấy / thôi / đi" ("anh vay hai trăm thôi") là khách nói rõ ý chốt
    số tiền. Từ 100 trở lên thì không thể là số tháng hay thu nhập tính bằng
    triệu, chỉ còn nghĩa số tiền - cũng không tính.
    """
    rest = fold(text[:q.start] + " " + text[q.end:]).strip(" .,!?:")
    return (q.kind == "bare" and q.value is not None and q.value < 100
            and bool(_CHI_TIENG_DEM.fullmatch(rest)))


def luot_truoc_bo_lung_ky_han(khach_truoc: str) -> bool:
    return bool(_BO_LUNG_KY_HAN.search(fold(khach_truoc or "").strip(" .,!?")))


def _apply(state: LoanState, text: str, turn: int, ai_truoc: str = "",
           khach_truoc: str = "") -> None:
    state.amount_updated = state.term_updated = state.unit_confirmed = False
    state.income_updated = state.nhan_de_nghi = False
    normal = fold(text).strip(" .,!?:")
    if is_readback(text):
        return
    de_nghi = _DE_NGHI_KY_HAN.search(unicodedata.normalize("NFC", (ai_truoc or "").lower()))
    gat = re.sub(r"[^a-z0-9]+", " ", normal).strip()
    if de_nghi and gat and _CHI_GAT.fullmatch(gat) and _GAT_LOI.search(gat):
        so, don_vi = int(de_nghi.group(1)), de_nghi.group(2)
        state.term = Fact("known", Decimal(so * (12 if don_vi == "năm" else 1)),
                          f"{so} {don_vi}", turn)
        state.term_updated = state.nhan_de_nghi = True
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
    # Khách sửa tần suất của đúng mức thu nhập đã khai từ tháng sang năm. Không
    # thể tiếp tục giữ đó là thu nhập tháng, cũng không được lấy ``một năm`` làm
    # kỳ hạn vay hay lấy số tiền này đè principal. Để trạng thái mơ hồ cho tầng
    # hội thoại hỏi lại mức thu nhập theo tháng.
    if (state.income.status == "known" and state.income.value is not None
            and _SUA_DON_VI_THU_NHAP_NAM.search(normal)
            and not _NEO_KHOAN_VAY_RO_RANG.search(normal)):
        annual_money = next((q for q in quantities(text)
                             if q.kind == "money" and q.value == state.income.value), None)
        if annual_money:
            state.income = Fact("ambiguous", raw=text, turn=turn, owner=state.income.owner)
            state.income_updated = True
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
    ai = fold(ai_truoc or "")
    # Câu hỏi CUỐI của AI mới là thứ khách đang đáp.
    ai_hoi = ai_vua_hoi(ai_truoc)
    if luot_truoc_bo_lung_ky_han(khach_truoc):
        ai_hoi = "term"
    da_co_du_kien = state.amount.status != "unknown" or state.term.status != "unknown"
    # A bare correction can refer to income when it is the only established
    # numeric fact. Keep this separate from `da_co_du_kien`: treating income as
    # an established loan fact would make unrelated bare numbers look like a
    # new principal or term.
    correction_target = ("income" if state.income.status != "unknown"
                         and state.amount.status == "unknown"
                         and state.term.status == "unknown" else None)
    established = da_co_du_kien or bool(ai_hoi)
    candidates: dict[str, list[Quantity]] = {"amount": [], "term": [], "income": []}
    income_owners: dict[tuple[int, int], str] = {}
    ignored_income = False
    negated_roles: set[str] = set()
    previous: tuple[Quantity, str | None] | None = None
    # Khoảng kỳ hạn xét TRƯỚC từng con số: các số trong khoảng không được đem đi
    # làm số tiền hay một kỳ hạn lẻ. Vai của cả khoảng vẫn do `_role` quyết, nên
    # "đi làm được 4-5 tháng" hay "tất toán 4-5 tháng rồi" không thành kỳ hạn vay.
    # AI vừa hỏi thu nhập, khách đáp chỉ gồm con số ("mười lăm mười sáu gì đấy"):
    # mọi con số trong câu là thu nhập. Một con số thì `_role` đã lo; ở đây là
    # trường hợp HAI con số, mỗi số làm "phần còn lại" của số kia hết trống.
    cac_so = quantities(text)
    con_lai = text
    for q in sorted(cac_so, key=lambda x: -x.start):
        con_lai = con_lai[:q.start] + " " + con_lai[q.end:]
    chi_co_so_dap_thu_nhap = (ai_hoi == "income" and len(cac_so) >= 2 and bool(
        _ONLY_NUMBER.fullmatch(fold(con_lai).strip(" .,!?:"))))
    vung = None if chi_co_so_dap_thu_nhap else khoang_ky_han(text)
    if vung:
        q_khoang = Quantity(text[vung[0]:vung[1]], vung[0], vung[1], None, "duration")
        if _role(text, q_khoang, da_co_du_kien, ai_hoi, correction_target) == "term" and not _negated(text, q_khoang):
            state.term = Fact("ambiguous", raw=vung[4], turn=turn, khoang=(vung[2], vung[3]))
            state.term_updated = True
    for q in cac_so:
        if vung and q.start < vung[1] and q.end > vung[0]:
            continue
        role = _role(text, q, da_co_du_kien, ai_hoi, correction_target)
        if role is None and chi_co_so_dap_thu_nhap and q.kind in ("bare", "money"):
            role = "income"
        if role is None and _xac_nhan_lai_so_cu(text, q, state.amount):
            role = "amount"
        elif role is None and established and re.search(
                r"\b(?:van|giu nguyen|cu la)\s*$", fold(text[:q.start])):
            role = "term" if q.kind == "duration" else "amount"
        if role is None and previous and previous[1] and _ALTERNATIVE.fullmatch(
                fold(text[previous[0].end:q.start])):
            role = previous[1]
        if role == "income":
            owner = _income_owner(text, q)
            if (correction_target == "income" and state.income.owner
                    and not _ANCHORS.search(fold(text[:q.start]))):
                owner = state.income.owner
            if not owner:
                ignored_income = True
                previous = q, None
                continue
            income_owners[(q.start, q.end)] = owner
        previous = q, role
        # A negated amount in an established discussion still clears the old
        # fact even when 'không phải' lacks another explicit loan keyword.
        if _negated(text, q):
            if role:
                negated_roles.add(role)
            elif (established or correction_target) and re.fullmatch(
                    r"\s*(?:chu )?khong phai\s*", fold(text[:q.start])):
                negated_roles.add(correction_target or (
                    "term" if q.kind == "duration" else "amount"))
            continue
        if role:
            candidates[role].append(q)
    for name, choices in candidates.items():
        if not choices:
            continue
        owner = (income_owners.get((choices[-1].start, choices[-1].end), "")
                 if name == "income" else "")
        distinct = {(q.value, q.kind) for q in choices}
        # Two different numbers require either an explicit correction between
        # them or a clarification. 'A hay B' must not become an arbitrary B.
        giua = fold(text[choices[-2].end:choices[-1].start]) if len(choices) > 1 else ""
        correction = len(choices) > 1 and (_CORRECTION.search(giua) or _TU_SUA.search(giua))
        if name == "amount" and len(choices) == 1 and _xac_nhan_lai_so_cu(
                text, choices[0], state.amount):
            fact = Fact("known", state.amount.value, choices[0].raw, turn)
        else:
            fact = (_fact(choices[-1], turn, owner) if len(distinct) == 1 or correction
                    else Fact("ambiguous", raw=" / ".join(q.raw for q in choices), turn=turn,
                              owner=owner))
        if (name == "income" and len(choices) == 2 and fact.status == "ambiguous"
                and None not in (choices[0].value, choices[1].value)
                and not text[choices[0].end:choices[1].start].strip()):
            dau, sau_so = choices[0].value, choices[1].value
            he_so = 10**6 if choices[1].kind == "bare" and _suy_don_vi() else 1
            if 0 < dau < sau_so <= dau * 2 and (choices[1].kind == "money" or he_so > 1):
                fact = Fact("ambiguous", raw=fact.raw, turn=turn,
                            khoang=(dau * he_so, sau_so * he_so), owner=owner)
        # Con số KHÔNG kèm đơn vị: "vay hai trăm", "lương hai chục". Số tiền vay
        # suy theo sản phẩm (`don_vi_suy_ra`); thu nhập tháng thì luôn là triệu.
        if fact.status == "missing_unit" and fact.coefficient is not None:
            # Số tiền ĐÃ chốt mà khách buông một con số trần, không "vay", không lời
            # sửa, AI cũng không vừa hỏi tiền: chưa chắc là đổi số tiền (có thể là
            # đáp một câu hỏi khác mà máy không nhận ra). Không lặng lẽ đè - để
            # nguyên "thiếu đơn vị" cho tầng luật hỏi lại như trước.
            de_len_so_cu = (name == "amount" and state.amount.status == "known"
                            and ai_hoi != "amount" and _so_tran_tro_troi(text, choices[-1]))
            don_vi = (None if de_len_so_cu
                      else don_vi_suy_ra(fact.coefficient, fact.raw) if name == "amount"
                      else 10**6 if name == "income" and _suy_don_vi()
                      and 1 <= fact.coefficient < 1000 else None)
            if don_vi:
                fact = Fact("known", fact.coefficient * don_vi, fact.raw, turn, owner=owner)
            thang = ky_han_suy_ra(fact.coefficient, fact.raw) if name == "term" else None
            if thang:
                fact = Fact("known", Decimal(thang), fact.raw + " tháng", turn)
        setattr(state, name, fact)
        setattr(state, name + "_updated", True)
    for name in negated_roles:
        if not candidates[name]:
            setattr(state, name, Fact("ambiguous", raw=text, turn=turn))
            if name in ("amount", "term"):
                setattr(state, name + "_updated", True)
    if da_co_du_kien and _co_y_sua(text) and not any(candidates.values()):
        # Unknown replacements invalidate their own slot, not always principal.
        owners = [a.lastgroup for a in _ANCHORS.finditer(normal) if a.lastgroup != "correction"]
        target = owners[-1] if owners else "amount"
        if target in candidates and not (target == "income" and ignored_income):
            setattr(state, target, Fact("ambiguous", raw=text, turn=turn))
            if target in ("amount", "term"):
                setattr(state, target + "_updated", True)
    if _RUT_LAI_TIEN.search(normal):
        state.amount = Fact("ambiguous", raw=text, turn=turn)
        state.amount_updated = True
    if _CALC.search(normal) and (state.amount_updated or state.term_updated
                                or not re.search(r"\b(?:luong|thu nhap)\b", normal)):
        state.request = "calculation"


def resolve(history: list[dict] | None = None, text: str | None = None) -> LoanState:
    """Pure chronological reducer. Ignores all assistant quantities, trừ đúng một
    trường hợp: khách gật với thời hạn AI hỏi thẳng (`_DE_NGHI_KY_HAN`).

    Callers may pass a history already containing the current user turn. Only
    the trailing duplicate is suppressed; repeated older corrections matter.
    """
    entries = list(history or [])
    if text is not None and not (entries and entries[-1].get("role") == "user"
                                and entries[-1].get("content") == text):
        entries.append({"role": "user", "content": text})
    state = LoanState()
    ai_truoc = khach_truoc = ""
    for i, row in enumerate(entries):
        if row.get("role") == "user":
            noi = unicodedata.normalize("NFC", row.get("content") or "")
            _apply(state, noi, i, ai_truoc, khach_truoc)
            ai_truoc, khach_truoc = "", noi
        elif row.get("role") == "assistant":
            ai_truoc = row.get("content") or ""
    return state
