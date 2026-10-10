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
from backend.pipeline.du_kien_khoan_vay import (
    _CALC, LoanState, chuan_hoa_so_khong_dau, is_readback, quantities, resolve,
    voi_tran_san_pham,
)
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
    # "Dạ, mức lãi này..." cũng là đã có "Dạ": chỉ so "da " thì dấu phẩy làm lọt
    # và ra "Dạ dạ, mức lãi này" (lộ ra 06-10-2026 khi tắt câu đệm - trước đó
    # bước nối sau câu đệm cắt mất chữ "Dạ" thừa).
    if not re.match(r"da\b", _bo_dau(c)):
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
    thuong = chuan_hoa_so_khong_dau(text or "").lower()
    m = re.search(r"\b(\d{1,2})\s*(tháng|năm)\b", thuong)
    if m:
        return int(m.group(1)) * (12 if m.group(2) == "năm" else 1)
    m = re.search(rf"\b({_TU_SO}(?:\s+{_TU_SO}){{0,3}})\s+(tháng|năm)\b", thuong)
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


# Câu chỉ gồm kỳ hạn và tiếng đệm: "thế một năm", "còn ba tháng thì sao".
_CHI_KY_GUI = re.compile(
    r"(?:(?:the|con|vay|neu|thi|sao|a|o|u|um|em|oi|gui|ky han|ky|duoc|bao nhieu|may|"
    r"phan tram|nhi|ha|hả|chi|anh|co|bac|chau|la|lai|suat)\s*)*")
# Lời MỞ ĐẦU bỏ lửng: "chị muốn gửi", "em ơi chị muốn gửi tiết kiệm".
_MUON_GUI = re.compile(
    r"(?:(?:a|o|u|um|da|em|oi|thi|la|anh|chi|toi|bac|co|chu|chau|dang|cung)\s+)*"
    r"(?:muon|can|dinh|tinh)\s+gui(?:\s+(?:tiet kiem|tien|it tien|mot it))*"
    r"(?:\s+(?:a|o|ay|ma|day|em|nhe|thoi))*")


_NEO_GUI = re.compile(r"\b(gui|tiet kiem|mo so|khoan gui|tien gui|ky han gui)\b")
_NEO_KHONG_PHAI_GUI = re.compile(
    r"\b(luong|thu nhap|doanh thu|gia nha|gia dat|gia tri tai san|tien vay|khoan vay|"
    r"ky han vay|thoi han vay|chuyen tien|chuyen khoan|thanh toan)\b")
_SUA_GUI = re.compile(r"\b(chot|doi|sua|a khong|a nham|nham|y la|thanh)\b")
_RUT_LAI_TIEN_GUI = re.compile(
    r"\b(chua|khong)\s+chot\s+(?:so )?tien\b|"
    r"\b(?:rut lai|bo|huy)\s+(?:(?:cai|so|khoan)\s+)?tien(?:\s+do)?\b|"
    r"\b(?:so tien|tien gui)\s+(?:do\s+)?(?:chua chot|bo|huy|rut lai)\b")
_HOI_TIEN_GUI = re.compile(
    r"\b(gui|tiet kiem|tien gui|so tien gui|khoan gui)\b.{0,32}"
    r"\b(bao nhieu|may|la bao nhieu)\b")
_HOI_KY_GUI = re.compile(
    r"\b(gui|tiet kiem|ky han gui)\b.{0,32}"
    r"\b(ky han|bao lau|may thang|bao nhieu thang|may nam|bao nhieu nam)\b")
_AI_HOI_TRUONG_KHAC = re.compile(
    r"\b(vay|khoan vay|tien vay|thoi han vay|ky han vay|tra gop|du no|"
    r"luong|thu nhap|doanh thu|lam viec|cong viec|gia nha|gia dat|tai san|"
    r"chuyen tien|chuyen khoan|thanh toan|the tin dung)\b")
_DAU_HOI_DU_KIEN = re.compile(
    r"\b(bao nhieu|bao lau|may thang|may nam|muc nao|la gi|cho biet|muon|du dinh)\b|\?")


def _ai_vua_hoi_truong_khac(text: str) -> bool:
    """AI vừa hỏi dữ kiện ngoài tiết kiệm thì câu số trần không thuộc kỳ gửi."""
    return bool(_AI_HOI_TRUONG_KHAC.search(text) and _DAU_HOI_DU_KIEN.search(text))


def _chu_so_huu_du_kien(text: str, start: int, end: int) -> str | None:
    """Chủ đề của con số theo mệnh đề; neo sau không được cướp neo trước.

    Dấu ``.``/``,`` giữa hai chữ số là dấu thập phân hoặc phân cách hàng nghìn,
    không phải ranh giới mệnh đề.
    """
    dau, cuoi = _gioi_han_menh_de(text, start, end)
    truoc = _bo_dau(text[dau:start])
    sau = _bo_dau(text[end:cuoi])

    # Neo đứng trước trong CHÍNH mệnh đề sở hữu con số. Một trường mở ở mệnh
    # đề sau không thể kéo con số trước dấu phẩy sang nó.
    ung_vien_truoc: list[tuple[int, str]] = []
    for owner, mau in (("gui", _NEO_GUI), ("khac", _NEO_KHONG_PHAI_GUI)):
        cac = list(mau.finditer(truoc))
        if cac:
            ung_vien_truoc.append((cac[-1].end(), owner))
    if ung_vien_truoc:
        return max(ung_vien_truoc)[1]

    # Neo sau chỉ được dùng cho cú pháp đảo có liên từ rõ: ``150 triệu là tiền
    # gửi``. Không dùng khoảng cách hai chiều tự do.
    dao = re.match(r"\s*(?:la|thuoc|de)\s+(.+)", sau)
    if dao:
        phan = dao.group(1)
        vi_tri: list[tuple[int, str]] = []
        for owner, mau in (("gui", _NEO_GUI), ("khac", _NEO_KHONG_PHAI_GUI)):
            m = mau.search(phan)
            if m:
                vi_tri.append((m.start(), owner))
        if vi_tri:
            return min(vi_tri)[1]
    return None


def _gioi_han_menh_de(text: str, start: int, end: int) -> tuple[int, int]:
    """Biên mệnh đề quanh một span, không cắt dấu thập phân/hàng nghìn."""
    def la_ranh(i: int) -> bool:
        if text[i] not in ",;.!?":
            return False
        truoc_so = i > 0 and text[i - 1].isdigit()
        sau_so = i + 1 < len(text) and text[i + 1].isdigit()
        return not (truoc_so and sau_so)

    dau = max((i + 1 for i in range(start) if la_ranh(i)), default=0)
    cuoi = next((i for i in range(end, len(text)) if la_ranh(i)), len(text))
    return dau, cuoi


_KENH_GUI = re.compile(r"\b(?P<online>online|truc tuyen)\b|\b(?P<quay>tai quay|o quay|quay)\b")


def _kenh_gui_trong_cau(text: str, co_ngu_canh_gui: bool) -> tuple[str | None, str | None]:
    """Kênh gửi khẳng định trong lượt; trả ``(value, status)`` nếu có cập nhật."""
    t = _bo_dau(text)
    cac = list(_KENH_GUI.finditer(t))
    # Câu trả lời chỉ nói về phương thức gửi. Từ ngoài tập này (mật khẩu, thẻ,
    # thông tin...) làm câu không còn là một sửa kênh trần.
    con_lai = _KENH_GUI.sub(" ", t)
    con_lai = re.sub(
        r"\b(a|da|vang|toi|anh|chi|minh|em|thi|khong|phai|chang|chua|con|nua|thoi|nhe|"
        r"gui|kenh|hinh thuc|chon|doi|chuyen|sua|tu|sang|thanh|la|se)\b", " ", con_lai)
    kenh_tran = co_ngu_canh_gui and not re.sub(r"[^a-z0-9]+", "", con_lai)

    hop_le: list[tuple[re.Match, str, bool]] = []
    for m in cac:
        # `_bo_dau` giữ chiều dài ký tự Latin/Vietnamese trong các token kênh.
        dau, cuoi = _gioi_han_menh_de(t, m.start(), m.end())
        menh_de = t[dau:cuoi]
        truoc = t[dau:m.start()]
        neo_gui = list(_NEO_GUI.finditer(truoc))
        neo_khac = list(_NEO_KHONG_PHAI_GUI.finditer(truoc))
        owner = None
        if neo_gui or neo_khac:
            g = neo_gui[-1].end() if neo_gui else -1
            k = neo_khac[-1].end() if neo_khac else -1
            owner = "gui" if g > k else "khac"
        doi_kenh_ro = bool(co_ngu_canh_gui and re.search(
            r"\b(?:doi|chuyen|sua)\s+(?:(?:kenh|hinh thuc)\s+)?(?:gui\s+)?"
            r"(?:sang|thanh)?\s*$", truoc))
        if owner == "gui" or kenh_tran or doi_kenh_ro:
            phu_dinh_truoc = bool(re.search(
                r"\b(?:khong\s+phai(?:\s+(?:toi|anh|chi|minh|em))?|khong|chang|chua)\s+"
                r"(?:con\s+)?(?:chon\s+)?(?:kenh\s+)?(?:gui\s+)?$", truoc))
            sau = t[m.end():cuoi]
            # Cấu trúc hậu tố: ``online thì không [gửi/chọn/dùng]``. Khớp hết
            # phần còn lại của mệnh đề để ``online thì không cần đến quầy``
            # không bị hiểu nhầm là phủ định kênh online.
            phu_dinh_sau = bool(re.fullmatch(
                r"\s*(?:(?:thi|la)\s+)?(?:khong|chang|chua)"
                r"(?:\s+(?:phai|gui|chon|dung))?(?:\s+nua)?\s*", sau))
            bi_phu_dinh = phu_dinh_truoc or phu_dinh_sau
            hop_le.append((m, m.lastgroup or "", bi_phu_dinh))
    if not hop_le:
        return None, None
    khang_dinh = [x for x in hop_le if not x[2]]
    if not khang_dinh:
        # Phủ định kênh cũ không tự suy ra quầy hay online; trạng thái cần được
        # xác nhận lại cho cả phép tính tiền và câu hỏi APR.
        return None, "ambiguous"
    if len(khang_dinh) > 1:
        giua = t[khang_dinh[0][0].end():khang_dinh[-1][0].start()]
        if re.search(r"\b(hay|hoac|va)\b", giua):
            return None, "ambiguous"
    # Khi câu vừa phủ định kênh cũ rồi chốt kênh mới, khẳng định cuối cùng thắng.
    return khang_dinh[-1][1], "known"


