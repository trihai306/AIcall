"""Chuẩn hoá text trước khi đưa vào F5-TTS.

Checkpoint ViVoice được train trên text tiếng Việt đã lowercase (xem README của
model: "Normalize to lowercase format"). Chuỗi VIẾT HOA - nhất là tên viết tắt -
gần như không xuất hiện trong dữ liệu train, nên model đọc ra sai bét: "ABC"
thành "y phê", "AC", "EC"... tuỳ lần sample.

Cách chữa là đọc hộ model: bung viết tắt thành tên chữ cái tiếng Việt rồi
lowercase toàn bộ, để mọi thứ vào model đều nằm trong phân bố nó từng thấy.
"""

import re

# Tên chữ cái tiếng Việt khi đánh vần. Dùng dạng tách bằng dấu cách thay vì gạch
# nối ("e lờ" chứ không phải "e-lờ") vì gạch nối là ký tự hiếm trong tập train.
#
# Chọn dạng NGẮN nhất còn nghe ra chữ cái ("ét" chứ không "ét sì", "em" chứ không
# "em mờ"): đo thực tế thấy tên chữ cái càng dài model càng dễ nhoè chúng vào
# nhau - "ét sì em mờ ét sì" (SMS) bị đọc thành "Etsy em mở Etsy".
VI_LETTER_NAMES = {
    "a": "a",      "b": "bê",     "c": "xê",      "d": "dê",
    "e": "e",      "f": "ép",     "g": "giê",     "h": "hát",
    "i": "i",      "j": "gi",     "k": "ca",      "l": "e lờ",
    "m": "em",     "n": "en",     "o": "o",       "p": "pê",
    "q": "quy",    "r": "e rờ",   "s": "ét",      "t": "tê",
    "u": "u",      "v": "vê",     "w": "vê kép",  "x": "ích",
    "y": "i dài",  "z": "dét",
}

# Viết tắt đọc theo lối riêng, không đánh vần từng chữ. Khớp trước bảng chữ cái.
ACRONYM_OVERRIDES = {
    "OTP": "ô tê pê",
    "ATM": "a tê em",
    "PIN": "pin",
    "SMS": "ét em ét",
    "VND": "việt nam đồng",
    "USD": "đô la mỹ",
    "CCCD": "căn cước công dân",
    "CMND": "chứng minh nhân dân",
    # Mã giấy tờ / tổ chức hay gặp trong tư vấn vay. Thiếu chúng thì F5 đọc ra
    # thứ không ai hiểu - đo được STT nghe "KT3" thành "kiev ba".
    "KT3": "ca tê ba",
    "CIC": "xê i xê",
    "BHXH": "bảo hiểm xã hội",
    "HĐLĐ": "hợp đồng lao động",
}

# "22-60", "12 - 60" - hai số NGẮN nối bằng gạch là một KHOẢNG, đọc là "đến".
#
# Cả hai vế phải ≤ 3 chữ số và KHÔNG dính chữ cái ở trước. Bản đầu chỉ đòi
# "chữ số - chữ số" nên nuốt luôn mã hợp đồng: "MN-2023-11204" thành "em en
# hai nghìn không trăm hai ba ĐẾN mười một nghìn hai trăm linh tư". Mã giấy tờ
# và mã hợp đồng đầy dấu gạch, không cái nào là khoảng.
_KHOANG_GACH_RE = re.compile(
    r"(?<![A-Za-zĐđ-])\b(\d{1,3})\s*[-–—]\s*(\d{1,3})\b(?![-\d])")

# Phải kể cả "Đ": `[A-Z]` là bảng chữ cái ASCII nên bỏ sót "HĐLĐ", "TĐ" - đúng
# loại viết tắt hay gặp nhất trong hồ sơ vay.
# 2 chữ hoa liên tiếp trở lên, cho phép chữ số dính đuôi ("KT3").
# `\b[A-Z]{2,}\b` KHÔNG khớp "KT3": sau "T" là "3" - vẫn là ký tự từ - nên
# không có ranh giới từ ở đó, cả cụm trượt luôn. Đúng lỗi làm "KT3" lọt xuống
# F5 nguyên dạng và bị đọc thành "kiev ba".
_ACRONYM_RE = re.compile(r"\b[A-ZĐ]{2,}\d*\b")

# TÊN NGÂN HÀNG kiểu HOA + "Bank" dính liền: VPBank, TPBank, MBBank, HDBank...
#
# `_ACRONYM_RE` KHÔNG bắt được chúng: `\b[A-Z]{2,}\b` đòi ranh giới từ ngay sau
# cụm hoa, mà sau "VP" là "ank" - vẫn là ký tự từ - nên cả cụm trượt và "VPBank"
# xuống tới F5 nguyên dạng chuỗi Latin. F5 phải tự đoán cách đọc, MỖI LẦN MỘT
# KIỂU. Đo 12-08-2026, cho STT nghe lại 10 lần sinh: sai 10/10, ra "vấp banh",
# "phập banh", "vạc bánh", "việt anh", "váp banh"... Đây là lỗi chiếm phần lớn
# trong toàn bộ bản ghi khách gửi về (thư mục "Check giọng", 5 đợt thu).
#
# "Bank" -> "ben" là chọn theo ĐO, không phải theo cách viết phiên âm cho đẹp.
# Thử 4 cách, mỗi cách sinh rồi cho STT nghe lại (`scripts/thu_cach_doc_bank.py`):
#
#   nguyên xi "VPBank"   -> 3/3 lần ra kết quả KHÁC NHAU
#   "vê pê bank"         -> 3/3 khác nhau
#   "vê pê banh"         -> 3/3 khác nhau
#   "vê pê ben"          -> 4/4 nghe ra đúng "vpbank"      <- chọn cái này
#
# Kèm theo: ở các bản bất ổn, chữ "ạ" ngay sau cũng hỏng lây ("cạ", "gạo",
# "cả") - hỏng một chỗ kéo theo chỗ bên cạnh, nên đừng coi đây là lỗi lẻ.
_NGAN_HANG_BANK_RE = re.compile(r"\b([A-ZĐ]{2,})Bank\b")

