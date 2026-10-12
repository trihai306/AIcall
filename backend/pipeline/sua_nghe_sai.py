"""Sửa lời khách bị máy nghe sai hoặc nói cụt TRƯỚC khi luật, kho và mô hình xét.

Bộ thử 156 lượt (12-10-2026): "xuất bao nhiêu" (lãi suất bao nhiêu), "cho anh
thông tin về khoảng tay" (khoản vay), "phí thường liên" (thường niên), và lượt
chỉ có một chữ "lãi" đều rơi xuống đường mô hình tự viết, mô hình đáp "em chưa
rõ ý" hoặc "chưa có thông tin về khoản vay của anh". Tài liệu có sẵn câu trả lời;
thứ hỏng là câu hỏi không còn giống câu nào trong kho.

Chỉ sửa cụm KHÔNG có nghĩa nào khác trong tiếng Việt ("lãi xuất", "tín chóp").
Cụm còn nghĩa thật thì không đụng, sai một chữ ở đây là đổi lời khách.
"""

import re
import unicodedata

# (mẫu trên chữ CÓ DẤU, chữ thay). Thứ tự có nghĩa: cụm dài trước.
_CUM = [
    (r"\b(?:lãi|lải|nãi)\s+(?:xuất|xuấc)\b", "lãi suất"),
    (r"\bnãi\s+suất\b", "lãi suất"),
    (r"\bmiễn\s+(?:lải|nãi)\b", "miễn lãi"),
    (r"\b(?:thường|thương)\s+liên\b", "thường niên"),
    (r"\btín\s+(?:chóp|chắp|chấm|chớp)\b", "tín chấp"),
    (r"\btính\s+dụng\b", "tín dụng"),
    (r"\bkhoảng\s+(?:tay|vai|vay)\b", "khoản vay"),
    (r"\bhạng\s+mức\b", "hạn mức"),
    (r"\bxổ\s+(đỏ|hồng)\b", r"sổ \1"),
    # Lẫn tr/ch: "chả trong hai mươi lăm thì mỗi tháng chả bao nhiêu". Chỉ đổi
    # khi chữ đứng cạnh cho thấy đây là TRẢ nợ; "chả biết", "chả cần" để yên.
    (r"\bchả\b(?= (?:trong|bao nhiêu|góp|nợ|trước|hết|gốc|dần|nổi|lãi)\b)", "trả"),
    (r"(?<=mỗi tháng )chả\b", "trả"),
    # Giọng miền Trung và lẫn l/n ở từ để hỏi.
    (r"\bthế\s+lào\b", "thế nào"),
    (r"\b(lãi|phí|làm|tính)\s+răng\b", r"\1 sao"),
    (r"\blãi\s+(?:sao|thế nào|ra sao|như nào)\b(?! kê)", "lãi suất thế nào"),
]
_SO_CHU = r"(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mươi|chục|\d+)"
_CUM += [
    # "vay một tỷ rưỡi hai mươi năm tháng trả bao nhiêu": lời nói không có dấu
    # phẩy nên bộ đọc số ghép "rưỡi" với số sau và đọc "hai mươi năm tháng" là
    # 25 tháng (khách đóng vai 12-10-2026: tính ra "1 tỷ trong 25 tháng").
    (rf"\b(rưỡi|rưởi) (?=(?:hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|\d+)\b[^,.]{{0,15}}\b(?:năm|tháng)\b)",
     r"\1, "),
    (rf"\b({_SO_CHU} năm) (?=(?:mỗi |một )?tháng (?:trả|đóng|góp|phải|hết|mất|nộp)\b)", r"\1, "),
]
_CUM = [(re.compile(m, re.IGNORECASE), t) for m, t in _CUM]