def _gan_neo_gui(text: str, start: int, end: int) -> bool:
    return _chu_so_huu_du_kien(text, start, end) == "gui"


def _chi_mot_du_kien(text: str, cac) -> bool:
    """Lượt chỉ trả một dữ kiện cùng tiếng đệm, ví dụ ``dạ 100 triệu ạ``."""
    if len(cac) != 1:
        return False
    q = cac[0]
    con_lai = _bo_dau(text[:q.start] + " " + text[q.end:])
    return bool(re.fullmatch(
        r"(?:(?:da|vang|u|um|o|a|the|con|thi|la|chot|lay|gui|ky han|em|anh|chi|toi|"
        r"nhe|nha|a|thoi|di)\s*)*", re.sub(r"[^a-z0-9\s]", " ", con_lai).strip()))


def _co_sua_giua(text: str, cac) -> bool:
    """Hai số trong một lượt chỉ lấy số cuối khi có lời sửa nằm giữa chúng."""
    if len(cac) < 2:
        return False
    giua = _bo_dau(text[cac[0].end:cac[-1].start])
    return bool(_SUA_GUI.search(giua)) and not re.search(r"\b(hay|hoac)\b", giua)


def _du_kien_tinh_lai_tiet_kiem(text: str, history: list[dict] | None,
                                bang: dict[int, str], cho_gia_dinh: bool = False) \
        -> tuple[Decimal | None, int | None, str, str, str | None, str]:
    """Chiếu tuần tự tiền/kỳ hạn/kênh từ lời khách, lời rõ sau thay lời rõ trước."""
    # Câu hỏi giả định dùng một phép chiếu tạm chỉ từ CHÍNH câu hỏi. Nó không
    # được mượn dữ kiện thật cũ, cũng không trở thành trạng thái thật ở lượt sau.
    rows = ([{"role": "user", "content": text}] if cho_gia_dinh
            else list(history or []) + [{"role": "user", "content": text}])
    tien: Decimal | None = None
    ky: int | None = None
    tien_status = ky_status = "unknown"
    kenh: str | None = None
    kenh_status = "unknown"
    ai_truoc = ""

    for row in rows:
        cau = row.get("content", "") or ""
        if row.get("role") == "assistant":
            ai_truoc = _bo_dau(cau)
            continue
        if row.get("role") != "user":
            continue
        t = _bo_dau(cau)
        # Giả định không thay dữ kiện đã xác nhận. Các con số thu nhập/giá tài
        # sản cũng chỉ được xét nếu chính chúng gắn với neo gửi.
        if re.search(r"\b(neu|gia su|vi du|thu dat vao)\b", t) and not cho_gia_dinh:
            continue
        tat_ca_q = quantities(cau)
        qs = [q for q in tat_ca_q if q.value is not None]
        dang_sua = bool(_SUA_GUI.search(t)) and (
            tien_status != "unknown" or ky_status != "unknown" or kenh_status != "unknown")
        gui_them = bool(re.search(r"\b(gui|nop|bo sung)\s+them\b", t))

        co_ngu_canh_gui = (tien_status != "unknown" or ky_status != "unknown"
                            or kenh_status != "unknown")
        kenh_moi, trang_thai_kenh = _kenh_gui_trong_cau(cau, co_ngu_canh_gui)
        if trang_thai_kenh == "known":
            kenh, kenh_status = kenh_moi, "known"
        elif trang_thai_kenh == "ambiguous":
            kenh, kenh_status = None, "ambiguous"

        tien_q = [q for q in qs if q.kind == "money" and (
            _gan_neo_gui(cau, q.start, q.end)
            or (dang_sua and _chu_so_huu_du_kien(cau, q.start, q.end) is None)
            or (_HOI_TIEN_GUI.search(ai_truoc) and _chi_mot_du_kien(cau, [q])))]
        tien_tran_sua = [q for q in tat_ca_q if q.kind == "bare" and dang_sua
                         and _SUA_GUI.search(_bo_dau(cau[:q.end]))
                         and _chu_so_huu_du_kien(cau, q.start, q.end) is None]
        # ``gửi 50 hoặc 100 triệu``: số đầu thiếu đơn vị nhưng cạnh tranh trực
        # tiếp với số tiền sau, nên cả lượt là mơ hồ chứ không tự chọn 100.
        lua_chon_tien = bool(tien_q and re.search(r"\b(hay|hoac)\b", t)
                             and len([q for q in qs if q.kind in ("money", "bare")]) > 1)
        rut_lai_tien = bool(_RUT_LAI_TIEN_GUI.search(t)) and not (
            _NEO_KHONG_PHAI_GUI.search(t) and not _NEO_GUI.search(t))
        if rut_lai_tien:
            tien, tien_status = None, "unknown"
        elif tien_tran_sua and not tien_q:
            # ``à không 150 thôi`` có ý thay tiền nhưng chưa có đơn vị. Không
            # giữ 100 triệu cũ và cũng không tự suy 150 triệu.
            tien, tien_status = None, "missing_unit"
        elif gui_them and tien_q:
            tien, tien_status = None, "ambiguous"
        elif lua_chon_tien:
            tien, tien_status = None, "ambiguous"
        elif len(tien_q) > 1:
            if _co_sua_giua(cau, tien_q):
                tien, tien_status = Decimal(tien_q[-1].value), "known"
            else:
                tien, tien_status = None, "ambiguous"
        elif len(tien_q) == 1:
            tien, tien_status = Decimal(tien_q[0].value), "known"

        # Mốc rút/tất toán không phải kỳ hạn gửi: ``rút sau 3 tháng`` không
        # được thay kỳ hạn 12 tháng đã chốt.
        rut_som = bool(re.search(r"\b(rut|tat toan).{0,24}\b(sau|truoc|som|thang|nam)\b", t))
        ky_q = [] if rut_som else [q for q in qs if q.kind == "duration" and (
            _gan_neo_gui(cau, q.start, q.end)
            or (_chu_so_huu_du_kien(cau, q.start, q.end) is None and bool(
                re.search(r"\b(ky han|trong)\b", _bo_dau(cau[:q.start]))))
            or (dang_sua and _chu_so_huu_du_kien(cau, q.start, q.end) is None)
            or (_HOI_KY_GUI.search(ai_truoc) and _chi_mot_du_kien(cau, [q]))
            # Module sản phẩm đã là tiết kiệm: một lượt chỉ nói ``sáu tháng``
            # là kỳ gửi, trừ khi AI vừa hỏi rõ một trường khác. Không quét thô
            # bằng `_ky_gui`; vẫn dùng đúng typed quantity và ownership này.
            or (_chu_so_huu_du_kien(cau, q.start, q.end) is None
                and _chi_mot_du_kien(cau, [q])
                and not _ai_vua_hoi_truong_khac(ai_truoc))
            or (_chu_so_huu_du_kien(cau, q.start, q.end) is None
                and (re.search(r"\b(phan tram|may cham)\b", t)
                     or (re.search(r"\blai(?: suat)?\b", t)
                         and re.search(r"\b(bao nhieu|la may|muc nao|the nao|nhu nao)\b", t)
                         and not re.search(r"\b(tien lai|bao nhieu tien)\b", t))
                     or (_chi_mot_du_kien(cau, [q]) and re.search(
                         r"\b(tiet kiem|lai suat|ky han gui)\b", ai_truoc))))
            or (_chu_so_huu_du_kien(cau, q.start, q.end) is None
                and (tien_status != "unknown" or ky_status != "unknown")
                and re.search(r"\b(tien lai|bao nhieu tien)\b", t)))]
        lua_chon_ky = bool(ky_q and re.search(r"\b(hay|hoac)\b", t)
                           and len([q for q in qs if q.kind in ("duration", "bare")]) > 1)
        if lua_chon_ky:
            ky, ky_status = None, "ambiguous"
        elif len(ky_q) > 1:
            if _co_sua_giua(cau, ky_q):
                ky, ky_status = int(ky_q[-1].value), "known"
            else:
                ky, ky_status = None, "ambiguous"
        elif len(ky_q) == 1:
            ky, ky_status = int(ky_q[0].value), "known"

        ai_truoc = ""

    return (tien if tien_status == "known" else None,
            ky if ky_status == "known" else None,
            tien_status, ky_status,
            kenh if kenh_status == "known" else None, kenh_status)


