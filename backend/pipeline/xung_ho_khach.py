"""Gọi khách theo đúng cách khách TỰ XƯNG trong cuộc gọi.

Cuộc gọi thật 13-10-2026: khách nói "tư vấn cho anh", "anh muốn vay mười hai
tháng" mà AI vẫn đáp "anh chị muốn vay trong bao lâu ạ" suốt cuộc. Đoán giới
tính bằng cao độ giọng (`gender_detect`) cần vài giây tiếng và hay rơi vào vùng
không chắc; lời khách tự xưng thì có ngay từ câu đầu và không phải đoán.

Chỉ đổi khi khách tự xưng RÕ (đại từ đứng ngay trước động từ nói về mình). Có
dấu hiệu khách xưng "em" hoặc đang gọi AI bằng chính đại từ đó ("chị ơi") thì
giữ "anh chị" - gọi sai còn tệ hơn gọi trung tính.
"""
from __future__ import annotations

import re

MAC_DINH = "anh chị"
_VAI = r"(anh|chị|cô|chú|bác)"
_DEM = r"(?:(?:thì|cũng|đang|mới|chỉ|đã|sẽ|vẫn|còn)\s+)?"
_VIEC_CUA_MINH = (
    r"(?:muốn|cần|hỏi|vay|gửi|lương|làm|định|tính|từng|nghe|bận|chưa|xem|bàn|trả|mở|dùng|"
    r"nhận|thấy|nghĩ|biết|hiểu|sợ|lo|mua|thu nhập|kinh doanh|hết|vừa|quan tâm|đang|không|"
    r"năm nay|\d+\s*tuổi|(?:hai|ba|bốn|năm|sáu|bảy)\s+mươi)")
_TU_XUNG = re.compile(rf"(?:^|[\s,.!?])(?:cho|của|giúp|với)?\s*{_VAI}\s+{_DEM}{_VIEC_CUA_MINH}\b", re.IGNORECASE)
_CHO_MINH = re.compile(rf"\b(?:cho|giúp|của|với)\s+{_VAI}\b(?!\s+(?:ơi|ạ|à|nhé|nha))", re.IGNORECASE)
# Khách xưng "em"/"cháu": người gọi là bề dưới, không đoán được nên gọi gì.
_XUNG_EM = re.compile(
    r"\b(?:cho|giúp)\s+(?:em|cháu)\b|\b(?:em|cháu)\s+(?:muốn|cần|hỏi|vay|gửi|lương|làm|định|đang|chưa|mới)\b",
    re.IGNORECASE)
_GOI_AI = re.compile(rf"\b{_VAI}\s+(?:ơi|à)\b", re.IGNORECASE)


def xung_ho_theo_loi(cac_loi_khach: list[str] | tuple[str, ...]) -> str:
    """Đại từ khách tự xưng ("anh", "chị", "cô", "chú", "bác") hoặc "" nếu chưa rõ."""
    dem: dict[str, int] = {}
    for loi in cac_loi_khach or ():
        loi = loi or ""
        if _XUNG_EM.search(loi):
            return ""
        goi_ai = {m.group(1).lower() for m in _GOI_AI.finditer(loi)}
        for mau in (_TU_XUNG, _CHO_MINH):
            for m in mau.finditer(loi):
                vai = m.group(1).lower()
                if vai not in goi_ai:
                    dem[vai] = dem.get(vai, 0) + 1
    if not dem:
        return ""
    xep = sorted(dem.items(), key=lambda kv: -kv[1])
    if len(xep) > 1 and xep[0][1] == xep[1][1]:
        return ""                      # hai cách xưng ngang nhau: chưa rõ
    return xep[0][0]


_ANH_CHI = re.compile(r"\banh\s*/\s*chị\b|\banh chị\b(?!\s+em\b)", re.IGNORECASE)


def doi_xung_ho(text: str, xung_ho: str) -> str:
    """Thay "anh chị", "anh/chị" trong lời AI bằng `xung_ho`, giữ chữ hoa đầu câu."""
    if not text or not xung_ho or xung_ho == MAC_DINH:
        return text
    return _ANH_CHI.sub(
        lambda m: xung_ho[:1].upper() + xung_ho[1:] if m.group(0)[:1].isupper() else xung_ho, text)


def ma_xung_ho(xung_ho: str) -> str:
    """Hậu tố ASCII cho mã tiếng sẵn: bản "anh" và bản "chị" không đè nhau trên đĩa."""
    return {"anh": "anh", "chị": "chi", "cô": "co", "chú": "chu", "bác": "bac"}.get(xung_ho, "")