# Lượt chỉ có một hai chữ: khách hỏi cụt, hoặc máy nuốt mất nửa đầu câu.
_DEM = r"(?:ờ|à|ừ|thế|vậy|thì|còn|em ơi|em|ạ|nhỉ|hả|cơ)"
_CUT = [
    (r"(?:lãi|lãi suất|xuất|suất)(?: (?:bao nhiêu|nhiêu|thế nào|sao|mấy))?", "lãi suất bao nhiêu"),
    (r"phí(?: (?:bao nhiêu|thế nào|sao))?", "phí bao nhiêu"),
    (r"hạn mức(?: (?:bao nhiêu|thế nào|sao))?", "hạn mức bao nhiêu"),
    (r"tối đa(?: (?:là )?bao nhiêu)?", "hạn mức tối đa bao nhiêu"),
    (r"(?:hồ sơ|thủ tục)(?: (?:thế nào|sao|gì))?", "cần giấy tờ gì"),
    (r"điều kiện(?: (?:thế nào|sao|gì))?", "điều kiện là gì"),
]
_CUT = [(re.compile(rf"^(?:{_DEM} )*{m}(?: {_DEM})*$", re.IGNORECASE), t) for m, t in _CUT]


# Lượt trước bị cắt giữa chừng ("trả trong ờ") và lượt này là phần còn lại ("ba
# năm"): ghép lại thành một câu. Chỉ ghép khi lượt trước dừng ở một chữ CHỜ con
# số và lượt này mở đầu bằng con số.
_BO_LUNG = re.compile(r"\b(trong|khoảng|tầm|chừng|độ|kỳ hạn|là)$", re.IGNORECASE)
_MO_BANG_SO = re.compile(
    r"^(?:\d|(?:một|hai|ba|bốn|tư|năm|sáu|bảy|tám|chín|mười|chục|trăm|vài|mấy|nửa)\b)", re.IGNORECASE)
_DEM_CUOI = re.compile(rf"(?: (?:ờ|à|ừm|ừ|ờm|thì))+$", re.IGNORECASE)
# Người lẫn l/n ("nãi suất", "nà", "anh nàm công nhân") nói "hai năm" thành "hai
# lăm". Chỉ đổi khi CHÍNH khách này đã lộ thói quen đó trong cuộc, và sau chữ
# "lăm" không còn đơn vị nào ("hai lăm triệu", "ba lăm tuổi" là 25, 35 thật).
_NGONG_LN = re.compile(r"\b(nà|nàm|nãi|nương|thế lào|nghe lào|lào)\b", re.IGNORECASE)
_X_LAM = re.compile(
    r"\b(một|hai|ba|bốn|sáu|bảy|tám|chín|mười)\s+lăm\b"
    r"(?!\s+(?:mươi|triệu|tỷ|tỉ|nghìn|ngàn|trăm|chục|tuổi|tháng|năm|phần|củ|chai)\b)", re.IGNORECASE)
_HOI_TRO = re.compile(rf"^(?:{_DEM} )*(?:bao )?nhiêu(?: {_DEM})*$", re.IGNORECASE)


def sua_nghe_sai(text: str, luot_truoc: str = "",
                 lich_su_khach: tuple[str, ...] | list[str] = ()) -> tuple[str, str]:
    """Trả (lời đã sửa, mô tả). Mô tả rỗng là không đổi gì.

    `luot_truoc` là lời khách ở lượt ngay trước: lượt chỉ có "nhiêu" là nửa sau
    của câu hỏi vừa bị cắt ("lãi" ... "nhiêu"), nên hỏi tiếp đúng chủ đề đó.
    """
    goc = unicodedata.normalize("NFC", text or "")
    ra, sua = goc, []
    for mau, thay in _CUM:
        moi = mau.sub(thay, ra)
        if moi != ra:
            sua.append(mau.sub(thay, mau.search(ra).group(0)))
            ra = moi
    if _X_LAM.search(ra) and any(_NGONG_LN.search(c or "") for c in (*lich_su_khach, goc)):
        ra = _X_LAM.sub(lambda m: f"{m.group(1)} năm", ra)
        sua.append("lẫn l/n: lăm -> năm")
    tran = re.sub(r"[.,!?…]+", " ", ra).strip()
    tran = re.sub(r"\s+", " ", tran)
    for mau, thay in _CUT:
        if mau.match(tran):
            sua.append(f"nói cụt -> {thay}")
            ra = thay
            break
    else:
        truoc = sua_nghe_sai(luot_truoc)[0].strip() if luot_truoc else ""
        dang_do = _DEM_CUOI.sub("", re.sub(r"[.,!?…]+", " ", truoc).strip())
        if (truoc and _BO_LUNG.search(dang_do) and len(dang_do.split()) <= 6
                and _MO_BANG_SO.match(tran) and len(tran.split()) <= 5):
            ra = f"{dang_do} {tran}"
            sua.append(f"ghép lượt bị cắt -> {ra}")
        if _HOI_TRO.match(tran) and truoc and len(truoc.split()) <= 5:
            ra = truoc if "bao nhiêu" in truoc else f"{truoc} bao nhiêu"
            sua.append(f"nối lượt trước -> {ra}")
    return (ra, "; ".join(sua)) if sua else (text, "")