def _lai_nguon_cho_ky(sp_doc: str, ky: int) -> Decimal | None:
    """Một APR duy nhất được nguồn ghi cho kỳ hạn; khác đi thì không tính."""
    cac: set[Decimal] = set()
    for dong in sp_doc.splitlines():
        d = _bo_dau(dong)
        m = re.search(r"\bky han\s+(\d+)\s*thang\s*:\s*lai suat\s*(\d+(?:[.,]\d+)?)\s*%", d)
        if m and int(m.group(1)) == ky:
            cac.add(Decimal(m.group(2).replace(",", ".")))
    return next(iter(cac)) if len(cac) == 1 else None


def _cong_them_online_tu_nguon(sp_doc: str) -> Decimal | None:
    """Mức cộng online duy nhất trong đúng mục nguồn; thiếu/xung đột là chưa biết."""
    cac: list[Decimal] = []
    for dong in _muc_tai_lieu(sp_doc, "gửi online"):
        d = _bo_dau(dong)
        # Chỉ áp dụng mức cộng được nguồn nói vô điều kiện. Một ưu đãi có
        # ngưỡng/đối tượng riêng không được biến thành lãi suất chung.
        m = re.fullmatch(
            r"lai suat\s+cong them\s+(\d+(?:[.,]\d+)?)\s*%\s*/?\s*nam\s+"
            r"so voi gui tai quay\s*\.?", d.strip())
        if m:
            cac.append(Decimal(m.group(1).replace(",", ".")))
    return cac[0] if len(cac) == 1 else None


def _lai_ap_dung(sp_doc: str, ky: int, kenh: str | None) \
        -> tuple[Decimal | None, str]:
    """APR đã áp dụng kênh và nhãn nguồn dùng chung cho tiền lãi/APR."""
    co_so = _lai_nguon_cho_ky(sp_doc, ky)
    if co_so is None:
        return None, ""
    if kenh == "online":
        cong_them = _cong_them_online_tu_nguon(sp_doc)
        if cong_them is None:
            return None, ""
        return co_so + cong_them, "gửi online"
    if kenh == "quay":
        return co_so, "gửi tại quầy"
    return co_so, "mức cơ sở trong tài liệu, chưa áp dụng cộng thêm online"


def _tinh_lai_tiet_kiem(text: str, t: str, sp_doc: str,
                        history: list[dict] | None, bang: dict[int, str],
                        du_kien_gui=None) \
        -> tuple[str, str] | None:
    hoi_tien_lai = bool(re.search(
        r"\b(tien lai|so tien lai|lai (?:duoc|nhan|thu ve).{0,18}(?:bao nhieu|may)|"
        r"bao nhieu tien(?: lai)?|cuoi ky.{0,18}(?:duoc|nhan).{0,12}bao nhieu)\b", t))
    if not hoi_tien_lai:
        return None
    if re.search(r"\b(rut|tat toan).{0,18}\b(truoc han|som)\b", t):
        return "khong_tinh_lai_rut_truoc_han", (
            "Dạ em chưa thể dùng lãi suất kỳ hạn để tính trường hợp rút trước hạn ạ. "
            "Tiền lãi thực tế còn phụ thuộc số ngày gửi và chính sách rút trước hạn.")
    tien, ky, tien_status, ky_status, kenh, kenh_status = (
        du_kien_gui if du_kien_gui is not None
        else _du_kien_tinh_lai_tiet_kiem(text, history, bang))
    if tien_status == "missing_unit":
        return "thieu_du_kien_tinh_lai_tiet_kiem", (
            "Dạ anh chị vừa sửa số tiền gửi nhưng chưa nêu đơn vị, vui lòng xác nhận "
            "lại số tiền kèm đơn vị triệu hoặc tỷ để em ước tính ạ.")
    if kenh_status == "ambiguous":
        return "thieu_du_kien_tinh_lai_tiet_kiem", (
            "Dạ anh chị đang nêu cả gửi online và gửi tại quầy, vui lòng xác nhận "
            "một hình thức gửi để em áp dụng đúng lãi suất ạ.")
    if "ambiguous" in (tien_status, ky_status):
        return "thieu_du_kien_tinh_lai_tiet_kiem", (
            "Dạ em thấy có nhiều số tiền hoặc kỳ hạn gửi khác nhau, anh chị xác nhận "
            "lại một số tiền gửi và một kỳ hạn để em ước tính ạ.")
    if tien is None or ky is None:
        thieu = ("số tiền gửi và kỳ hạn" if tien is None and ky is None
                 else "số tiền gửi" if tien is None else "kỳ hạn gửi")
        return "thieu_du_kien_tinh_lai_tiet_kiem", (
            f"Dạ để ước tính tiền lãi, anh chị cho em biết {thieu} ạ.")
    apr, nhan_kenh = _lai_ap_dung(sp_doc, ky, kenh)
    if apr is None:
        neu_online = " và mức cộng thêm online" if kenh == "online" else ""
        return "khong_co_lai_suat_tiet_kiem", (
            f"Dạ tài liệu hiện chưa có một mức lãi suất xác định cho kỳ hạn {ky} tháng"
            f"{neu_online}, "
            "nên em chưa thể ước tính tiền lãi ạ.")
    lai = tien * apr / Decimal(100) * Decimal(ky) / Decimal(12)
    mo_dau = "Dạ nếu gửi" if re.search(r"\b(neu|gia su|vi du|thu dat vao)\b", t) else "Dạ với"
    return "uoc_tinh_tien_lai_tiet_kiem", (
        f"{mo_dau} {_fmt_trieu(float(tien))}, kỳ hạn {ky} tháng và lãi suất {nhan_kenh} "
        f"{str(apr).replace('.', ',')}% một năm, tiền lãi ước tính khoảng "
        f"{_fmt_trieu(float(lai))} ạ. Số thực nhận còn phụ thuộc số ngày gửi thực tế "
        "và điều kiện tại thời điểm mở sổ; đây chưa phải lịch lãi chính thức.")


def _uu_dai_tiet_kiem(text: str, t: str, sp_doc: str) -> tuple[str, str] | None:
    """Đọc điều kiện quà tặng từ nguồn, đối chiếu với tiền gửi của lượt này."""
    raw = unicodedata.normalize("NFC", (text or "").lower())
    # Bỏ dấu thì "quá/qua" thành "quà", "tăng" thành "tặng". Chỉ nhận hai
    # từ này trên chữ gốc; câu không dấu cần có cụm hỏi quà rõ nghĩa.
    if not (re.search(r"\b(quà|tặng)\b", raw) or re.search(
            r"\b(uu dai|khuyen mai|qua tang|co qua (?:gi|chi|khong)|"
            r"duoc tang (?:gi|chi)|tang gi|tang chi)\b", t)):
        return None
    uu_dai = _muc_tai_lieu(sp_doc, "ưu đãi")
    if not uu_dai:
        return None
    # Câu gõ không dấu vẫn nêu đơn vị rõ ràng ("gui 50 trieu"). Chuẩn hoá đúng
    # token đơn vị, giữ nguyên vị trí để kiểm tra động từ gửi trước số tiền.
    don_vi = {"trieu": "triệu", "ty": "tỷ", "ti": "tỉ", "dong": "đồng",
              "nghin": "nghìn", "ngan": "ngàn"}
    text_so = re.sub(r"\b(trieu|ty|ti|dong|nghin|ngan)\b",
                     lambda m: don_vi[m.group()], raw)
    tien_gui = [q for q in quantities(text_so) if q.kind == "money"
                and q.value is not None and re.search(r"\bgui\b", _bo_dau(text[:q.start]))]
    so_tien = tien_gui[0].value if len(tien_gui) == 1 else None
    cac = []
    for dong in uu_dai:
        # Chỉ kết luận với điều kiện ngưỡng đơn giản đã ghi rõ; những điều kiện
        # khác vẫn đọc nguyên dòng để không biến một điều kiện thành lời hứa.
        m = re.search(r"\bcho (?:so|khoan gui|tien gui) tu (.+?) tro len\b", _bo_dau(dong))
        nguong = [q for q in quantities(dong) if q.kind == "money" and q.value is not None]
        if m and len(nguong) == 1 and so_tien is not None and so_tien < nguong[0].value:
            cac.append(f"Với {_fmt_trieu(float(so_tien))}, khoản gửi chưa đạt ngưỡng "
                       f"{_fmt_trieu(float(nguong[0].value))} để nhận quà này.")
        cac.append(_cau_tu_dong(dong))
    return "uu_dai_tiet_kiem", " ".join(cac)


