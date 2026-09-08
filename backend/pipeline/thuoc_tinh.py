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
# Bắt dải số dạng "N - M đơn_vị" hoặc "N đến M đơn_vị": số đầu không có đơn vị ngay sau.
_DAI = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:-|–|đến)\s*(\d+(?:[.,]\d+)?)\s*(%|triệu|tỷ|tháng|năm|giờ|ngày|tuổi)",
    re.I,
)
_RADIUS = 85  # ký tự tối đa giữa từ khoá và số


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

    # Bước 1: thu thập tất cả cặp (vị_trí_số, số, đơn_vị).
    # Xử lý _DAI trước để bắt số đầu dải ("12" trong "12 - 60 tháng").
    tat_ca: list[tuple[int, str, str]] = []
    da_co: set[int] = set()

    for m in _DAI.finditer(t):
        dvi = m.group(3).lower()
        p1, s1 = m.start(1), chuan_so(m.group(1))
        p2, s2 = m.start(2), chuan_so(m.group(2))
        if p1 not in da_co:
            tat_ca.append((p1, s1, dvi))
            da_co.add(p1)
        if p2 not in da_co:
            tat_ca.append((p2, s2, dvi))
            da_co.add(p2)

    for m in _SO.finditer(t):
        p = m.start(1)
        if p not in da_co:
            tat_ca.append((p, chuan_so(m.group(1)), m.group(2).lower()))
            da_co.add(p)

    tat_ca.sort()

    # Bước 2: với mỗi số, chọn thuộc tính có từ khoá GẦN NHẤT (không lấy đầu tiên trong dict).
    for pos_so, so, dvi in tat_ca:
        ung_cu: list[tuple[int, str]] = []  # (khoảng_cách, tên_thuộc_tính)
        for ten, d in bang.items():
            if dvi not in d["dvi"]:
                continue
            for k in d["khoa"]:
                for mk in re.finditer(re.escape(k), t):
                    kc = abs(mk.start() - pos_so)
                    if kc <= _RADIUS:
                        ung_cu.append((kc, ten))
        if ung_cu:
            ung_cu.sort()
            ra.append((ung_cu[0][1], so, dvi))

    return ra


def gia_tri_tai_lieu(tai_lieu: str, bang: dict) -> dict[str, set[tuple[str, str]]]:
    """{thuộc tính: {(số, đơn vị)}} đọc được từ tài liệu.

    Đọc TỪNG DÒNG chứ không cả khối: từ khoá của thuộc tính này không được vơ
    lấy con số của dòng khác.
    """
    kho: dict[str, set[tuple[str, str]]] = {}
    for dong in (tai_lieu or "").splitlines():
        for ten, so, dvi in cap_trong(dong, bang):
            kho.setdefault(ten, set()).add((so, dvi))
    return kho


def _quy_doi(so: str, dvi: str) -> list[tuple[str, str]]:
    """Các cách viết tương đương của cùng một lượng."""
    ra = [(so, dvi)]
    try:
        v = float(so)
    except ValueError:
        return ra
    if dvi == "tỷ":
        ra.append((chuan_so(str(v * 1000)), "triệu"))
    elif dvi == "triệu":
        ra.append((chuan_so(str(v / 1000)), "tỷ"))
    return ra


def chan_thuoc_tinh_sai(text: str, tai_lieu: str, bang: dict,
                        khach_noi: str = "") -> tuple[str, str | None]:
    """Con số gán cho một thuộc tính có đúng như tài liệu không?

    Trả `(văn bản nguyên vẹn, mô tả chỗ lệch hoặc None)` - CÙNG DẠNG với
    `chan_so_sai` để chỗ gọi xử lý thống nhất. Hàm này KHÔNG tự thay câu.

    Ba trường hợp im lặng, đều có chủ ý:
      - thuộc tính không có trong tài liệu -> việc của lưới NLI, không phải của đây
      - con số do chính KHÁCH nêu -> AI nhắc lại là đúng
      - không trích được cặp nào -> không có gì để phán
    """
    kho = gia_tri_tai_lieu(tai_lieu, bang)
    if not kho:
        return text, None
    # `cap_trong` trả BỘ BA (tên, số, đơn vị). Đọc thành bộ đôi là nổ giữa
    # cuộc gọi - đã lọt qua test một lần vì câu thử không trích được cặp nào.
    so_khach = {so for _, so, _ in cap_trong(khach_noi, bang)} | set(
        re.findall(r"\d+(?:[.,]\d+)?", (khach_noi or "")))
    lech = []
    for ten, so, dvi in cap_trong(text, bang):
        if ten not in kho or so in so_khach:
            continue
        if any(c in kho[ten] for c in _quy_doi(so, dvi)):
            continue
        dung = ", ".join(f"{a}{b}" for a, b in sorted(kho[ten]))
        lech.append(f"{ten} {so}{dvi} (tài liệu: {dung})")
    return text, ("; ".join(lech) if lech else None)