# DẤU CÂU LẶP: "......" -> "."
#
# F5 cấp thời lượng theo SỐ BYTE của chữ, nên 6 dấu chấm được tính là 6 ký tự
# phải đọc trong khi chúng không có âm nào. Model thừa ra một khoảng thời gian
# không có chữ để lấp, và nó lấp bằng cách kéo giãn các từ quanh đó rồi bịa thêm
# một âm ở cuối.
#
# Kịch bản khách đang dùng có "…bên em...... Không biết…" - và ĐÚNG chỗ đó là
# nơi mọi bản ghi bị hỏng: "bêm", "bmm", "bmin", "bên mi", "bên em em".
#
# Đo 12-08-2026 (`scripts/thu_dau_cham.py`, 5 lần mỗi bản, bỏ nhiễu tên ngân
# hàng): giữ "......" cho 5 lỗi/5 lượt, thay bằng một dấu chấm còn 2 lỗi/5 lượt
# và có một lượt SẠCH HOÀN TOÀN. Trước khi chữa tên ngân hàng thì chênh lệch này
# bị lỗi tên át mất (20 so với 17) nên đo lần đầu tưởng là nhiễu.
#
# Sửa ở ĐÂY chứ không sửa kịch bản: kịch bản do người dùng viết, họ cứ viết như
# cũ. Xem "GHI CHU.txt" trong thư mục Check giọng - bản vá này đã được đề xuất
# từ 08-08 nhưng chưa bao giờ có trong code.
_DAU_LAP_RE = re.compile(r"([.,!?;:…])\1+")


# Tên ngân hàng đọc KHÔNG theo bảng chữ cái chung. Để riêng ở đây thay vì sửa
# `VI_LETTER_NAMES`: "P" đọc thành "bê" là riêng của VPBank, đổi trong bảng
# chung thì "OTP" hoá "ô tê bê" - sai một chỗ khác.
#
# Người dùng chốt cách đọc này (13-08-2026). Số đo của tôi nghiêng về "vê pê
# ben" vì nó ổn định hơn khi cho STT nghe lại, NHƯNG thước đo đó chỉ nói máy
# nghe ra gì, không nói tai người thấy đúng hay sai. Tên riêng thì người dùng
# mới là bên biết khách nghe quen kiểu nào.
NGAN_HANG_OVERRIDES = {
    "VPBank": "vê bê banh",
}


def _doc_ten_ngan_hang(m: re.Match) -> str:
    if m.group(0) in NGAN_HANG_OVERRIDES:
        return NGAN_HANG_OVERRIDES[m.group(0)]
    chu = " ".join(VI_LETTER_NAMES.get(c.lower(), c) for c in m.group(1))
    return f"{chu} banh"

_VOWELS = set("aeiouy")
# Âm tiết tiếng Việt chỉ kết thúc bằng nguyên âm hoặc một trong các phụ âm cuối này.
_VALID_CODAS = {"", "c", "ch", "m", "n", "ng", "nh", "p", "t", "i", "y", "o", "u"}


def _looks_like_vi_syllable(word: str) -> bool:
    """Từ viết hoa này là một âm tiết tiếng Việt hay là viết tắt?

    Từ có dấu tự bảo vệ được (regex không khớp vì "À" không nằm trong [A-Z]),
    nhưng từ KHÔNG dấu thì không: "ANH", "EM", "XIN" đều lọt vào regex viết tắt
    và bị đánh vần thành "a en hát". Mà "anh" là từ dày đặc nhất trong kịch bản
    bán hàng - hỏng nó là hỏng cả cuộc gọi.

    Phân biệt bằng phụ âm cuối: "anh" -> coda "nh" hợp lệ nên là từ; "abc" ->
    coda "bc", "otp" -> "tp", "atm" -> "tm" đều không phải phụ âm cuối tiếng
    Việt nên là viết tắt. Không có nguyên âm (SMS, VND, TP) thì chắc chắn viết tắt.
    """
    w = word.lower()
    idx = [i for i, c in enumerate(w) if c in _VOWELS]
    if not idx:
        return False
    if idx != list(range(idx[0], idx[-1] + 1)):
        return False  # nguyên âm rời rạc => nhiều âm tiết => viết tắt
    return w[idx[-1] + 1:] in _VALID_CODAS


def _spell_out(match: re.Match) -> str:
    word = match.group(0)
    if word in ACRONYM_OVERRIDES:
        return ACRONYM_OVERRIDES[word]
    if _looks_like_vi_syllable(word):
        return word  # để .lower() ở dưới xử lý
    return " ".join(VI_LETTER_NAMES.get(c.lower(), c) for c in word)


# "Dạ" đứng đầu câu mà dính liền chữ sau thì F5-TTS đọc nhoè thành "giả".
# Đo trên PhoWhisper, mỗi câu 8 lượt:
#   "Dạ anh chị cần chuẩn bị chứng minh nhân dân"   -> sai 7/8 (87%)
#   "Dạ, anh chị cần chuẩn bị chứng minh nhân dân"  -> sai 0/8
#   "Dạ anh cho em hỏi mình thuê bao nhiêu ngày"    -> sai 7/8 (87%)
#   "Dạ, anh cho em hỏi mình thuê bao nhiêu ngày"   -> sai 0/8
# Nặng nhất khi chữ sau bắt đầu bằng nguyên âm ("anh" 87%, "em" 50%, "mình" 12%),
# đúng kiểu ghép âm qua ranh giới từ. Dấu phẩy tạo chỗ ngắt nhịp nên tách hẳn ra.
# Không nghe rõ được chỗ ngắt này - độ dài audio trước/sau chênh dưới 40ms.
# Đây là lỗi của mô hình gốc, sửa ở khâu chuẩn hoá vì rẻ hơn train lại.
_DA_DAU_CAU_RE = re.compile(r"^(\s*dạ)\s+(?=\w)", re.IGNORECASE)


# --- Đọc số thành chữ ------------------------------------------------------
# VÌ SAO LÀM BẰNG CODE CHỨ KHÔNG NHỜ LLM: prompt từng có quy tắc "viết số thành
# chữ khi nói tiền", và mô hình 7B đọc SAI - tài liệu ghi lãi suất 7.9%/năm mà nó
# nói "sáu phẩy chín phần trăm" (6.9%). Trong cuộc gọi bán sản phẩm tài chính,
# báo sai lãi suất là lỗi nặng. Chuyển số sang chữ là quy tắc xác định, viết bằng
# code thì luôn đúng - đừng giao cho mô hình đoán.
_CHU_SO = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")