def _tra_loi_tiet_kiem(text: str, t: str, sp_doc: str,
                       history: list[dict] | None = None) -> tuple[str, str] | None:
    """Gửi tiết kiệm: lãi suất đi theo KỲ HẠN, không có hạn mức hay trả góp."""
    uu_dai = _uu_dai_tiet_kiem(text, t, sp_doc)
    if uu_dai:
        return uu_dai
    if re.search(r"\blai\b.{0,24}\bthap\b|\bthap\b.{0,12}\blai\b", t):
        gia_tri = _gia_tri_dong(sp_doc, "chê lãi thấp")
        if gia_tri:
            return "phan_hoi_lai_thap", _cau_tu_dong(gia_tri)
    bang, khong_ky_han = _bang_lai_tiet_kiem(sp_doc)
    if re.search(r"\b(vang|do la|usd|ngoai te)\b", t) and re.search(
            r"\b(gui|tiet kiem|mo so)\b", t):
        doc = _bo_dau(sp_doc)
        thieu = []
        if "vang" in t and "vang" not in doc:
            thieu.append("vàng")
        if re.search(r"\b(do la|usd|ngoai te)\b", t) and not re.search(
                r"\b(do la|usd|ngoai te)\b", doc):
            thieu.append("ngoại tệ")
        if thieu:
            loai = " và ".join(thieu)
            return "tien_gui_khong_co_chinh_sach", (
                f"Dạ tài liệu sản phẩm hiện chưa nêu chính sách gửi tiết kiệm bằng {loai}, "
                "nên em chưa thể xác nhận điều kiện hoặc lãi suất ạ.")
    du_kien_luot_nay = [q for q in quantities(text) if q.value is not None]
    co_tien_gia_dinh = any(q.kind == "money" for q in du_kien_luot_nay)
    co_ky_gia_dinh = any(q.kind == "duration" for q in du_kien_luot_nay)
    de_xuat_khoan_gui = bool(re.search(r"\b(gui|tiet kiem|mo so)\b", t))
    la_cau_hoi_gia_dinh = bool(
        re.search(r"\b(neu|gia su|vi du|thu dat vao)\b", t)
        and (de_xuat_khoan_gui or (co_tien_gia_dinh and co_ky_gia_dinh))
        and re.search(r"\b(tien lai|bao nhieu tien|lai suat|phan tram|may cham)\b", t))
    du_kien_gui = _du_kien_tinh_lai_tiet_kiem(
        text, history, bang, cho_gia_dinh=la_cau_hoi_gia_dinh)
    tinh_lai = _tinh_lai_tiet_kiem(text, t, sp_doc, history, bang, du_kien_gui)
    if tinh_lai:
        return tinh_lai
    if _MUON_GUI.fullmatch(re.sub(r"[^a-z0-9\s]", " ", t).strip()):
        m = re.search(r"toi thieu\s*:\s*([^\n]+)", _bo_dau(sp_doc))
        dong = _gia_tri_dong(sp_doc, "Số tiền gửi tối thiểu") if m else None
        if dong:
            return "muon_gui_tiet_kiem", f"Dạ vâng ạ, bên em nhận gửi tiết kiệm từ {dong} ạ."
    _, ky, _, ky_status, kenh, kenh_status = du_kien_gui
    ai_truoc = _bo_dau(next((m.get("content", "") for m in reversed(history or [])
                             if m.get("role") == "assistant"), ""))
    hoi_lai = bool(re.search(r"\blai\b", t)) and bool(re.search(
        r"\b(bao nhieu|may phan tram|the nao|nhu nao|ra sao|la may|muc nao|hien tai|hien nay)\b", t))
    # Hỏi lãi mà không nói chữ "lãi": "sáu tháng thì được bao nhiêu phần trăm",
    # hoặc đáp cụt một kỳ hạn ngay sau khi AI vừa nói về lãi ("thế một năm").
    # Bộ thử 10-10-2026: "thế một năm" nhận lại nguyên câu của kỳ hạn 6 tháng.
    if ky is not None and not hoi_lai:
        con_lai = re.sub(
            rf"\b(?:\d{{1,2}}|{_TU_SO}(?:\s+{_TU_SO}){{0,3}})\s+(?:tháng|năm)\b",
            " ", chuan_hoa_so_khong_dau(text or "").lower())
        chi_ky = bool(_CHI_KY_GUI.fullmatch(re.sub(r"\s+", " ", _bo_dau(con_lai)).strip(" .,!?")))
        hoi_lai = (bool(re.search(r"\b(phan tram|may cham)\b", t))
                   or (chi_ky and bool(re.search(r"\blai suat\b|%", ai_truoc))))
    # Tiền lãi nhận được, rút trước hạn, chê lãi: có dòng riêng hoặc cần tính.
    # Hỏi APR online đi qua chính phép chiếu kênh ở trên để không có sổ phụ quét
    # lịch sử và không bỏ sót mức cộng thêm có nguồn.
    if not hoi_lai or re.search(
            r"\b(tien lai|so lai|bao nhieu tien|rut|truoc han|thap|cao hon)\b", t):
        return None
    if not bang:
        return None
    if re.search(r"\bkhong (?:ky han|thoi han|ky)\b", t):
        if khong_ky_han:
            return "lai_tiet_kiem_khong_ky_han", (
                f"Dạ gửi không kỳ hạn lãi suất {khong_ky_han}% một năm ạ.")
        return None
    cac_ky = sorted(bang)
    if ky_status == "ambiguous":
        return "lai_tiet_kiem_ky_mo_ho", (
            "Dạ anh chị đang nêu nhiều kỳ hạn gửi khác nhau, vui lòng xác nhận "
            "một kỳ hạn để em báo đúng lãi suất ạ.")
    if kenh_status == "ambiguous":
        return "lai_tiet_kiem_kenh_mo_ho", (
            "Dạ anh chị đang nêu cả gửi online và gửi tại quầy, vui lòng xác nhận "
            "một hình thức gửi để em báo đúng lãi suất ạ.")
    if ky is None:
        dau, cuoi = cac_ky[0], cac_ky[-1]
        lai_dau, nhan = _lai_ap_dung(sp_doc, dau, kenh)
        lai_cuoi, _ = _lai_ap_dung(sp_doc, cuoi, kenh)
        if lai_dau is None or lai_cuoi is None:
            return "khong_co_lai_suat_tiet_kiem", (
                "Dạ tài liệu chưa có các mức lãi suất nguồn xác định"
                + (" cùng một mức cộng thêm online" if kenh == "online" else "")
                + ", nên em chưa thể báo lãi suất ạ.")
        return "lai_tiet_kiem_theo_ky", (
            f"Dạ lãi suất {nhan} từ {str(lai_dau).replace('.', ',')}% một năm cho kỳ hạn "
            f"{dau} tháng đến {str(lai_cuoi).replace('.', ',')}% một năm cho kỳ hạn "
            f"{cuoi} tháng ạ.")
    if ky in bang:
        apr, nhan = _lai_ap_dung(sp_doc, ky, kenh)
        if apr is None:
            return "khong_co_lai_suat_tiet_kiem", (
                f"Dạ tài liệu chưa có một mức lãi suất xác định cho kỳ hạn {ky} tháng"
                + (" và mức cộng thêm online" if kenh == "online" else "")
                + ", nên em chưa thể báo lãi suất ạ.")
        mo_kenh = ("gửi online" if kenh == "online" else "gửi tại quầy" if kenh == "quay"
                   else "gửi tiết kiệm")
        ghi_chu = f" theo {nhan}" if kenh is None else ""
        return "lai_tiet_kiem_theo_ky", (
            f"Dạ {mo_kenh} kỳ hạn {ky} tháng lãi suất "
            f"{str(apr).replace('.', ',')}% một năm{ghi_chu} ạ.")
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
    if re.search(r"\b(dong|huy|cham dut|ngung)\b.{0,16}\bthe\b|"
                 r"\bthe\b.{0,16}\b(dong|huy|cham dut|ngung)\b", t):
        dong_nguon = next((d.strip().lstrip("- ") for d in sp_doc.splitlines()
                           if not d.lstrip().startswith("#") and re.search(
                               r"\b(dong|huy|cham dut|ngung)\b.{0,18}\bthe\b|"
                               r"\bthe\b.{0,18}\b(dong|huy|cham dut|ngung)\b",
                               _bo_dau(d))), None)
        if dong_nguon:
            return "chinh_sach_dong_the", _cau_tu_dong(dong_nguon)
        return "phi_dong_the_chua_co_nguon", (
            "Dạ tài liệu thẻ hiện chưa nêu phí hoặc chính sách đóng, hủy thẻ, "
            "nên em chưa thể xác nhận mức phí ạ.")
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
                             r"\bphi (?:thuong nien|nam)\b", t))
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


def _thoi_han_toi_da(tai_lieu: str) -> int | None:
    """Số tháng dài nhất khi tài liệu chỉ nêu trần: "Thời hạn: tối đa 25 năm"."""
    for dong in _dong_co(tai_lieu, "thời hạn"):
        m = re.search(r"tối đa\s*(\d+)\s*(tháng|năm)", dong, re.I)
        if m:
            return int(m.group(1)) * (12 if m.group(2).lower() == "năm" else 1)
    return None


def _doc_ky_han(thang: int, theo_nam: bool) -> str:
    return f"{thang // 12} năm" if theo_nam and thang % 12 == 0 else f"{thang} tháng"


