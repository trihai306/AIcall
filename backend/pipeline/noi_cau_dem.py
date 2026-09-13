"""Join an already spoken lead-in to a fixed answer without rewriting facts.

Run this on the COMPLETE answer before tokenisation, synthesis and cache lookup.
Changing only response_chunk text would leave an old recording saying something
different. This is presentation logic, never number correction or paraphrasing.
"""
from __future__ import annotations

import re

from backend.pipeline.text_chunker import JITTER_MS, noi_lo, sap_cum_gop


_LE_PHEP = re.compile(r"^\s*(?:dạ(?:\s+vâng)?|vâng)(?:\s+ạ)?\b[\s,;:.!?]*", re.I)

# Chỉ những chủ đề có thể bỏ lặp mà bản thân chúng không mang điều kiện/số liệu.
# Giá trị là các cụm đầu câu trả lời được phép coi là phần chủ đề đã nói ở filler.
# Cố ý KHÔNG có các chủ đề nhạy nghĩa như nợ xấu, điều kiện vay, trả chậm...
# vì xóa nhầm một phần của chúng có thể đổi điều kiện nghiệp vụ.
_CHU_DE_LAP_AN_TOAN: dict[str, tuple[str, ...]] = {
    "lãi suất": ("mức lãi suất", "lãi suất"),
    "hạn mức vay": ("hạn mức vay", "hạn mức"),
    "hạn mức": ("hạn mức vay", "hạn mức"),
    "mức vay được": ("mức vay được", "mức vay", "hạn mức"),
    "hồ sơ": ("hồ sơ",),
    "giấy tờ": ("giấy tờ",),
    "thời hạn vay": ("thời hạn vay", "thời hạn"),
    "kỳ hạn": ("kỳ hạn",),
    "thời gian duyệt hồ sơ": ("thời gian duyệt hồ sơ", "thời gian duyệt"),
    "tiến độ duyệt": ("tiến độ duyệt", "tiến độ"),
    "ưu đãi hiện tại": ("ưu đãi hiện tại", "ưu đãi"),
    "chương trình đang có": ("chương trình đang có", "chương trình"),
    "phần tính toán": ("phần tính toán", "tính toán"),
    "khoản trả hàng tháng": ("khoản trả hàng tháng", "khoản trả"),
    "tăng hạn mức thẻ": ("tăng hạn mức thẻ", "hạn mức thẻ"),
    "các khoản phí": ("các khoản phí", "khoản phí", "phí"),
    "chi nhánh": ("chi nhánh",),
    "địa điểm": ("địa điểm",),
    "nơi làm hồ sơ": ("nơi làm hồ sơ",),
    "tất toán khoản vay": ("tất toán khoản vay", "tất toán"),
    "phần tài liệu": ("phần tài liệu", "tài liệu"),
    "bảo hiểm khoản vay": ("bảo hiểm khoản vay", "bảo hiểm"),
    "cách trả hàng tháng": ("cách trả hàng tháng", "cách trả"),
    "hồ sơ của anh chị": ("hồ sơ của anh chị", "hồ sơ"),
    "số liên lạc": ("số liên lạc",),
    "quy trình": ("quy trình",),
    "thủ tục": ("thủ tục",),
}


def _chuan_hoa_chu_de(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip(" \t\r\n,;:.!?" )).casefold()


def _chu_de_cau_dem(cau_dem: str) -> str:
    """Lấy chủ đề chỉ từ các frame filler rõ nghĩa, không suy đoán tự do."""
    text = _LE_PHEP.sub("", (cau_dem or "").strip(), count=1).strip()
    text = text.rstrip(" \t\r\n,;:.!?")
    # CHỈ khung kết "thì" mới được cắt chủ đề. Khung dấu phẩy (sau `bo_thi_cuoi`,
    # 13-09-2026) không đỡ được phần vị ngữ cụt: ghép thử câu trả lời thật ra
    # "Dạ về hồ sơ, chính gồm căn cước..." và "Dạ về hạn mức vay, tối đa của gói
    # vay..." - nghe như rớt chữ. Để nguyên "Dạ về hồ sơ, hồ sơ chính gồm..." là
    # cách nói thường ngày. Kho không còn mẩu nào kết "thì" nên nhánh cắt dưới đây
    # gần như không chạy nữa; giữ lại cho dữ liệu cũ.
    if not re.search(r"\bthì$", text, re.I):
        return ""
    match = re.match(r"^về\s+(.+?)(?:\s+bên\s+em)?\s+thì$", text, re.I)
    if not match:
        match = re.match(r"^về\s+(.+)$", text, re.I)
    if not match:
        match = re.match(r"^(.+?)\s+bên\s+em\s+thì$", text, re.I)
    if not match:
        return ""
    return _chuan_hoa_chu_de(match.group(1))


def _bo_chu_de_lap(cau_dem: str, text: str) -> str:
    chu_de = _chu_de_cau_dem(cau_dem)
    prefixes = _CHU_DE_LAP_AN_TOAN.get(chu_de)
    if not prefixes:
        return text
    for prefix in prefixes:
        match = re.match(rf"^{re.escape(prefix)}\b[\s,;:.-]*", text, re.I)
        if not match:
            continue
        tail = text[match.end():].strip()
        # "Dạ về lãi suất," + "của gói vay là từ 7.9%" cụt nghĩa: phần còn lại
        # mở bằng "của" là bổ ngữ CỦA chính chủ đề vừa cắt. Giữ nguyên câu.
        if re.match(r"^của\b", tail, re.I):
            return text
        # Không biến một câu chỉ có tên chủ đề thành chuỗi rỗng.
        if any(c.isalnum() for c in tail):
            return tail
    return text


def loi_sau_dem(cau_dem: str, tra_loi: str) -> str:
    """Remove repeated salutation/topic head while preserving answer facts.

Only a small allow-list of filler topic frames can lose a duplicated noun head.
Do not fuzzy-match topics, remove conditions, infer subjects or touch numbers.
An answer consisting only of an acknowledgement must remain an acknowledgement.
With no spoken lead-in the original answer is returned byte-for-byte.
"""
    if not (cau_dem or "").strip() or not (tra_loi or "").strip():
        return tra_loi
    text = tra_loi.strip()
    original = text
    # The opening can contain repeated politeness tokens. Do not match words
    # such as 'vâng lời' as a greeting, or remove a one-word answer altogether.
    while not re.match(r"^vâng\s+lời\b", text, re.I):
        match = _LE_PHEP.match(text)
        if not match:
            break
        tail = text[match.end():].strip()
        if not any(c.isalnum() for c in tail):
            return original
        text = tail
    return _bo_chu_de_lap(cau_dem, text)


def xep_ghep_dau(dau: tuple[str, float], cho: list, het_luot: bool,
                 du_dia_ms: float, uoc_sinh):
    """Use only existing filler playback headroom to merge the first clauses.

The regular comma/length rules still apply. Any clauses that do not fit the
remaining synthesis budget go back ahead of the end marker in original order.
This helper never waits and never cuts audio or joins across a sentence end.
"""
    dan, tra_lai = sap_cum_gop(dau, cho, het_luot)
    while len(dan) > 1 and uoc_sinh(noi_lo([t for t, _ in dan])) + JITTER_MS > du_dia_ms:
        tra_lai.insert(0, dan.pop())
    return dan, tra_lai
