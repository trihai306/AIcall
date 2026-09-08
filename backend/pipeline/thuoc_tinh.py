"""Trích cặp (thuộc tính, giá trị) từ câu, để đối chiếu với tài liệu.

Bảng thuộc tính ở đây là MẶC ĐỊNH gieo vào DB lần đầu; đường chạy thật đọc bảng
`thuoc_tinh_kiem`. Giữ bản gốc trong code để mất DB vẫn còn.
"""
import re

THUOC_TINH_MAC_DINH: dict[str, dict] = {
    "lãi suất":  {"khoa": ("lãi suất", "lãi xuất"), "dvi": ("%",)},
    "hạn mức":   {"khoa": ("hạn mức", "vay tối đa", "lên đến", "tối đa"), "dvi": ("triệu", "tỷ")},
    "thời hạn":  {"khoa": ("thời hạn", "kỳ hạn", "vay trong"), "dvi": ("tháng", "năm")},
    "giải ngân": {"khoa": ("giải ngân",), "dvi": ("giờ", "ngày")},
    "tuổi":      {"khoa": ("tuổi",), "dvi": ("tuổi",)},
    "thu nhập":  {"khoa": ("thu nhập", "lương từ"), "dvi": ("triệu",)},
    "sao kê":    {"khoa": ("sao kê",), "dvi": ("tháng",)},
    "miễn lãi":  {"khoa": ("miễn lãi",), "dvi": ("ngày",)},
}

_SO = re.compile(r"(\d+(?:[.,]\d+)?)\s*(%|triệu|tỷ|tháng|năm|giờ|ngày|tuổi)", re.I)


def chuan_so(s: str) -> str:
    """Chỉ bỏ số 0 thừa SAU dấu thập phân. `"500".rstrip("0")` cho "5" - đã mắc."""
    s = s.replace(",", ".")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def cap_trong(cau: str, bang: dict) -> list[tuple[str, str, str]]:
    """[(thuộc tính, số, đơn vị)] tìm được trong câu."""
    t = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", (cau or "").lower())
    ra = []
    for m in _SO.finditer(t):
        so, dvi = chuan_so(m.group(1)), m.group(2).lower()
        # Tìm từ khoá CẢ HAI PHÍA: "trên 70 tuổi" có từ khoá nằm SAU số.
        quanh = t[max(0, m.start() - 60):min(len(t), m.end() + 25)]
        for ten, d in bang.items():
            if dvi in d["dvi"] and any(k in quanh for k in d["khoa"]):
                ra.append((ten, so, dvi))
                break
    return ra