def _doc_ba_so(n: int, day_du: bool) -> str:
    """Đọc một nhóm 3 chữ số. `day_du` = có nhóm lớn hơn đứng trước nên phải
    đọc đủ cả 'không trăm'."""
    tram, chuc, dv = n // 100, (n // 10) % 10, n % 10
    ra = []
    if tram or day_du:
        ra += [_CHU_SO[tram], "trăm"]
    if chuc == 0 and dv and (tram or day_du):
        ra += ["lẻ", _CHU_SO[dv]]
    elif chuc == 1:
        ra.append("mười")
        if dv == 5:
            ra.append("lăm")          # mười lăm, không phải "mười năm"
        elif dv:
            ra.append(_CHU_SO[dv])
    elif chuc > 1:
        ra += [_CHU_SO[chuc], "mươi"]
        if dv == 1:
            ra.append("mốt")          # hai mươi mốt
        elif dv == 4:
            ra.append("tư")           # hai mươi tư
        elif dv == 5:
            ra.append("lăm")          # hai mươi lăm
        elif dv:
            ra.append(_CHU_SO[dv])
    elif dv and not (tram or day_du):
        ra.append(_CHU_SO[dv])
    return " ".join(ra)


def doc_so(n: int) -> str:
    """Đọc số nguyên thành chữ tiếng Việt."""
    if n < 0:
        return "âm " + doc_so(-n)
    if n == 0:
        return "không"
    nhom, i = [], 0
    while n > 0:
        nhom.append(n % 1000)
        n //= 1000
        i += 1
    ten = ("", "nghìn", "triệu", "tỷ", "nghìn tỷ")
    ra = []
    for k in range(len(nhom) - 1, -1, -1):
        if nhom[k] == 0:
            continue
        ra.append(_doc_ba_so(nhom[k], day_du=(k < len(nhom) - 1)))
        if ten[k]:
            ra.append(ten[k])
    return " ".join(x for x in ra if x)


# Số có thể kèm % ngay sau. Dấu phân cách nghìn (1.000 / 1,000) phải phân biệt
# với dấu thập phân (7.9 / 7,9): nhóm 3 chữ số theo sau là phân cách nghìn.
# `(?:\s*(%))?` chứ không `\s*(%)?`: viết cách kia thì khoảng trắng bị nuốt cả khi
# KHÔNG có dấu %, làm "12 - 60" thành "mười hai- sáu mươi".
# Nhìn trước chỉ chặn chữ, KHÔNG chặn "/": "7.9%/năm" là dạng rất hay gặp.
_SO_RE = re.compile(
    r"(?<![\w/])(\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,](\d+))?(?:\s*(%))?(?!\w)"
)


def _doc_khop(m: re.Match) -> str:
    nguyen, thap_phan, phan_tram = m.group(1), m.group(2), m.group(3)
    # bỏ dấu phân cách nghìn
    ra = doc_so(int(re.sub(r"[.,]", "", nguyen)))
    if thap_phan:
        ra += " phẩy " + " ".join(_CHU_SO[int(c)] for c in thap_phan)
    if phan_tram:
        ra += " phần trăm"
    return ra


# Số điện thoại Việt Nam: 9-11 chữ số, bắt đầu bằng 0, có thể có dấu ngăn.
# ĐỌC TỪNG CHỮ SỐ, không đọc như số lượng.
#
# Lỗi thật bắt được 2026-08-10 trên cuộc gọi thử: "0912345678" bị đọc thành
# "chín trăm mười hai TRIỆU ba trăm bốn mươi lăm nghìn sáu trăm bảy mươi tám" -
# tức thành một SỐ TIỀN, và mất luôn số 0 đầu. Khách nghe xong không có cách nào
# ghi lại được số.
_SDT_RE = re.compile(r"(?<![\d.,])0\d{1,3}[.\s-]?\d{3}[.\s-]?\d{3,4}(?![\d.,])")
_DOC_CHU_SO = {"0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn",
               "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín"}


def doc_tung_chu_so(s: str) -> str:
    """Đọc rời từng chữ số: "0912" -> "không chín một hai"."""
    return " ".join(_DOC_CHU_SO[c] for c in s if c.isdigit())


def doc_so_trong_cau(text: str) -> str:
    """Thay mọi con số trong câu bằng cách đọc thành chữ.

    Số điện thoại xử TRƯỚC: nó cũng là một dãy chữ số nên `_SO_RE` sẽ nuốt mất
    nếu để sau, và đọc nó như số lượng là sai hẳn nghĩa.
    """
    text = _SDT_RE.sub(lambda m: doc_tung_chu_so(m.group(0)), text)
    return _SO_RE.sub(_doc_khop, text)


# --- Hàng rào: số AI nói phải có trong tài liệu ----------------------------
# VÌ SAO CẦN: mô hình đọc SAI số một cách HỆ THỐNG, không phải ngẫu nhiên. Đo
# trên `tuvan-qwen`, hỏi 6 lần ở mỗi mức temperature với tài liệu ghi rõ 7.9%:
#     temp 0.7 -> đúng 1/6      temp 0.4 -> 0/6
#     temp 0.2 -> 0/6           temp 0.0 -> 0/6
# Nó nói "sáu phẩy chín" (6.9%), nhầm đúng chữ số hàng đơn vị. Hạ nhiệt độ càng
# làm nó ỔN ĐỊNH Ở CHỖ SAI. Sửa bằng prompt đã thử và không ăn thua.
#
# Trong cuộc gọi bán sản phẩm tài chính, báo sai lãi suất là lỗi không chấp nhận
# được, nên phải chặn ở tầng cuối thay vì tin mô hình.
#
# CỐ Ý CHỈ CHẶN SỐ THẬP PHÂN (lãi suất, phí). Số nguyên như "năm trăm triệu" đo
# thấy mô hình đọc đúng, mà chặn rộng thì dễ sửa nhầm câu vốn đúng.
_TU_SO = {t: i for i, t in enumerate(_CHU_SO)}
_PHAY_CHU_RE = re.compile(
    r"\b(" + "|".join(_CHU_SO) + r")\s+phẩy\s+(" + "|".join(_CHU_SO) + r")\b",
    re.IGNORECASE)
_PHAY_SO_RE = re.compile(r"\b(\d+)[.,](\d)\b")


def _so_thap_phan_trong(tai_lieu: str) -> set[tuple[int, int]]:
    """Các số thập phân xuất hiện trong tài liệu, dạng (phần nguyên, phần lẻ)."""
    return {(int(a), int(b)) for a, b in _PHAY_SO_RE.findall(tai_lieu or "")}


