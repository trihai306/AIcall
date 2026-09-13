"""Trả lời các câu có số khoản vay bằng quy tắc, không giao cho LLM đoán.

Đây là đường cho ba loại dữ kiện dễ bị mô hình trộn lẫn:

* trần CHUNG của sản phẩm (từ tài liệu sản phẩm),
* hạn mức RIÊNG đã duyệt (từ hồ sơ khách),
* nhu cầu và kỳ hạn khách vừa nói (từ hội thoại).

Chỉ khi đủ dữ kiện mới trả lời. Câu còn lại vẫn đi RAG/LLM như trước; không
nhét thêm context để mong mô hình tự chọn đúng một con số trong nhiều con số.
"""

import re
import unicodedata
from decimal import Decimal

from backend.pipeline.text_normalizer import _chu_thanh_so, _tien_trong
from backend.pipeline.du_kien_khoan_vay import _CALC, LoanState, resolve
from backend.pipeline.tra_loi_dieu_kien import tra_loi_dieu_kien

_TU_SO = (
    r"(?:không|một|mốt|hai|ba|bốn|tư|năm|lăm|sáu|bảy|tám|chín|"
    r"mười|mươi|chục|trăm|linh|lẻ)"
)


def _bo_dau(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _mot_so_tien(text: str) -> float | None:
    cac = _tien_trong(text or "")
    return next(iter(cac)) if len(cac) == 1 else None


def _la_ngu_canh_thu_nhap(text: str) -> bool:
    t = _bo_dau(text)
    return bool(re.search(
        r"\b(luong|thu nhap|doanh thu|tien cong|chuyen khoan luong)\b", t))


def _so_tien_nhu_cau(text: str) -> float | None:
    """Compatibility accessor; unspecified units are never silently invented."""
    value = resolve(text=text).amount.value
    return float(value) if value is not None else None


def _so_thang(text: str) -> int | None:
    value = resolve(text=text).term.value
    return int(value) if value is not None else None


def _so_thang_gan_nhat(text: str, history: list[dict] | None) -> int | None:
    value = resolve(history, text).term.value
    return int(value) if value is not None else None


def _la_lenh_tinh_noi_tiep(text: str) -> bool:
    """Nhận câu nối cực ngắn sau khi khách đã nêu đủ số tiền và kỳ hạn.

    ``ý`` là lỗi STT thường gặp của ``đi`` trong đúng cuộc gọi thật. Hàm này
    chỉ bật đường tính khi phía dưới đã tìm đủ cả tiền lẫn tháng trong lịch sử,
    nên một câu "tính đi" đứng riêng không thể tự tạo ra con số.
    """
    t = re.sub(r"[^a-z0-9\s]", " ", _bo_dau(text))
    t = re.sub(r"\s+", " ", t).strip()
    return bool(re.fullmatch(
        r"(?:(?:o|a|da|vang|the)\s+)*(?:tinh|tinh toan)"
        r"(?:\s+(?:di|y|giup|luon|cho anh|cho toi))*",
        t,
    ))


def _dong_co(tai_lieu: str, cum: str) -> list[str]:
    c = _bo_dau(cum)
    return [dong for dong in (tai_lieu or "").splitlines() if c in _bo_dau(dong)]


def _gia_tri_dong(tai_lieu: str, cum: str) -> str | None:
    """Phần sau dấu hai chấm của dòng thuộc tính, giữ nguyên mọi điều kiện.

    Nối cả dòng TIẾP THEO nếu nó là phần xuống dòng của cùng gạch đầu dòng
    (không mở đầu bằng `-`, `#`, `|`). Tài liệu thật viết "Chê lãi cao: ... rồi
    ạ,\n  do vay không tài sản thế chấp ..." - chỉ lấy dòng đầu là mất nửa câu.
    """
    c = _bo_dau(cum)
    cac = (tai_lieu or "").splitlines()
    for i, dong in enumerate(cac):
        if c not in _bo_dau(dong) or ":" not in dong:
            continue
        gia_tri = dong.split(":", 1)[1].strip()
        for tiep in cac[i + 1:]:
            st = tiep.strip()
            if not st or st[0] in "-#|*":
                break
            gia_tri += " " + st
        return gia_tri.strip().rstrip(".")
    return None


def _cau_tu_dong(gia_tri: str) -> str:
    """Biến giá trị đọc từ tài liệu thành một câu nói: "Dạ ... ạ."."""
    c = re.sub(r"\s+", " ", (gia_tri or "").strip().strip('"')).strip().rstrip(".,;")
    if not c:
        return ""
    if not _bo_dau(c).startswith("da "):
        c = "Dạ " + c[0].lower() + c[1:]
    if not _bo_dau(c).endswith(" a"):
        c += " ạ"
    return c + "."


def _cau_nen_noi(tai_lieu: str, ten_muc: str) -> str | None:
    """Câu trong ngoặc kép sau "Câu nên nói:" của một mục Markdown, nếu có.

    Tài liệu vay tín chấp có mục "Khách hỏi về nợ xấu" kèm đúng câu người vận
    hành muốn AI nói. Đọc nguyên văn thay vì để mô hình diễn lại: đây là chỗ
    họ đã cố ý viết "TUYỆT ĐỐI không hứa là vẫn vay được".
    """
    ten = _bo_dau(ten_muc)
    trong_muc = False
    khoi: list[str] = []
    for dong in (tai_lieu or "").splitlines():
        st = dong.strip()
        if st.startswith("#"):
            if trong_muc:
                break
            trong_muc = ten in _bo_dau(st.lstrip("# "))
            continue
        if trong_muc:
            khoi.append(dong)
    m = re.search(r'c[aâ]u n[eê]n n[oó]i\s*:\s*"(.+?)"', "\n".join(khoi), re.I | re.S)
    if not m:
        return None
    return _cau_tu_dong(m.group(1))


def _vua_hoi(history: list[dict] | None, cau: str) -> bool:
    """Lượt trả lời gần nhất của AI có đúng là câu này không."""
    for luot in reversed(history or []):
        if luot.get("role") == "assistant":
            return (luot.get("content") or "").strip() == cau.strip()
    return False


def _gia_tri_theo_san_pham(tai_lieu: str, cum: str) -> tuple[str, str] | None:
    """Lấy giá trị FAQ đúng sản phẩm từ dòng chứa nhiều nhãn ``Sản phẩm: ...``."""
    tieu_de = ""
    for dong in (tai_lieu or "").splitlines():
        s = dong.strip()
        if s.startswith("# "):
            tieu_de = _bo_dau(s[2:])
            break

    nhan = None
    if "vay tin chap" in tieu_de:
        nhan = ("vay tin chap", "vay tín chấp")
    elif "vay mua nha" in tieu_de:
        nhan = ("vay mua nha", "vay mua nhà")
    if nhan is None:
        return None

    for dong in _dong_co(tai_lieu, cum):
        for doan in re.split(r"(?<=[.!?])\s+", dong.strip()):
            if ":" not in doan:
                continue
            ten, gia_tri = doan.split(":", 1)
            if nhan[0] in _bo_dau(ten):
                return nhan[1], gia_tri.strip().rstrip(".")
    return None


def _ma_san_pham(tai_lieu: str) -> str:
    """Loại sản phẩm theo tiêu đề ``# ...`` đầu tài liệu; "" nếu không nhận ra.

    Luật trong tệp này viết cho KHOẢN VAY. Pipeline truyền vào tài liệu của mọi
    sản phẩm, nên bộ thử 10.000 câu (13-09) ra "lãi suất của gói vay là
    0.5%/năm" cho gửi tiết kiệm mọi kỳ hạn và "hạn mức gói vay 500 triệu" cho
    thẻ Gold. Tài liệu không có tiêu đề nhận ra được thì giữ luật khoản vay như cũ.
    """
    for dong in (tai_lieu or "").splitlines():
        s = dong.strip()
        if not s.startswith("# "):
            continue
        td = _bo_dau(s[2:])
        for ma, cum in (("tiet_kiem", "tiet kiem"), ("the_tin_dung", "the tin dung"),
                        ("vay_mua_nha", "vay mua nha"), ("vay_tin_chap", "vay tin chap")):
            if cum in td:
                return ma
        return ""
    return ""


def _phan_san_pham(tai_lieu: str) -> str:
    """Chỉ phần tài liệu SẢN PHẨM, cắt FAQ chung mà `ngu_canh_tai_lieu.toan_van`
    nối phía sau. FAQ có dòng "Hạn mức vay ... Vay tín chấp tối đa 500 triệu" -
    đọc trần trên cả khối là thẻ tín dụng, tiết kiệm cũng ra 500 triệu."""
    ra: list[str] = []
    da_gap = False
    for dong in (tai_lieu or "").splitlines():
        if dong.startswith("# "):
            if da_gap:
                break
            da_gap = True
        ra.append(dong)
    return "\n".join(ra)


def _so_phay(so: str) -> str:
    return so.replace(".", ",")


def _noi_so(cac: list[int]) -> str:
    return _noi_danh_sach([str(x) for x in cac])


def _bang_lai_tiet_kiem(sp_doc: str) -> tuple[dict[int, str], str | None]:
    bang: dict[int, str] = {}
    khong_ky_han = None
    for dong in sp_doc.splitlines():
        d = _bo_dau(dong)
        m = re.search(r"\bky han\s+(\d+)\s*thang\s*:\s*lai suat\s*(\d+(?:[.,]\d+)?)\s*%", d)
        if m:
            bang[int(m.group(1))] = _so_phay(m.group(2))
        m = re.search(r"\bkhong ky han\s*:\s*lai suat\s*(\d+(?:[.,]\d+)?)\s*%", d)
        if m:
            khong_ky_han = _so_phay(m.group(1))
    return bang, khong_ky_han


def _ky_gui(text: str, bang: dict[int, str]) -> int | None:
    """Kỳ gửi tính theo tháng: "12 tháng", "một năm", "hai mươi tư tháng", "ba sáu tháng"."""
    thuong = (text or "").lower()
    m = re.search(r"\b(\d{1,2})\s*(tháng|năm)\b", thuong)
    if m:
        return int(m.group(1)) * (12 if m.group(2) == "năm" else 1)
    m = re.search(rf"\b({_TU_SO}(?:\s+{_TU_SO}){{0,2}})\s+(tháng|năm)\b", thuong)
    if not m:
        return None
    chu = m.group(1).split()
    so = _chu_thanh_so(" ".join(chu))
    if so is None:
        return None
    # "ba sáu tháng" là 36 chứ không phải 9: khách đọc gọn hai chữ số.
    if len(chu) == 2 and not re.search(r"mươi|mười|trăm|linh|lẻ", m.group(1)):
        a, b = _chu_thanh_so(chu[0]), _chu_thanh_so(chu[1])
        if a and b is not None and a < 10 and b < 10 and (10 * a + b) in bang:
            so = 10 * a + b
    return so * (12 if m.group(2) == "năm" else 1)


def _tra_loi_tiet_kiem(text: str, t: str, sp_doc: str) -> tuple[str, str] | None:
    """Gửi tiết kiệm: lãi suất đi theo KỲ HẠN, không có hạn mức hay trả góp."""
    if re.search(r"\blai\b.{0,24}\bthap\b|\bthap\b.{0,12}\blai\b", t):
        gia_tri = _gia_tri_dong(sp_doc, "chê lãi thấp")
        if gia_tri:
            return "phan_hoi_lai_thap", _cau_tu_dong(gia_tri)
    hoi_lai = bool(re.search(r"\blai\b", t)) and bool(re.search(
        r"\b(bao nhieu|may phan tram|the nao|nhu nao|ra sao|la may|muc nao|hien tai|hien nay)\b", t))
    # Tiền lãi nhận được, lãi online cộng thêm, rút trước hạn, chê lãi: có dòng
    # riêng hoặc cần tính - để mô hình đọc trọn tài liệu.
    if not hoi_lai or re.search(
            r"\b(tien lai|so lai|bao nhieu tien|online|rut|truoc han|thap|cao hon)\b", t):
        return None
    bang, khong_ky_han = _bang_lai_tiet_kiem(sp_doc)
    if not bang:
        return None
    if re.search(r"\bkhong (?:ky han|thoi han|ky)\b", t):
        if khong_ky_han:
            return "lai_tiet_kiem_khong_ky_han", (
                f"Dạ gửi không kỳ hạn lãi suất {khong_ky_han}% một năm ạ.")
        return None
    ky = _ky_gui(text, bang)
    cac_ky = sorted(bang)
    if ky is None:
        dau, cuoi = cac_ky[0], cac_ky[-1]
        return "lai_tiet_kiem_theo_ky", (
            f"Dạ lãi suất gửi tiết kiệm từ {bang[dau]}% một năm cho kỳ hạn {dau} tháng "
            f"đến {bang[cuoi]}% một năm cho kỳ hạn {cuoi} tháng ạ.")
    if ky in bang:
        return "lai_tiet_kiem_theo_ky", (
            f"Dạ gửi tiết kiệm kỳ hạn {ky} tháng lãi suất {bang[ky]}% một năm ạ.")
    return "lai_tiet_kiem_ky_khong_co", (
        f"Dạ bên em chưa có kỳ hạn {ky} tháng, các kỳ hạn hiện có là "
        f"{_noi_so(cac_ky)} tháng ạ.")


_TEN_THE = (("classic", ("classic", "clat sic", "co ban")),
            ("gold", ("gold", "gon")),
            ("platinum", ("platinum", "platinium", "plantinum", "bach kim")))


def _cac_loai_the(sp_doc: str) -> dict[str, tuple[str, str, str]]:
    """{"gold": ("Gold", "30-200 triệu", "400.000đ/năm")} từ mục "Các loại thẻ"."""
    ra: dict[str, tuple[str, str, str]] = {}
    for dong in sp_doc.splitlines():
        m = re.search(r"thẻ\s+(\w+)\s*:\s*hạn mức\s+([^,]+?)\s*,\s*phí thường niên\s+(.+?)\s*$",
                      dong.strip(), re.I)
        if m:
            ra[m.group(1).lower()] = (m.group(1), m.group(2).strip(), m.group(3).strip().rstrip("."))
    return ra


def _tra_loi_the_tin_dung(t: str, sp_doc: str, text: str = "") -> tuple[str, str] | None:
    """Thẻ tín dụng: hạn mức và phí đi theo LOẠI THẺ."""
    t = re.sub(r"\bhang muc\b", "han muc", t)   # STT nghe "hạn mức" thành "hạng mức"
    if re.search(r"\b(hoan tien|cashback|cash back)\b", t):
        cb = _gia_tri_dong(sp_doc, "cashback")
        them = next((d for d in _muc_tai_lieu(sp_doc, "ưu đãi") if "hoan tien" in _bo_dau(d)), None)
        if cb:
            cau = f"Dạ thẻ tín dụng hoàn tiền {cb}"
            if them:
                cau += f", ưu đãi hiện tại {them[:1].lower() + them[1:]}"
            return "hoan_tien_the", cau + " ạ."
    cac_the = _cac_loai_the(sp_doc)
    if not cac_the:
        return None
    hoi_han_muc = bool(re.search(r"\bhan muc\b", t)) and not re.search(
        r"\b(tang|nang|len|thap|it|nho|giam)\b", t)
    hoi_phi = bool(re.search(r"\bphi\b.{0,20}\b(thuong nien|hang nam|moi nam|bao nhieu|la may)\b|"
                             r"\bphi thuong nien\b", t))
    mien_nam_dau = "mien phi thuong nien nam dau" in _bo_dau(sp_doc)
    duoi_mien = ", năm đầu được miễn phí" if mien_nam_dau else ""

    ten = next((k for k, cum in _TEN_THE if k in cac_the and any(
        re.search(rf"\b{c}\b", t) for c in cum)), None)
    if ten:
        hien, hm, phi = cac_the[ten]
        if hoi_han_muc and not hoi_phi:
            return "han_muc_loai_the", f"Dạ thẻ {hien} có hạn mức {hm} ạ."
        if hoi_phi and not hoi_han_muc:
            return "phi_loai_the", f"Dạ thẻ {hien} phí thường niên {phi}{duoi_mien} ạ."
        if hoi_phi and hoi_han_muc:
            return "loai_the", f"Dạ thẻ {hien} có hạn mức {hm}, phí thường niên {phi}{duoi_mien} ạ."
        return None

    # Xét "vay" trên bản CÒN DẤU: bỏ dấu thì "trả góp được không vậy" cũng có
    # chữ "vay" và câu hỏi trả góp thẻ bị đẩy sang mô hình (bộ thử 10k #5342).
    goc = unicodedata.normalize("NFC", (text or "").lower())
    if re.search(r"\btra gop\b", t) and not re.search(r"khoản vay|\bvay\b", goc):
        dong = next((d for d in _muc_tai_lieu(sp_doc, "ưu đãi") if "tra gop" in _bo_dau(d)), None)
        if dong:
            return "tra_gop_the", _cau_tu_dong("thẻ tín dụng được " + dong[:1].lower() + dong[1:])

    liet_ke = [cac_the[k] for k, _ in _TEN_THE if k in cac_the]
    if hoi_han_muc and re.search(r"\b(bao nhieu|toi da|la may|nhu nao|the nao|duoc bao)\b", t):
        chung = _gia_tri_dong(sp_doc, "hạn mức")
        dau = f"từ {chung.replace(' - ', ' đến ')} tuỳ loại thẻ: " if chung else "tuỳ loại thẻ: "
        return "han_muc_the", (
            "Dạ hạn mức thẻ tín dụng " + dau
            + ", ".join(f"thẻ {h} {hm}" for h, hm, _ in liet_ke) + " ạ.")
    if hoi_phi and not re.search(r"\b(rut tien|chuyen doi|tra gop|cham)\b", t):
        return "phi_the", (
            "Dạ phí thường niên "
            + ", ".join(f"thẻ {h} {phi}" for h, _, phi in liet_ke) + duoi_mien + " ạ.")
    return None


def _tran_san_pham(tai_lieu: str) -> float | None:
    cac: set[float] = set()
    for dong in _dong_co(tai_lieu, "hạn mức"):
        cac |= _tien_trong(dong)
    return max(cac) if cac else None


def _lai_suat(tai_lieu: str) -> float | None:
    for dong in _dong_co(tai_lieu, "lãi suất"):
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", dong)
        if m:
            return float(m.group(1).replace(",", "."))
    return None


def _thoi_han(tai_lieu: str) -> tuple[int, int] | None:
    for dong in _dong_co(tai_lieu, "thời hạn"):
        m = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*tháng", dong, re.I)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def _muc_tai_lieu(tai_lieu: str, ten_muc: str) -> list[str]:
    """Lấy các dòng gạch đầu dòng trong đúng một mục Markdown."""
    trong_muc = False
    ket: list[str] = []
    ten = _bo_dau(ten_muc)
    for dong in (tai_lieu or "").splitlines():
        stripped = dong.strip()
        if stripped.startswith("##"):
            trong_muc = ten in _bo_dau(stripped.lstrip("# "))
            continue
        if trong_muc and stripped.startswith("#"):
            break
        if trong_muc and stripped.startswith("-"):
            ket.append(stripped.lstrip("- ").strip())
    return ket


def _ho_so_chinh(tai_lieu: str) -> list[str]:
    cac = _muc_tai_lieu(tai_lieu, "hồ sơ")
    giay_to = None
    thu_nhap = None
    du_phong: list[str] = []
    for dong in cac:
        d = _bo_dau(dong)
        if "cmnd" in d or "cccd" in d or "can cuoc" in d:
            giay_to = "căn cước công dân"
        elif "sao ke" in d or "xac nhan thu nhap" in d:
            thu_nhap = dong[:1].lower() + dong[1:].rstrip(".")
        else:
            du_phong.append(dong.rstrip("."))
    ra = [x for x in (giay_to, thu_nhap) if x]
    for dong in du_phong:
        if len(ra) >= 2:
            break
        ra.append(dong)
    return ra


def _noi_danh_sach(cac: list[str]) -> str:
    if len(cac) <= 1:
        return "".join(cac)
    return ", ".join(cac[:-1]) + " và " + cac[-1]


def _tien_gan_nhat(text: str, history: list[dict] | None) -> float | None:
    """Read the projected current amount; NEVER scan past a correction."""
    value = resolve(history, text).amount.value
    return float(value) if value is not None else None


_NAM_LAM_VIEC = re.compile(
    rf"\b(?:làm|công tác|ở công ty).{{0,36}}?"
    rf"(\d{{1,2}}|{_TU_SO}(?:\s+{_TU_SO}){{0,2}})\s+năm\b", re.I)


def _thu_nhap_gan_nhat(history: list[dict] | None) -> float | None:
    value = resolve(history).income.value
    return float(value) if value is not None else None


def _nam_lam_viec_gan_nhat(history: list[dict] | None) -> int | None:
    for luot in reversed(history or []):
        if luot.get("role") != "user":
            continue
        m = _NAM_LAM_VIEC.search(luot.get("content", ""))
        if not m:
            continue
        raw = m.group(1)
        return int(raw) if raw.isdigit() else _chu_thanh_so(raw.lower())
    return None


def _nhu_cau_du_gan_nhat(history: list[dict] | None) \
        -> tuple[float, int] | None:
    state = resolve(history)
    if state.amount.value is not None and state.term.value is not None:
        return float(state.amount.value), int(state.term.value)
    return None


def _tra_loi_nhac_lai(text: str, history: list[dict] | None,
                      xung_ho: str) -> tuple[str, str] | None:
    """Đọc lại dữ kiện khách đã nói bằng bộ nhớ có cấu trúc.

    Không tóm tắt toàn bộ lịch sử rồi nhét thêm vào prompt. Chỉ khi khách hỏi
    lại một dữ kiện rõ ràng mới quét lời KHÁCH, lấy đúng loại số và trả thẳng.
    Cách này không phụ thuộc việc model nhỏ có chịu chú ý tới lượt thứ 10 hay
    không, đồng thời không làm phình cửa sổ context.
    """
    t = _bo_dau(text)
    hoi_lai = bool(re.search(
        r"\b(nhac lai|da (?:noi|cung cap)|noi luc dau|truoc do|"
        r"anh noi|chi noi|toi noi)\b", t))
    if not hoi_lai:
        return None

    if re.search(r"\b(luc dau|ban dau)\b", t):
        # Historical recall is distinct from the current corrected request.
        # Select the earliest customer-supplied complete pair, or the first
        # partial fact if no complete pair was ever provided.
        first_partial = None
        for end, row in enumerate(history or [], 1):
            if row.get("role") != "user":
                continue
            prefix = history[:end]
            facts = resolve(prefix)
            if facts.amount.value is not None or facts.term.value is not None:
                if first_partial is None:
                    first_partial = prefix
                if facts.amount.value is not None and facts.term.value is not None:
                    history = prefix
                    break
        else:
            history = first_partial or []

    hoi_nhu_cau = bool(re.search(
        r"\b(so tien|khoan vay|can vay|muon vay|thoi han|ky han)\b", t))
    if hoi_nhu_cau:
        cap = _nhu_cau_du_gan_nhat(history)
        tien = cap[0] if cap else _tien_gan_nhat(text, history)
        thang = cap[1] if cap else _so_thang_gan_nhat(text, history)
        if tien is not None and thang is not None:
            return "nhac_lai_nhu_cau", (
                f"Dạ trước đó {xung_ho} nói cần vay {_fmt_trieu(tien)} "
                f"trong {thang} tháng ạ."
            )
        if tien is not None:
            return "nhac_lai_nhu_cau", (
                f"Dạ trước đó {xung_ho} nói cần vay {_fmt_trieu(tien)} ạ."
            )
        if thang is not None:
            return "nhac_lai_nhu_cau", (
                f"Dạ thời hạn {xung_ho} đã nói là {thang} tháng ạ."
            )

    hoi_thu_nhap = bool(re.search(
        r"\b(thu nhap|luong|thoi gian lam viec|lam viec|cong tac)\b", t))
    if hoi_thu_nhap:
        thu_nhap = _thu_nhap_gan_nhat(history)
        nam = _nam_lam_viec_gan_nhat(history)
        cac = []
        if thu_nhap is not None:
            cac.append(f"thu nhập {_fmt_trieu(thu_nhap)} một tháng")
        if nam is not None:
            cac.append(f"đã làm việc tại công ty {nam} năm")
        if cac:
            return "nhac_lai_thu_nhap", (
                f"Dạ {xung_ho} đã cho biết " + _noi_danh_sach(cac) + " ạ."
            )
    return None


def _ghi_nhan_thu_nhap(text: str, xung_ho: str) -> tuple[str, str] | None:
    """Xác nhận đúng dữ kiện khách VỪA khai, không để model đổi con số."""
    t = _bo_dau(text)
    if not _la_ngu_canh_thu_nhap(text):
        return None
    # Chỉ nhận đây là hồ sơ của khách khi câu có đại từ tự xưng. Câu hỏi chung
    # "thu nhập bao nhiêu thì được vay" không được biến thành dữ kiện cá nhân.
    if not re.search(r"\b(anh|chi|toi|minh|em)\b", t):
        return None
    thu_nhap = _thu_nhap_gan_nhat([{"role": "user", "content": text}])
    m = _NAM_LAM_VIEC.search(text)
    nam = None
    if m:
        raw = m.group(1)
        nam = int(raw) if raw.isdigit() else _chu_thanh_so(raw.lower())
    if thu_nhap is None and nam is None:
        return None

    cac = []
    if nam is not None:
        cac.append(f"đã làm việc tại công ty {nam} năm")
    if thu_nhap is not None:
        kenh = " chuyển khoản" if "chuyen khoan" in t else ""
        cac.append(f"thu nhập{kenh} {_fmt_trieu(thu_nhap)} một tháng")
    return "ghi_nhan_thu_nhap", (
        f"Dạ em ghi nhận {xung_ho} " + _noi_danh_sach(cac) + " ạ."
    )


def _fmt_trieu(dong: float, uoc_tinh: bool = False) -> str:
    trieu = Decimal(str(dong)) / Decimal(1_000_000)
    if trieu >= 1000:
        # "10000 triệu đồng" (vay mua nhà) - không ai nói thế.
        ty = trieu / Decimal(1000)
        if ty == ty.to_integral():
            return f"{int(ty)} tỷ đồng"
        return format(ty.normalize(), "f").replace(".", ",") + " tỷ đồng"
    if trieu == trieu.to_integral():
        return f"{int(trieu)} triệu đồng"
    value = f"{trieu:.1f}" if uoc_tinh else format(trieu.normalize(), "f")
    return value.replace(".", ",") + " triệu đồng"


def tra_loi(text: str, tai_lieu: str, ho_so: dict | None = None,
            history: list[dict] | None = None, xung_ho: str = "anh chị",
            du_kien: LoanState | None = None) \
        -> tuple[str, str] | None:
    """Trả ``(mã, câu)`` khi đủ dữ kiện để trả lời xác định."""
    t = re.sub(r"\bhang muc\b", "han muc", _bo_dau(text))
    if not t:
        return None
    ma_sp = _ma_san_pham(tai_lieu)
    sp_doc = _phan_san_pham(tai_lieu)
    # Tiết kiệm và thẻ không phải khoản vay: KHÔNG chạy luật nhu cầu/trần/trả
    # góp bên dưới cho chúng, kể cả khi khách nói "gửi 100 triệu 12 tháng".
    if ma_sp == "tiet_kiem":
        return _tra_loi_tiet_kiem(text, t, sp_doc) or tra_loi_dieu_kien(text, ma_sp, sp_doc)
    if ma_sp == "the_tin_dung":
        return _tra_loi_the_tin_dung(t, sp_doc, text) or tra_loi_dieu_kien(text, ma_sp, sp_doc)
    state = du_kien if du_kien is not None else resolve(history, text)
    if state.amount_updated and state.amount.status == "cancelled":
        return "huy_nhu_cau_vay", "Dạ em ghi nhận anh chị không tiếp tục nhu cầu vay này ạ."

    nhac_lai = _tra_loi_nhac_lai(text, history, xung_ho)
    if nhac_lai:
        return nhac_lai

    # A question explicitly about an existing contract belongs to the profile
    # route, even when a separate new-loan request has already been discussed.
    if not (state.amount_updated or state.term_updated) and re.search(
            # "hợp đồng lao động" là giấy tờ, không phải hợp đồng vay cũ.
            r"\b(hop dong(?! lao dong)|khoan vay cu|han muc da duyet)\b|"
            r"\bdu no\b(?! giam dan)", t):
        return None

    ghi_nhan = None if state.amount_updated else _ghi_nhan_thu_nhap(text, xung_ho)
    if ghi_nhan:
        return ghi_nhan

    # Trước khi đọc số tiền: "anh 45 tuổi vay được không" không phải nhu cầu 45.
    dieu_kien = tra_loi_dieu_kien(text, ma_sp, sp_doc)
    if dieu_kien:
        return dieu_kien

    tran = _tran_san_pham(sp_doc)
    ky_han = _thoi_han(sp_doc)
    # Khách CHÊ thì đọc đúng câu người vận hành đã soạn trong mục "khi khách
    # chê", không đọc lại con số. Cuộc gọi 7db3f780: "hạn mức thấp vậy" ba lần
    # đều nhận lại "hạn mức tối đa 500 triệu" - đúng thứ khách vừa chê.
    if re.search(r"\b(lai suat|lai).{0,32}(cao|dat)\b", t):
        gia_tri = _gia_tri_dong(tai_lieu, "chê lãi cao")
        if gia_tri:
            return "phan_hoi_lai_cao", _cau_tu_dong(gia_tri)
        if _dong_co(tai_lieu, "chê lãi cao"):
            return "phan_hoi_lai_cao", (
                "Dạ vì đây là khoản vay không có tài sản thế chấp nên lãi suất "
                "sẽ cao hơn một chút ạ."
            )
    if (re.search(r"\bhan muc\b.{0,20}\b(thap|it|be|nho)\b|\b(thap|it|be)\b.{0,16}\bhan muc\b", t)
            and not re.search(r"\b(thap nhat|it nhat|toi thieu)\b", t)):
        gia_tri = _gia_tri_dong(tai_lieu, "chê hạn mức")
        if gia_tri:
            return "phan_hoi_han_muc_thap", _cau_tu_dong(gia_tri)

    co_hoi_tra_hang_thang = bool(re.search(
        r"\b(moi thang|hang thang|tra bao nhieu|dong bao nhieu)\b", t))
    # "lãi như nào" cũng là hỏi lãi suất (7db3f780 lượt 5: rơi xuống mô hình,
    # mô hình đọc dòng ƯU ĐÃI thay vì dòng lãi suất). Nhưng "số lãi phải trả"
    # là hỏi TIỀN lãi - phải để cho nhánh tính bên dưới.
    hoi_lai_suat = bool(re.search(r"\blai suat\b", t)) or (
        bool(re.search(r"\blai\b", t))
        and not re.search(r"\b(so|tien|so tien)\s+lai\b|\blai\b.{0,18}\b(chi tra|phai tra|phai dong)\b", t))
    if (hoi_lai_suat and not co_hoi_tra_hang_thang and re.search(
            r"\b(bao nhieu|mot nam|la may|muc nao|the nao|nhu nao|nhu the nao|"
            r"ra sao|hien tai|hien nay|may phan tram|phan tram)\b", t)):
        # Vay mua nhà có HAI dòng lãi: ưu đãi 2 năm đầu rồi thả nổi. Đọc dòng
        # đầu cho "sau hai năm lãi thế nào" là đọc sai (bộ thử 10k: 12/12 trượt).
        sau = _gia_tri_dong(sp_doc, "lãi suất sau ưu đãi")
        if sau:
            sau = re.sub(r"\s*\((.+?)\)", r", khoảng \1", sau)
        if sau and re.search(
                r"\bsau\s+(?:uu dai|khi het|thoi gian uu dai|\S+ nam|nam thu)|"
                r"\b(het uu dai|tha noi|ve sau|nhung nam sau|cac nam sau|nam thu ba)\b", t):
            return "lai_suat_sau_uu_dai", f"Dạ sau thời gian ưu đãi, lãi suất {sau} ạ."
        gia_tri = _gia_tri_dong(sp_doc, "lãi suất")
        if gia_tri:
            if sau and sau != gia_tri:
                return "lai_suat_san_pham", (
                    f"Dạ lãi suất ưu đãi {gia_tri}, sau đó {sau} ạ.")
            return "lai_suat_san_pham", (
                f"Dạ lãi suất của gói vay là {gia_tri} ạ."
            )

    if (re.search(r"\bgiai ngan\b", t)
            and re.search(r"\b(bao lau|khi nao|may ngay|may gio)\b", t)):
        gia_tri = _gia_tri_dong(tai_lieu, "giải ngân")
        if gia_tri:
            return "thoi_gian_giai_ngan", f"Dạ bên em giải ngân {gia_tri} ạ."

    if (re.search(r"\b(?:tra(?: no)?|tat toan)(?:.{0,16}truoc han\b|\s+som\b)", t)
            and re.search(r"\b(phi|phat)\b", t)):
        gia_tri = _gia_tri_theo_san_pham(tai_lieu, "trả trước hạn")
        if gia_tri:
            ten, noi_dung = gia_tri
            return "phi_tra_truoc_han", f"Dạ {ten} bên em {noi_dung} ạ."

    # "nợ tất toán trên một năm thì có vay được không" (7db3f780) - không có
    # chữ "xấu" nhưng vẫn là câu hỏi nợ đã tất toán, không phải nhu cầu vay.
    if re.search(r"\bno\b(?: xau)?.{0,16}\b(tat toan|tra xong)\b", t) and re.search(
            r"\b(tat toan|tra xong).{0,18}(mot nam|1 nam|hon nam)\b", t):
        if _dong_co(tai_lieu, "nợ đã tất toán trên 1 năm"):
            return "no_xau_da_tat_toan", (
                "Dạ nếu đã tất toán trên một năm thì hồ sơ có thể được xem xét; "
                "vẫn cần kiểm tra hồ sơ cụ thể ạ."
            )

    if re.search(r"\bno (?:xau|loai|nhom)\b", t):
        cau = _cau_nen_noi(tai_lieu, "nợ xấu")
        if cau:
            return "no_xau_cau_nen_noi", cau

    if re.search(r"\b(phi tu van|tu van.{0,12}mat phi)\b", t):
        uu_dai = "\n".join(_muc_tai_lieu(tai_lieu, "ưu đãi"))
        if "mien phi tu van" in _bo_dau(uu_dai):
            return "phi_tu_van", "Dạ bên em miễn phí tư vấn và thẩm định ạ."

    # "thời gian vay tối đa bao lâu" là hỏi THỜI HẠN, không phải hạn mức
    # (f441bc66: khớp "vay toi da" rồi đọc 500 triệu cho câu hỏi về thời gian).
    hoi_thoi_han = bool(re.search(
        r"\b(thoi han|thoi gian|ky han)\b.{0,24}\b(vay|tra gop|tra no)\b|"
        r"\bvay\b.{0,16}\b(bao lau|may thang|may nam|bao nhieu nam|bao nhieu thang)\b|"
        # "vay tín chấp trả trong mấy năm": "năm" không phải số tiền năm triệu.
        r"\btra(?: gop| no)?\b.{0,12}\b(bao lau|may thang|may nam|bao nhieu nam|bao nhieu thang)\b|"
        r"\b(thoi han|ky han)\b.{0,24}\b(bao lau|toi da|bao nhieu|may thang|may nam|"
        r"the nao|nhu nao)\b", t)) and not re.search(
        r"\b(giai ngan|duyet|phe duyet|tham dinh|xet)\b", t)
    if hoi_thoi_han and ky_han:
        return "thoi_han_san_pham", (
            f"Dạ thời hạn vay của gói là từ {ky_han[0]} đến {ky_han[1]} tháng ạ."
        )
    if hoi_thoi_han:
        gia_tri = _gia_tri_dong(sp_doc, "thời hạn")
        if gia_tri and re.search(r"\d", gia_tri):
            return "thoi_han_san_pham", f"Dạ thời hạn vay {gia_tri} ạ."

    if tran and re.search(
            r"\b(han muc|(?:thue|the) vay toi da|vay (?:tin chap )?toi da(?: duoc)?|vay duoc bao nhieu)\b", t) \
            and not re.search(r"\b(thoi gian|thoi han|bao lau|ky han|may thang|may nam|"
                              r"bao nhieu nam|bao nhieu thang)\b", t):
        gia_hm = _gia_tri_dong(sp_doc, "hạn mức")
        if gia_hm and "%" in gia_hm:
            # "lên đến 80% giá trị bất động sản, tối đa 10 tỷ đồng": đọc trọn dòng,
            # chỉ đọc con số trần là bỏ mất điều kiện 80%.
            return "han_muc_san_pham", (
                _cau_tu_dong(f"hạn mức vay {gia_hm}")
                + " Mức được duyệt thực tế còn phụ thuộc hồ sơ của anh chị.")
        return "han_muc_san_pham", (
            f"Dạ hạn mức tối đa của gói vay hiện là {_fmt_trieu(tran)} ạ. "
            "Mức được duyệt thực tế còn phụ thuộc hồ sơ của anh chị."
        )

    if re.search(r"\b(?:vo|chong)\b.{0,24}\b(?:ky|chu ky|ho so)\b", t):
        return "thieu_quy_dinh_nguoi_than_ky", (
            "Dạ tài liệu hiện tại chưa nêu yêu cầu vợ hoặc chồng ký hồ sơ, "
            "nên em chưa thể khẳng định ạ."
        )

    # "làm tự do có vay vay tín chấp được không": chữ sản phẩm chen giữa "vay" và "được".
    if re.search(r"\b(lam tu do|tu kinh doanh|kinh doanh tu do)\b", t) and re.search(
            r"\b(vay duoc khong|co vay duoc|du dieu kien)\b|\bvay\b.{0,24}\bduoc\b", t):
        dieu_kien = "\n".join(_muc_tai_lieu(tai_lieu, "điều kiện vay"))
        d = _bo_dau(dieu_kien)
        if "thu nhap on dinh" in d and "giay phep kinh doanh" in d:
            return "dieu_kien_lam_tu_do", (
                "Dạ trường hợp làm tự do vẫn cần chứng minh thu nhập ổn định "
                "và có giấy phép kinh doanh; khả năng duyệt còn cần thẩm định hồ sơ ạ."
            )

    hoi_ho_so = bool(re.search(
        r"\b(can|chuan bi|gom|ho so).{0,20}(giay to|gi|nhung gi)\b|"
        r"\bgiay to (gi|nao)\b|\btong hop.{0,24}\bho so\b|"
        r"\b(thu tuc|ho so|giay to)\b.{0,24}\b(nhu the nao|the nao|ra sao|"
        r"gom (?:nhung )?gi|can (?:nhung )?gi)\b", t))
    if hoi_ho_so:
        cac = _ho_so_chinh(tai_lieu)
        if cac:
            return "ho_so_can_thiet", (
                f"Dạ hồ sơ chính gồm {_noi_danh_sach(cac)} ạ."
            )
        # An explicit procedure question must not fall through to the generic
        # principal/limit acknowledgement just because it also says 400 million.
        # Without a sourced document section, leave it to the retrieval path.
        return None

    lien_quan_so = state.amount_updated or state.term_updated or bool(re.search(
        r"\b(vay|tinh|so tien|thoi han|ky han|moi thang|hang thang|lai phai tra)\b", t))
    # Chỉ hỏi lại về dữ kiện phát sinh Ở LƯỢT NÀY, hoặc khi khách đang đòi tính
    # ngay mà dữ kiện treo chặn phép tính. Dữ kiện mơ hồ từ lượt trước KHÔNG
    # được đem ra hỏi ở câu khác: cuộc gọi 7db3f780 một lần "ba sáu tháng"
    # không đọc được kéo theo sáu lượt "muốn vay bao nhiêu tháng", kể cả khi
    # khách hỏi nợ xấu. Và không hỏi cùng một câu hai lần liền - lần hai khách
    # đã trả lời theo cách của họ rồi, để mô hình xử lý.
    doi_tinh = bool(_CALC.search(t)) or _la_lenh_tinh_noi_tiep(text) or bool(
        re.search(r"\b(so|tien).{0,12}lai.{0,18}(chi tra|phai tra|bao nhieu)", t))
    if state.amount.status in ("missing_unit", "ambiguous") and (
            state.amount_updated or (lien_quan_so and doi_tinh)):
        if state.amount.status == "missing_unit":
            ma, cau = "xac_nhan_don_vi_vay", (
                f"Dạ {xung_ho} vừa nói {state.amount.raw}. "
                "Số tiền này tính theo triệu hay tỷ đồng ạ?"
            )
        else:
            ma, cau = "xac_nhan_so_tien_vay", (
                f"Dạ {xung_ho} nhắc lại giúp em một số tiền muốn vay, kèm đơn vị triệu hoặc tỷ đồng ạ."
            )
        if not _vua_hoi(history, cau):
            return ma, cau
    if state.term.status in ("ambiguous", "missing_unit") and (
            state.term_updated or (lien_quan_so and doi_tinh)):
        cau = "Dạ anh chị muốn vay trong bao nhiêu tháng hoặc năm ạ?"
        if not _vua_hoi(history, cau):
            return "xac_nhan_ky_han_vay", cau

    moi_tu_van = bool(re.search(
        r"\b(tu van|gioi thieu).{0,24}(khoan vay|goi vay|vay ben)\b|"
        r"\b(goi nay|san pham nay).{0,16}(uu diem|loi ich|co gi hay)\b", t))
    lai = _lai_suat(sp_doc)
    if moi_tu_van and lai is not None and tran and ky_han:
        lai_s = str(lai).replace(".", ",")
        return "gioi_thieu_san_pham", (
            f"Dạ gói vay có lãi suất từ {lai_s}% một năm, hạn mức tối đa "
            f"{_fmt_trieu(tran)} và thời hạn từ {ky_han[0]} đến {ky_han[1]} tháng ạ."
        )

    so_tien = float(state.amount.value) if state.amount.value is not None else None
    thang = int(state.term.value) if state.term.value is not None else None
    hoi_so_lai = bool(re.search(
        r"\b(so|tien).{0,12}lai.{0,18}(chi tra|phai tra|bao nhieu)|"
        r"\blai.{0,18}(chi tra|phai tra|bao nhieu)\b", t))
    if hoi_so_lai and (so_tien is None or thang is None):
        if so_tien is not None:
            return "thieu_du_kien_tinh_lai", (
                f"Dạ để tính tiền lãi cho khoản {_fmt_trieu(so_tien)}, "
                "anh chị cho em biết thời hạn vay ạ."
            )
        return "thieu_du_kien_tinh_lai", (
            "Dạ để tính tiền lãi, anh chị cho em biết số tiền muốn vay và thời hạn vay ạ."
        )

    hoi_hang_thang = bool((not _la_ngu_canh_thu_nhap(text) or state.amount_updated) and re.search(
        r"\b(moi thang|hang thang|mot thang|tra bao nhieu|dong bao nhieu)\b", t))
    hoi_hang_thang = hoi_hang_thang or _la_lenh_tinh_noi_tiep(text)
    # Khách đã đòi tính, lượt này bổ sung đúng dữ kiện còn thiếu -> tính luôn,
    # đừng bắt họ hỏi lại lần nữa (7db3f780: "ba sáu tháng" sau câu hỏi tính).
    hoi_hang_thang = hoi_hang_thang or (
        (state.unit_confirmed or state.amount_updated or state.term_updated)
        and state.request == "calculation")
    # "vay một trăm triệu trong ba sáu tháng thì như nào": nêu đủ tiền + kỳ hạn
    # rồi hỏi "như nào" là muốn biết phải trả bao nhiêu.
    hoi_hang_thang = hoi_hang_thang or bool(
        so_tien and thang and (state.amount_updated or state.term_updated)
        and re.search(r"\b(nhu nao|the nao|nhu the nao|ra sao)\b", t)
        and not re.search(r"\b(dieu kien|ho so|giay to|thu tuc)\b", t))

    if hoi_hang_thang and (so_tien is None or thang is None) and (
            state.amount.status != "unknown" or state.term.status != "unknown"):
        missing = ("số tiền muốn vay kèm đơn vị và thời hạn vay" if so_tien is None and thang is None
                   else "số tiền muốn vay kèm đơn vị" if so_tien is None else "thời hạn vay")
        return "thieu_du_kien_tinh_lai", f"Dạ để tính khoản trả hàng tháng, {xung_ho} cho em biết {missing} ạ."

    if so_tien and thang and hoi_hang_thang:
        lai = _lai_suat(sp_doc)
        if lai is None:
            return None
        if tran and so_tien > tran:
            return "vuot_han_muc", (
                f"Dạ nhu cầu {_fmt_trieu(so_tien)} đang vượt hạn mức tối đa "
                f"{_fmt_trieu(tran)} của gói này, nên em chưa thể tính phương án đó ạ."
            )
        thang_dau = so_tien / thang + so_tien * lai / 100 / 12
        return "tinh_tra_gop", (
            f"Dạ nếu được duyệt {_fmt_trieu(so_tien)} trong {thang} tháng, "
            f"tạm tính theo lãi suất từ {str(lai).replace('.', ',')}% một năm "
            f"trên dư nợ giảm dần thì tháng đầu khoảng {_fmt_trieu(thang_dau, uoc_tinh=True)}; "
            "các tháng sau sẽ giảm dần ạ. Đây là số ước tính, chưa phải lịch trả nợ chính thức."
        )

    # Con số phải nằm trong CHÍNH câu này. "nợ tất toán ... có vay được không"
    # 4 lượt sau khi khách nêu 100 triệu không phải là hỏi lại về 100 triệu.
    hoi_duoc_khong = state.amount_updated and bool(re.search(
        r"\b(vay|may)\b.{0,45}\b(duoc khong|co duoc)\b", t))
    neu_nhu_cau = state.amount_updated or bool(re.search(
        r"\b(muon (?:vay|may)|can vay|nhu cau|vay tam|vay khoang|dang vay|"
        r"can nhac vay|du dinh vay|xin vay)\b", t)
        or hoi_duoc_khong)
    if not (so_tien and neu_nhu_cau and tran):
        return None

    # "vay HƠN năm trăm triệu được không" khi trần đúng 500: là hỏi vượt trần.
    hon_muc = bool(state.amount.raw) and bool(re.search(
        r"\b(hon|tren|qua|vuot)\s+(?:muc\s+)?" + re.escape(_bo_dau(state.amount.raw)), t))
    if hon_muc and so_tien == tran:
        return "vuot_han_muc", (
            f"Dạ gói này hỗ trợ tối đa {_fmt_trieu(tran)}, hơn mức đó thì "
            "chưa được ạ."
        )
    if so_tien > tran or (hon_muc and so_tien >= tran):
        return "vuot_han_muc", (
            f"Dạ gói này hỗ trợ tối đa {_fmt_trieu(tran)}. Nhu cầu "
            f"{_fmt_trieu(so_tien)} đang vượt trần sản phẩm nên chưa phù hợp ạ."
        )

    # Nhu cầu vay MỚI là câu hỏi về sản phẩm, không tự lôi hạn mức của hợp đồng
    # cũ vào. Hồ sơ mẫu trên máy test có 300 triệu; trộn nó vào câu "muốn vay
    # 400 triệu" tuy có nguồn nhưng vẫn sai ý định và khiến khách tưởng trần
    # sản phẩm chỉ có 300 triệu. Khi khách hỏi rõ "hồ sơ/đã duyệt của tôi" thì
    # `tra_loi_ho_so` ở pipeline mới là đường được phép đọc dữ liệu riêng.
    return "nhu_cau_vay", (
        f"Dạ gói này hỗ trợ tối đa {_fmt_trieu(tran)}, nên nhu cầu "
        f"{_fmt_trieu(so_tien)} đang nằm trong trần sản phẩm. Hạn mức thực tế "
        "vẫn cần thẩm định theo hồ sơ ạ."
    )
