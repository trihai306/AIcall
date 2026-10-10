"""Diện việc làm khách đã tự nói (làm tự do / đi làm công), để câu hỏi giấy tờ ở
lượt SAU được tra kho theo đúng diện đó.

Vì sao cần (đo 09-10-2026): kho chọn đáp án theo chữ của MỘT lượt. Khách nói
"anh làm tự do" rồi mấy lượt sau hỏi "thế cần giấy tờ gì" thì kho trả câu hồ sơ
chung, có "hợp đồng lao động" - sai với người không đi làm công. Hỏi gộp trong
một lượt ("làm tự do cần giấy tờ gì") thì kho chọn đúng, nên ở đây chỉ GHÉP diện
của khách vào câu đem đi tra.

Không mang dữ kiện ngân hàng nào: đáp án vẫn là dòng đã soạn trong kho.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Sequence


def _bo_dau(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _bo_dau_giu_ranh(text: str) -> str:
    """Bỏ dấu nhưng giữ nguyên vị trí dấu câu để scope chủ thể theo mệnh đề."""
    text = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9,;.!?]", " ", text)


# Xét trên chữ ĐÃ BỎ DẤU. Chỉ nhận cụm khách nói về việc làm của CHÍNH MÌNH; chữ
# "tự do" đứng một mình thì không ("trả nợ tự do", "rút tiền tự do").
_TU_DO = re.compile(
    r"\b(?:lam|lao dong|nghe|viec|kinh doanh|buon ban|ban hang) tu do\b"
    r"|\bbuon ban\b|\btu kinh doanh\b|\bho kinh doanh\b"
    r"|\bkinh doanh (?:rieng|nho|online|tai nha|ca the)\b"
    r"|\bban hang (?:online|tren mang|o cho|ngoai cho)\b"
    r"|\b(?:mo|chu|co) (?:quan|tiem|shop|sap|cua hang)\b"
    r"|\bkhong (?:co |ky )?hop dong lao dong\b|\bfreelance")
_DI_LAM = re.compile(
    r"\b(?:di lam|lam) (?:o |cho |tai |trong )?"
    r"(?:cong ty|co quan|nha nuoc|nha may|xi nghiep|van phong)\b"
    r"|\b(?:nhan vien|cong nhan|cong chuc|vien chuc)\b"
    r"|(?<!khong )\bco hop dong lao dong\b")

# Chủ thể của lời khai việc làm. Đại từ trong ``vợ anh`` là sở hữu, không phải
# lời khai rằng chính ``anh`` đi làm công ty. Chỉ xét neo nằm trước cụm nghề
# trong cùng mệnh đề; nếu không có neo thì giữ hành vi cũ và coi câu trả lời
# trần như ``làm tự do`` là lời của khách về mình.
_CHU_NGUOI_GOI = re.compile(r"\b(?:anh|chi|toi|minh|em)\b")
_CHU_NGUOI_KHAC = re.compile(
    r"\b(?:vo|chong|nguoi yeu|ban|sep|dong nghiep|bo|me|cha|"
    r"anh trai|chi gai|em trai|em gai)"
    r"(?:\s+(?:cua\s+)?(?:anh|chi|toi|minh|em))?\b"
    r"|\b(?:anh|chi|em)\s+(?:cua\s+)?(?:toi|minh)\b")

# Hỏi CẦN NHỮNG GIẤY TỜ GÌ. Cố ý hẹp hơn luật `ho_so_can_thiet`: "hồ sơ bao lâu
# thì duyệt" hỏi thời gian, ghép diện vào chỉ kéo truy vấn lệch sang câu khác.
_HOI_GIAY_TO = re.compile(
    r"\b(?:giay to|ho so|thu tuc)\b.{0,30}\b(?:gi|nao|sao|gom|can|the nao)\b"
    r"|\b(?:can|chuan bi|mang|nop|gom)\b.{0,16}\b(?:giay to|ho so|thu tuc)\b"
    r"|\b(?:can|chuan bi|mang theo|nop) (?:nhung |them )?(?:gi|cai gi)\b")

# Từ nối đầu câu bỏ đi khi ghép: "thế cần giấy tờ gì" -> "làm tự do cần giấy tờ
# gì". Để lại thì bộ chọn coi cả câu là câu NỐI TIẾP và neo nó vào lượt trước.
_NOI_DAU = re.compile(r"^(?:thế thì|vậy thì|thế|vậy|còn|rồi)\s+(?:thì\s+)?",
                      re.IGNORECASE)

CHU_TU_DO = "làm tự do"


def _chu_the_cum_viec_lam(text: str, start: int) -> str:
    """``self``/``other`` theo neo gần nhất trước cụm nghề trong mệnh đề."""
    dau = max((text.rfind(d, 0, start) for d in ",;.!?"), default=-1) + 1
    truoc = text[dau:start]

    nguoi_khac = list(_CHU_NGUOI_KHAC.finditer(truoc))
    # Không đếm đại từ sở hữu nằm bên trong ``vợ anh`` như một neo người gọi.
    nguoi_goi = [m for m in _CHU_NGUOI_GOI.finditer(truoc)
                 if not any(k.start() <= m.start() < k.end() for k in nguoi_khac)]
    neo = ([(m.start(), "other") for m in nguoi_khac]
           + [(m.start(), "self") for m in nguoi_goi])
    return max(neo)[1] if neo else "self"


def _dien_trong_luot(luot: str) -> tuple[bool, str]:
    """Có lời khai của chính khách hay không, và diện việc làm của lời khai đó."""
    co_ranh = _bo_dau_giu_ranh(luot)
    # Thay dấu câu bằng khoảng trắng nhưng không co chuỗi, để vị trí match còn
    # trùng với bản giữ ranh giới truyền cho `_chu_the_cum_viec_lam`.
    t = re.sub(r"[,;.!?]", " ", co_ranh)
    tu_do = [m for m in _TU_DO.finditer(t)
             if _chu_the_cum_viec_lam(co_ranh, m.start()) == "self"]
    di_lam = [m for m in _DI_LAM.finditer(t)
              if _chu_the_cum_viec_lam(co_ranh, m.start()) == "self"]
    if not tu_do and not di_lam:
        return False, ""
    if tu_do and di_lam:
        # "trước làm công ty giờ ra buôn bán": vẫn không tự đoán diện hiện tại.
        return True, ""
    return True, "tu_do" if tu_do else "di_lam"


def dien_khach(cac_luot_khach: Sequence[str]) -> str:
    """"tu_do" / "di_lam" / "" - theo lượt GẦN NHẤT khách nói về việc làm của mình."""
    for luot in reversed(list(cac_luot_khach or ())):
        co_loi_khai, dien = _dien_trong_luot(luot)
        if co_loi_khai:
            return dien
    return ""


def cau_hoi_cho_kho(text: str, cac_luot_khach_truoc: Sequence[str]) -> str:
    """Câu đem đi tra kho câu trả lời.

    Trả nguyên `text`, trừ khi khách ĐÃ nói mình làm tự do ở lượt trước và lượt
    này hỏi giấy tờ mà không nhắc lại diện của mình.
    """
    t = _bo_dau(text)
    if not _HOI_GIAY_TO.search(t) or _TU_DO.search(t) or _DI_LAM.search(t):
        return text
    if dien_khach(cac_luot_khach_truoc) != "tu_do":
        return text
    goc = _NOI_DAU.sub("", unicodedata.normalize("NFC", text.strip()), count=1)
    return f"{CHU_TU_DO} {goc}".strip()