def _dap_ky_han(ngan_kh: int, dai_kh: int, khach_noi: str, khung: tuple[int | None, int],
                theo_nam: bool, so_tien: str = "", da_noi: bool = False) -> tuple[str, str]:
    """Kỳ hạn khách nêu so với thời hạn của sản phẩm: nói thẳng ĐƯỢC hay CHƯA ĐƯỢC.

    `ngan_kh..dai_kh` là kỳ hạn khách nêu theo tháng (một số thì hai đầu bằng
    nhau), `khach_noi` là cách đọc lại nó; `khung` là (ngắn nhất hoặc None, dài
    nhất) của sản phẩm.

    Bản cũ đáp "thời hạn 4 tháng nằm ngoài khung từ 12 đến 60 tháng" rồi hỏi sang
    thu nhập. Người dùng (09-10-2026): "hỏi 4-5 tháng nó trả lời chả rõ ràng" -
    khách không biết là được hay không, cũng không biết phải vay bao lâu. Nên
    câu ngoài khung luôn nêu đầu gần nhất và hỏi luôn khách có vay mức đó không.
    """
    ngan, dai = khung
    # Khách nói theo NĂM thì đọc khung theo năm khi chia hết ("60 tháng" -> "5
    # năm"): cùng một con số của tài liệu, chỉ đổi đơn vị cho khớp lời khách.
    theo_nam = theo_nam or ("năm" in khach_noi and dai % 12 == 0 and (ngan or 12) % 12 == 0)
    doc = lambda th: _doc_ky_han(th, theo_nam)
    # MỖI CÂU NGẮN CHỈ MANG MỘT CON SỐ, và câu mở đầu là phán quyết về kỳ hạn.
    # Tiếng được cất theo từng câu ngắn (`tieng_san` - kho mảnh): "vay 4 tháng
    # thì chưa được..." chỉ có vài chục biến thể nên dựng sẵn được hết, còn câu
    # số tiền dùng lại cho mọi kỳ hạn. Gộp hai con số vào một câu là thành hàng
    # nghìn tổ hợp, lần nào cũng phải sinh tiếng tại chỗ (đo 09-10-2026: 740ms
    # mới ra tiếng, so với 130ms khi có sẵn).
    mo = f"Dạ vay {khach_noi} thì chưa được ạ, "
    ve_tien = f" Còn số tiền {so_tien} thì trong hạn mức ạ." if so_tien else ""
    for ngoai, dau, ten in ((bool(ngan) and dai_kh < (ngan or 0), ngan, "ngắn nhất"),
                            (ngan_kh > dai, dai, "dài nhất")):
        if not ngoai:
            continue
        if da_noi:
            # Khách nhắc lại đúng kỳ hạn vừa bị từ chối: không đọc lại nguyên câu.
            return "ky_han_ngoai_khung", (
                f"Dạ em hiểu ạ, nhưng {'dưới' if ten == 'ngắn nhất' else 'trên'} "
                f"{doc(dau)} thì bên em chưa có. Anh chị vay {doc(dau)} được không ạ?")
        return "ky_han_ngoai_khung", (
            f"{mo}bên em cho vay {ten} là {doc(dau)}.{ve_tien} "
            f"Anh chị vay {doc(dau)} được không ạ?")
    ca_khung = (f"từ {ngan // 12 if theo_nam else ngan} đến {doc(dai)}" if ngan
                else f"dài nhất là {doc(dai)}")
    if (ngan or 0) <= ngan_kh and dai_kh <= dai:
        if ngan_kh != dai_kh:
            return "ky_han_trong_khung", (
                f"Dạ vay {khach_noi} thì được ạ. Anh chị chốt giúp em một thời hạn cụ thể ạ?")
        if so_tien:
            return "nhu_cau_vay", (
                f"Dạ vay {khach_noi} thì được ạ. Số tiền {so_tien} cũng trong hạn mức, "
                "còn hạn mức thực tế thì cần thẩm định theo hồ sơ ạ.")
        return "ky_han_trong_khung", f"Dạ vay {khach_noi} thì được ạ. Bên em cho vay {ca_khung}."
    # Khoảng khách nêu vắt qua một đầu của khung: không đoán họ chọn đầu nào.
    return "ky_han_ngoai_khung", (
        f"Dạ bên em cho vay {ca_khung} ạ. Anh chị chọn giúp em một thời hạn trong khoảng đó ạ?")


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


# Trong một câu khai thu nhập, "được không / được hông / đủ không" là hỏi có đạt
# điều kiện không (hàm này chỉ chạy trên câu có chữ lương/thu nhập + đại từ).
_HOI_DUOC_KHONG = re.compile(
    r"\bduoc (?:khong|hong|hok|ko|chua)\b|\bco duoc\b|"
    r"\bdu (?:dieu kien )?(?:khong|hong|chua)\b|\bduoc (?:vay )?bao nhieu\b")


def _thu_nhap_toi_thieu(sp_doc: str) -> float | None:
    """Mức thu nhập tối thiểu ghi trong mục Điều kiện của tài liệu (đồng/tháng)."""
    trong = False
    for dong in (sp_doc or "").splitlines():
        d = _bo_dau(dong).strip()
        if d.startswith("#"):
            trong = d.startswith("##") and "dieu kien" in d
            continue
        if trong and "thu nhap" in d:
            m = re.search(r"tu\s+(\d+(?:[.,]\d+)?)\s*trieu", d)
            if m:
                return float(m.group(1).replace(",", ".")) * 1e6
    return None


def _ghi_nhan_thu_nhap(text: str, xung_ho: str, sp_doc: str = "",
                       tran: float | None = None) -> tuple[str, str] | None:
    """Xác nhận đúng dữ kiện khách VỪA khai, không để model đổi con số.

    Khách hỏi luôn "... thì vay được không / được bao nhiêu" trong cùng câu thì
    phải đáp vế đó: đối chiếu với MỨC THU NHẬP TỐI THIỂU ghi trong tài liệu và
    nêu hạn mức sản phẩm, không phán hồ sơ được duyệt hay không. Bộ thử
    10-10-2026: "lương mười hai triệu ... thì vay được không và được bao nhiêu"
    chỉ nhận "em ghi nhận thu nhập 12 triệu".
    """
    t = _bo_dau(text)
    if not _la_ngu_canh_thu_nhap(text):
        return None
    # Chỉ nhận đây là hồ sơ của khách khi câu có đại từ tự xưng. Câu hỏi chung
    # "thu nhập bao nhiêu thì được vay" không được biến thành dữ kiện cá nhân.
    if not re.search(r"\b(anh|chi|toi|minh|em)\b", t):
        return None
    du_kien = resolve([{"role": "user", "content": text}]).income
    thu_nhap = float(du_kien.value) if du_kien.value is not None else None
    khoang = du_kien.khoang
    m = _NAM_LAM_VIEC.search(text)
    nam = None
    if m:
        raw = m.group(1)
        nam = int(raw) if raw.isdigit() else _chu_thanh_so(raw.lower())
    # "lương anh ba chục vợ anh hai chục": giữ cả hai mức để xác nhận đúng
    # lời khách, dù projection đã chọn riêng 30 triệu là thu nhập `self`.
    hai_muc = None
    if not khoang and re.search(r"\b(vo|chong)\b", t):
        from backend.pipeline.du_kien_khoan_vay import quantities
        cac_so = [q for q in quantities(text) if q.value and q.kind in ("bare", "money")]
        if len(cac_so) == 2 and re.search(r"\b(vợ|chồng)\b", text[cac_so[0].end:cac_so[1].start].lower()):
            hai_muc = tuple(float(q.value) * (1e6 if q.kind == "bare" else 1) for q in cac_so)
    toi_thieu = _thu_nhap_toi_thieu(sp_doc)
    hoi_dieu_kien_rieng = bool(toi_thieu and _HOI_DUOC_KHONG.search(t))
    # Chỉ hỏi lại chủ sở hữu khi khách thực sự vừa nêu một MỨC thu nhập ngoài
    # cá nhân/hộ gia đình. Câu không có con số như ``làm tự do, thu nhập không
    # đều`` phải đi tiếp tới luật điều kiện nghề nghiệp có nguồn phía dưới.
    if (hoi_dieu_kien_rieng and du_kien.owner != "self"
            and (thu_nhap is not None or khoang)):
        noi_nguon = ("Mức anh chị vừa nêu là thu nhập chung của hộ gia đình. "
                     if du_kien.owner == "household" else
                     "Mức thu nhập vừa nêu chưa được xác định là thu nhập của chính anh chị. ")
        return "xac_nhan_thu_nhap_ca_nhan", (
            f"Dạ điều kiện của bên em yêu cầu thu nhập cá nhân từ "
            f"{_fmt_trieu(toi_thieu)} một tháng ạ. {noi_nguon}"
            "Anh chị cho em biết thu nhập riêng mỗi tháng của người đứng tên vay để đối chiếu ạ.")
    if thu_nhap is None and nam is None and not khoang and not hai_muc:
        return None

    cac = []
    if nam is not None:
        cac.append(f"đã làm việc tại công ty {nam} năm")
    kenh = " chuyển khoản" if "chuyen khoan" in t else ""
    if hai_muc:
        dau = _fmt_trieu(hai_muc[0]).replace(" triệu đồng", " triệu")
        cac.append(f"thu nhập hai vợ chồng là {dau} và {_fmt_trieu(hai_muc[1])} một tháng")
    elif du_kien.owner == "household" and thu_nhap is not None:
        cac.append(f"thu nhập chung của hộ gia đình là {_fmt_trieu(thu_nhap)} một tháng")
    elif thu_nhap is not None:
        cac.append(f"thu nhập{kenh} {_fmt_trieu(thu_nhap)} một tháng")
    elif khoang:
        # "lương mười lăm mười sáu gì đấy": đọc lại đúng khoảng khách nói.
        dau = _fmt_trieu(float(khoang[0])).replace(" triệu đồng", "")
        cac.append(f"thu nhập{kenh} khoảng {dau} đến {_fmt_trieu(float(khoang[1]))} một tháng")
    muc_ca_nhan = (float(khoang[0]) if du_kien.owner == "self" and khoang
                   else thu_nhap if du_kien.owner == "self" else None)
    if muc_ca_nhan is not None and hoi_dieu_kien_rieng:
        noi = (f"thu nhập {_fmt_trieu(thu_nhap)}" if thu_nhap is not None
               else cac[-1].replace(" một tháng", ""))
        if muc_ca_nhan >= toi_thieu:
            cau = (f"Dạ {noi} một tháng thì đạt mức thu nhập tối thiểu "
                   f"{_fmt_trieu(toi_thieu)} của bên em ạ.")
            if tran:
                cau += (f" Hạn mức tối đa là {_fmt_trieu(tran)}, "
                        "mức được duyệt còn tuỳ thẩm định hồ sơ ạ.")
            return "thu_nhap_dat_muc", cau
        return "thu_nhap_duoi_muc", (
            f"Dạ bên em yêu cầu thu nhập từ {_fmt_trieu(toi_thieu)} một tháng ạ. "
            f"Với {noi} thì em xin ghi nhận để chuyên viên xem thêm hồ sơ giúp {xung_ho} ạ.")
    return "ghi_nhan_thu_nhap", (
        f"Dạ em ghi nhận {xung_ho} " + _noi_danh_sach(cac) + " ạ."
    )