# --- Hàng rào thứ hai: SỐ TIỀN NGUYÊN (triệu / tỷ) -------------------------
# Lưới trên chỉ canh số thập phân, vì đo được mô hình đọc đúng số nguyên. ĐIỀU ĐÓ
# KHÔNG CÒN ĐÚNG. Bắt được trong cuộc gọi thật (2026-08-05), tài liệu ghi rõ
# "Hạn mức: lên đến 500 triệu đồng":
#
#     khách: anh muốn tư vấn về khoản vay năm mươi triệu
#     AI   : bên em chỉ nhận tối đa SÁU TRĂM TRIỆU đồng một lượt   <- bịa
#
# Báo sai hạn mức trong cuộc gọi bán sản phẩm tài chính là lỗi nặng ngang báo sai
# lãi suất, nên phải chặn ở tầng cuối y như vậy.
_DON_VI_TIEN = ("triệu", "tỷ", "tỉ")
_HE_SO = {"triệu": 10 ** 6, "tỷ": 10 ** 9, "tỉ": 10 ** 9}

# "500 triệu" hoặc "năm trăm triệu" - bắt cả hai dạng vì mô hình viết lẫn lộn.
# Lookbehind kể cả DẤU CHẤM/PHẨY, không chỉ `\w` và `/`.
#
# Thiếu chúng thì nó khớp MỘT PHẦN của số thập phân: nhóm `\d{3}` đòi đúng ba
# chữ số, nên "2.78 triệu" không khớp được từ đầu, và regex khớp luôn cụm
# "78 triệu" nằm giữa. Lưới chặn thay đúng cụm đó và để lại "2." đằng trước:
#
#   "trả khoảng 2.78 triệu đồng"  ->  "trả khoảng 2.năm trăm triệu đồng"
#
# Bắt được 13-08-2026 trong bộ test nhiều hội thoại - khách nghe một chuỗi
# không có nghĩa, mà log chỉ ghi là đã "chặn số sai" nên nhìn như đang chạy tốt.
_TIEN_SO_RE = re.compile(
    r"(?<![\w/.,])(\d{1,3}(?:[.,]\d{3})*)\s*(" + "|".join(_DON_VI_TIEN) + r")\b",
    re.IGNORECASE)
# Các từ có thể ghép thành một số tiếng Việt. Sắp XUỐNG DẦN theo độ dài để
# regex không khớp trước phần đầu của từ dài hơn ("mười" trước "mươi").
_TU_GHEP_SO = sorted(set(_CHU_SO) | {"mười", "mươi", "trăm", "nghìn", "lăm",
                                     "mốt", "tư", "linh", "lẻ"},
                     key=len, reverse=True)
_MOT_TU = "(?:" + "|".join(_TU_GHEP_SO) + ")"
_TIEN_CHU_RE = re.compile(
    r"\b(" + _MOT_TU + r"(?:\s+" + _MOT_TU + r"){0,4})\s+("
    + "|".join(_DON_VI_TIEN) + r")\b", re.IGNORECASE)


def _chu_thanh_so(cum: str) -> int | None:
    """"năm trăm" -> 500, "hai mươi tư" -> 24. None nếu không hiểu."""
    tong, hien = 0, 0
    for t in cum.lower().split():
        if t in ("linh", "lẻ"):
            continue
        if t == "trăm":
            hien = (hien or 1) * 100
        elif t in ("mươi", "mười"):
            hien = (hien or 1) * 10
        elif t == "nghìn":
            tong += (hien or 1) * 1000
            hien = 0
        elif t in _TU_SO:
            hien += _TU_SO[t]
        elif t == "lăm":
            hien += 5
        elif t == "mốt":
            hien += 1
        elif t == "tư":
            hien += 4
        else:
            return None
    return (tong + hien) or None


# Tiền viết TOÀN chữ số, không có chữ đơn vị: "2.000.000.000 đồng".
# Đây từng là LỖ HỔNG của lưới chặn: `_TIEN_SO_RE` đòi phải có "triệu"/"tỷ" đi
# kèm, nên "2 tỷ đồng" thì chặn được mà "2.000.000.000 đồng" thì lọt thẳng.
# Mô hình hay viết dạng chữ số này khi trả lời về hạn mức, và đó đúng là cách
# con số 2 tỷ (sai, tài liệu ghi 500 triệu) tới được tai khách.
# Đòi ÍT NHẤT hai nhóm nghìn để khỏi nuốt nhầm năm ("2024 đồng" không tồn tại,
# nhưng "12.000" thì đúng là tiền).
# CHỈ khớp phần chữ số, KHÔNG nuốt chữ đứng sau. Bản đầu nuốt cả "đồng" và cả
# khoảng trắng, nên "300.000.000 được không" ra "năm trăm triệuđược không" -
# dính chữ. Để nguyên "đồng" thì câu thay ra cũng tự nhiên hơn.
# Chặn khi có "triệu"/"tỷ" đứng ngay sau: chỗ đó là việc của `_TIEN_SO_RE`.
_TIEN_CHU_SO_RE = re.compile(
    r"(?<![\w/])(\d{1,3}(?:[.,]\d{3}){2,})\b(?!\s*(?:triệu|tỷ|tỉ))",
    re.IGNORECASE)


def _tien_trong(van_ban: str) -> set[float]:
    """Mọi số tiền (quy về đồng) xuất hiện trong văn bản."""
    ra = set()
    for so, dv in _TIEN_SO_RE.findall(van_ban or ""):
        ra.add(int(re.sub(r"[.,]", "", so)) * _HE_SO[dv.lower()])
    for cum, dv in _TIEN_CHU_RE.findall(van_ban or ""):
        n = _chu_thanh_so(cum)
        if n:
            ra.add(n * _HE_SO[dv.lower()])
    for so in _TIEN_CHU_SO_RE.findall(van_ban or ""):
        ra.add(float(re.sub(r"[.,]", "", so)))
    return ra


