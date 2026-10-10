"""Câu hỏi ĐIỀU KIỆN và GIẤY TỜ: đọc thẳng dòng trong tài liệu sản phẩm.

Bộ thử 10.000 câu (13-09-2026): mô hình trượt ~5% số câu nó tự trả lời, dồn vào
đúng nhóm này - "có cần hộ khẩu không", "thu nhập bao nhiêu thì vay được", "vay
mua nhà có cần tài sản đảm bảo không" - dù tài liệu nằm trọn trong prompt. Cùng
một câu có lúc đúng lúc "để em kiểm tra lại" (nhiệt độ 0,3), và có câu lần nào
cũng sai. Đây là dữ kiện có sẵn từng dòng, không có lý do để mô hình diễn lại.

Chỉ trả lời khi tìm được dòng tài liệu khớp; không khớp thì None để đường cũ lo.
Không phán khách có đủ điều kiện hay không - chỉ đọc điều kiện.
"""
import re
import unicodedata

from backend.pipeline.du_kien_khoan_vay import quantities

TEN_SP = {"vay_tin_chap": "vay tín chấp", "vay_mua_nha": "vay mua nhà",
          "the_tin_dung": "mở thẻ tín dụng", "tiet_kiem": "gửi tiết kiệm"}
TEN_GON = {"vay_tin_chap": "vay tín chấp", "vay_mua_nha": "vay mua nhà",
           "the_tin_dung": "thẻ tín dụng", "tiet_kiem": "gửi tiết kiệm"}

# (regex câu hỏi trên chữ bỏ dấu, từ khoá phải có trong dòng tài liệu)
_GIAY_TO = (
    (r"\b(ho khau|kt ?3|kt ba|ca te ba|ko te ba|tam tru)\b", ("ho khau", "kt3")),
    (r"\bhop dong lao dong\b", ("hop dong lao dong",)),
    (r"\b(tai san dam bao|tai san the chap|the chap|tai san)\b", ("tai san",)),
    (r"\bsao ke\b", ("sao ke",)),
    (r"\b(chung minh|xac nhan) thu nhap\b", ("thu nhap",)),
    (r"\b(cccd|can cuoc|cmnd|cmt|chung minh nhan dan|chung minh thu)\b", ("cmnd", "cccd", "can cuoc")),
)
_HOI_CO_CAN = re.compile(
    r"\b(can|phai|yeu cau|bat buoc|doi hoi|khong co|thieu|chua co|may thang|"
    r"bao nhieu thang|duoc khong|thi sao|co duoc)\b")