_LO_LANG_GANH_TRA = re.compile(
    r"\b(khong kham|khong du (?:tien|kha nang)|lay gi an|ap luc|qua suc|nang qua)\b")
_NHAC_KHOAN_TRA = re.compile(r"\b(tra|dong|gop|khoan tra|tien tra)\b")


def _can_nhac_kha_nang_tra(text: str, state: LoanState, sp_doc: str) \
        -> tuple[str, str] | None:
    """Phản hồi lo gánh trả bằng phép tính nguồn, không tự đặt ngưỡng DTI."""
    t = _bo_dau(text)
    if not (_LO_LANG_GANH_TRA.search(t) and _NHAC_KHOAN_TRA.search(t)):
        return None

    dau = "Dạ em hiểu anh chị đang lo khoản trả hàng tháng ảnh hưởng đến chi tiêu sinh hoạt ạ."
    so_tien = float(state.amount.value) if state.amount.value is not None else None
    thang = int(state.term.value) if state.term.value is not None else None
    thu_nhap = float(state.income.value) if state.income.value is not None else None

    # `owner` do projection dữ kiện gắn từ chính lời khách. Không suy chủ sở
    # hữu lần nữa ở đây từ raw history; chỉ `self` được đem so sánh như thu
    # nhập của người gọi. Thiếu provenance cũng phải hỏi lại, không được coi là
    # self theo mặc định.
    owner = getattr(state.income, "owner", "")
    if owner != "self":
        if owner == "household":
            return "can_nhac_kha_nang_tra", (
                f"{dau} Mức thu nhập đang được ghi nhận là thu nhập chung của hộ gia đình, "
                "nên em chưa thể coi đó là thu nhập riêng của người sẽ trả khoản vay. Anh chị "
                "xác nhận giúp phần thu nhập mỗi tháng của chính người trả khoản vay ạ.")
        return "can_nhac_kha_nang_tra", (
            f"{dau} Em chưa có mức thu nhập mỗi tháng của chính anh chị để so sánh với "
            "khoản trả. Anh chị cho em biết mức thu nhập của người sẽ trả khoản vay ạ.")

    if state.income.khoang:
        a, b = (float(x) for x in state.income.khoang)
        return "can_nhac_kha_nang_tra", (
            f"{dau} Anh chị đang nêu thu nhập khoảng {_fmt_trieu(a)} đến "
            f"{_fmt_trieu(b)} một tháng, nên em chưa thể so sánh bằng một mức xác định. "
            "Anh chị cho em một mức thu nhập dự kiến cụ thể mỗi tháng để em ước tính ạ.")
    if state.income.status == "ambiguous":
        return "can_nhac_kha_nang_tra", (
            f"{dau} Anh chị đang nêu nhiều mức thu nhập nên em chưa thể so sánh bằng "
            "một mức xác định. Anh chị cho em một mức thu nhập dự kiến cụ thể mỗi tháng "
            "để em ước tính ạ.")

    thieu = []
    if so_tien is None:
        thieu.append("số tiền muốn vay kèm đơn vị")
    if thang is None:
        thieu.append("thời hạn vay")
    if thu_nhap is None:
        thieu.append("thu nhập mỗi tháng")
    if thieu:
        return "can_nhac_kha_nang_tra", (
            f"{dau} Để so sánh khoản trả ước tính với thu nhập, anh chị cho em biết "
            f"{_noi_danh_sach(thieu)} ạ.")

    khung = _thoi_han(sp_doc)
    toi_da = None if khung else _thoi_han_toi_da(sp_doc)
    if ((khung and not (khung[0] <= thang <= khung[1]))
            or (toi_da and not (0 < thang <= toi_da))):
        gioi_han = (f"từ {khung[0]} đến {khung[1]} tháng" if khung
                     else f"tối đa {toi_da} tháng")
        return "can_nhac_kha_nang_tra", (
            f"{dau} Thời hạn {thang} tháng nằm ngoài khung {gioi_han} của tài liệu, "
            "nên em chưa dùng công thức để ước tính khoản trả. Anh chị cho em một thời hạn "
            "trong khung này ạ.")

    tran = _tran_san_pham(sp_doc)
    if tran and so_tien > tran:
        return "can_nhac_kha_nang_tra", (
            f"{dau} Số tiền {_fmt_trieu(so_tien)} vượt hạn mức tối đa "
            f"{_fmt_trieu(tran)} trong tài liệu, nên em chưa thể ước tính phương án đó ạ.")
    lai = _lai_suat(sp_doc)
    if lai is None:
        return "can_nhac_kha_nang_tra", (
            f"{dau} Tài liệu hiện chưa có lãi suất xác định để em ước tính khoản trả ạ.")

    thang_dau = so_tien / thang + so_tien * lai / 100 / 12
    so_sanh = ("cao hơn" if thang_dau > thu_nhap else
               "thấp hơn" if thang_dau < thu_nhap else "bằng")
    return "can_nhac_kha_nang_tra", (
        f"{dau} Với khoản vay {_fmt_trieu(so_tien)} trong {thang} tháng, tạm tính theo "
        f"lãi suất từ {str(lai).replace('.', ',')}% một năm trên dư nợ giảm dần, tháng đầu "
        f"khoảng {_fmt_trieu(thang_dau, uoc_tinh=True)}, {so_sanh} mức thu nhập "
        f"{_fmt_trieu(thu_nhap)} anh chị đã nêu. Đây là so sánh ước tính, chưa đủ để kết luận "
        "phương án phù hợp hay hồ sơ được duyệt. Anh chị nên xem lại số tiền, thời hạn, chi phí "
        "sinh hoạt và các khoản nợ khác trước khi quyết định ạ.")


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
    if value.endswith(".0"):
        value = value[:-2]            # "45,0 triệu" đọc lên thành "phẩy không"
    return value.replace(".", ",") + " triệu đồng"


# Chủ đề hẹp khách nêu đích danh. Tài liệu đang dùng (sản phẩm + FAQ) không có
# chữ nào của nhóm thì nói thật là chưa có thông tin. Đo 02-10-2026: "lãi suất
# thấu chi" được luật lãi suất đọc thành "lãi suất gói vay 7,9%", còn "ứng tiền
# mặt bằng thẻ có miễn lãi không" được mô hình đáp "mọi giao dịch miễn lãi 55
# ngày" - ứng tiền mặt thật ra không được miễn lãi.
_CHU_DE_HEP = (
    ("ứng tiền mặt", ("ung tien", "ung truoc", "rut tien mat")),
    ("thấu chi", ("thau chi",)),
    ("trả nợ trước hạn", ("tra no truoc han", "tra truoc han", "tat toan truoc", "tat toan som")),
    ("rút tiền trước hạn", ("rut truoc han", "rut tien truoc", "rut truoc ky han")),
    ("bảo hiểm", ("bao hiem",)),
)
_TEN_SP = (("tiet_kiem", "tiet kiem"), ("the_tin_dung", "the tin dung"),
           ("vay_mua_nha", "vay mua nha"), ("vay_tin_chap", "vay tin chap"))


def _chu_de_khong_co(t: str, tai_lieu: str, ma_sp: str) -> str | None:
    if not (tai_lieu or "").strip():
        return None  # chưa biết sản phẩm: để RAG tra cả kho
    # Câu nêu SẢN PHẨM KHÁC thì là đổi chủ đề, không phải hỏi trong tài liệu này.
    if any(cum in t for ma, cum in _TEN_SP if ma != ma_sp):
        return None
    doc = _bo_dau(tai_lieu)
    for ten, cac in _CHU_DE_HEP:
        if (any(re.search(rf"\b{c}\b", t) for c in cac)
                and not any(re.search(rf"\b{c}\b", doc) for c in cac)):
            return ten
    return None


_MUON_VAY = re.compile(
    r"(?:(?:a|o|u|um|da|em|oi|thi|la|anh|chi|toi|bac|co|chu|chau|dang|cung)\s+)*"
    r"(?:muon|can|dinh|tinh)\s+(?:vay|may)"
    r"(?:\s+(?:tien|it tien|mot it tien|mot it|it|mot so tien|mot khoan|it von))*"
    r"(?:\s+(?:a|o|ay|ma|day|em|nhe|thoi))*")