def chan_tien_sai(text: str, tai_lieu: str,
                  khach_noi: str = "") -> tuple[str, str | None]:
    """Bỏ số tiền AI nói mà KHÔNG có trong tài liệu và KHÔNG do khách nêu ra.

    Ba ràng buộc cố ý:
      1. Số khách vừa nói thì KHÔNG đụng - AI nhắc lại con số của khách là đúng.
      2. Số có trong tài liệu thì để nguyên, kể cả khi nó nằm ở phần ví dụ.
      3. Thay bằng số LỚN NHẤT trong tài liệu (thường là hạn mức), và chỉ khi
         tài liệu có số tiền để mà thay. Không có thì trả nguyên - đoán bừa còn
         tệ hơn.

    Trả (văn bản đã sửa, mô tả chỗ sửa hoặc None).
    """
    hop_le = _tien_trong(tai_lieu) | _tien_trong(khach_noi)
    if not hop_le:
        return text, None
    sua = None

    # Diễn đạt số thay thế bằng ĐƠN VỊ CỦA CHÍNH NÓ, đừng ép về đơn vị của câu
    # gốc: 500 triệu ép sang "tỷ" thành 0 -> câu ra "không tỷ đồng". Chọn đơn vị
    # lớn nhất mà vẫn cho số nguyên >= 1.
    def _dien_dat(dong: float) -> str:
        for ten in ("tỷ", "triệu"):
            n = int(dong // _HE_SO[ten])
            if n >= 1 and dong % _HE_SO[ten] == 0:
                return f"{doc_so(n)} {ten}"
        return f"{doc_so(int(dong))} đồng"

    def _xu_ly(gia_tri: float, goc: str, dv: str) -> str:
        nonlocal sua
        if gia_tri in hop_le:
            return goc
        # Thay bằng số GẦN NHẤT, không phải số LỚN NHẤT.
        #
        # Bản cũ dùng `max(hop_le)` với lý do "thường là hạn mức". Nó làm câu
        # trả lời SAI HƠN hẳn khi khách đã nêu một con số. Bắt được 13-08-2026
        # trong bộ test nhiều hội thoại:
        #
        #   khách: "anh cần vay 80 triệu"
        #   model: "vay 78 triệu"                     (lệch nhẹ)
        #   lưới : "78 triệu -> NĂM TRĂM TRIỆU"       (sai gấp 6 lần)
        #
        # 500 triệu là hạn mức trong tài liệu, và nó là số lớn nhất nên luôn
        # thắng. Lấy số gần nhất thì ra "80 triệu" - đúng con số khách vừa nói.
        # Không có trường hợp nào "gần nhất" tệ hơn "lớn nhất": lớn nhất chỉ
        # đúng khi chính nó là số gần nhất.
        moi_gt = min(hop_le, key=lambda v: abs(v - gia_tri))
        moi = _dien_dat(moi_gt)
        sua = f"{goc} -> {moi}"
        return moi

    def _t_so(m):
        gt = int(re.sub(r"[.,]", "", m.group(1))) * _HE_SO[m.group(2).lower()]
        return _xu_ly(gt, m.group(0), m.group(2))

    def _t_chu(m):
        n = _chu_thanh_so(m.group(1))
        if not n:
            return m.group(0)
        return _xu_ly(n * _HE_SO[m.group(2).lower()], m.group(0), m.group(2))

    def _t_chu_so(m):
        # Tiền viết TOÀN chữ số: "2.000.000.000 đồng". Trước đây lọt hẳn - lưới
        # chỉ biết dạng có chữ đơn vị đi kèm ("2 tỷ"), mà mô hình lại hay viết
        # dạng chữ số khi trả lời về hạn mức. Đó đúng là đường con số 2 tỷ (sai,
        # tài liệu ghi 500 triệu) tới được tai khách.
        return _xu_ly(float(re.sub(r"[.,]", "", m.group(1))), m.group(0), "")

    text = _TIEN_SO_RE.sub(_t_so, text)
    text = _TIEN_CHU_RE.sub(_t_chu, text)
    # Chạy SAU hai cái trên: "500 triệu" đã được xử ở `_TIEN_SO_RE`, chạy trước
    # thì regex chữ-số thuần nuốt mất phần "500" và bỏ lại "triệu" chơ vơ.
    text = _TIEN_CHU_SO_RE.sub(_t_chu_so, text)
    return text, sua


def chan_so_sai(text: str, tai_lieu: str) -> tuple[str, str | None]:
    """Sửa số thập phân AI nói nếu nó KHÔNG có trong tài liệu.

    Chỉ sửa khi tài liệu có ĐÚNG MỘT số thập phân - lúc đó không có gì mơ hồ về
    ý định. Tài liệu có nhiều số thì để nguyên: đoán bừa còn tệ hơn.

    Trả (văn bản đã sửa, mô tả chỗ sửa hoặc None).
    """
    hop_le = _so_thap_phan_trong(tai_lieu)
    if len(hop_le) != 1:
        return text, None
    ng, le = next(iter(hop_le))

    sua = None

    def _thay_chu(m):
        nonlocal sua
        a, b = _TU_SO[m.group(1).lower()], _TU_SO[m.group(2).lower()]
        if (a, b) in hop_le:
            return m.group(0)
        sua = f"{a},{b} -> {ng},{le}"
        return f"{_CHU_SO[ng]} phẩy {_CHU_SO[le]}"

    def _thay_so(m):
        nonlocal sua
        if (int(m.group(1)), int(m.group(2))) in hop_le:
            return m.group(0)
        sua = f"{m.group(0)} -> {ng}.{le}"
        return f"{ng}.{le}"

    text = _PHAY_CHU_RE.sub(_thay_chu, text)
    text = _PHAY_SO_RE.sub(_thay_so, text)
    return text, sua


# --------------------------------------------------------------------------
# Bớt "dạ/ạ" thừa
# --------------------------------------------------------------------------
# Dọn hai tật của model NỀN, không phải của prompt.
#
# 1. SỐ THỨ TỰ ĐẦU CÂU. `CORE_RULES` là một danh sách đánh số (1-11, luật riêng
#    của kịch bản nối tiếp từ 12). Model bám vai hội thoại lỏng thì thấy danh
#    sách đang dở và ĐỌC TIẾP SỐ thay vì trả lời. Đo trên Vistral-7B-Chat:
#        'cho anh hỏi khoản vay năm mươi triệu' -> '14. Anh muốn đăng ký sản phẩm nào?'
#        'đúng rồi'                             -> '1. Dạ anh Anh là ai ạ?'
#    Qwen không bị. Sửa ở đây thay vì bỏ đánh số trong prompt: đánh số giúp
#    model theo được luật, mà lỗi này chỉ vài model mắc.
#
#    Bắt buộc có KHOẢNG TRẮNG sau dấu chấm, nếu không sẽ ăn nhầm "7.9% một năm"
#    - đúng con số quan trọng nhất của tài liệu.
_SO_TT_DAU_RE = re.compile(r"^\s*\d{1,2}\s*[.)]\s+")

# 2. XƯNG "TÔI". Luật 1 đã ghi rõ phải xưng "em", nhưng model nền không tuân thì
#    prompt không ép được. Vỡ vai nhân viên tư vấn ngay câu đầu.
#    "chúng tôi" phải đổi thành "bên em" chứ không phải "chúng em" - đó mới là
#    cách nhân viên ngân hàng nói.
_CHUNG_TOI_RE = re.compile(r"\bchúng\s+tôi\b", re.IGNORECASE)
_TOI_RE = re.compile(r"\btôi\b", re.IGNORECASE)
# "bạn" khi nó là ĐẠI TỪ gọi khách. Loại trừ "bạn bè", "bạn hàng", "bạn đọc" -
# đó là danh từ, thay vào thành "anh chị bè" thì thành câu vô nghĩa.
_BAN_RE = re.compile(r"\bbạn\b(?!\s+(?:bè|hàng|đọc|thân))", re.IGNORECASE)


def _giu_hoa(goc: str, moi: str) -> str:
    """Giữ chữ hoa đầu nếu từ gốc viết hoa - "Tôi" -> "Em", "tôi" -> "em"."""
    return moi[:1].upper() + moi[1:] if goc[:1].isupper() else moi


# Chữ Hán, Kana, Hangul, VÀ dấu câu toàn rộng của chúng (，。！？、「」).
# KHÔNG đụng tiếng Việt: chữ Việt có dấu nằm ở dải Latin mở rộng.
#
# Dải dấu câu (U+3000-303F, U+FF00-FFEF) PHẢI có: thiếu nó thì cắt chữ Hán xong
# còn sót "，。" giữa câu - đã đo được đúng lỗi này khi thử trên câu thật.
_CHU_NGOAI_RE = re.compile(
    r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
    r"\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]+")
# Khoảng trắng thừa còn lại sau khi cắt, và khoảng trắng trước dấu câu.
_TRANG_THUA_RE = re.compile(r"\s{2,}")
_TRANG_TRUOC_DAU_RE = re.compile(r"\s+([.,!?;:])")


# Từ chức năng tiếng Anh - không từ nào là từ tiếng Việt. Dùng CHÚNG để nhận
# tiếng Anh, KHÔNG dùng "chữ không dấu": mã giấy tờ (CMND, CCCD, KT3, CIC) và
# tên riêng (ABC) cũng không dấu, cắt theo dấu là cắt nhầm cả câu hợp lệ.
_TU_ANH = {
    "the", "your", "you", "and", "with", "for", "are", "is", "was", "will",
    "can", "may", "other", "actual", "amount", "income", "depend", "dependent",
    "factors", "vary", "please", "that", "this", "from", "have", "has", "based",
    "of", "to", "in", "or", "on", "we", "our", "it", "be", "as", "at", "by",
}
_TU_RE = re.compile(r"[A-Za-z]+")
# Bao nhiêu từ chức năng LIỀN NHAU thì coi là đã trượt sang tiếng Anh. 3 là mức
# an toàn: "combo", "OK", "CIC" đứng lẻ không bao giờ đủ chuỗi.
_NGUONG_TU_ANH = 3


def _cat_duoi_tieng_anh(text: str) -> tuple[str, str | None]:
    """Cắt từ chỗ câu trượt sang tiếng Anh tới hết chuỗi.

    Dạng lọt đo được (qwen2.5:7b, 2/36 lượt = 5,6%): câu tiếng Việt trọn vẹn,
    rồi CHẤM, rồi cả đoạn tiếng Anh chạy tới hết -
        "...lên đến 500 triệu đồng. Dependent on your income and other factors,
         the actual amount may vary."
    Nên cắt tới hết chuỗi là đúng dạng, không phải cắt từng từ.
    """
    dem = 0
    for m in _TU_RE.finditer(text):
        if m.group(0).lower() in _TU_ANH:
            dem += 1
            if dem >= _NGUONG_TU_ANH:
                # Lùi về đầu cụm: bỏ luôn cả những từ tiếng Anh đứng trước nó.
                dau = m.start()
                for m2 in _TU_RE.finditer(text):
                    if m2.start() > dau:
                        break
                    if m2.group(0).lower() in _TU_ANH:
                        dau = min(dau, m2.start())
                        break
                return text[:dau].rstrip(" ,;:-").rstrip(), text[dau:].strip()
        else:
            dem = 0
    return text, None


def chan_chu_ngoai(text: str) -> tuple[str, str | None]:
    """Bỏ chữ Hán/Nhật/Hàn khỏi câu sắp đọc cho khách.

    Trả (câu đã sạch, cụm đầu tiên bị bỏ) - cụm đó để ghi log, vì lọt chữ nước
    ngoài là dấu hiệu model đang trượt khỏi tiếng Việt và cần biết tần suất.

    Vì sao cần: qwen2.5 là model Trung Quốc. Đo 08-08 trên qwen2.5:3b, nó trả
    lời "CMND hoặc CCCD bản chính và 复印件" - chữ Hán nghĩa là "bản photo".
    F5-TTS không đọc được, khách nghe ra tiếng lạ ngay giữa câu tư vấn.

    Bỏ chứ không thay bằng gì: đoán nghĩa rồi dịch là tự bịa thêm một tầng sai.
    Câu còn lại có thể hơi cụt ("bản chính và, Hộ khẩu") nhưng vẫn đọc được và
    không sai sự thật - hơn hẳn để TTS đọc bừa.
    """
    if not text:
        return text, None

    dinh = None
    tim = _CHU_NGOAI_RE.search(text)
    if tim:
        dinh = tim.group(0)
        text = _CHU_NGOAI_RE.sub("", text)
        text = _TRANG_THUA_RE.sub(" ", text)
        text = _TRANG_TRUOC_DAU_RE.sub(r"\1", text).strip()

    # Tiếng Anh xét SAU khi đã bỏ chữ Hán: câu có thể lọt cả hai.
    text, duoi = _cat_duoi_tieng_anh(text)
    if duoi and not dinh:
        dinh = duoi

    text = _TRANG_THUA_RE.sub(" ", text)
    text = _TRANG_TRUOC_DAU_RE.sub(r"\1", text)
    return text.strip(), dinh


def sua_xung_ho(text: str, goi_khach: str = "anh chị") -> str:
    """Bỏ số thứ tự đầu câu, ép cách AI TỰ XƯNG và cách nó GỌI KHÁCH.

    Hai chuyện khác nhau, bản cũ chỉ lo chuyện đầu:
      - tự xưng: "tôi" -> "em", "chúng tôi" -> "bên em"
      - gọi khách: "bạn" -> `goi_khach`

    Vì sao thêm vế sau (đo 08-08): đổi sang qwen2.5:3b thì mô hình gọi khách là
    "bạn" ở 4/9 lượt - "Bạn có thể vay tối đa 500 triệu". Tổng đài ngân hàng gọi
    cho khách mà xưng "bạn" là sai vai, nghe như quảng cáo dạo. Prompt có dặn
    nhưng model nhỏ không giữ được, nên chặn bằng code.

    `goi_khach` lấy từ `gender_detect.xung_ho()` để hợp giới tính đã đoán; không
    chắc thì mặc định "anh chị" - trung tính, không sai được với ai.
    """
    if not text:
        return text
    text = _SO_TT_DAU_RE.sub("", text)
    text = _CHUNG_TOI_RE.sub(lambda m: _giu_hoa(m.group(0), "bên em"), text)
    text = _TOI_RE.sub(lambda m: _giu_hoa(m.group(0), "em"), text)
    text = _BAN_RE.sub(lambda m: _giu_hoa(m.group(0), goi_khach), text)
    return text


# --------------------------------------------------------------------------
# Dùng chung quãng nghỉ với bộ cắt mảnh, để chỗ ngắt do bỏ "ạ" nghe giống hệt
# chỗ ngắt tự nhiên. (text_chunker không import gì nên không sợ vòng lặp.)
from backend.pipeline.text_chunker import (  # noqa: E402
    DAU_KET_CAU, NGHI_CHAM_MS, NGHI_PHAY_MS)

# " ạ" ngay trước dấu câu hoặc hết chuỗi. Không cần lo đụng vào "Dạ": "D" là ký
# tự chữ nên \b không khớp ở giữa từ.
_A_CUOI_RE = re.compile(r"\s+ạ(?=[.,!?;:]|\s|$)")
_DA_DAU_RE = re.compile(r"^\s*Dạ[\s,]+", re.IGNORECASE)
# "ạ" mắc kẹt ở ĐẦU mảnh: bộ cắt mảnh cắt theo số từ nên cắt trúng ngay trước nó
# ("... gần nhất" | "ạ. Anh chị ..."). Không có khoảng trắng đứng trước nên
# _A_CUOI_RE không thấy, mà giao nguyên cho TTS thì mảnh mở đầu bằng "ạ." đọc
# nghe hụt. Bỏ hẳn, và KHÔNG tính là cái "ạ" được giữ của lượt.
#
# Nhóm 1 giữ lại DẤU CÂU đi kèm. Bỏ luôn cả dấu là mất chỗ ngắt câu - đo được:
# "... sao kê lương ba tháng gần nhất Anh chị đang làm ở đâu" đọc liền một hơi,
# và mảnh chỉ có mỗi "ạ?" thì biến mất kéo theo dấu hỏi của cả câu.
_A_MO_DAU_RE = re.compile(r"^\s*ạ\s*([.,!?;:]*)\s*")
_CO_CHU_RE = re.compile(r"\w")


class BotLichSu:
    """Bớt "ạ"/"Dạ" cho MỘT lượt trả lời, gọi được trên từng mảnh khi đang stream.

    Vì sao phải làm ở tầng code: mô hình kết thúc CÂU NÀO CŨNG bằng "ạ" và mở đầu
    LƯỢT NÀO CŨNG bằng "Dạ" - đo trong hội thoại dựng thử là 15/15 câu và 8/8
    lượt. Nghe qua điện thoại thành ra lải nhải.

    Đã thử gỡ bằng prompt và KHÔNG được (`scripts/do_dem_a.py`, 6 câu × 2 lần):

        prompt hiện tại        1.00 "ạ"/câu
        bỏ chỗ mớm "ạ"         1.04
        bỏ hẳn khối ví dụ      1.00
        bỏ cả hai              0.96

    Tức "ạ" nằm trong trọng số LoRA (bộ dữ liệu train sinh ra từ chính prompt cũ,
    câu đáp nào cũng có "ạ"), prompt không với tới. Giống hệt vụ đọc sai số: việc
    gì prompt không chữa được thì chặn bằng code.

    KHÔNG bỏ sạch: "ạ" là dấu hiệu lễ phép, cắt hết thì cộc lốc với khách lớn
    tuổi - đúng nhóm khách của sản phẩm này. Giữ MỘT lần mỗi lượt.

    Giữ cái ĐẦU TIÊN chứ không phải cái cuối, vì mảnh được giao cho TTS ngay khi
    cắt xong - lúc đó chưa biết lượt còn mấy câu nữa.

    Trả về CHUỖI RỖNG nếu bỏ xong mảnh không còn chữ nào (mảnh chỉ có mỗi "ạ.").
    Nơi gọi phải bỏ qua mảnh rỗng thay vì giao cho TTS - nhưng vẫn phải cộng
    `nghi_truoc_ms` vào quãng nghỉ, không thì mất luôn chỗ ngắt câu.
    """

    def __init__(self, bo_da: bool = False):
        self._con_a = True
        self._bo_da = bo_da
        self._dau_luot = True
        # Quãng nghỉ phải chèn TRƯỚC mảnh vừa xử lý, vì chỗ ngắt câu nằm ở chữ
        # "ạ" đầu mảnh mà ta vừa bỏ. Đặt lại mỗi lần gọi.
        self.nghi_truoc_ms = 0.0

    def __call__(self, doan: str) -> str:
        if self._dau_luot:
            self._dau_luot = False
            if self._bo_da:
                doan = _DA_DAU_RE.sub("", doan, count=1)
                doan = doan[:1].upper() + doan[1:] if doan else doan

        self.nghi_truoc_ms = 0.0
        m = _A_MO_DAU_RE.match(doan)
        if m:
            dau = m.group(1)
            self.nghi_truoc_ms = (NGHI_CHAM_MS if dau.startswith(DAU_KET_CAU)
                                  else NGHI_PHAY_MS if dau else 0.0)
            doan = doan[m.end():]

        if self._con_a:
            # Chừa lại đúng một "ạ", bỏ những cái sau nó trong cùng mảnh.
            m = _A_CUOI_RE.search(doan)
            if m:
                self._con_a = False
                doan = doan[:m.end()] + _A_CUOI_RE.sub("", doan[m.end():])
        else:
            doan = _A_CUOI_RE.sub("", doan)

        return doan if _CO_CHU_RE.search(doan) else ""



# --- Dấu gạch chéo -----------------------------------------------------------
#
# F5 đọc "/" thành "như": khách nghe "dư nợ của anh NHƯ chị là..." - vô nghĩa và
# lộ ngay là máy. Lỗi này nằm im rất lâu vì "anh/chị" là cụm mô hình dùng ở gần
# như MỌI câu, mà không ai soi phần chữ trước khi nó xuống TTS.
#
# Ba dạng, ba cách đọc khác nhau - gộp một luật là sai:
_XIEN_DON_VI_RE = re.compile(r"/\s*(năm|tháng|ngày|tuần|giờ|quý)\b", re.I)
_XIEN_XUNG_HO_RE = re.compile(r"\banh\s*/\s*chị\b", re.I)
_XIEN_CHUNG_RE = re.compile(r"(?<=\w)\s*/\s*(?=\w)")


# Thành ngữ đọc liền, không phải liệt kê. "24/7" mà đổi thành "hoặc" ra
# "hai mươi tư hoặc bảy" - vô nghĩa.
_XIEN_THANH_NGU = {"24/7": "hai mươi tư trên bảy"}


def doc_dau_xien(text: str) -> str:
    """Đổi "/" thành chữ đọc được, theo đúng nghĩa của từng dạng."""
    if "/" not in text:
        return text
    # "7,9%/năm" -> "một năm". KHÔNG dùng "mỗi năm": lãi suất nói "một năm" tự
    # nhiên hơn trong tiếng Việt tổng đài.
    text = _XIEN_DON_VI_RE.sub(lambda m: f" một {m.group(1).lower()}", text)
    # "anh/chị" -> "anh chị". Người Việt nói liền, không đọc "hoặc".
    text = _XIEN_XUNG_HO_RE.sub("anh chị", text)
    # Còn lại là liệt kê: "CMND/CCCD" -> "CMND hoặc CCCD".
    return _XIEN_CHUNG_RE.sub(" hoặc ", text)


def normalize_for_tts(text: str) -> str:
    """Bung viết tắt rồi lowercase, cho khớp phân bố text lúc train model.

    Không đụng tới dấu câu: F5-TTS dùng dấu câu để ngắt nhịp, bỏ đi thì giọng
    đọc liền tù tì một hơi. Chỉ THÊM một dấu phẩy sau "Dạ" mở đầu (xem trên).
    """
    if not text:
        return text
    # Gộp dấu câu lặp NGAY ĐẦU, trước mọi luật khác: "......" chiếm ngân sách
    # thời lượng của F5 mà không có âm nào - xem `_DAU_LAP_RE`.
    text = _DAU_LAP_RE.sub(r"\1", text)
    # Đọc số TRƯỚC khi bung viết tắt: bung trước thì "500 triệu" đã thành chữ
    # lẫn lộn, khó bắt lại bằng biểu thức chính quy.
    # Thành ngữ thay TRƯỚC khi đọc số: `doc_so_trong_cau` biến "24" thành chữ
    # rồi thì chuỗi "24/7" không còn để mà nhận ra.
    for _cu, _moi in _XIEN_THANH_NGU.items():
        text = text.replace(_cu, _moi)
    # Khoảng viết bằng dấu gạch. PHẢI làm trước `doc_so_trong_cau`, không thì
    # "22" đã thành chữ và không còn hai chữ số cạnh gạch để nhận ra nữa.
    # Không bỏ hẳn dấu gạch: "hai mươi hai-sáu mươi tuổi" đọc lên nghe dính,
    # phải thành "từ hai mươi hai ĐẾN sáu mươi tuổi".
    text = _KHOANG_GACH_RE.sub(r"\1 đến \2", text)
    text = doc_so_trong_cau(text)
    # Xử "/" TRƯỚC khi bung viết tắt: "CMND/CCCD" phải còn nguyên dạng viết tắt
    # thì luật liệt kê mới nhận ra hai vế.
    text = doc_dau_xien(text)
    # Tên ngân hàng TRƯỚC luật viết tắt chung: phải ăn nguyên cụm "VPBank" khi
    # chữ "Bank" còn nguyên chữ hoa đầu. Chạy sau `_ACRONYM_RE` thì không sao
    # (nó vốn không khớp), nhưng chạy sau `.lower()` thì hỏng hẳn.
    text = _NGAN_HANG_BANK_RE.sub(_doc_ten_ngan_hang, text)
    text = _ACRONYM_RE.sub(_spell_out, text).lower()
    return _DA_DAU_CAU_RE.sub(r"\1, ", text)


# --- bỏ câu lùi thừa ở đầu lượt -----------------------------------------------

# Câu lùi lấy nguyên văn từ quy tắc 3 và khối ví dụ trong `llm_service.CORE_RULES`.
# Mô hình 3B chép chúng làm câu mở đầu RỒI VẪN trả lời đúng ngay sau - đo được
# 07-08 bằng `scripts/cham_chat_luong.py`:
#
#     "Dạ em xin phép kiểm tra lại và báo anh/chị thời gian giải ngân là trong
#      vòng 24 giờ sau khi phê duyệt."
#
# Khách nghe thành "để em kiểm tra đã... à mà 24 giờ" - vừa thừa vừa làm câu trả
# lời mất tin cậy. Prompt KHÔNG dứt được (đã thử nói thẳng trong quy tắc 3 và
# thêm quy tắc 12, vẫn còn), nên chặn bằng code - cùng cách dự án đã xử lý số
# đọc sai và "ạ" lải nhải.
_CAU_LUI_RE = re.compile(
    r"^\s*(?:dạ[\s,]*)?em\s+(?:xin\s+phép\s+)?(?:sẽ\s+)?kiểm\s+tra\s+lại"
    # Nhánh DÀI phải đứng trước: regex lấy nhánh khớp đầu tiên, để "anh" lên đầu
    # thì "anh/chị" chỉ ăn được chữ "anh" và bỏ lại "/chị" giữa câu.
    r"(?:\s+và\s+báo)?(?:\s+(?:lại\s+)?(?:cho\s+)?(?:anh\s*/\s*chị|anh\s+chị|anh|chị))?"
    r"(?:\s+ngay)?(?:\s+ạ)?\s*[.,!;:]*\s*",
    re.IGNORECASE,
)


def bo_cau_lui_thua(text: str) -> str:
    """Bỏ câu "em xin phép kiểm tra lại và báo anh/chị" KHI phía sau đã có câu trả lời.

    CHỈ bỏ khi còn nội dung thật phía sau. Nếu mô hình thật sự không tra được thì
    câu đó CHÍNH LÀ câu trả lời - bỏ đi sẽ để lại một mảnh rỗng, tệ hơn hẳn.
    Ngưỡng "có nội dung thật": còn ít nhất 4 từ, hoặc có chữ số.
    """
    m = _CAU_LUI_RE.match(text or "")
    if not m:
        return text
    con = text[m.end():].strip()
    if not con:
        return text
    if not (re.search(r"\d", con) or len(con.split()) >= 4):
        return text
    # Giữ lại "Dạ" mở đầu cho tự nhiên - mọi lượt của bot đều mở bằng "Dạ".
    return con if con.lower().startswith("dạ") else "Dạ " + con[0].lower() + con[1:]
