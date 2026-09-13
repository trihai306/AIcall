"""Trả lời "bên em có những sản phẩm gì" từ DANH MỤC có tài liệu, không qua LLM.

VÌ SAO. Danh mục là dữ kiện xác định: kho có tài liệu sản phẩm nào thì bên em bán
sản phẩm đó. Cuộc gọi `7db3f780` (13-09-2026) lượt đầu "bên bạn cho vay những cái
gì" đi xuống mô hình; lần đó nó đáp đúng, nhưng đó là may. Nguy hơn là khách hỏi
sản phẩm KHÔNG có tài liệu ("có bảo hiểm không"): mô hình dễ nói "có" rồi bịa
điều kiện, và lưới số không bắt được vì câu không có con số nào.

Ba loại câu, còn lại trả None để đường cũ lo:

    danh_muc_vay / danh_muc_san_pham   "cho vay những gì", "có những sản phẩm gì"
    co_san_pham                        "có vay tín chấp không" - có tài liệu
    chua_co_san_pham                   "có bảo hiểm không"     - không có tài liệu

Lưới hẹp có chủ ý: "hồ sơ cần những gì", "vay tín chấp có cần thế chấp không",
"có vay được không" đều KHÔNG phải hỏi danh mục - test canh từng câu.
"""
from __future__ import annotations

import re
import unicodedata

# Tên đọc cho khách. Khớp `RAGService._TU_KHOA_SP` (test canh), thứ tự là thứ
# tự đọc ra - sản phẩm vay đứng trước vì kịch bản gọi ra là tư vấn vay.
TEN: dict[str, str] = {
    "vay_tin_chap": "vay tín chấp",
    "vay_mua_nha": "vay mua nhà",
    "the_tin_dung": "thẻ tín dụng",
    "tiet_kiem": "tiết kiệm",
    "bao_hiem": "bảo hiểm",
    "chung_khoan": "chứng khoán",
    "ngoai_te": "ngoại tệ",
}