def _muc_san_pham(tai_lieu: str) -> tuple[float | None, int | None]:
    """(hạn mức tối đa, thời hạn dài nhất theo tháng) của sản phẩm trong `tai_lieu`."""
    sp_doc = _phan_san_pham(tai_lieu or "")
    ky = _thoi_han(sp_doc)
    return _tran_san_pham(sp_doc), (ky[1] if ky else _thoi_han_toi_da(sp_doc))


def du_kien_cua_luot(history: list[dict] | None, text: str | None,
                     tai_lieu: str) -> LoanState:
    """Sổ dữ kiện khoản vay của lượt này, suy đơn vị theo hạn mức của `tai_lieu`.

    Nơi nào cần sổ để đưa vào `tra_loi(du_kien=...)` thì lấy qua đây, đừng gọi
    `resolve` trần: thiếu hạn mức sản phẩm thì "vay hai" ở vay mua nhà không
    thành 2 tỷ, và hai nơi sẽ nhìn ra hai sổ khác nhau.
    """
    with voi_tran_san_pham(*_muc_san_pham(tai_lieu)):
        return resolve(history, text)


def tra_loi(text: str, tai_lieu: str, ho_so: dict | None = None,
            history: list[dict] | None = None, xung_ho: str = "anh chị",
            du_kien: LoanState | None = None) \
        -> tuple[str, str] | None:
    """Trả ``(mã, câu)`` khi đủ dữ kiện để trả lời xác định."""
    # Mọi lần đọc sổ dữ kiện bên trong đều suy đơn vị theo hạn mức sản phẩm này.
    with voi_tran_san_pham(*_muc_san_pham(tai_lieu)):
        return _tra_loi(text, tai_lieu, ho_so, history, xung_ho, du_kien)