def _bo_dau(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


def _muc(sp_doc: str, ten: str) -> list[str]:
    """Gạch đầu dòng trong các mục `##` có tên chứa `ten`."""
    ra: list[str] = []
    trong = False
    for dong in (sp_doc or "").splitlines():
        s = dong.strip()
        if s.startswith("#"):
            trong = s.startswith("##") and ten in _bo_dau(s.lstrip("# "))
            continue
        if trong and s.startswith("-"):
            ra.append(s.lstrip("- ").strip())
    return ra


def _gon(dong: str) -> str:
    """Dòng tài liệu -> vế câu nói: bỏ ngoặc, "22 - 60" thành "22 đến 60"."""
    s = re.sub(r"\s*\(([^)]*)\)", r", \1", dong.strip().rstrip("."))
    s = re.sub(r"(\d)\s*-\s*(\d)", r"\1 đến \2", s)
    if s[:2].isupper():            # CMND/CCCD, KT3: giữ nguyên chữ hoa
        return s
    return s[:1].lower() + s[1:]


def _cau(ten_sp: str, cap: list[tuple[str, str]]) -> str:
    """Ghép tối đa hai dòng (mục, dòng) thành một câu "Dạ ... ạ."."""
    dau_muc, dau_dong = cap[0]
    if _bo_dau(dau_dong).startswith(("khong yeu cau", "khong can")):
        return f"Dạ không ạ, {ten_sp} {_gon(dau_dong)}."
    ve = []
    for muc, dong in cap[:2]:
        loi_dan = f"điều kiện {ten_sp} là" if muc == "dieu kien" else f"hồ sơ {ten_sp} cần"
        ve.append(f"{loi_dan} {_gon(dong)}")
    return "Dạ " + ", ".join(ve) + " ạ."


def _dong_khop(sp_doc: str, tu_khoa: tuple[str, ...]) -> list[tuple[str, str]]:
    ra = []
    for muc in ("dieu kien", "ho so"):
        for dong in _muc(sp_doc, muc):
            d = _bo_dau(dong).replace("kt 3", "kt3")
            if any(k in d for k in tu_khoa) and (muc, dong) not in ra:
                ra.append((muc, dong))
    return ra


def _tuoi_khach(text: str) -> int | None:
    cac = []
    for q in quantities(text or ""):
        if q.value is None or q.value != q.value.to_integral():
            continue
        if re.search(r"\btuổi\b", q.raw.lower()) or re.match(
                r"\s*tuổi\b", (text or "")[q.end:].lower()):
            cac.append(int(q.value))
    return cac[0] if len(cac) == 1 else None


def _khung_tuoi(cap: list[tuple[str, str]]) -> tuple[int, int] | None:
    for _, dong in cap:
        m = re.search(r"\btu\s+(\d+)\s*[-–]\s*(\d+)\s*tuoi\b", _bo_dau(dong))
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def tra_loi_dieu_kien(text: str, ma_sp: str, sp_doc: str) -> tuple[str, str] | None:
    ten_sp = TEN_SP.get(ma_sp)
    t = _bo_dau(text)
    if not ten_sp or not t:
        return None
    co_so = bool(re.search(r"\d", t))
    # Làm tự do đã có luật riêng ở `tra_loi_khoan_vay` (điều kiện kèm thẩm định).
    if re.search(r"\b(lam tu do|tu kinh doanh|kinh doanh tu do)\b", t):
        return None

    if re.search(r"\b(sao hoa|mat trang|hanh tinh|ngoai vu tru)\b", t) and re.search(
            r"\b(dat|nha|tai san|the chap|dam bao)\b", t):
        return "tai_san_khong_co_chinh_sach", (
            "Dạ tài liệu sản phẩm hiện không có chính sách cho loại tài sản này, "
            "nên em chưa thể xác nhận có thể dùng làm tài sản đảm bảo ạ.")

    # "em bao nhiêu tuổi rồi, có người yêu chưa": khách hỏi tuổi của NHÂN VIÊN,
    # không phải điều kiện tuổi vay (bộ thử 10-10-2026 từng đọc "từ 22 đến 60 tuổi").
    hoi_tuoi_nhan_vien = bool(re.search(
        r"\b(em|ban|chau|co)\b(?: \w+){0,2} (?:bao nhieu|may) tuoi\b|\bnguoi yeu\b|"
        r"\b(?:lay|co) (?:vo|chong) chua\b", t))
    if re.search(r"\btuoi\b", t) and not hoi_tuoi_nhan_vien:
        cap = _dong_khop(sp_doc, ("tuoi",))
        if cap:
            tuoi = _tuoi_khach(text)
            khung = _khung_tuoi(cap)
            if tuoi is not None and khung:
                dau, cuoi = khung
                if tuoi < dau or tuoi > cuoi:
                    huong = "dưới" if tuoi < dau else "vượt"
                    return "dieu_kien_tuoi_khong_khop", (
                        f"Dạ điều kiện tuổi của {ten_sp} là từ {dau} đến {cuoi} tuổi ạ. "
                        f"Tuổi {tuoi} đang {huong} giới hạn này, nên em chưa thể xác nhận "
                        "hồ sơ phù hợp; việc xét hồ sơ vẫn cần thẩm định cụ thể ạ.")
                return "dieu_kien_tuoi_khop", (
                    f"Dạ tuổi {tuoi} nằm trong khung từ {dau} đến {cuoi} tuổi ạ. "
                    "Việc đủ điều kiện vay vẫn cần đối chiếu các điều kiện khác và thẩm định hồ sơ.")
            return "dieu_kien_tuoi", _cau(ten_sp, cap)

    if (re.search(r"\b(thu nhap|luong)\b", t) and not co_so
            and re.search(r"\b(bao nhieu|toi thieu|it nhat|muc nao|tu bao nhieu|la may|du)\b", t)
            and not re.search(r"\bsao ke\b", t)):
        cap = [(m, d) for m, d in _dong_khop(sp_doc, ("thu nhap",)) if m == "dieu kien"]
        if cap:
            return "dieu_kien_thu_nhap", _cau(ten_sp, cap)

    if _HOI_CO_CAN.search(t):
        for mau, tu_khoa in _GIAY_TO:
            if re.search(mau, t):
                cap = _dong_khop(sp_doc, tu_khoa)
                if cap:
                    return "dieu_kien_giay_to", _cau(ten_sp, cap)
                break

    # "có ưu đãi gì không", "đang có khuyến mãi gì" - không phải "lãi ưu đãi bao nhiêu".
    if (re.search(r"\b(uu dai|khuyen mai|chuong trinh)\b.{0,16}\b(gi|nao|khong)\b", t)
            and not re.search(r"\blai\b", t)):
        ud = _muc(sp_doc, "uu dai")
        if ud:
            cac = [_gon(d) for d in ud[:4]]
            noi = ", ".join(cac[:-1]) + " và " + cac[-1] if len(cac) > 1 else cac[0]
            return "uu_dai_hien_tai", f"Dạ {TEN_GON[ma_sp]} hiện có ưu đãi {noi} ạ."

    if re.search(r"\bdieu kien\b.{0,20}\b(gi|nao|nhu the nao|the nao|ra sao|nhung gi|gom)\b", t):
        dk = _muc(sp_doc, "dieu kien")
        if dk:
            cac = [_gon(d) for d in dk[:4]]
            noi = ", ".join(cac[:-1]) + " và " + cac[-1] if len(cac) > 1 else cac[0]
            return "dieu_kien_chung", f"Dạ điều kiện {ten_sp} gồm {noi} ạ."
    return None