# Cụm nhận ra sản phẩm trong câu ĐÃ BỎ DẤU. Dài trước ngắn để "vay tin chap" khớp
# trước "tin chap".
_CUM: list[tuple[str, str]] = [
    ("vay_tin_chap", r"vay tin chap|tin chap"),
    ("vay_mua_nha", r"vay mua nha|mua bat dong san"),
    ("the_tin_dung", r"the tin dung"),
    ("tiet_kiem", r"gui tiet kiem|tiet kiem"),
    ("bao_hiem", r"bao hiem"),
    ("chung_khoan", r"chung khoan"),
    ("ngoai_te", r"doi ngoai te|ngoai te|doi tien"),
]


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower().replace("đ", "d"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


def _noi(cac: list[str]) -> str:
    if len(cac) <= 1:
        return "".join(cac)
    return ", ".join(cac[:-1]) + " và " + cac[-1]


def _sap(ma_co: set[str], chi_vay: bool) -> list[str]:
    ra = [ma for ma in TEN if ma in ma_co]
    if chi_vay:
        ra = [ma for ma in ra if ma.startswith("vay_")]
    return ra


# "những gì / những cái gì / những sản phẩm nào / mấy loại / các gói nào..."
_HOI_LIET_KE = re.compile(
    r"\b(?:nhung|cac|may)\s+(?:cai\s+)?(?:gi|nao|loai|goi|san pham|dich vu)\b"
    r"|\b(?:san pham|dich vu|goi vay|loai vay)\s+(?:gi|nao)\b")
# Phải hỏi về BÊN BÁN, không phải về một thuộc tính: "hồ sơ cần những gì" có
# "những gì" nhưng hỏi giấy tờ.
_VE_BEN_BAN = re.compile(
    r"\b(?:ben (?:ban|em|minh|chi)|ngan hang)\b|\bcho vay\b|\bsan pham\b|\bdich vu\b"
    r"|\bgoi vay\b|\bloai vay\b")
_THUOC_TINH = re.compile(
    r"\b(?:ho so|giay to|dieu kien|uu dai|lai|phi|thu tuc|quy trinh|han muc"
    r"|thoi han|tai san|the chap)\b")
# Đuôi cho phép sau tên sản phẩm trong câu "có X không".
_DUOI_CO = r"(?:\s+(?:khong|ko|k|a|nhi|the|vay|em|chi|anh|ban|nhe))*$"
# Động từ đệm giữa "có" và tên sản phẩm.
_DEM_CO = r"(?:(?:cho|lam|ho tro|san pham|goi|dich vu|gui|mo|ban|trien khai)\s+)*"


def tra_loi(text: str, ma_co_tai_lieu: set[str] | None,
            hoi_them: bool = False) -> tuple[str, str] | None:
    """`(mã, câu)` khi câu là hỏi danh mục; None để đường cũ trả lời.

    `ma_co_tai_lieu`: mã sản phẩm có tài liệu trong kho (`RAGService.
    _san_pham_co_tai_lieu`). None/rỗng nghĩa là chưa biết kho - KHÔNG đoán.
    `hoi_them`: phiên chưa rõ khách quan tâm gì thì hỏi lại một câu.
    """
    if not ma_co_tai_lieu:
        return None
    t = _bo_dau(text)
    if not t:
        return None

    # 1) "có X không" - X là một sản phẩm cụ thể.
    for ma, cum in _CUM:
        m = re.search(rf"\bco\s+{_DEM_CO}(?:{cum}){_DUOI_CO}", t)
        if m and re.search(r"\b(?:khoan vay|goi vay|khi vay|the|vay)\b", t[:m.start()]):
            # "vay tín chấp CÓ BẢO HIỂM không" hỏi THUỘC TÍNH của khoản vay,
            # không hỏi bên em có bán bảo hiểm - trả "chưa có sản phẩm bảo
            # hiểm" là trả lời trớt.
            return None
        if m:
            if ma in ma_co_tai_lieu:
                return "co_san_pham", f"Dạ bên em có sản phẩm {TEN[ma]} ạ."
            dang_co = _noi([TEN[m] for m in _sap(ma_co_tai_lieu, False)])
            return "chua_co_san_pham", (
                f"Dạ hiện bên em chưa có sản phẩm {TEN[ma]}, bên em đang có "
                f"{dang_co} ạ.")

    # 2) "cho vay những gì / có những sản phẩm gì".
    if not (_HOI_LIET_KE.search(t) and _VE_BEN_BAN.search(t)):
        return None
    if _THUOC_TINH.search(t):
        return None
    if any(re.search(rf"\b(?:{cum})\b", t) for _, cum in _CUM):
        # Đã nêu một sản phẩm cụ thể ("vay tín chấp có những gói nào") - hỏi
        # chi tiết sản phẩm, không phải hỏi danh mục.
        return None
    # Xét trên bản CÒN DẤU: bỏ dấu thì "vậy" cuối câu cũng thành "vay", và
    # "bên em có những sản phẩm nào vậy" bị hiểu nhầm là chỉ hỏi sản phẩm vay.
    chi_vay = bool(re.search(r"\bvay\b", unicodedata.normalize("NFC", (text or "").lower())))
    cac = _sap(ma_co_tai_lieu, chi_vay)
    if not cac:
        return None
    ma = "danh_muc_vay" if chi_vay else "danh_muc_san_pham"
    ten = [TEN[m] for m in cac]
    if chi_vay:
        # "cho vay vay tín chấp" lặp chữ: bỏ "vay" của tên đầu tiên.
        ten[0] = re.sub(r"^vay\s+", "", ten[0])
        cau = f"Dạ bên em hiện cho vay {_noi(ten)} ạ."
    else:
        cau = f"Dạ bên em hiện có {_noi(ten)} ạ."
    if hoi_them:
        cau += " Anh chị đang quan tâm sản phẩm nào ạ?"
    return ma, cau