def _tra_loi(text: str, tai_lieu: str, ho_so: dict | None = None,
             history: list[dict] | None = None, xung_ho: str = "anh chị",
             du_kien: LoanState | None = None) \
        -> tuple[str, str] | None:
    t = re.sub(r"\bhang muc\b", "han muc", _bo_dau(text))
    if not t:
        return None
    ma_sp = _ma_san_pham(tai_lieu)
    sp_doc = _phan_san_pham(tai_lieu)
    chu_de = _chu_de_khong_co(t, tai_lieu, ma_sp)
    if chu_de:
        return "chua_co_thong_tin_chu_de", (
            f"Dạ phần {chu_de} hiện em chưa có thông tin chính xác, em xin phép kiểm tra "
            f"lại và báo {xung_ho} sau ạ.")
    # Tiết kiệm và thẻ không phải khoản vay: KHÔNG chạy luật nhu cầu/trần/trả
    # góp bên dưới cho chúng, kể cả khi khách nói "gửi 100 triệu 12 tháng".
    if ma_sp == "tiet_kiem":
        return _tra_loi_tiet_kiem(text, t, sp_doc, history) or tra_loi_dieu_kien(text, ma_sp, sp_doc)
    if ma_sp == "the_tin_dung":
        # Khách khai lương rồi hỏi "làm thẻ được không": đối chiếu mức thu nhập
        # tối thiểu của tài liệu, như với khoản vay.
        return (_tra_loi_the_tin_dung(t, sp_doc, text)
                or _ghi_nhan_thu_nhap(text, xung_ho, sp_doc)
                or tra_loi_dieu_kien(text, ma_sp, sp_doc))
    # Chưa có tài liệu sản phẩm (kịch bản riêng như Shinhan, hoặc chưa biết sản
    # phẩm) mà khách nêu rõ thẻ/tiết kiệm: luật bên dưới là luật KHOẢN VAY.
    # "thẻ tín dụng Shinhan miễn lãi bao nhiêu ngày" từng nhận "cho em biết số
    # tiền muốn vay và thời hạn vay" (02-10-2026).
    if not ma_sp and re.search(r"\b(the tin dung|tiet kiem)\b", t):
        return None
    state = du_kien if du_kien is not None else resolve(history, text)
    if state.amount_updated and state.amount.status == "cancelled":
        return "huy_nhu_cau_vay", "Dạ em ghi nhận anh chị không tiếp tục nhu cầu vay này ạ."

    nhac_lai = _tra_loi_nhac_lai(text, history, xung_ho)
    if nhac_lai:
        return nhac_lai
    if is_readback(text):
        # Một con số nghe chưa rõ không phải là nhu cầu mới của khách. Hỏi rõ
        # ngay để mô hình không tự gắn "ba trăm" thành khoản vay 300 triệu.
        return "xac_nhan_y_nghe_lai", (
            f"Dạ {xung_ho} muốn em nhắc lại phần nào vừa nói ạ?")

    # A question explicitly about an existing contract belongs to the profile
    # route, even when a separate new-loan request has already been discussed.
    hop_dong_rieng = re.search(
        r"\bhop dong(?: vay)?\s+(?:cu|hien tai|truoc day|cua (?:anh|chi|toi|minh|em))\b|"
        r"\bhop dong\s+(?:so|ma)\b", t)
    if not (state.amount_updated or state.term_updated) and (
            hop_dong_rieng or re.search(
                r"\b(khoan vay cu|han muc da duyet)\b|\bdu no\b(?! giam dan)", t)):
        return None

    can_nhac_tra = _can_nhac_kha_nang_tra(text, state, sp_doc)
    if can_nhac_tra:
        return can_nhac_tra

    ghi_nhan = None if state.amount_updated else _ghi_nhan_thu_nhap(
        text, xung_ho, sp_doc, _tran_san_pham(sp_doc))
    if ghi_nhan:
        return ghi_nhan

    # Trước khi đọc số tiền: "anh 45 tuổi vay được không" không phải nhu cầu 45.
    dieu_kien = tra_loi_dieu_kien(text, ma_sp, sp_doc)
    if dieu_kien:
        return dieu_kien

    tran = _tran_san_pham(sp_doc)
    ky_han = _thoi_han(sp_doc)
    # "anh muốn vay ờ", "anh đang muốn vay ít tiền ấy mà": lời mở đầu chưa có con
    # số nào. Nhận lời bằng một dữ kiện của sản phẩm, lớp dẫn dắt hỏi tiếp số
    # tiền. Bộ thử 10-10-2026: kho đáp "mở ứng dụng ngân hàng để đăng ký".
    if tran and state.amount.status == "unknown" and _MUON_VAY.fullmatch(
            re.sub(r"[^a-z0-9\s]", " ", t).strip()):
        return "muon_vay", f"Dạ vâng ạ, gói vay bên em hỗ trợ tối đa {_fmt_trieu(tran)} ạ."
    # Khung để xét kỳ hạn khách nêu. Vay mua nhà chỉ ghi "tối đa 25 năm": không
    # có đầu ngắn nhất, và khách nói theo NĂM nên đọc lại cũng theo năm.
    toi_da = None if ky_han else _thoi_han_toi_da(sp_doc)
    khung = ky_han or ((None, toi_da) if toi_da else None)
    theo_nam = bool(toi_da and toi_da % 12 == 0)

    def khach_noi_ky_han(so_thang: int) -> str:
        noi_nam = "nam" in _bo_dau(state.term.raw) or theo_nam
        return _doc_ky_han(so_thang, noi_nam and so_thang % 12 == 0)

    ai_vua_noi = next((m.get("content", "") for m in reversed(history or [])
                       if m.get("role") == "assistant"), "")
    # AI vừa báo một kỳ hạn chưa được: khách nhắc lại thì không đọc lại nguyên câu.
    vua_tu_choi_ky_han = "thì chưa được" in ai_vua_noi
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

    # "khi nào thì có tiền" là hỏi giải ngân (bộ thử 10k #3380: mô hình đáp
    # "chưa có thông tin về thời gian giải ngân" dù tài liệu ghi 24 giờ).
    # "khi nào có tiền anh trả" thì không: có trả/đóng/gửi là chuyện khác.
    hoi_co_tien = bool(re.search(
        r"\b(khi nao|bao lau|bao gio|may ngay|may gio)\b.{0,16}\b(co tien|nhan (?:duoc )?tien|"
        r"lay (?:duoc )?tien|ra tien|tien ve)\b|"
        r"\b(co tien|nhan (?:duoc )?tien|tien ve)\b.{0,12}\b(khi nao|bao lau|bao gio|may ngay)\b", t)
    ) and not re.search(r"\b(tra|dong|gui|nop)\b", t.replace("hop dong", ""))
    if ((re.search(r"\bgiai ngan\b", t)
            and re.search(r"\b(bao lau|khi nao|may ngay|may gio)\b", t)) or hoi_co_tien):
        gia_tri = _gia_tri_dong(sp_doc, "giải ngân")
        if gia_tri:
            if re.search(r"\b(phi|phat)\b", t):
                uu_dai = _muc_tai_lieu(sp_doc, "ưu đãi")
                phi = next((d for d in uu_dai if re.search(
                    r"\bmien phi tu van\b.*\btham dinh\b", _bo_dau(d))), None)
                phi_cau = (("Theo tài liệu hiện có, " + phi[:1].lower() + phi[1:].rstrip(".") + " ạ.") if phi else
                           "Phần phí em chưa có thông tin chính xác để xác nhận ạ.")
                return "giai_ngan_va_phi", (
                    f"Dạ bên em giải ngân {gia_tri} ạ. {phi_cau}")
            return "thoi_gian_giai_ngan", f"Dạ bên em giải ngân {gia_tri} ạ."

    # Không có chữ "phí/phạt" vẫn là hỏi trả trước hạn: "khi nào có tiền thì anh
    # trả nợ trước hạn được không" rơi xuống mô hình, mô hình lúc nói "miễn phí"
    # lúc nói "chưa có thông tin về chính sách trả nợ trước hạn".
    if (re.search(r"\b(?:tra(?: het)?(?: no)?|tat toan)(?:.{0,16}truoc han\b|\s+(?:het\s+)?(?:no\s+)?som\b)", t)
            and re.search(r"\b(phi|phat|duoc khong|co duoc|duoc ko|the nao|nhu nao|ra sao|"
                          r"thi sao|co mat|mat gi|co sao)\b", t)):
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
    # "thế ngắn nhất là bao lâu", "vay tối thiểu mấy tháng": hỏi MỘT ĐẦU của
    # khung thì đáp đúng đầu đó trước. Kho từng đáp "vay tối đa 500 triệu với hạn
    # 12-60 tháng" cho câu này (09-10-2026).
    if ky_han and re.search(r"\b(ngan nhat|toi thieu|it nhat)\b", t) and re.search(
            r"\b(bao lau|may thang|bao nhieu thang|may nam|bao nhieu nam|thoi han|ky han|"
            r"thoi gian)\b", t) and not re.search(
            r"\b(giai ngan|duyet|phe duyet|tham dinh|xet|nhan tien|thu nhap|luong)\b", t):
        return "ky_han_ngan_nhat", (
            f"Dạ bên em cho vay ngắn nhất là {ky_han[0]} tháng, dài nhất là {ky_han[1]} tháng ạ.")
    if ky_han and re.search(r"\b(dai nhat|lau nhat)\b", t) and re.search(
            r"\b(bao lau|may thang|bao nhieu thang|may nam|bao nhieu nam|thoi han|ky han|"
            r"thoi gian)\b", t) and not re.search(
            r"\b(giai ngan|duyet|phe duyet|tham dinh|xet|nhan tien)\b", t):
        return "ky_han_dai_nhat", (
            f"Dạ bên em cho vay dài nhất là {ky_han[1]} tháng, ngắn nhất là {ky_han[0]} tháng ạ.")
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
        elif state.amount.raw.count(" / ") == 1 and all(
                re.search(r"\b(triệu|tỷ|tỉ|tr)\b", phan) for phan in state.amount.raw.split(" / ")):
            # Khách nêu HAI mức có đủ đơn vị ("một tỷ đến hai tỷ gì đó"): xin chốt
            # một mức, đừng đòi "kèm đơn vị" thứ khách đã nói.
            ma, cau = "xac_nhan_so_tien_vay", (
                f"Dạ {xung_ho} chốt giúp em một số tiền cụ thể muốn vay ạ.")
        else:
            ma, cau = "xac_nhan_so_tien_vay", (
                f"Dạ {xung_ho} nhắc lại giúp em một số tiền muốn vay, kèm đơn vị triệu hoặc tỷ đồng ạ."
            )
        if not _vua_hoi(history, cau):
            return ma, cau
    # Khách nêu một KHOẢNG ("4-5 tháng", "vài tháng"): chưa đủ để tính, nhưng đủ
    # để nói khoảng đó có vay được không - đừng hỏi lại "bao nhiêu tháng" khi cả
    # khoảng đều nằm ngoài thời hạn của sản phẩm.
    if state.term_updated and state.term.khoang and khung:
        ngan_kh, dai_kh = (int(x) for x in state.term.khoang)
        so_tien_noi = (_fmt_trieu(float(state.amount.value))
                       if state.amount_updated and state.amount.value is not None else "")
        return _dap_ky_han(ngan_kh, dai_kh, state.term.raw, khung, theo_nam, so_tien_noi,
                           da_noi=vua_tu_choi_ky_han)
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
        # Kỳ hạn sản phẩm không có thì không tính trả góp cho nó.
        if khung and not ((khung[0] or 0) <= thang <= khung[1]):
            return _dap_ky_han(thang, thang, khach_noi_ky_han(thang), khung, theo_nam,
                               da_noi=vua_tu_choi_ky_han)
        lai = _lai_suat(sp_doc)
        if lai is None:
            return None
        if tran and so_tien > tran:
            return "vuot_han_muc", (
                f"Dạ nhu cầu {_fmt_trieu(so_tien)} đang vượt hạn mức tối đa "
                f"{_fmt_trieu(tran)} của gói này, nên em chưa thể tính phương án đó ạ."
            )
        thang_dau = so_tien / thang + so_tien * lai / 100 / 12
        # Câu DẪN cố định đi trước (có tiếng sẵn, dài ~4 giây), câu mang con số
        # theo sau: tiếng của câu số được dựng trong lúc khách nghe câu dẫn, nên
        # tổ hợp số tiền x kỳ hạn nào cũng ra tiếng ngay.
        return "tinh_tra_gop", (
            f"Dạ em tạm tính theo lãi suất từ {str(lai).replace('.', ',')}% một năm, "
            "trên dư nợ giảm dần ạ. "
            f"Nếu được duyệt {_fmt_trieu(so_tien)} trong {khach_noi_ky_han(thang)} thì tháng đầu "
            f"trả khoảng {_fmt_trieu(thang_dau, uoc_tinh=True)}, các tháng sau giảm dần. "
            "Đây là số ước tính, chưa phải lịch trả nợ chính thức."
        )

    # Con số phải nằm trong CHÍNH câu này. "nợ tất toán ... có vay được không"
    # 4 lượt sau khi khách nêu 100 triệu không phải là hỏi lại về 100 triệu.
    hoi_duoc_khong = state.amount_updated and bool(re.search(
        r"\b(vay|may)\b.{0,45}\b(duoc khong|co duoc)\b", t))
    neu_nhu_cau = state.amount_updated or bool(re.search(
        r"\b(muon (?:vay|may)|can vay|nhu cau|vay tam|vay khoang|dang vay|"
        r"can nhac vay|du dinh vay|xin vay)\b", t)
        or hoi_duoc_khong)
    # Khách nêu KỲ HẠN muốn vay ngay trong câu này mà chưa nói số tiền: "anh
    # muốn vay mười hai tháng được không". Phải đáp ĐƯỢC hay KHÔNG. Cuộc gọi
    # 7b63d2db (08-10-2026): kho đáp "thời hạn từ 12 đến 60 tháng" ba lần liền
    # cho ba lần khách hỏi lại, vì câu đó không nói ra chữ "được".
    # ... hoặc khách chỉ đáp cụt "mười hai tháng" cho câu AI vừa hỏi "vay trong
    # bao lâu": cũng là nêu kỳ hạn. Không có nhánh này, lượt đó rơi xuống mô
    # hình và nó tự tính tiền trả góp (bộ thử 304 lượt, 08-10-2026).
    ai_vua_hoi_ky_han = bool(re.search(
        r"\b(bao lau|may thang|bao nhieu thang|may nam|vay \d+ (?:thang|nam) duoc khong|"
        r"mot thoi han)\b",
        _bo_dau(ai_vua_noi)))
    # Khách gật với thời hạn AI vừa đề nghị ("vay 12 tháng được không ạ?" - "ừ
    # được"): xác nhận lại cho rõ rồi để lớp dẫn dắt hỏi ý kế tiếp.
    if state.nhan_de_nghi and thang:
        return "ghi_nhan_ky_han", f"Dạ vâng, em ghi nhận thời hạn vay {khach_noi_ky_han(thang)} ạ."
    # "trả mười lăm năm", "trả góp ba năm": cũng là nêu kỳ hạn muốn vay.
    if (state.term_updated and thang and khung and not state.amount_updated
            and (re.search(r"\b(vay|may|tra|gop)\b", t) or ai_vua_hoi_ky_han)):
        return _dap_ky_han(thang, thang, khach_noi_ky_han(thang), khung, theo_nam,
                           da_noi=vua_tu_choi_ky_han)

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
    # Khách nêu CẢ kỳ hạn trong chính câu này ("năm trăm triệu trong mười hai
    # tháng") thì phải đáp cả vế đó. Cuộc gọi 08-10-2026: AI chỉ nói về 500
    # triệu, khách phải hỏi lại vì tưởng máy không nghe thấy "mười hai tháng".
    if state.term_updated and thang and khung:
        return _dap_ky_han(thang, thang, khach_noi_ky_han(thang), khung, theo_nam,
                           _fmt_trieu(so_tien), da_noi=vua_tu_choi_ky_han)
    # Câu NGẮN (25 từ thay vì 34) để còn chỗ nối câu hỏi dẫn dắt phía sau - bản
    # dài làm lượt này luôn kết thúc cụt, không hỏi được thời hạn (`dan_dat`).
    # Hai câu: câu đầu chỉ mang số tiền của khách (ngắn, dựng sẵn được cho mọi
    # mức hay gặp), câu sau cố định theo sản phẩm.
    return "nhu_cau_vay", (
        f"Dạ {_fmt_trieu(so_tien)} thì trong hạn mức ạ. "
        f"Bên em cho vay tối đa {_fmt_trieu(tran)}, hạn mức thực tế vẫn cần thẩm định theo hồ sơ."
    )