_QUANH_SO_TIEN = frozenset(
    "tầm khoảng chừng độ cỡ chắc được không em ạ thôi anh chị tôi mình cần là thì nhé nha hả "
    "à ừ ờ thế vậy đó đấy cũng phải lấy".split())
_CAN_TIEN = re.compile(r"\b(vay|mượn|cần (?:ít |chút |một ít |thêm )?(?:tiền|vốn)|kẹt tiền|thiếu tiền)\b",
                       re.IGNORECASE)


def neo_so_tien_vay(text: str, lich_su_khach, san_pham: str) -> tuple[str, str]:
    """"tầm trăm rưỡi được không em" sau khi khách kể đang cần tiền -> "vay tầm trăm rưỡi...".

    Sổ dữ kiện khoản vay chỉ nhận con số có chữ "vay" neo trước (hoặc khi AI vừa
    hỏi số tiền). Khách đóng vai 12-10-2026: khách nói "đang cần ít tiền làm đám
    cưới", AI hỏi vu vơ, khách đáp "tầm trăm rưỡi được không em" - con số không
    được gắn vào khoản vay, và hai lượt hỏi trả góp sau đó đều hỏng theo.

    Chỉ thêm chữ "vay" khi: sản phẩm là vay, khách ĐÃ nói cần tiền/vay ở lượt
    trước, lượt này gần như chỉ có một con số, và con số đó không thể là kỳ hạn
    (có đơn vị tiền, hoặc số trần lớn hơn 60).
    """
    from backend.pipeline.du_kien_khoan_vay import quantities
    goc = text or ""
    if "vay" not in (san_pham or "").lower() or re.search(r"\bvay\b", goc, re.IGNORECASE):
        return text, ""
    # "chị cần gấp tám chục triệu đóng học cho con": chính lượt này nói CẦN một
    # khoản tiền. Thêm chữ "vay" ngay sau "cần" để sổ dữ kiện nhận đó là số tiền vay.
    m = re.search(r"\bcần\b((?:\s+(?:gấp|khoảng|tầm|chừng|độ|thêm|có|đúng))*)\s+(?=\S)", goc, re.IGNORECASE)
    if m:
        sau = [q for q in quantities(goc[m.end():]) if q.value is not None]
        if sau and sau[0].kind == "money" and sau[0].start <= 2:
            moi = goc[:m.start()] + "cần vay" + m.group(1) + " " + goc[m.end():]
            return moi, f"neo số tiền vay -> {moi}"
    if not any(_CAN_TIEN.search(c or "") for c in list(lich_su_khach or [])[-4:]):
        return text, ""
    cac = [q for q in quantities(goc) if q.value is not None]
    if len(cac) != 1 or cac[0].kind == "duration":
        return text, ""
    q = cac[0]
    if q.kind != "money" and not (q.kind == "bare" and q.value > 60):
        return text, ""
    con = re.findall(r"\w+", (goc[:q.start] + " " + goc[q.end:]).lower())
    if len(con) > 6 or any(c not in _QUANH_SO_TIEN for c in con):
        return text, ""
    return f"vay {goc.strip()}", f"neo số tiền vay -> vay {goc.strip()}"
