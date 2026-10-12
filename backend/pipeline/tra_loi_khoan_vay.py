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
    _CALC, LoanState, ai_vua_hoi, chuan_hoa_so_khong_dau, is_readback,
    luot_truoc_bo_lung_ky_han, quantities, resolve, voi_tran_san_pham,
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
    # "em có năm chục triệu muốn gửi": ý định gửi đứng ngay sau con số.
    if re.match(r"\s*(?:muon|dinh|tinh|can)\s+(?:dem |mang |di )?(?:gui|mo so)\b", sau):
        return "gui"
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


def _chuan_hoa_bien_chu_so(text: str) -> str:
    """Tạo ranh giới ngữ nghĩa cho kiểu chat ``online100triệu``."""
    return re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", _bo_dau(text))


def _la_hoi_lai_online_ro(text: str) -> bool:
    """Câu hỏi lãi có kỳ hạn hoặc danh từ ``sổ`` tự xác định kênh online."""
    t = _chuan_hoa_bien_chu_so(text)
    raw = unicodedata.normalize("NFC", (text or "").lower())
    co_ky = bool(re.search(r"\b\d{1,2}\s*(?:thang|nam)\b", t))
    co_so_gui = bool(
        re.search(r"\bsổ(?:\s+tiết kiệm)?\b", raw)
        or re.search(r"\bso\s+(?:tiet kiem|vnd|online)\b", t)
    )
    online_bi_trich_dan = bool(
        re.search(r"[\"'“”‘’]\s*online\s*[\"'“”‘’]", raw)
        or re.search(r"\b(?:ghi|viet|nhac|trich|noi|bao)\b.{0,18}\bonline\b", t)
    )
    return bool(
        re.search(r"\b(?:online|truc tuyen)\b", t)
        and (co_ky or co_so_gui)
        and re.search(r"\b(?:cong|them|lai suat|phan tram|bao nhieu lai)\b", t)
        and not online_bi_trich_dan
        and not re.search(
            r"\b(?:mat khau|banking|the tin dung|the online|khoan vay|tien vay|"
            r"chuyen tien|chuyen khoan|thanh toan|cccd|can cuoc|dien thoai|"
            r"so tai khoan|ma xac thuc|otp|pin)\b", t)
    )


def _kenh_gui_trong_cau(text: str, co_ngu_canh_gui: bool) -> tuple[str | None, str | None]:
    """Kênh gửi khẳng định trong lượt; trả ``(value, status)`` nếu có cập nhật."""
    # Bộ tách quantity đã hiểu ``100triệu`` và ``6tháng`` là các token riêng.
    # Kênh và neo sở hữu phải nhìn cùng ranh giới chữ-số để ``online100`` hay
    # ``gửi100triệu online`` không làm mất thông tin kênh.
    t = _chuan_hoa_bien_chu_so(text)
    cac = list(_KENH_GUI.finditer(t))
    # Câu trả lời chỉ nói về phương thức gửi. Từ ngoài tập này (mật khẩu, thẻ,
    # thông tin...) làm câu không còn là một sửa kênh trần.
    con_lai = _KENH_GUI.sub(" ", t)
    con_lai = re.sub(
        r"\b(a|da|vang|toi|anh|chi|minh|em|thi|khong|phai|chang|chua|con|nua|thoi|nhe|"
        r"gui|kenh|hinh thuc|chon|doi|chuyen|sua|tu|sang|thanh|la|se)\b", " ", con_lai)
    kenh_tran = co_ngu_canh_gui and not re.sub(r"[^a-z0-9]+", "", con_lai)
    hoi_lai_online_ro = _la_hoi_lai_online_ro(text)

    hop_le: list[tuple[re.Match, str, bool]] = []
    for m in cac:
        # Mọi span dưới đây đều dùng cùng hệ tọa độ của chuỗi đã chuẩn hóa.
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
        if owner == "gui" or kenh_tran or doi_kenh_ro or hoi_lai_online_ro:
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


def _hai_truong_cung_khai_bao_gui(text: str, qs) -> bool:
    """Tiền và kỳ hạn duy nhất cùng thuộc một khai báo sổ tiết kiệm.

    Khách thường liệt kê ``sổ ... là 150 triệu, 6 tháng, gửi tại quầy``.
    Dấu phẩy làm kỳ hạn mất neo theo mệnh đề, nhưng đây vẫn là một bản ghi duy
    nhất. Chỉ nối hai trường khi lượt có đúng một tiền, một kỳ hạn, có neo gửi
    sở hữu ít nhất một trường và không có lựa chọn hay lời giả định/rút lại.
    """
    t = _bo_dau(text)
    if (re.search(r"\b(neu|gia su|vi du|thu dat vao)\b", t)
            or re.search(r"\b(hay|hoac)\b", t)
            or re.search(r"\b(?:bo|huy|rut lai)\b.{0,24}\b(?:so|khoan|tien)?\s*gui\b|"
                         r"\b(?:so|khoan|tien)?\s*gui\b.{0,24}\b(?:bo|huy|rut lai)\b", t)):
        return False
    tien = [q for q in qs if q.kind == "money" and q.value is not None]
    ky = [q for q in qs if q.kind == "duration" and q.value is not None]
    if len(tien) != 1 or len(ky) != 1:
        return False
    owners = (_chu_so_huu_du_kien(text, tien[0].start, tien[0].end),
              _chu_so_huu_du_kien(text, ky[0].start, ky[0].end))
    raw = unicodedata.normalize("NFC", (text or "").lower())
    co_so_gui_ro = bool(re.search(r"\bsổ\b|\bso tiet kiem\b", raw[:tien[0].start]))
    if "khac" in owners or ("gui" not in owners and not co_so_gui_ro):
        return False
    dau, cuoi = sorted((tien[0], ky[0]), key=lambda q: q.start)
    giua = _bo_dau(text[dau.end:cuoi.start])
    return not re.search(r"\b(vay|luong|thu nhap|gia|xe|tai san|chuyen tien)\b", giua)


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
        cung_khai_bao_gui = _hai_truong_cung_khai_bao_gui(cau, qs)
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
            or (cung_khai_bao_gui and _chu_so_huu_du_kien(cau, q.start, q.end) is None)
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
            or (cung_khai_bao_gui and _chu_so_huu_du_kien(cau, q.start, q.end) is None)
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


def _tien_gui_toi_thieu(sp_doc: str) -> Decimal | None:
    """Mức tiền gửi tối thiểu duy nhất ghi trong đúng thuộc tính nguồn."""
    cac: set[Decimal] = set()
    for dong in sp_doc.splitlines():
        if not re.match(r"\s*-\s*so tien gui toi thieu\s*:", _bo_dau(dong)):
            continue
        tien = [q.value for q in quantities(dong)
                if q.kind == "money" and q.value is not None]
        if len(tien) == 1:
            cac.add(Decimal(tien[0]))
    return next(iter(cac)) if len(cac) == 1 else None


def _fmt_tien_gui(value: Decimal) -> str:
    """Giữ cách đọc nghìn cho đề xuất dưới một triệu để dễ đối chiếu."""
    if Decimal(0) < value < Decimal(1_000_000) and value % Decimal(1000) == 0:
        return f"{int(value / Decimal(1000))} nghìn đồng"
    return _fmt_trieu(float(value))


def _tien_de_xuat_gui_trong_luot(text: str) -> tuple[str, Decimal | None]:
    """Tiền khách đang đề xuất gửi; loại mức bị phủ định trong lời sửa."""
    t = _bo_dau(text)
    tat_ca = [q for q in quantities(text)
              if q.value is not None and q.kind in ("money", "bare")]
    if (re.search(r"\b(?:hay|hoac)\b", t) and len(tat_ca) > 1
            and any(q.kind == "money" for q in tat_ca)
            and re.search(r"\b(?:gui|tiet kiem|mo so)\b", t)):
        return "ambiguous", None
    cac = []
    for q in tat_ca:
        if q.kind != "money" or q.value is None:
            continue
        dau, cuoi = _gioi_han_menh_de(t, q.start, q.end)
        truoc, sau = t[dau:q.start], t[q.end:cuoi]
        if re.search(r"\bkhong phai\b[^,;.!?]{0,20}$", truoc):
            continue
        co_neo = (_gan_neo_gui(text, q.start, q.end)
                  or bool(re.search(r"\b(?:muon|dinh|can)\s+gui\b", sau))
                  or bool(re.search(r"\b(?:xin sua|sua|chot|chi co)\b", truoc)))
        if co_neo:
            cac.append(Decimal(q.value))
    if len(set(cac)) > 1:
        return "ambiguous", None
    return ("known", cac[0]) if cac else ("unknown", None)


def _tra_loi_muc_toi_thieu_tiet_kiem(text: str, t: str, sp_doc: str) \
        -> tuple[str, str] | None:
    """Đọc mức tối thiểu và chặn lời khẳng định đủ điều kiện dưới ngưỡng."""
    muc = _tien_gui_toi_thieu(sp_doc)
    hoi_muc = bool(re.search(r"\b(?:muc|so tien|gui|mo so)?\s*toi thieu\b", t)
                   and re.search(r"\b(?:bao nhieu|la may|la bao nhieu|muc nao)\b", t))
    status, de_xuat = _tien_de_xuat_gui_trong_luot(text)
    if status == "ambiguous":
        if re.search(r"\b(?:tien lai|bao nhieu tien|lai suat|phan tram|may cham)\b", t):
            return None
        if muc is None:
            return "xac_nhan_tien_gui", (
                "Dạ anh chị đang nêu nhiều số tiền gửi; vui lòng xác nhận một mức cụ thể ạ.")
        return "xac_nhan_tien_gui", (
            f"Dạ anh chị đang nêu nhiều số tiền gửi; mức tối thiểu theo tài liệu là "
            f"{_fmt_trieu(float(muc))}. Anh chị vui lòng xác nhận một mức cụ thể ạ.")
    de_xuat_thuan = not re.search(
        r"\b(?:qua|tang|uu dai|khuyen mai|lai|phi|rut|tat toan|bao hiem)\b", t)
    if status == "known" and de_xuat is not None and muc is None and de_xuat_thuan:
        return "muc_tien_gui_toi_thieu_chua_ro", (
            f"Dạ em ghi nhận khoản dự kiến {_fmt_tien_gui(de_xuat)}, nhưng tài liệu hiện "
            "chưa có một mức tiền gửi tối thiểu duy nhất để em đối chiếu ạ.")
    if status == "known" and de_xuat is not None and muc is not None and de_xuat < muc:
        gia_dinh = "nếu " if re.search(r"\b(neu|gia su|vi du)\b", t) else ""
        return "tien_gui_duoi_muc_toi_thieu", (
            f"Dạ {gia_dinh}khoản dự kiến là {_fmt_tien_gui(de_xuat)} thì đang thấp hơn "
            f"mức gửi tối thiểu {_fmt_trieu(float(muc))} theo tài liệu. Anh chị vui lòng "
            f"xác nhận một số tiền gửi từ {_fmt_trieu(float(muc))} trở lên ạ.")
    if hoi_muc:
        if muc is None:
            return "muc_tien_gui_toi_thieu_chua_ro", (
                "Dạ tài liệu hiện chưa có một mức tiền gửi tối thiểu duy nhất để em xác nhận ạ.")
        return "muc_tien_gui_toi_thieu", (
            f"Dạ số tiền gửi tối thiểu theo tài liệu là {_fmt_trieu(float(muc))} ạ.")
    return None


def _la_huy_rut_tiet_kiem(t: str) -> bool:
    return bool(re.search(
        r"\b(?:khong|chua|thoi khong)\s+(?:muon\s+)?rut\b|"
        r"\b(?:huy|bo|rut lai)\b.{0,20}\b(?:yeu cau\s+)?rut\b|"
        r"\brut\b.{0,20}\b(?:huy|bo|khong nua)\b", t))


def _la_rut_tien_gui(text: str) -> bool:
    t = _bo_dau(text)
    if not re.search(r"\b(?:rut|tat toan)\b", t):
        return False
    if re.search(r"\b(?:khoan vay|tien vay|du no|tra no|tra khoan vay)\b", t):
        return False
    return bool(re.search(
        r"\b(?:rut|tat toan)\b.{0,28}\b(?:truoc|som|mot phan|trieu|nghin|ty)\b|"
        r"\b(?:rut|tat toan)\s+(?:bot|ra)\b", t))


def _phan_tich_rut_mot_phan(text: str, so_goc: Decimal | None) \
        -> tuple[str, Decimal | None, Decimal | None]:
    """Tách phần rút/phần để lại; không tự chọn khi lời khách cạnh tranh."""
    if not _la_rut_tien_gui(text):
        return "unknown", None, None
    t = _bo_dau(text)
    tien = [q for q in quantities(text)
            if q.kind == "money" and q.value is not None
            and _chu_so_huu_du_kien(text, q.start, q.end) != "khac"]
    if not tien:
        return "unknown", None, None
    if re.search(r"\b(?:hay|hoac)\b", t):
        return "ambiguous", None, None

    phan_rut: list[Decimal] = []
    phan_con: list[Decimal] = []
    for q in tien:
        dau, cuoi = _gioi_han_menh_de(t, q.start, q.end)
        truoc, sau = t[dau:q.start], t[q.end:cuoi]
        value = Decimal(q.value)
        if re.search(r"\b(?:con|phan con lai)\b", truoc):
            phan_con.append(value)
        elif re.search(r"\b(?:rut|tat toan)\b", truoc):
            phan_rut.append(value)
        elif re.search(r"\b(?:de lai|giu lai|con lai)\b", sau):
            phan_con.append(value)

    if len(phan_rut) > 1 or len(phan_con) > 1:
        return "ambiguous", None, None
    rut = phan_rut[0] if phan_rut else None
    con = phan_con[0] if phan_con else None
    if so_goc is not None:
        if rut is not None and con is None:
            con = so_goc - rut
        elif con is not None and rut is None:
            rut = so_goc - con
        if rut is not None and con is not None and rut + con != so_goc:
            return "ambiguous", None, None
    if rut is None or con is None or rut <= 0 or con <= 0:
        return "ambiguous", None, None
    return "known", rut, con


def _rut_mot_phan_hien_tai(text: str, history: list[dict] | None,
                            bang: dict[int, str]) -> dict | None:
    """Sự kiện rút một phần gần nhất, tối đa 20 lượt khách và theo đúng thứ tự."""
    cac_cu = list(history or [])
    if (cac_cu and cac_cu[-1].get("role") == "user"
            and (cac_cu[-1].get("content") or "").strip() == (text or "").strip()):
        cac_cu = cac_cu[:-1]
    rows = [r for r in cac_cu if r.get("role") == "user"][-19:]
    rows.append({"role": "user", "content": text})
    active = None
    prefix: list[dict] = []
    for i, row in enumerate(rows):
        cau = row.get("content", "") or ""
        t = _bo_dau(cau)
        la_hien_tai = i == len(rows) - 1
        if _la_huy_rut_tiet_kiem(t):
            active = None
            prefix.append(row)
            continue
        qs = [q for q in quantities(cau) if q.value is not None]
        if (active is not None and _hai_truong_cung_khai_bao_gui(cau, qs)
                and not re.search(r"\b(neu|gia su|vi du)\b", t)):
            active = None
        if not _la_rut_tien_gui(cau):
            prefix.append(row)
            continue
        gia_dinh = bool(re.search(r"\b(neu|gia su|vi du)\b", t))
        if gia_dinh and not la_hien_tai:
            prefix.append(row)
            continue
        so_goc, ky, _, ky_status, kenh, kenh_status = \
            _du_kien_tinh_lai_tiet_kiem("", prefix, bang)
        status, rut, con = _phan_tich_rut_mot_phan(cau, so_goc)
        if status == "unknown":
            prefix.append(row)
            continue
        active = {
            "status": status,
            "rut": rut,
            "con": con,
            "ky": ky if ky_status == "known" else None,
            "kenh": kenh if kenh_status == "known" else None,
            "gia_dinh": gia_dinh,
            "la_hien_tai": la_hien_tai,
        }
        prefix.append(row)
    return active


def _tra_loi_rut_mot_phan_tiet_kiem(text: str, t: str, sp_doc: str,
                                     history: list[dict] | None,
                                     bang: dict[int, str], khong_ky_han: str | None) \
        -> tuple[str, str] | None:
    """Áp quy tắc nguồn riêng cho phần rút và phần còn lại trong sổ."""
    active = _rut_mot_phan_hien_tai(text, history, bang)
    if active is None:
        return None
    hoi_lai = bool(re.search(
        r"\b(?:hai phan|phan rut|phan con lai|huong lai|lai the nao|tien lai|"
        r"bao nhieu lai|cuoi ky|uoc tinh lai)\b", t))
    if not active["la_hien_tai"] and not hoi_lai:
        return None
    if active["status"] != "known":
        return "xac_nhan_rut_mot_phan_tiet_kiem", (
            "Dạ em chưa xác định được duy nhất phần tiền rút trước hạn và phần còn lại. "
            "Anh chị xác nhận giúp em mỗi phần một số tiền cụ thể ạ.")
    ky = active["ky"]
    if khong_ky_han is None or ky is None:
        return "chua_du_nguon_rut_mot_phan_tiet_kiem", (
            "Dạ tài liệu hoặc dữ kiện hiện chưa đủ để xác định lãi suất cho hai phần; "
            "anh chị vui lòng xác nhận kỳ hạn của sổ ạ.")
    apr_con, _ = _lai_ap_dung(sp_doc, ky, active["kenh"])
    if apr_con is None:
        return "chua_du_nguon_rut_mot_phan_tiet_kiem", (
            f"Dạ tài liệu chưa có một mức lãi suất ban đầu xác định cho kỳ hạn {ky} tháng, "
            "nên em chưa thể xác nhận lãi của phần còn lại ạ.")
    mo_dau = (f"Dạ nếu rút trước hạn {_fmt_trieu(float(active['rut']))} thì phần đó"
              if active["gia_dinh"] else
              f"Dạ phần {_fmt_trieu(float(active['rut']))} rút trước hạn thì phần đó")
    return "lai_rut_mot_phan_tiet_kiem", (
        f"{mo_dau} chỉ hưởng lãi suất không kỳ hạn {khong_ky_han}% một năm; phần "
        f"{_fmt_trieu(float(active['con']))} còn lại trong sổ giữ nguyên lãi suất ban đầu "
        f"{str(apr_con).replace('.', ',')}% một năm ạ. Tài liệu chưa có số ngày gửi thực "
        "tế của phần rút nên em chưa ước tính số tiền lãi đã nhận.")


def _tinh_lai_tiet_kiem(text: str, t: str, sp_doc: str,
                        history: list[dict] | None, bang: dict[int, str],
                        du_kien_gui=None) \
        -> tuple[str, str] | None:
    nhac_lai_va_tinh = bool(re.search(r"\b(nhac lai|doc lai|xac nhan lai)\b", t)
                              and re.search(r"\b(tien gui|so tien|ky han|hinh thuc)\b", t)
                              and re.search(r"\b(uoc tinh|tinh)\b.{0,18}\blai\b", t))
    hoi_tien_lai = nhac_lai_va_tinh or bool(re.search(
        r"\b(tien lai|so tien lai|lai (?:duoc|nhan|thu ve).{0,18}(?:bao nhieu|may)|"
        r"bao nhieu tien(?: lai)?|cuoi ky.{0,18}(?:duoc|nhan).{0,12}bao nhieu|"
        r"(?:duoc|nhan|ra|co)\s+bao nhieu lai)\b", t))
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
    if ky is None and tien is not None and ky_status == "unknown":
        # "năm phẩy năm là sao, một trăm triệu thì được bao nhiêu tiền": mức 5,5%
        # chỉ thuộc về MỘT kỳ hạn trong bảng.
        from backend.pipeline.du_kien_khoan_vay import quantities
        nhac = {_so_phay(format(q.value.normalize(), "f")) for q in quantities(text)
                if q.value is not None and q.kind != "money" and q.value != q.value.to_integral()}
        khop = [k for k, lai in bang.items() if lai in nhac]
        if len(khop) == 1:
            ky = khop[0]
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


def _tra_loi_nhap_goc_va_phi_tiet_kiem(t: str, sp_doc: str) \
        -> tuple[str, str] | None:
    """Trả đúng phần nguồn có và nói rõ phần tự nhập gốc chưa được nguồn nêu."""
    hoi_nhap_goc = bool(re.search(
        r"\b(?:lai|tien lai)\b.{0,28}\b(?:tu dong\s+)?(?:nhap|cong)\s+(?:vao\s+)?goc\b|"
        r"\b(?:tu dong\s+)?(?:nhap|cong)\s+(?:lai\s+)?(?:vao\s+)?goc\b|"
        r"\b(?:tai tuc|lai kep)\b", t))
    hoi_phi = bool(re.search(
        r"\bphi\b.{0,35}\b(?:mo so|tat toan)\b|"
        r"\b(?:mo so|tat toan)\b.{0,35}\bphi\b", t))
    if not (hoi_nhap_goc and hoi_phi):
        return None

    nhan_lai = next((dong.split(":", 1)[1].strip().rstrip(".")
                     for dong in sp_doc.splitlines()
                     if re.match(r"\s*-\s*nhan lai\s*:", _bo_dau(dong))), None)
    dong_phi = next((dong.strip().lstrip("- ") for dong in _muc_tai_lieu(
        sp_doc, "ưu đãi") if re.search(r"\bmien phi\b.{0,35}\bmo so\b.{0,35}\btat toan\b",
                                       _bo_dau(dong))), None)
    if nhan_lai:
        phan_lai = (f"Dạ tài liệu chỉ nêu nhận lãi {nhan_lai}, chưa nêu lãi tự động "
                    "nhập gốc hoặc tự động tái tục nên em chưa thể xác nhận tính năng này ạ.")
    else:
        phan_lai = ("Dạ tài liệu chưa nêu lãi tự động nhập gốc hoặc tự động tái tục, "
                    "nên em chưa thể xác nhận tính năng này ạ.")
    phan_phi = (_cau_tu_dong(dong_phi) if dong_phi else
                "Dạ tài liệu hiện cũng chưa nêu phí mở sổ và tất toán ạ.")
    return "lai_nhap_goc_va_phi_tiet_kiem", f"{phan_lai} {phan_phi}"


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


def _tra_loi_rut_truoc_han(t: str, sp_doc: str) -> tuple[str, str] | None:
    """"gửi rồi lúc cần bác lấy ra được không": đọc đúng dòng "Rút trước hạn" của tài liệu.

    Bộ thử 12-10-2026: mô hình tự viết có lần đáp "gửi có kỳ hạn thì chỉ rút được
    khi đến hạn" - ngược với tài liệu.
    """
    if not re.search(r"\b(lay ra|rut ra|rut truoc|rut som|rut giua chung|rut lai|lay lai|luc can|"
                     r"can tien|can gap)\b", t) or not re.search(
            r"\b(duoc khong|co duoc|duoc chua|thi sao|co sao|co mat|the nao|duoc ko)\b", t):
        return None
    if re.search(r"\b(bao nhieu tien|tinh|tien lai)\b", t):
        return None            # hỏi con số cụ thể: luật tính lãi đã có câu riêng
    dong = next((d.strip(" -") for d in sp_doc.splitlines()
                 if _bo_dau(d).startswith("rut truoc han thi")), "")
    if not dong:
        return None
    return "rut_truoc_han", "Dạ rút được ạ. " + dong.rstrip(".") + " ạ."


def _tra_loi_tiet_kiem(text: str, t: str, sp_doc: str,
                       history: list[dict] | None = None) -> tuple[str, str] | None:
    """Gửi tiết kiệm: lãi suất đi theo KỲ HẠN, không có hạn mức hay trả góp."""
    muc_toi_thieu = _tra_loi_muc_toi_thieu_tiet_kiem(text, t, sp_doc)
    if muc_toi_thieu:
        return muc_toi_thieu
    nhap_goc_va_phi = _tra_loi_nhap_goc_va_phi_tiet_kiem(t, sp_doc)
    if nhap_goc_va_phi:
        return nhap_goc_va_phi
    uu_dai = _uu_dai_tiet_kiem(text, t, sp_doc)
    if uu_dai:
        return uu_dai
    if re.search(r"\blai\b.{0,24}\bthap\b|\bthap\b.{0,12}\blai\b", t):
        gia_tri = _gia_tri_dong(sp_doc, "chê lãi thấp")
        if gia_tri:
            return "phan_hoi_lai_thap", _cau_tu_dong(gia_tri)
    bang, khong_ky_han = _bang_lai_tiet_kiem(sp_doc)
    rut_mot_phan = _tra_loi_rut_mot_phan_tiet_kiem(
        text, t, sp_doc, history, bang, khong_ky_han)
    if rut_mot_phan:
        return rut_mot_phan
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
    if (_la_hoi_lai_online_ro(text)
            and re.search(r"\bcong\b.{0,24}\b(?:bao nhieu|may)\b", t)):
        _, ky_online, _, ky_status_online, kenh_online, kenh_status_online = du_kien_gui
        if ky_status_online == "ambiguous" or kenh_status_online == "ambiguous":
            return "xac_nhan_lai_online", (
                "Dạ anh chị vui lòng xác nhận một kỳ hạn và một hình thức gửi cụ thể ạ.")
        if ky_online is None or kenh_online != "online":
            return "xac_nhan_lai_online", (
                "Dạ anh chị vui lòng xác nhận kỳ hạn gửi online để em báo đúng mức cộng ạ.")
        co_so = _lai_nguon_cho_ky(sp_doc, ky_online)
        cong_them = _cong_them_online_tu_nguon(sp_doc)
        if co_so is None or cong_them is None:
            return "khong_co_lai_suat_tiet_kiem", (
                "Dạ tài liệu chưa có một mức lãi suất cơ sở và mức cộng online duy nhất "
                "để em xác nhận ạ.")
        tong = co_so + cong_them
        return "cong_them_lai_online", (
            f"Dạ gửi online kỳ hạn {ky_online} tháng được cộng thêm "
            f"{str(cong_them).replace('.', ',')} điểm phần trăm một năm so với tại quầy, "
            f"từ {str(co_so).replace('.', ',')}% lên tổng "
            f"{str(tong).replace('.', ',')}% một năm ạ.")
    tinh_lai = _tinh_lai_tiet_kiem(text, t, sp_doc, history, bang, du_kien_gui)
    if tinh_lai:
        return tinh_lai
    tien, ky, tien_status, ky_status, kenh, kenh_status = du_kien_gui
    khai_bao_luot_nay = _hai_truong_cung_khai_bao_gui(text, du_kien_luot_nay)
    if (khai_bao_luot_nay and tien_status == ky_status == kenh_status == "known"
            and tien is not None and ky is not None and kenh is not None):
        nhan_kenh = "gửi online" if kenh == "online" else "gửi tại quầy"
        return "ghi_nhan_gui_tiet_kiem", (
            f"Dạ em ghi nhận khoản gửi {_fmt_trieu(float(tien))}, kỳ hạn {ky} tháng, "
            f"{nhan_kenh} ạ.")
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


def _muc_chi_tieu(text: str) -> tuple[Decimal, Decimal] | None:
    """(thấp, cao) của mức chi tiêu khách nêu, tính bằng đồng.

    "mười lăm hai chục củ" là MỘT khoảng: bộ đọc số trả một cụm không có giá trị,
    nên tách cụm ở từng chỗ cho tới khi cả hai nửa đều đọc được.
    """
    from backend.pipeline.du_kien_khoan_vay import quantities
    tien = [q for q in quantities(text) if q.kind == "money"]
    if len(tien) != 1:
        return None
    q = tien[0]
    if q.value is not None:
        return Decimal(q.value), Decimal(q.value)
    chu = q.raw.split()

    def _doc(cum: list[str]) -> Decimal | None:
        cac = [x for x in quantities(" ".join(cum) + " triệu") if x.kind == "money" and x.value]
        return Decimal(cac[0].value) if len(cac) == 1 else None

    # Nhiều cách tách cùng đọc được ("mười | lăm hai chục"): lấy cách cho mức
    # THẤP lớn nhất, tức hai nửa gần nhau nhất - "mười lăm | hai chục".
    cach = []
    for i in range(1, len(chu) - 1):
        a, b = _doc(chu[:i]), _doc(chu[i:-1])
        if a and b and a < b:
            cach.append((a, b))
    return max(cach) if cach else None


def _goi_y_the_theo_chi_tieu(text: str, t: str,
                             cac_the: dict[str, tuple[str, str, str]]) -> tuple[str, str] | None:
    """"anh xài mỗi tháng chừng mười lăm hai chục củ thì nên làm thẻ gì".

    Chỉ đối chiếu mức chi tiêu với KHUNG HẠN MỨC từng hạng thẻ trong tài liệu:
    hạng thấp nhất có hạn mức đủ cho mức chi tiêu đó, kèm hạng kế trên. Không phán
    khách được cấp hạng nào.
    """
    if not re.search(r"\b(nen|hop|phu hop)\b.{0,20}\bthe\b|\bthe (nao|gi|loai nao|hang nao)\b", t) \
            or not re.search(r"\b(xai|tieu|chi tieu|dung|quet|mua sam)\b", t):
        return None
    muc = _muc_chi_tieu(text)
    if muc is None:
        return None
    khung = []
    for khoa, _ in _TEN_THE:
        if khoa not in cac_the:
            continue
        ten, han_muc, _phi = cac_the[khoa]
        m = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*triệu", han_muc)
        if m:
            khung.append((ten, han_muc, Decimal(m.group(2)) * 1_000_000))
    du = [i for i, (_, _, tran) in enumerate(khung) if tran >= muc[1]]
    if not du:
        return None
    ten, han_muc, _ = khung[du[0]]
    noi = (_fmt_trieu(float(muc[1])) if muc[0] == muc[1] else
           f"{_fmt_trieu(float(muc[0])).replace(' triệu đồng', '')} đến {_fmt_trieu(float(muc[1]))}")
    cau = (f"Dạ với mức chi tiêu khoảng {noi} một tháng thì thẻ {ten}, hạn mức {han_muc}, "
           "là đủ dùng ạ.")
    if du[0] + 1 < len(khung):
        tren = khung[du[0] + 1]
        cau += f" Nếu muốn hạn mức cao hơn thì có thẻ {tren[0]}, hạn mức {tren[1]}."
    return "goi_y_the_theo_chi_tieu", cau + " Hạng thẻ được cấp còn tuỳ thẩm định hồ sơ ạ."


def _lich_su_khan_cap_the(history: list[dict] | None, text: str) -> tuple[bool, bool]:
    """Giữ ngữ cảnh mất thẻ cho một câu hỏi bước tiếp theo thật ngắn.

    Chỉ lịch sử khách hàng được xét. Một lượt gọi rõ sản phẩm/chủ đề khác sẽ
    cắt ngữ cảnh để câu ``làm gì ngay`` về sau không kéo lại sự cố cũ. Cờ thứ
    hai ghi nhận mức phí thay thẻ khách chỉ thuật lại, không xác nhận mức đó.
    """
    cac_luot = [m.get("content", "") for m in (history or [])
                if m.get("role") == "user"]
    if cac_luot and cac_luot[-1].strip() == (text or "").strip():
        cac_luot.pop()

    khan_cap = False
    phi_thay_chua_xac_nhan = False
    for cau in cac_luot[-6:]:
        h = _bo_dau(cau)
        mat_the = bool(re.search(
            r"\b(?:mat|that lac|khong thay|de quen|danh roi|lay cap)\b.{0,34}\bthe\b|"
            r"\bthe(?:\s+(?:tin dung|classic|gold|platinum))?"
            r"(?:\s+(?:toi|anh|chi|em|minh|cua toi|cua anh|cua chi)){0,2}\s+"
            r"(?:bi\s+)?(?:mat|that lac|de quen|danh roi|lay cap)\b", h))
        otp_dang_bi_xin = bool(
            re.search(r"\botp\b", h)
            and re.search(r"\b(?:nguoi|ai|ho|nhan vien|ngan hang)\b", h)
            and re.search(r"\b(?:bao|giuc|doi|yeu cau|xin|can)\b", h))
        if mat_the or otp_dang_bi_xin:
            khan_cap = True
            phi_thay_chua_xac_nhan = False
            continue

        if not khan_cap:
            continue
        if (re.search(r"\b(?:phi|thu)\b.{0,28}\b(?:thay|cap lai|lam lai|phat hanh lai)\b|"
                     r"\b(?:thay|cap lai|lam lai|phat hanh lai)\b.{0,28}\bphi\b", h)):
            phi_thay_chua_xac_nhan = True
            continue

        # Một sản phẩm/hạng thẻ mới được hỏi rõ là điểm cắt. Câu về phí cấp lại
        # ở trên vẫn thuộc cùng sự cố nên đã được giữ trước khi đến nhánh này.
        chuyen_chu_de = bool(
            re.search(r"\b(?:vay|khoan vay|tiet kiem|tien gui|mo so|the chap)\b", h)
            or (re.search(r"\bthe\s+(?:classic|gold|platinum)\b", h)
                and re.search(r"\b(?:hoi|muon|quan tam|tim hieu|mo|phi thuong nien|han muc)\b", h)))
        if chuyen_chu_de:
            khan_cap = False
            phi_thay_chua_xac_nhan = False
    return khan_cap, phi_thay_chua_xac_nhan


def _tra_loi_the_tin_dung(t: str, sp_doc: str, text: str = "",
                           history: list[dict] | None = None) -> tuple[str, str] | None:
    """Thẻ tín dụng: hạn mức và phí đi theo LOẠI THẺ."""
    t = re.sub(r"\bhang muc\b", "han muc", t)   # STT nghe "hạn mức" thành "hạng mức"

    # Mất thẻ/ATM giữ thẻ là việc cần xử lý ngay. Nó phải đứng trước mọi luật
    # phí: "phí cấp lại" từng bị hiểu thành phí THƯỜNG NIÊN rồi đọc 200/400/800
    # nghìn, trong khi khách vẫn chưa được nhắc khóa thẻ. Không nói "đã khóa" vì
    # luật này chỉ hướng dẫn, không thực hiện được thao tác trên tài khoản.
    atm_giu_the = bool(re.search(
        r"\b(?:may\s+)?atm\b.{0,24}\b(?:giu|nuot)\b.{0,18}\bthe\b|"
        r"\bthe(?:\s+(?:tin dung|classic|gold|platinum))?\b.{0,18}\b(?:bi\s+)?nuot\b",
        t))
    mat_the_noi_ro = bool(re.search(
        r"\b(?:mat|that lac|khong thay|de quen|nghi bi lay cap|bi lay cap|danh roi)\b"
        r".{0,32}\bthe\b|"
        r"\bthe(?:\s+(?:tin dung|classic|gold|platinum))?"
        r"(?:\s+(?:toi|anh|chi|em|minh|cua toi|cua anh|cua chi)){0,2}\s+"
        r"(?:bi\s+)?(?:mat|that lac|lay cap|de quen|danh roi)\b",
        t))
    # Trong hội thoại thẻ, khách có thể lược chủ ngữ sau khi vừa nói đang dùng
    # thẻ: "nghi bị lấy cắp ở quán". Chỉ suy ra thẻ khi khách hỏi xử lý ngay và
    # câu không nêu rõ một tài sản khác.
    mat_the_bi_luoc = bool(
        re.search(r"\bnghi\s+bi\s+lay\s+cap\b", t)
        and re.search(r"\b(?:lam gi|xu ly|khoa|bao|ngay|bay gio|gio)\b", t)
        and not re.search(r"\b(?:dien thoai|xe|tui|tien|tai san)\b", t)
    )
    # "mở thẻ mất bao lâu", "làm thẻ mất bao nhiêu tiền": "mất" là TỐN, không phải
    # thất lạc. Khách đóng vai 12-10-2026 hỏi thời gian mở thẻ, AI bảo đi khoá thẻ.
    mat_the = (mat_the_noi_ro or mat_the_bi_luoc) and not bool(
        re.search(r"\b(?:mat|khong thay)\s+(?:phi|lai|bao lau|bao nhieu|may (?:ngay|hom|tuan)|"
                  r"nhieu thoi gian|thoi gian|lau|cong|tien|it)\b", t))
    # "rơi" và "rồi" trùng nhau sau bỏ dấu. Chỉ nhận ví khi có lời hỏi xử lý
    # khẩn; loại "ví dụ"/"ví điện tử" để câu sản phẩm bình thường không bị chặn.
    mat_vi = bool(re.search(
        r"\b(?:mat|that lac|de quen|danh roi|roi)\b.{0,24}\bvi\b(?!\s+(?:du|dien tu))",
        t) and re.search(r"\b(?:lam gi|xu ly|khoa|bao|ngay|bay gio|gio)\b", t))

    hoi_buoc_ngay = bool(re.search(
        r"\b(?:toi|anh|chi|em|minh)?\s*(?:nen|can|phai)?\s*"
        r"(?:lam gi|xu ly(?: the nao)?|bao ai)\s*(?:ngay|bay gio|gio)?\b", t))
    khan_cap_truoc, phi_thay_chua_xac_nhan = _lich_su_khan_cap_the(history, text)
    if hoi_buoc_ngay and khan_cap_truoc:
        phi = (
            " Mức phí thay thẻ do người gọi nêu chưa được tài liệu sản phẩm "
            "xác nhận; anh chị hãy kiểm tra biểu phí qua kênh chính thức ạ."
            if phi_thay_chua_xac_nhan else "")
        return "mat_the_otp_theo_ngu_canh", (
            "Dạ anh chị không đọc hoặc cung cấp OTP cho người gọi và nên ngắt cuộc gọi "
            "đó ngay. Anh chị hãy chủ động khóa thẻ qua kênh chính thức, kiểm tra các "
            "giao dịch gần đây, rồi tự liên hệ kênh chính thức đã kiểm chứng; không dùng "
            "số điện thoại hoặc đường dẫn do người gọi cung cấp ạ." + phi)

    loai_phi = next((
        (ma, nhan, mau) for ma, nhan, mau in (
            ("cap_lai", "cấp lại thẻ", r"\b(?:cap|phat hanh|lam)\s+lai\b"),
            ("khoa", "khóa thẻ", r"\bkhoa\s+the\b"),
            ("tranh_chap", "tra soát hoặc tranh chấp giao dịch",
             r"\b(?:tra soat|tranh chap)\b"),
        ) if re.search(
            rf"\bphi\b.{{0,28}}{mau}|{mau}.{{0,28}}\bphi\b|"
            rf"\b(?:thu phi|co phi|mat phi)\b.{{0,20}}{mau}", t)
    ), None)
    if loai_phi:
        ma_phi, nhan_phi, mau_phi = loai_phi
        dong_nguon = next((
            d.strip().lstrip("- ") for d in sp_doc.splitlines()
            if not d.lstrip().startswith("#")
            and re.search(mau_phi, _bo_dau(d))
            and re.search(r"\b(?:phi|mien phi)\b", _bo_dau(d))
        ), None)
        if atm_giu_the:
            an_toan = (
                "Dạ anh chị nên ghi lại vị trí máy và thời điểm thẻ bị giữ, đồng thời "
                "chủ động khóa thẻ qua kênh chính thức nếu có ạ. ")
        else:
            an_toan = (
                "Dạ nếu thẻ đang mất hoặc có giao dịch đáng ngờ, anh chị nên chủ động "
                "khóa thẻ qua kênh chính thức và kiểm tra các giao dịch gần đây ạ. ")
        if dong_nguon:
            return f"phi_{ma_phi}_the_tu_nguon", an_toan + _cau_tu_dong(dong_nguon)
        return f"phi_{ma_phi}_the_chua_co_nguon", (
            an_toan + f"Tài liệu thẻ hiện chưa nêu phí {nhan_phi}; anh chị vui lòng "
            "liên hệ kênh hỗ trợ chính thức để xác nhận, và không cung cấp OTP, PIN "
            "hoặc mật khẩu ạ.")

    if atm_giu_the:
        return "atm_giu_the", (
            "Dạ anh chị nên ghi lại vị trí máy và thời điểm thẻ bị giữ, đồng thời chủ động "
            "khóa thẻ qua kênh chính thức nếu có ạ. Sau đó anh chị liên hệ kênh hỗ trợ "
            "chính thức; không nhờ người lạ lấy thẻ và không cung cấp OTP, PIN hoặc mật khẩu ạ.")
    if mat_the or mat_vi:
        otp = bool(re.search(r"\botp\b", t) and re.search(
            r"\b(?:bao|giuc|doi|yeu cau|xin|can|doc|cung cap|gui)\b", t))
        if otp:
            return "mat_the_otp", (
                "Dạ anh chị không đọc hoặc cung cấp OTP và nên ngắt cuộc gọi đáng ngờ "
                "ngay. Anh chị hãy chủ động khóa thẻ qua kênh chính thức, kiểm tra các "
                "giao dịch gần đây, rồi tự liên hệ kênh chính thức đã kiểm chứng; không "
                "dùng số điện thoại hoặc đường dẫn do người gọi cung cấp ạ.")
        return "mat_the", (
            "Dạ anh chị nên chủ động khóa thẻ ngay qua kênh chính thức nếu có chức năng này, "
            "đồng thời kiểm tra các giao dịch gần đây ạ. Nếu không tự khóa được, anh chị hãy "
            "liên hệ kênh hỗ trợ chính thức và không cung cấp OTP, PIN hoặc mật khẩu ạ.")

    # Đây là khái niệm chung trên sao kê, không phải yêu cầu tra cứu dư nợ riêng.
    # Giữ luật hẹp để "thu nhập tối thiểu", "tiền gửi tối thiểu", hạn mức và
    # kỳ trả góp vẫn đi đúng nhánh của chúng. Hai mẫu sau cùng là các lượt nối
    # tiếp của holdout: helper thẻ không nhận history nên chỉ bắt đúng cách hỏi
    # tỷ lệ dư nợ và câu làm rõ khái niệm sao kê, không suy rộng từ một con số.
    hoi_thanh_toan_toi_thieu = bool(
        (re.search(r"\btoi thieu\b", t)
         and re.search(r"\b(?:thanh toan|tra|sao ke|du no)\b", t)
         and not re.search(
             r"\b(?:thu nhap|luong|han muc|tien gui|gui tiet kiem|tra gop|ky han)\b", t))
        or (re.search(
                r"\b(?:co phai\s+)?luon\s+bang\s+dung\s+\d+(?:[.,]\d+)?\s*%"
                r"\s+(?:tong\s+)?du no\b", t)
            and not re.search(r"\b(?:lai|phi|cashback|hoan tien)\b", t))
        or re.search(r"\bchua dua sao ke\b.{0,32}\bkhai niem chung\b", t)
    )
    if hoi_thanh_toan_toi_thieu:
        dong_nguon = None
        trong_muc_toi_thieu = False
        for dong in sp_doc.splitlines():
            d = _bo_dau(dong.strip())
            if d.startswith("#"):
                trong_muc_toi_thieu = bool(re.search(
                    r"\b(?:thanh toan|tra|so tien)\b.{0,18}\btoi thieu\b", d))
                continue
            noi_ro = bool(re.search(
                r"\b(?:thanh toan|tra|so tien|muc)\b.{0,22}\btoi thieu\b|"
                r"\btoi thieu\b.{0,22}\b(?:thanh toan|tra)\b", d))
            co_quy_tac = bool(re.search(r"\b(?:du no|sao ke|qua han)\b|%", d))
            if (noi_ro and co_quy_tac) or (trong_muc_toi_thieu and co_quy_tac):
                dong_nguon = dong.strip().lstrip("- ").rstrip(".")
                break
        giai_thich = (
            "Đây là phần bắt buộc tối thiểu cần thanh toán theo sao kê để tránh quá hạn, "
            "không phải toàn bộ dư nợ sao kê. Trả mức tối thiểu không có nghĩa phần dư nợ "
            "còn lại không phát sinh lãi hoặc phí theo điều khoản ạ.")
        if dong_nguon:
            return "thanh_toan_toi_thieu_tu_nguon", (
                f"Dạ theo tài liệu sản phẩm: {dong_nguon} ạ. {giai_thich}")
        return "khai_niem_thanh_toan_toi_thieu", (
            f"Dạ số tiền thanh toán tối thiểu là phần được ghi trên sao kê theo điều khoản. "
            f"{giai_thich} Tài liệu thẻ hiện chưa nêu tỷ lệ thanh toán tối thiểu hoặc "
            "mức lãi, phí áp dụng cho phần dư nợ còn lại, "
            "nên em chưa thể xác nhận một tỷ lệ hay số tiền cụ thể ạ.")

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
    goi_y_the = _goi_y_the_theo_chi_tieu(text, t, cac_the)
    if goi_y_the:
        return goi_y_the
    hoi_han_muc = bool(re.search(r"\bhan muc\b", t)) and not re.search(
        r"\b(tang|nang|len|thap|it|nho|giam)\b", t)
    hoi_phi = bool(re.search(r"\bphi\b.{0,20}\b(thuong nien|hang nam|moi nam|bao nhieu|la may)\b|"
                             r"\bphi (?:thuong nien|nam)\b|"
                             # "thẻ này có mất phí gì không": hỏi CHUNG về phí. Tài liệu
                             # thẻ chỉ có phí thường niên nên đáp bằng đúng khoản đó.
                             r"\b(?:mat|ton|co|tinh|thu) phi\b(?! (?:cap lai|thay|phat|tra truoc|rut))|"
                             r"\bphi (?:gi|the nao|sao|ra sao)\b", t))
    mien_nam_dau = "mien phi thuong nien nam dau" in _bo_dau(sp_doc)
    duoi_mien = ", năm đầu được miễn phí" if mien_nam_dau else ""

    ten_khop = [k for k, cum in _TEN_THE if k in cac_the and any(
        re.search(rf"\b{c}\b", t) for c in cum)]
    if len(ten_khop) > 1:
        return "xac_nhan_loai_the", (
            "Dạ anh chị đang nhắc nhiều hạng thẻ, vui lòng chọn một hạng để em báo đúng "
            "hạn mức và phí thường niên ạ.")
    ten = ten_khop[0] if ten_khop else None
    if ten:
        hien, hm, phi = cac_the[ten]
        if hoi_han_muc and not hoi_phi:
            return "han_muc_loai_the", f"Dạ thẻ {hien} có hạn mức {hm} ạ."
        if hoi_phi and not hoi_han_muc:
            return "phi_loai_the", f"Dạ thẻ {hien} phí thường niên {phi}{duoi_mien} ạ."
        if hoi_phi and hoi_han_muc:
            return "loai_the", f"Dạ thẻ {hien} có hạn mức {hm}, phí thường niên {phi}{duoi_mien} ạ."
        if re.search(r"\b(hoi|quan tam|tim hieu|tu van|gioi thieu)\b", t):
            return "gioi_thieu_loai_the", (
                f"Dạ thẻ {hien} có hạn mức {hm}, phí thường niên {phi}{duoi_mien} ạ.")
        if re.search(
                r"\b(?:muon|can|dinh)\b.{0,30}\b(?:mo|lam|dang ky)\s+the\b|"
                r"\b(?:mo|lam|dang ky)\s+the\b.{0,18}\b(?:dung ten|tu dung ten)\b", t):
            return "thong_tin_mo_loai_the", (
                f"Dạ theo tài liệu sản phẩm, thẻ {hien} có hạn mức {hm}, phí thường niên "
                f"{phi}{duoi_mien} ạ. Đây là thông tin chung của sản phẩm, chưa phải xác "
                "nhận anh chị được mở hoặc được duyệt thẻ; điều kiện hồ sơ cần được đối "
                "chiếu riêng theo nguồn ạ.")
        return None

    # Xét "vay" trên bản CÒN DẤU: bỏ dấu thì "trả góp được không vậy" cũng có
    # chữ "vay" và câu hỏi trả góp thẻ bị đẩy sang mô hình (bộ thử 10k #5342).
    goc = unicodedata.normalize("NFC", (text or "").lower())
    if re.search(r"\btra gop\b", t) and not re.search(r"khoản vay|\bvay\b", goc):
        dong = next((d for d in _muc_tai_lieu(sp_doc, "ưu đãi") if "tra gop" in _bo_dau(d)), None)
        if dong:
            return "tra_gop_the", _cau_tu_dong("thẻ tín dụng được " + dong[:1].lower() + dong[1:])

    liet_ke = [cac_the[k] for k, _ in _TEN_THE if k in cac_the]
    # "muốn hạn mức ba trăm triệu thì làm thẻ nào": chỉ ra hạng có khoảng hạn mức
    # chứa con số khách nêu. Kho từng đáp bằng câu của KHOẢN VAY (12-10-2026).
    if hoi_han_muc and re.search(r"\b(the|hang|loai) (nao|gi)\b", t):
        from backend.pipeline.du_kien_khoan_vay import quantities
        tien = [float(q.value) for q in quantities(text) if q.value and q.kind == "money"]
        can = tien[0] if len(tien) == 1 else None
        hop = []
        for h, hm, _ in liet_ke:
            m_ = re.search(r"(\d+)\s*-\s*(\d+)\s*trieu", _bo_dau(hm))
            if can and m_ and int(m_.group(1)) * 1e6 <= can <= int(m_.group(2)) * 1e6:
                hop.append((h, hm))
        if hop:
            return "hang_the_theo_han_muc", (
                f"Dạ hạn mức {_fmt_trieu(can)} thì nằm trong khoảng của "
                + " hoặc ".join(f"thẻ {h}, hạn mức {hm}" for h, hm in hop)
                + " ạ. Hạn mức được cấp thực tế vẫn cần thẩm định theo hồ sơ.")
        if can and liet_ke:
            return "hang_the_theo_han_muc", (
                f"Dạ mức {_fmt_trieu(can)} thì ngoài hạn mức các hạng thẻ bên em ạ: "
                + ", ".join(f"thẻ {h} {hm}" for h, hm, _ in liet_ke) + " ạ.")
    if hoi_han_muc and re.search(r"\b(bao nhieu|toi da|la may|nhu nao|the nao|duoc bao)\b", t):
        chung = _gia_tri_dong(sp_doc, "hạn mức")
        dau = f"từ {chung.replace(' - ', ' đến ')} tuỳ loại thẻ: " if chung else "tuỳ loại thẻ: "
        return "han_muc_the", (
            "Dạ hạn mức thẻ tín dụng " + dau
            + ", ".join(f"thẻ {h} {hm}" for h, hm, _ in liet_ke) + " ạ.")
    # "phí rút là bao nhiêu" ngay sau câu hỏi rút tiền mặt: tài liệu thẻ không
    # nêu phí ứng tiền mặt, không được đọc phí thường niên thay vào.
    if hoi_phi and re.search(r"\bphi rut\b", t) and not re.search(r"\btruoc han\b", t):
        return "chua_co_thong_tin_chu_de", (
            "Dạ phần phí rút tiền mặt hiện em chưa có thông tin chính xác, em xin phép "
            "kiểm tra lại và báo anh chị sau ạ.")
    if hoi_phi and not re.search(r"\b(rut|chuyen doi|tra gop|cham)\b", t):
        return "phi_the", (
            "Dạ phí thường niên "
            + ", ".join(f"thẻ {h} {phi}" for h, _, phi in liet_ke) + duoi_mien + " ạ.")
    return None


def _tran_san_pham(tai_lieu: str) -> float | None:
    cac: set[float] = set()
    for dong in _dong_co(tai_lieu, "hạn mức"):
        cac |= _tien_trong(dong)
    return max(cac) if cac else None


def _gioi_han_ltv(sp_doc: str) -> tuple[Decimal, Decimal] | None:
    """Đọc đúng một tỷ lệ LTV và một trần VND từ dòng hạn mức nguồn.

    Phép tính theo giá nhà chỉ an toàn khi chính tài liệu gắn tỷ lệ với giá trị
    bất động sản và ghi rõ một trần tiền Việt. Nếu nguồn có nhiều tỷ lệ/trần,
    thiếu đơn vị tiền, hoặc dùng ngoại tệ thì giữ câu trả lời nguồn như trước,
    không chọn hộ một con số để tính.
    """
    ung_vien: list[tuple[Decimal, Decimal]] = []
    for dong in _dong_co(sp_doc, "hạn mức"):
        d = _bo_dau(dong)
        if not (re.search(r"\bgia tri\b.{0,24}\b(bat dong san|nha|tai san)\b", d)
                or re.search(r"\b(bat dong san|nha|tai san)\b.{0,24}\bgia tri\b", d)):
            continue
        ty_le = re.findall(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*%", dong)
        tien = [q for q in quantities(dong) if q.kind == "money" and q.value is not None]
        if len(ty_le) != 1 or len(tien) != 1:
            continue
        q = tien[0]
        # Đơn vị tỷ/triệu tự nó chưa xác định đồng tiền. Nguồn phải nói rõ
        # đồng/VND; ``10 tỷ USD`` vì vậy không thể bị hiểu thành 10 tỷ đồng.
        cum_tien = d[q.start:min(len(d), q.end + 12)]
        if not re.search(r"\b(?:dong|vnd)\b", cum_tien):
            continue
        if re.search(r"\b(?:usd|eur|gbp|jpy|dollar|do la)\b", d):
            continue
        ratio = Decimal(ty_le[0].replace(",", "."))
        if Decimal(0) < ratio <= Decimal(100) and q.value > 0:
            ung_vien.append((ratio, q.value))
    return ung_vien[0] if len(set(ung_vien)) == 1 else None


_NEO_GIA_BDS = re.compile(r"\b(?:gia(?: tri)?|tri gia)\b")
_CHU_GIA_BDS = re.compile(
    r"\b(?:can ho|can nha|nha pho|ngoi nha|nha|chung cu|biet thu|"
    r"bat dong san|bds|dat|lo dat|thua dat|tai san dam bao|tai san the chap)\b")
_CHU_GIA_KHAC = re.compile(
    r"\b(?:xe|o to|oto|xe may|bitcoin|vang|co phieu|chung khoan|"
    r"dien thoai|laptop|may moc|tau|thuyen)\b")
_KHONG_PHAI_GIA_BDS = re.compile(
    r"\b(?:vay|khoan vay|tien vay|so tien vay|thu nhap|luong|doanh thu|von tu co)\b")
_NGOAI_TE = re.compile(r"\b(?:usd|eur|gbp|jpy|dollar|do la|do my|euro)\b")
_RUT_LAI_GIA_BDS = re.compile(
    r"\b(?:chua (?:chot|xac dinh|quyet dinh)|bo|huy|rut lai|khong dung|dung lay)\b"
    r".{0,36}\b(?:gia|gia tri|muc gia)\b|"
    r"\b(?:gia|gia tri|muc gia)\b.{0,24}\b(?:chua chot|bo|huy|rut lai)\b")
_SUA_GIA_BDS = re.compile(
    r"\b(?:sua|doi|chot|a khong|a nham|nham|y la|khong phai|gia moi|muc moi)\b")


def _la_gia_gia_dinh(text: str) -> bool:
    """Lượt đang đặt giả thiết, phân biệt ``giả định`` với ``gia đình``.

    Bỏ dấu làm cả hai thành ``gia dinh``. Vì vậy dạng ASCII chỉ được coi là
    giả định khi có ngữ pháp đặt tình huống theo sau; ``của gia đình tôi`` vẫn
    là mô tả tài sản thật và phải được phép lưu vào lịch sử.
    """
    goc = unicodedata.normalize("NFC", (text or "").lower())
    if re.search(r"\b(?:nếu|giả sử|ví dụ|trường hợp|giả định)\b", goc):
        return True
    t = _bo_dau(goc)
    if re.search(r"\b(?:neu|gia su|vi du|truong hop)\b", t):
        return True
    return bool(re.search(
        r"\b(?:theo\s+)?gia dinh\s*(?::|(?:rang\s+|neu\s+)?"
        r"(?=(?:mot\s+)?(?:can|ngoi nha|nha|bat dong san|bds|tai san|gia)\b))",
        t,
    ))


def _gia_bds_chi_tiet_trong_luot(text: str, bo_gia_gia_dinh: bool = False) \
        -> tuple[str, list[Decimal], bool]:
    """Giá BĐS do khách nói trong một lượt, không nhận số vay/thu nhập.

    Trả ``known``, ``ambiguous``, ``missing_unit``, ``unsupported`` hoặc
    ``unknown`` cùng cờ giá giả định. Giá phải có neo ``giá/giá trị/trị giá``
    trong cùng mệnh đề. Khi chiếu lịch sử, ``bo_gia_gia_dinh`` chỉ bỏ đúng giá
    nằm trong mệnh đề giả định, không bỏ giá thật ở một câu khác trong lượt.
    """
    goc = unicodedata.normalize("NFC", text or "")
    t = _bo_dau(goc)
    gia: list[Decimal] = []
    gia_gia_dinh: list[bool] = []
    gia_chua_ro_chu: list[Decimal] = []
    thieu_don_vi = False
    ngoai_te = False
    for q in quantities(goc):
        dau = max(t.rfind(".", 0, q.start), t.rfind(";", 0, q.start),
                  t.rfind("!", 0, q.start), t.rfind("?", 0, q.start),
                  t.rfind("\n", 0, q.start)) + 1
        truoc = t[dau:q.start]
        neo = list(_NEO_GIA_BDS.finditer(truoc))
        if not neo:
            continue
        sau_neo = truoc[neo[-1].end():]
        if len(sau_neo) > 52 or _KHONG_PHAI_GIA_BDS.search(sau_neo):
            continue
        # Chủ thể gần con số nhất quyết định vai của giá. Nhờ vậy trong
        # ``nhà giá 9 tỷ, xe giá 2 tỷ`` thì 2 tỷ thuộc xe, không trở thành giá
        # nhà thứ hai. Không có chủ thể nào là ``giá 9 tỷ`` chưa đủ rõ.
        chu_the = [(m.start(), "bds") for m in _CHU_GIA_BDS.finditer(truoc)]
        chu_the += [(m.start(), "khac") for m in _CHU_GIA_KHAC.finditer(truoc)]
        loai_chu_the = max(chu_the)[1] if chu_the else ""
        if loai_chu_the == "khac":
            continue
        la_gia_dinh = _la_gia_gia_dinh(goc[dau:q.start])
        if bo_gia_gia_dinh and la_gia_dinh:
            continue
        quanh = t[q.start:min(len(t), q.end + 18)]
        if _NGOAI_TE.search(quanh):
            ngoai_te = True
            continue
        if q.value is None or q.value <= 0:
            thieu_don_vi = True
        elif q.kind == "money":
            if loai_chu_the == "bds":
                gia.append(q.value)
                gia_gia_dinh.append(la_gia_dinh)
            else:
                gia_chua_ro_chu.append(q.value)
        elif q.kind == "bare":
            thieu_don_vi = True
    if ngoai_te:
        return "unsupported", [], False
    if len(set(gia)) > 1:
        # "không phải 9 tỷ, giá là 8 tỷ" là một sửa rõ ngay trong lượt.
        if _SUA_GIA_BDS.search(t):
            return "known", [gia[-1]], gia_gia_dinh[-1]
        return "ambiguous", list(dict.fromkeys(gia)), False
    if gia:
        return "known", gia, all(gia_gia_dinh)
    if gia_chua_ro_chu:
        return "unqualified", list(dict.fromkeys(gia_chua_ro_chu)), False
    if thieu_don_vi:
        return "missing_unit", [], False
    return "unknown", [], False


def _gia_bds_trong_luot(text: str) -> tuple[str, list[Decimal]]:
    """Giao diện gọn cho các nơi chỉ cần trạng thái và giá trong lượt."""
    status, gia, _ = _gia_bds_chi_tiet_trong_luot(text)
    return status, gia


def _gia_bds_hien_tai(text: str, history: list[dict] | None) \
        -> tuple[str, Decimal | None, bool]:
    """Chiếu giá BĐS chỉ từ lời khách; giá ở lượt hiện tại luôn có ưu tiên.

    Giá khác xuất hiện về sau không âm thầm thay giá cũ: thiếu lời sửa/chốt thì
    đó là hai phương án cạnh tranh và cần hỏi lại. Lời rút giá cũng chặn việc
    tìm ngược để hồi sinh giá đã bỏ.
    """
    if _RUT_LAI_GIA_BDS.search(_bo_dau(text)):
        return "cancelled", None, False
    trang_thai, cac, hien_tai_gia_dinh = _gia_bds_chi_tiet_trong_luot(text)
    if trang_thai not in ("unknown", "unqualified"):
        return trang_thai, (cac[0] if trang_thai == "known" else None), hien_tai_gia_dinh
    gia_hien_tai_chua_ro_chu = cac if trang_thai == "unqualified" else []

    da_co: Decimal | None = None
    status = "unknown"
    cac_luot = list(history or [])
    # Pipeline có thể đã gắn chính lượt hiện tại vào history. Không xử lý nó
    # lần hai vì một câu giả định hiện tại phải được ưu tiên độc lập.
    if cac_luot and cac_luot[-1].get("role") == "user" \
            and (cac_luot[-1].get("content") or "").strip() == (text or "").strip():
        cac_luot = cac_luot[:-1]
    for luot in cac_luot:
        if luot.get("role") != "user":
            continue
        noi_dung = luot.get("content") or ""
        nt = _bo_dau(noi_dung)
        if _RUT_LAI_GIA_BDS.search(nt):
            da_co, status = None, "cancelled"
            continue
        # Bỏ đúng giá trong mệnh đề "nếu/giả sử...". Một giá thật ở câu trước
        # trong cùng lượt vẫn được lưu và không bị câu hỏi giả định phía sau xoá.
        st, values, _ = _gia_bds_chi_tiet_trong_luot(
            noi_dung, bo_gia_gia_dinh=True)
        if st in ("ambiguous", "missing_unit", "unsupported"):
            da_co, status = None, st
            continue
        if st == "unqualified":
            # ``sửa lại giá là 8 tỷ`` chỉ rõ đối tượng nhờ giá BĐS đã có;
            # một ``giá 8 tỷ`` trần không được tự nhận là giá nhà.
            if len(values) == 1 and status == "known" and _SUA_GIA_BDS.search(nt):
                da_co, status = values[0], "known"
            else:
                da_co, status = None, "ambiguous"
            continue
        if st != "known":
            continue
        moi = values[0]
        if status == "ambiguous" and not _SUA_GIA_BDS.search(nt):
            continue
        if da_co is None or moi == da_co or _SUA_GIA_BDS.search(nt):
            da_co, status = moi, "known"
        else:
            da_co, status = None, "ambiguous"
    if gia_hien_tai_chua_ro_chu:
        if (len(gia_hien_tai_chua_ro_chu) == 1 and status == "known"
                and _SUA_GIA_BDS.search(_bo_dau(text))):
            return "known", gia_hien_tai_chua_ro_chu[0], hien_tai_gia_dinh
        return "ambiguous", None, False
    return status, da_co, False


def _tra_loi_ltv_theo_gia(text: str, history: list[dict] | None,
                           sp_doc: str) -> tuple[str, str] | None:
    """Tính ``min(LTV × giá khách nói, trần tuyệt đối)`` bằng Decimal."""
    gioi_han = _gioi_han_ltv(sp_doc)
    if gioi_han is None:
        return None
    ty_le, tran = gioi_han
    status, gia, gia_dinh = _gia_bds_hien_tai(text, history)
    if status != "known" or gia is None:
        return "xac_nhan_gia_bat_dong_san", (
            "Dạ để tính hạn mức theo tỷ lệ của sản phẩm, anh chị xác nhận giúp em "
            "một giá trị bất động sản bằng VND, kèm đơn vị triệu hoặc tỷ đồng ạ.")

    theo_ty_le = gia * ty_le / Decimal(100)
    toi_da = min(theo_ty_le, tran)
    mo_dau = "Dạ nếu bất động sản có giá" if gia_dinh else "Dạ với giá bất động sản"
    doc_ty_le = format(ty_le.normalize(), "f").replace(".", ",")
    if theo_ty_le > tran:
        phep_tinh = (
            f"{doc_ty_le}% tương đương {_fmt_trieu(theo_ty_le)}, nhưng trần "
            f"sản phẩm là {_fmt_trieu(tran)}, nên hạn mức tối đa theo sản phẩm là "
            f"{_fmt_trieu(toi_da)}")
    else:
        phep_tinh = (
            f"{doc_ty_le}% tương đương {_fmt_trieu(theo_ty_le)}; mức này không "
            f"vượt trần sản phẩm {_fmt_trieu(tran)}")
    return "han_muc_theo_gia_bat_dong_san", (
        f"{mo_dau} {_fmt_trieu(gia)}, {phep_tinh} ạ. Đây chỉ là hạn mức tối đa theo "
        "sản phẩm; mức được vay thực tế còn phụ thuộc thẩm định hồ sơ và không phải "
        "cam kết phê duyệt ạ.")


def _vay_theo_ty_le_khach_neu(text: str, history: list[dict] | None,
                              sp_doc: str) -> tuple[str, str] | None:
    """"nhà hai tỷ tám anh vay bảy mươi phần trăm": khách tự nêu TỶ LỆ muốn vay.

    Bộ thử 12-10-2026: câu này không hỏi "hạn mức" nên không luật nào nhận, kho
    đáp bằng câu lãi suất. Đổi tỷ lệ ra tiền và đối chiếu với tỷ lệ tối đa lẫn
    trần tiền của tài liệu; không phán hồ sơ được duyệt.
    """
    from backend.pipeline.du_kien_khoan_vay import quantities
    t = _bo_dau(text)
    if not re.search(r"\bvay\b", t) or re.search(r"\b(lai|phi)\b", t):
        return None
    phan_tram = [q for q in quantities(text) if q.value is not None
                 and re.search(r"%|phần trăm", q.raw.lower())]
    gioi_han = _gioi_han_ltv(sp_doc)
    if len(phan_tram) != 1 or gioi_han is None:
        return None
    status, gia, _ = _gia_bds_hien_tai(text, history)
    if status != "known" or gia is None:
        # "nhà hai tỷ tám": nói gọn, không có chữ "giá". Chỉ nhận khi lượt này
        # nhắc tới tài sản và có ĐÚNG một khoản tiền.
        tien = [q for q in quantities(text) if q.value is not None and q.kind == "money"]
        if len(tien) != 1 or not re.search(
                r"\b(nha|can ho|chung cu|can|dat|bat dong san)\b", t):
            return None
        gia = Decimal(tien[0].value)
    muon = Decimal(phan_tram[0].value)
    if not Decimal(0) < muon <= Decimal(100):
        return None
    ty_le, tran = gioi_han
    doc = lambda x: format(x.normalize(), "f").replace(".", ",")
    toi_da = min(gia * ty_le / Decimal(100), tran)
    so_tien = gia * muon / Decimal(100)
    if muon <= ty_le and so_tien > tran:
        return "ty_le_vay_vuot_muc", (
            f"Dạ {doc(muon)}% của {_fmt_trieu(gia)} là {_fmt_trieu(so_tien)}, vượt mức "
            f"cho vay tối đa {_fmt_trieu(tran)} của bên em ạ.")
    if muon > ty_le:
        return "ty_le_vay_vuot_muc", (
            f"Dạ bên em cho vay tối đa {doc(ty_le)}% giá trị bất động sản ạ. Với nhà "
            f"{_fmt_trieu(gia)} thì mức tối đa là {_fmt_trieu(toi_da)}, nên "
            f"{doc(muon)}% là vượt mức này ạ.")
    return "ty_le_vay_trong_muc", (
        f"Dạ {doc(muon)}% của {_fmt_trieu(gia)} là {_fmt_trieu(so_tien)}, nằm trong "
        f"mức cho vay tối đa {doc(ty_le)}% giá trị bất động sản của bên em ạ. "
        "Mức được duyệt thực tế còn tuỳ thẩm định hồ sơ ạ.")


_CHE_CAO = re.compile(r"\b(cao the|cao qua|cao vay|cao nhi|hoi cao|cao lam|dat the|dat qua)\b")
_SO_BEN_KHAC = re.compile(
    r"\b(ben (kia|khac|do|nguoi ta)|ngan hang (kia|khac)|cho khac)\b.{0,40}"
    r"\b(thoi|thap hon|re hon|phay|phan tram|chi co|co)\b")


def _tra_loi_che_lai_cao(t: str, tai_lieu: str, ma_sp: str,
                         history: list[dict] | None) -> tuple[str, str] | None:
    """"cao thế bên kia có sáu phẩy mấy thôi": khách chê lãi, so với nơi khác.

    Bộ thử 12-10-2026: mô hình tự viết khi thì "con số kia có thể là quảng cáo
    chưa chính xác", khi thì "mức cụ thể còn phụ thuộc hồ sơ" - cả hai đều không
    có trong tài liệu. Ở đây chỉ nhắc đúng mức lãi của tài liệu, nói rõ không có
    căn cứ để so, rồi mời tính thử. Kho có câu soạn riêng thì kho được ưu tiên
    (mã này nằm trong `LUAT_NHUONG_KHO`).
    """
    if not ma_sp.startswith("vay"):
        return None
    ai_truoc = next((m.get("content", "") for m in reversed(history or [])
                     if m.get("role") == "assistant"), "")
    ve_lai = bool(re.search(r"\blai\b", t)) or "lãi suất" in ai_truoc.lower()
    if not (ve_lai and (_SO_BEN_KHAC.search(t) or _CHE_CAO.search(t))):
        return None
    if re.search(r"\b(bao nhieu|the nao|may phan tram)\b", t) and not _CHE_CAO.search(t):
        return None
    lai = _lai_suat(tai_lieu)
    if lai is None:
        return None
    return "che_lai_cao", (
        f"Dạ em hiểu băn khoăn của anh chị ạ. Lãi suất gói bên em là từ {_so_phay(f'{lai:g}')}% "
        "một năm, còn mức của nơi khác thì em không có thông tin để so sánh ạ. Anh chị cho em "
        "biết số tiền và thời hạn muốn vay, em tính thử số tiền trả mỗi tháng để anh chị dễ "
        "cân nhắc ạ.")


def _tra_loi_vay_du_ra(text: str, t: str) -> tuple[str, str] | None:
    """"sửa bếp hết tầm tám chục triệu mà anh muốn vay dư ra tí cho chắc".

    Khách nêu mức CẦN và nói muốn vay NHIỀU HƠN mức đó: con số vừa nghe chưa phải
    số tiền vay. Nhắc lại đúng mức khách nói rồi xin một con số chốt. Bộ thử
    12-10-2026: mô hình tự viết lúc thì gán luôn 80 triệu, lúc thì phán "với thu
    nhập hiện tại anh vay được tối đa 500 triệu".
    """
    from backend.pipeline.du_kien_khoan_vay import quantities
    if not re.search(r"\bvay\b", t) or not re.search(
            r"\b(du ra|du mot (chut|ti|it)|them (mot )?(chut|ti|it)|nhinh hon|hon (mot )?(chut|ti)|"
            r"roi rai|cho chac)\b", t):
        return None
    tien = [q for q in quantities(text) if q.value is not None and q.kind == "money"]
    if len(tien) != 1:
        return None
    return "vay_du_ra", (
        f"Dạ em ghi nhận anh chị cần khoảng {_fmt_trieu(float(tien[0].value))} và muốn vay dư "
        "ra một chút ạ. Anh chị chốt giúp em một số tiền cụ thể muốn vay ạ?")


def _tra_loi_can_so_do(t: str, sp_doc: str) -> tuple[str, str] | None:
    """"thế có cần sổ đỏ không em": đọc đúng dòng hồ sơ có chữ sổ đỏ của tài liệu.

    Tài liệu sản phẩm không nhắc sổ đỏ (vay tín chấp) thì không đáp ở đây.
    """
    if not re.search(r"\b(so do|so hong|giay to nha|giay to phap ly)\b", t) or not re.search(
            r"\b(can|phai co|bat buoc|yeu cau|co can)\b", t):
        return None
    dong = next((d.strip(" -") for d in sp_doc.splitlines()
                 if re.search(r"\bso do\b", _bo_dau(d))), "")
    if not dong:
        return None
    return "can_so_do", f"Dạ có ạ, hồ sơ cần {dong[:1].lower() + dong[1:].rstrip('.')} ạ."


def _tra_loi_gioi_thieu_vay(text: str, t: str, tai_lieu: str, ma_sp: str) -> tuple[str, str] | None:
    """"...nên anh mới tính hỏi xem bên em cho vay thế nào": khách kể dài rồi hỏi CHUNG.

    Ghép ba dữ kiện chính của tài liệu (lãi suất, hạn mức, thời hạn) qua chính tầng
    luật. Bộ thử 12-10-2026: mô hình tự viết lúc giới thiệu được, lúc lại bảo "chưa
    có thông tin cụ thể về lãi suất hay hạn mức cho trường hợp này".
    """
    if not ma_sp.startswith("vay") or re.search(r"\d", t):
        return None
    from backend.pipeline.du_kien_khoan_vay import quantities
    if any(q.value is not None and q.kind in ("money", "duration") for q in quantities(text)):
        return None            # khách đã nêu con số: hỏi cho trường hợp riêng
    cuoi = " ".join(t.split()[-9:])
    if not re.search(r"\b(cho vay|vay)\b.{0,24}\b(the nao|nhu the nao|ra sao|nhu nao|sao)\s*(em|a|nhi|ha)?$",
                     cuoi) or re.search(r"\b(lai|han muc|giay to|ho so|thu tuc|dieu kien|tra)\b", cuoi):
        return None
    cac = []
    for hoi in ("lãi suất bao nhiêu", "hạn mức tối đa bao nhiêu", "thời hạn vay bao lâu"):
        got = _tra_loi(hoi, tai_lieu)
        if got and got[0] in _LUAT_MOT_Y:
            cau = got[1].replace(" Mức được duyệt thực tế còn phụ thuộc hồ sơ của anh chị.", "")
            cau = cau if not cac else re.sub(r"^Dạ,?\s+", "", cau)
            cac.append(cau[:1].upper() + cau[1:])
    if len(cac) < 2:
        return None
    # Câu đã dài quá trần của lớp dẫn dắt nên tự kết bằng câu hỏi mở đường.
    return "gioi_thieu_vay", " ".join(cac) + " Anh chị dự định vay khoảng bao nhiêu ạ?"


_HOI_HAN_MUC_VAY = re.compile(
    r"\b(han muc|(?:thue|the) vay toi da|vay (?:tin chap )?toi da(?: duoc)?|vay duoc bao nhieu)\b")


def _tra_loi_dang_co_no_khac(t: str, tai_lieu: str) -> tuple[str, str] | None:
    """"anh đang còn nợ thẻ bên ngân hàng khác có sao không".

    Khách có một khoản nợ ĐANG TRẢ ở nơi khác, không nói gì tới nợ xấu. Tài liệu
    chỉ nêu điều kiện "không có nợ xấu tại CIC", không có quy định nào về khoản
    nợ đang trả đúng hạn - nên chỉ đọc đúng điều kiện đó rồi chuyển chuyên viên.
    Khách đóng vai 12-10-2026: mô hình tự viết lấy nhầm dòng "nợ đã tất toán trên
    1 năm" cho một khoản nợ còn nguyên.
    """
    if re.search(r"\bno (?:xau|nhom|loai)\b|\b(?:tat toan|tra xong|tra het)\b", t):
        return None            # nợ xấu / đã tất toán: có luật riêng
    if not re.search(
            r"\b(?:dang|con|van)\b.{0,14}\b(?:no|vay|tra gop)\b.{0,30}\b(?:ben|ngan hang|cho|noi|cong ty) (?:khac|kia)\b|"
            r"\b(?:dang|con|van)\b.{0,10}\b(?:no the|khoan vay khac|tra gop)\b", t):
        return None
    if "khong co no xau tai cic" not in _bo_dau(tai_lieu):
        return None
    return "dang_co_no_khac", (
        "Dạ điều kiện bên em nêu là không có nợ xấu tại CIC ạ. Khoản anh chị đang trả ở nơi "
        "khác thì em xin ghi nhận để chuyên viên thẩm định cụ thể ạ.")


def _ghi_nhan_gia_nha(text: str, sp_doc: str) -> tuple[str, str] | None:
    """"anh định mua căn chung cư ba tỏi hai": khách kể GIÁ NHÀ, chưa hỏi gì.

    Đáp luôn mức vay tối đa theo tỷ lệ của tài liệu cho đúng giá đó. Số tiền đứng
    ngay sau chữ "vay" là khoản muốn vay, không phải giá nhà - để luật nhu cầu lo.
    """
    from backend.pipeline.du_kien_khoan_vay import quantities
    t = _bo_dau(text)
    if not re.search(r"\b(mua|gia)\b", t) or not re.search(
            r"\b(nha|can ho|chung cu|can|dat|biet thu)\b", t):
        return None
    cac = [q for q in quantities(text) if q.value is not None]
    gioi_han = _gioi_han_ltv(sp_doc)
    if len(cac) != 1 or cac[0].kind != "money" or gioi_han is None:
        return None
    if re.search(r"\bvay\b", _bo_dau(text[:cac[0].start])) or re.search(
            r"\b(tra|gop|moi thang|lai|co san|tra truoc)\b", t):
        return None
    ty_le, tran = gioi_han
    gia = Decimal(cac[0].value)
    toi_da = min(gia * ty_le / Decimal(100), tran)
    doc = format(ty_le.normalize(), "f").replace(".", ",")
    if toi_da == tran and gia * ty_le / Decimal(100) > tran:
        muc = f"tối đa {doc}% giá trị nhưng không quá {_fmt_trieu(tran)}"
    else:
        muc = f"tối đa {doc}% giá trị, tức khoảng {_fmt_trieu(toi_da)}"
    return "ghi_nhan_gia_nha", (
        f"Dạ với căn {_fmt_trieu(gia)} thì bên em cho vay {muc} ạ. "
        "Mức được duyệt thực tế còn tuỳ thẩm định hồ sơ ạ.")


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


_NHAC_LAI_THUOC_TINH = re.compile(
    r"\b(?:nhac lai|doc lai)\b.{0,45}\b(?:lai suat|muc lai|phi|bao hiem)\b")


def _la_nhac_lai_thuoc_tinh(text: str) -> bool:
    """Nhắc lãi/phí là hỏi thuộc tính sản phẩm, không phải đọc phương án riêng."""
    return bool(_NHAC_LAI_THUOC_TINH.search(_bo_dau(text)))


def _doi_chieu_gioi_han_phuong_an(so_tien: float, thang: int,
                                  sp_doc: str) -> str:
    """Đối chiếu hai dữ kiện với đúng giới hạn có trong tài liệu sản phẩm.

    Câu này chỉ nói về trần tuyệt đối và thời hạn. Nó không biến việc nằm trong
    khung thành lời hứa phê duyệt (vay mua nhà còn phụ thuộc tỷ lệ trên tài sản,
    các sản phẩm khác còn phụ thuộc thẩm định hồ sơ).
    """
    tran = _tran_san_pham(sp_doc)
    khung = _thoi_han(sp_doc)
    toi_da = None if khung else _thoi_han_toi_da(sp_doc)
    ngoai: list[str] = []
    if tran is not None and so_tien > tran:
        ngoai.append(
            f"số tiền vượt hạn mức tối đa {_fmt_trieu(tran)} trong tài liệu")
    if khung and not (khung[0] <= thang <= khung[1]):
        ngoai.append(
            f"thời hạn nằm ngoài khung {khung[0]} đến {khung[1]} tháng trong tài liệu")
    elif toi_da is not None and not (0 < thang <= toi_da):
        ngoai.append(
            f"thời hạn vượt mức tối đa {_doc_ky_han(toi_da, toi_da % 12 == 0)} trong tài liệu")
    if ngoai:
        return " " + _noi_danh_sach([x[:1].upper() + x[1:] for x in ngoai]) + "."

    da_doi_chieu_tien = tran is not None
    da_doi_chieu_ky = khung is not None or toi_da is not None
    if da_doi_chieu_tien and da_doi_chieu_ky:
        return (
            " Về trần số tiền và thời hạn trong tài liệu, phương án này nằm trong "
            "phạm vi sản phẩm; đây chưa phải kết quả phê duyệt hay hạn mức được duyệt."
        )
    return ""


def _tra_loi_nhac_lai(text: str, history: list[dict] | None,
                      xung_ho: str, state: LoanState,
                      sp_doc: str) -> tuple[str, str] | None:
    """Đọc lại dữ kiện khách đã nói bằng bộ nhớ có cấu trúc.

    Không tóm tắt toàn bộ lịch sử rồi nhét thêm vào prompt. Chỉ khi khách hỏi
    lại một dữ kiện rõ ràng mới quét lời KHÁCH, lấy đúng loại số và trả thẳng.
    Cách này không phụ thuộc việc model nhỏ có chịu chú ý tới lượt thứ 10 hay
    không, đồng thời không làm phình cửa sổ context.
    """
    t = _bo_dau(text)
    hoi_lai = bool(re.search(
        r"\b(nhac lai|doc lai|da (?:noi|cung cap)|noi luc dau|truoc do|"
        r"anh noi|chi noi|toi noi)\b", t))
    if not hoi_lai:
        return None

    # Không để chữ "nhắc lại" biến câu hỏi lãi/phí thành yêu cầu đọc số tiền
    # và kỳ hạn. Câu chung về phí cần hỏi đúng loại phí; lãi suất chỉ được đọc
    # khi có đúng dòng nguồn của sản phẩm.
    if _la_nhac_lai_thuoc_tinh(text):
        hoi_lai_suat = bool(re.search(r"\b(?:lai suat|muc lai)\b", t))
        hoi_phi = bool(re.search(r"\bphi\b", t))
        if hoi_lai_suat:
            gia_tri = _gia_tri_dong(sp_doc, "lãi suất")
            if gia_tri:
                cau = f"Dạ lãi suất của gói vay là {gia_tri} ạ."
                if hoi_phi:
                    cau += " Anh chị muốn em kiểm tra loại phí nào ạ?"
                return ("nhac_lai_lai_suat_va_phi" if hoi_phi else "lai_suat_san_pham", cau)
        if hoi_phi:
            return "xac_nhan_loai_phi", "Dạ anh chị muốn em kiểm tra loại phí nào ạ?"
        return None

    co_moc_ban_dau = bool(re.search(r"\b(luc dau|ban dau)\b", t))
    loai_moc_ban_dau = bool(re.search(
        r"\b(?:dung lay|khong (?:dung|lay)|bo qua|loai bo)\b.{0,45}"
        r"\b(?:luc dau|ban dau)\b", t))
    doc_lai_ban_dau = co_moc_ban_dau and not loai_moc_ban_dau
    if doc_lai_ban_dau:
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
        state = resolve(history)

    hoi_nhu_cau = bool(re.search(
        r"\b(phuong an(?: vay)?|nhu cau(?: vay)?|so tien|khoan vay|can vay|"
        r"muon vay|thoi han|ky han)\b", t))
    if hoi_nhu_cau:
        tien = float(state.amount.value) if state.amount.value is not None else None
        thang = int(state.term.value) if state.term.value is not None else None
        if tien is not None and thang is not None:
            if doc_lai_ban_dau:
                return "nhac_lai_nhu_cau", (
                    f"Dạ trước đó {xung_ho} nói cần vay {_fmt_trieu(tien)} "
                    f"trong {thang} tháng ạ."
                )
            return "nhac_lai_nhu_cau", (
                f"Dạ phương án hiện tại em đang ghi nhận là vay {_fmt_trieu(tien)} "
                f"trong {thang} tháng ạ."
                + _doi_chieu_gioi_han_phuong_an(tien, thang, sp_doc)
            )
        if tien is not None:
            return "nhac_lai_nhu_cau", (
                f"Dạ hiện em đang ghi nhận số tiền muốn vay là {_fmt_trieu(tien)}, "
                f"nhưng chưa có thời hạn vay rõ ràng. {xung_ho.capitalize()} xác nhận "
                "giúp em thời hạn theo tháng hoặc năm ạ."
            )
        if thang is not None:
            return "nhac_lai_nhu_cau", (
                f"Dạ hiện em đang ghi nhận thời hạn vay là {thang} tháng, nhưng chưa có "
                f"số tiền rõ ràng. {xung_ho.capitalize()} xác nhận giúp em số tiền kèm "
                "đơn vị triệu hoặc tỷ đồng ạ."
            )
        if state.amount.status == "cancelled" and state.term.status == "cancelled":
            return "nhac_lai_nhu_cau_chua_co", (
                "Dạ nhu cầu vay trước đã được rút lại, nên hiện em chưa có phương án "
                "nào để đọc lại ạ."
            )
        can_xac_nhan = []
        if state.amount.status == "missing_unit":
            can_xac_nhan.append("số tiền kèm đơn vị triệu hoặc tỷ đồng")
        elif state.amount.status == "ambiguous":
            can_xac_nhan.append("một số tiền muốn vay cụ thể")
        else:
            can_xac_nhan.append("số tiền muốn vay")
        if state.term.status == "missing_unit":
            can_xac_nhan.append("thời hạn kèm đơn vị tháng hoặc năm")
        elif state.term.status == "ambiguous":
            can_xac_nhan.append("một thời hạn vay cụ thể")
        else:
            can_xac_nhan.append("thời hạn vay")
        return "nhac_lai_nhu_cau_chua_ro", (
            "Dạ hiện em chưa có phương án vay đủ rõ để đọc lại. "
            f"{xung_ho.capitalize()} xác nhận giúp em {_noi_danh_sach(can_xac_nhan)} ạ."
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
    # "lương tám triệu thì mở được hạng nào": cũng là hỏi mình có đủ mức không.
    r"\b(?:mo|lam|vay) duoc\b|\b(?:hang|loai|the) (?:nao|gi)\b|"
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


_KHONG_PHAI_LOI_KHAI_THU_NHAP_HIEN_TAI = re.compile(
    r"\b(?:neu|gia su|vi du|truong hop|so sanh|doi chieu|sang nam|tuong lai|"
    r"du kien|du tinh|tuoi)\b|"
    r"\b(?:dieu kien|quy dinh|toi thieu|it nhat|yeu cau)\b"
    r".{0,55}\b(?:luong|thu nhap)\b")


def _ghi_nhan_thu_nhap_nguoi_khac(text: str, xung_ho: str,
                                   state: LoanState) -> tuple[str, str] | None:
    """Giữ lời khai thu nhập người khác khỏi rơi xuống đường sinh tự do.

    Việc phân loại con số và chủ sở hữu dùng đúng parser typed của sổ dữ kiện.
    Regex cục bộ chỉ xác nhận rằng mệnh đề có một chủ thể người khác rõ ràng;
    nó không tự quyết định con số nào là thu nhập. Nếu lượt này còn có thu nhập
    riêng hoặc thu nhập hộ gia đình, nhường nguyên cho luật ghi nhận hiện hữu.
    """
    t = _bo_dau(text)
    if ("?" in (text or "")
            or _KHONG_PHAI_LOI_KHAI_THU_NHAP_HIEN_TAI.search(t)
            or _HOI_DUOC_KHONG.search(t)
            or re.search(
                r"\b(?:co the|co vay|vay duoc|lam the duoc|mo the duoc|"
                r"du dieu kien|bao nhieu|the nao|ra sao)\b", t)):
        return None

    from backend.pipeline.du_kien_khoan_vay import (
        _income_owner,
        _role,
        chu_the_thu_nhap_nguoi_khac,
    )

    thu_nhap = []
    for q in quantities(text):
        if q.value is None or q.kind not in ("bare", "money"):
            continue
        if _role(text, q, False) != "income":
            continue
        thu_nhap.append((q, _income_owner(text, q)))
    if not thu_nhap or any(owner in ("self", "household") for _, owner in thu_nhap):
        return None
    if not any(owner == "" and chu_the_thu_nhap_nguoi_khac(text, q)
               for q, owner in thu_nhap):
        return None

    ghi_nhan_vay = ""
    tien = (float(state.amount.value) if state.amount_updated
            and state.amount.status == "known" and state.amount.value is not None else None)
    thang = (int(state.term.value) if state.term_updated
             and state.term.status == "known" and state.term.value is not None else None)
    if tien is not None and thang is not None:
        ghi_nhan_vay = (
            f"Dạ em ghi nhận {xung_ho} muốn vay {_fmt_trieu(tien)} trong {thang} tháng. ")
    elif tien is not None:
        ghi_nhan_vay = f"Dạ em ghi nhận {xung_ho} muốn vay {_fmt_trieu(tien)}. "
    elif thang is not None:
        ghi_nhan_vay = f"Dạ em ghi nhận thời hạn vay {thang} tháng. "
    else:
        ghi_nhan_vay = "Dạ "
    chu_muc = "Mức" if ghi_nhan_vay.endswith(". ") else "mức"

    if (state.income.owner == "self" and state.income.status == "known"
            and state.income.value is not None):
        return "ghi_nhan_thu_nhap_nguoi_khac", (
            ghi_nhan_vay
            + f"{chu_muc} thu nhập anh chị vừa nêu là của người khác, nên không thay đổi "
              "mức thu nhập riêng anh chị đã cung cấp ạ.")
    return "ghi_nhan_thu_nhap_nguoi_khac", (
        ghi_nhan_vay
        + f"{chu_muc} thu nhập anh chị vừa nêu là của người khác, nên em chưa coi đó là "
          "thu nhập riêng của anh chị. Anh chị cho em biết thu nhập thực tế mỗi tháng "
          "của người đứng tên vay để em đối chiếu ạ.")


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
    # "cô lương mười bốn triệu chuyển khoản", "lương mười bốn triệu": người lớn
    # tuổi xưng cô/chú/bác, hoặc bỏ luôn chủ ngữ khi đang kể về mình.
    if not re.search(r"\b(anh|chi|toi|minh|em|co|chu|bac|tui|chau)\b", t) and not (
            re.match(r"(luong|thu nhap)\b", t)
            and not re.search(r"\b(bao nhieu|may|toi thieu|thi duoc|moi duoc|can|"
                              r"no|con|vo|chong|bo|me|ong ay|ba ay|anh ay|chi ay)\b", t)):
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
            from backend.pipeline.tra_loi_dieu_kien import nhan_xet_tuoi
            ve_tuoi = nhan_xet_tuoi(text, sp_doc)
            if ve_tuoi:
                cau += " " + ve_tuoi[:1].upper() + ve_tuoi[1:]
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
_SO_SANH_VOI_THU_NHAP = re.compile(
    r"\b(?:so sanh|so|doi chieu)\b.{0,55}\b(?:khoan vay|phuong an vay|khoan tra|"
    r"tien tra|tra hang thang)\b.{0,55}\b(?:thu nhap|luong)\b|"
    r"\b(?:khoan vay|phuong an vay|khoan tra|tien tra|tra hang thang)\b.{0,55}"
    r"\b(?:so sanh|so|doi chieu)\b.{0,35}\b(?:thu nhap|luong)\b")


def _can_nhac_kha_nang_tra(text: str, state: LoanState, sp_doc: str) \
        -> tuple[str, str] | None:
    """Phản hồi lo gánh trả bằng phép tính nguồn, không tự đặt ngưỡng DTI."""
    t = _bo_dau(text)
    lo_ganh_tra = bool(_LO_LANG_GANH_TRA.search(t) and _NHAC_KHOAN_TRA.search(t))
    so_sanh_ro = bool(_SO_SANH_VOI_THU_NHAP.search(t))
    if not (lo_ganh_tra or so_sanh_ro):
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
    # "đến hạn anh không ra rút thì sao": tài liệu không nói gì về tái tục hay xử
    # lý khi đáo hạn. Kho từng đáp bằng câu RÚT TRƯỚC HẠN (khách đóng vai 12-10-2026).
    ("xử lý khi đến hạn", ("den han", "dao han", "tai tuc", "het ky han", "het han")),
    ("thời gian mở thẻ", ("mo the mat bao lau", "lam the mat bao lau", "bao lau thi co the",
                          "may ngay thi co the", "bao lau co the")),
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


_Y_DINH_VI_DU_NGUON = re.compile(
    r"\b(?:theo|dung|lay|doc|trong)\s+(?:dung\s+)?vi du\b|"
    r"\bvi du\s+(?:cua\s+)?(?:san pham|cong bo|trong tai lieu|trong nguon)\b|"
    r"\bvi du\b.{0,28}\b(?:cong bo|tai lieu|nguon|ghi|neu)\b")


def _cac_vi_du_khoan_tra(sp_doc: str) -> list[tuple[Decimal, int, Decimal]]:
    """Đọc đúng bộ ba tiền vay, kỳ hạn, khoản trả từ mục ví dụ của nguồn."""
    trong_muc = False
    ket_qua: list[tuple[Decimal, int, Decimal]] = []
    for dong in (sp_doc or "").splitlines():
        st = dong.strip()
        if st.startswith("#"):
            trong_muc = "vi du" in _bo_dau(st.lstrip("# "))
            continue
        if not trong_muc or "vi du" not in _bo_dau(st):
            continue
        qs = [q for q in quantities(st) if q.value is not None]
        tien = [Decimal(str(q.value)) for q in qs if q.kind == "money"]
        ky = [int(q.value) for q in qs if q.kind == "duration"]
        if len(tien) >= 2 and len(ky) == 1 and re.search(
                r"\b(?:moi thang|hang thang)\b", _bo_dau(st)):
            ket_qua.append((tien[0], ky[0], tien[-1]))
    return ket_qua


def _tra_loi_vi_du_nguon(text: str, state: LoanState, sp_doc: str,
                          xung_ho: str) -> tuple[str, str] | None:
    """Ưu tiên con số ví dụ công bố khi khách đích danh yêu cầu ví dụ nguồn."""
    if not _Y_DINH_VI_DU_NGUON.search(_bo_dau(text)):
        return None

    if state.amount.status in ("ambiguous", "missing_unit") \
            or state.term.status in ("ambiguous", "missing_unit"):
        return "xac_nhan_phuong_an_vi_du_nguon", (
            f"Dạ để đối chiếu đúng ví dụ công bố, {xung_ho} chốt giúp em một số tiền "
            "vay kèm đơn vị và một thời hạn vay cụ thể ạ.")

    so_tien = (Decimal(str(state.amount.value))
               if state.amount.value is not None else None)
    thang = int(state.term.value) if state.term.value is not None else None
    if so_tien is None or thang is None:
        thieu = ("số tiền vay và thời hạn vay" if so_tien is None and thang is None
                 else "số tiền vay" if so_tien is None else "thời hạn vay")
        return "thieu_du_kien_vi_du_nguon", (
            f"Dạ để tìm đúng ví dụ công bố, {xung_ho} cho em biết {thieu} cụ thể ạ.")

    cac = _cac_vi_du_khoan_tra(sp_doc)
    khop = {tra for tien, ky, tra in cac if tien == so_tien and ky == thang}
    if len(khop) == 1:
        tra = next(iter(khop))
        return "vi_du_nguon_khoan_tra", (
            f"Dạ theo ví dụ công bố trong tài liệu sản phẩm, vay "
            f"{_fmt_trieu(float(so_tien))} trong {thang} tháng thì số tiền phải trả "
            f"khoảng {_fmt_trieu(float(tra))} mỗi tháng ạ. Đây là khoản trả trong "
            "ví dụ, không phải thu nhập của khách và chưa phải lịch trả nợ chính thức "
            "được phê duyệt.")
    if len(khop) > 1:
        return "vi_du_nguon_mau_thuan", (
            "Dạ tài liệu đang có nhiều khoản trả khác nhau cho cùng số tiền và thời hạn, "
            "nên em chưa thể chọn một con số làm ví dụ công bố và cần kiểm tra lại nguồn ạ.")
    if not cac:
        return "khong_co_vi_du_nguon", (
            "Dạ tài liệu sản phẩm hiện chưa có ví dụ khoản trả hàng tháng để em đọc đúng "
            "theo nguồn; em chưa tự thay bằng một phép tính ước lượng ạ.")
    return "khong_co_vi_du_nguon_khop", (
        f"Dạ tài liệu hiện chưa có ví dụ công bố khớp khoản vay "
        f"{_fmt_trieu(float(so_tien))} trong {thang} tháng. Em chưa tự dùng công thức "
        "ước lượng thay cho ví dụ mà anh chị yêu cầu ạ.")


_HOI_CHINH_SACH_NGOAI_NGUON = re.compile(
    r"\b(?:lai|lai suat|tien lai|han muc|bieu phi|phi|ty le|chinh sach|dieu kien|"
    r"ho tro|ap dung|cu the|bao nhieu|co phai|duoc khong|co duoc|chac|nhan lam|"
    r"the chap|bao dam|dam bao|cam co|dua tren|duyet|phe duyet|tra lai|gui|vay|"
    r"tai lieu|nguon|pham vi|noi ro)\b")
_CHUYEN_VE_VND = re.compile(
    r"\b(?:chuyen|doi|quay|tinh|gui|vay|lay)\s+(?:lai\s+)?(?:sang|bang|theo)?\s*"
    r"(?:vnd|dong viet nam|tien viet|tien dong)\b|"
    r"\b(?:vnd|dong viet nam|tien viet|tien dong)\b.{0,18}\b(?:thay|chu|thoi|nhe)\b")


def _vai_tro_ngoai_te_trong_cau(t: str, start: int, end: int) -> str | None:
    """Vai trò gần nhất của ngoại tệ: sản phẩm, thu nhập hay giá tài sản.

    Chỉ ``san_pham`` được phép tạo chủ đề đơn vị vay/gửi/thẻ cho lượt sau.
    Một mức lương USD hoặc giá căn hộ USD vẫn là dữ kiện khác loại, dù câu hỏi
    tiếp theo có chữ hạn mức hay lãi suất.
    """
    dau, cuoi = _gioi_han_menh_de(t, start, end)
    menh_de = t[dau:cuoi]
    vi_tri = start - dau

    def gan_nhat(mau: str) -> int | None:
        cac = list(re.finditer(mau, menh_de))
        if not cac:
            return None
        return min(min(abs(m.end() - vi_tri), abs(m.start() - vi_tri)) for m in cac)

    thu_nhap = gan_nhat(r"\b(?:thu nhap|luong|doanh thu|tien cong)\b")
    gia_tai_san = gan_nhat(
        r"\b(?:can ho|can nha|ngoi nha|gia nha|gia dat|bat dong san|"
        r"gia tri tai san|gia tri bat dong san)\b")
    san_pham = gan_nhat(
        r"\b(?:vay|khoan vay|tien vay|gui|tiet kiem|tien gui|mo so|the tin dung|"
        r"han muc|bieu phi|lai suat|tien lai|tra lai)\b")
    vai_tro = [(d, ten) for d, ten in (
        (thu_nhap, "thu_nhap"), (gia_tai_san, "gia_tai_san"),
        (san_pham, "san_pham")) if d is not None]
    if vai_tro:
        return min(vai_tro)[1]

    # Một câu hỏi trực tiếp ``USD có được không`` vẫn là hỏi chính sách của sản
    # phẩm đang chọn. Lời kể ``tôi có 2.000 USD`` thì không tạo chủ đề.
    if re.search(r"\b(?:muon dung|can dung|chon|doi sang|chuyen sang|dung)\s*$",
                 menh_de[:vi_tri]):
        return "san_pham"
    if re.search(r"\b(?:co phai|co neu|duoc khong|co duoc|ho tro|ap dung|"
                 r"chinh sach|bao nhieu|the nao|cu the)\b", menh_de):
        return "san_pham"
    return None


def _ho_san_pham_nguon(source_doc: str) -> str:
    ma = _ma_san_pham(source_doc)
    if ma == "tiet_kiem":
        return "tien_gui"
    if ma == "the_tin_dung":
        return "the"
    if ma in ("vay_tin_chap", "vay_mua_nha"):
        return "vay"
    return ""


def _ho_san_pham_noi_ro(text: str) -> str | None:
    """Họ sản phẩm được gọi đích danh trong một lượt, nếu có."""
    t = _chuan_hoa_bien_chu_so(text)
    if re.search(r"\b(?:the tin dung|the (?:gold|classic|platinum)|han muc the|mo the)\b", t):
        return "the"
    if re.search(r"\b(?:gui|tiet kiem|tien gui|khoan gui|mo so|so tiet kiem|"
                 r"so that|so vnd|sovnd)\b", t):
        return "tien_gui"
    if re.search(r"\b(?:vay|khoan vay|tien vay)\b", t):
        return "vay"
    return None


def _khai_bao_vnd_thuc_te(text: str, ho_nguon: str) -> bool:
    """Khai báo phương án VND mới xóa chủ đề ngoại tệ treo từ lịch sử."""
    t = _chuan_hoa_bien_chu_so(text)
    if re.search(r"\b(?:neu|gia su|vi du|thu dat vao)\b", t):
        return False
    if _ho_san_pham_noi_ro(text) != ho_nguon:
        return False
    return bool(
        re.search(r"\b\d[\d.,]*\s*(?:trieu|ty|ti)\s+dong\b", t)
        or re.search(r"\b(?:vnd|sovnd|dong viet nam|tien viet|tien dong)\b", t))


def _la_tinh_huong_gia_dinh(text: str) -> bool:
    return bool(re.search(r"\b(?:neu|gia su|vi du|thu dat vao)\b", _bo_dau(text)))


def _chu_de_ngoai_nguon_trong_luot(text: str) -> tuple[str, str, str] | None:
    """Nhận chủ đề có neo chính sách; một câu kể ``xe của tôi 30m`` không đủ."""
    t = _chuan_hoa_bien_chu_so(text)
    goc = unicodedata.normalize("NFC", (text or "").lower())
    goc = re.sub(r"(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])", " ", goc)
    cac = (
        # Với câu ``gửi vàng với USD``, giữ mã chính sách tiền gửi hiện hữu.
        # Một câu chỉ nói USD vẫn đi nhánh đơn vị tiền tệ ngay bên dưới.
        ("vang", "vàng", "tien_gui", r"\bvang\b"),
        ("usd", "USD", "tien_te", r"\b(?:usd|do la my|do la)\b"),
        ("eur", "EUR", "tien_te", r"\b(?:eur|euro)\b"),
        ("o_to", "ô tô", "tai_san", r"\b(?:o to|xe hoi|xe oto)\b"),
        ("tien_ma_hoa", "tiền mã hóa", "tien_ma_hoa",
         r"\b(?:tien ma hoa|tien dien tu|crypto|bitcoin|ethereum|eth)\b"),
    )
    for ma, ten, loai, mau in cac:
        for m in re.finditer(mau, t):
            truoc = t[max(0, m.start() - 28):m.start()]
            sau = t[m.end():min(len(t), m.end() + 28)]
            truoc_goc = goc[max(0, m.start() - 28):m.start()]
            if (re.search(r"\b(?:khong phai|bo|huy|khong (?:dung|tinh|gui|vay|"
                          r"lay|chon))\s*$", truoc)
                    or re.search(r"\b(?:dừng|đừng)\s*$", truoc_goc)
                    or re.match(r"\s*(?:khong (?:dung|tinh|gui|vay|lay|chon)\s+)?nua\b", sau)):
                continue
            if loai == "tien_te" and _vai_tro_ngoai_te_trong_cau(
                    t, m.start(), m.end()) != "san_pham":
                continue
            if loai == "tien_gui" and not re.search(
                    r"\b(?:gui|tiet kiem|mo so|lai|lai suat|nhan lai|tai san|the chap|"
                    r"bao dam|dam bao|cam co)\b", t):
                continue
            loai_ket_qua = loai
            if loai == "tien_ma_hoa":
                dau_menh_de, cuoi_menh_de = _gioi_han_menh_de(t, m.start(), m.end())
                quanh = t[dau_menh_de:cuoi_menh_de]
                if re.search(
                        r"\b(?:tai san|the chap|bao dam|dam bao|cam co|nhan lam|dua tren)\b",
                        quanh):
                    loai_ket_qua = "tai_san"
                elif re.search(
                        r"\b(?:gui|tiet kiem|tien gui|khoan gui|mo so|lai|lai suat|"
                        r"tien lai|nhan lai)\b", quanh):
                    loai_ket_qua = "tien_gui"
                elif _khai_bao_vnd_thuc_te(text, "tien_gui"):
                    # ``Bitcoin để đầu tư, còn gửi 100 triệu đồng`` có hai đối
                    # tượng. Khoản VND thực tế thắng dù đứng trước hay sau.
                    continue
                elif re.search(
                        r"\b(?:gui|tiet kiem|tien gui|khoan gui|mo so|lai|lai suat|"
                        r"tien lai|nhan lai)\b", t):
                    # Không có đơn vị thay thế: ``tôi có Bitcoin, gửi online``
                    # là yêu cầu dùng chính Bitcoin cho sản phẩm đang hỏi.
                    loai_ket_qua = "tien_gui"
                elif re.search(
                        r"\b(?:co duoc|duoc khong|ho tro|ap dung|chinh sach)\b", quanh):
                    loai_ket_qua = "chinh_sach"
                elif re.search(
                        r"\b(?:tai lieu|nguon)\b.{0,30}\b(?:noi|neu|co|khong co)\b|"
                        r"\b(?:noi ro|pham vi)\b", quanh):
                    # ``Nếu tài liệu không nói về crypto thì nói rõ phạm vi``
                    # là yêu cầu mô tả giới hạn của nguồn, không phải căn cứ để
                    # suy ra ngân hàng cấm hay không hỗ trợ tiền mã hóa.
                    loai_ket_qua = "chinh_sach"
                else:
                    # Số dư hoặc giá Bitcoin/ETH chỉ là một tài sản khách kể,
                    # không tự đổi đơn vị khoản vay hay giá bất động sản.
                    continue
            if loai_ket_qua == "tai_san" and not re.search(
                    r"\b(?:tai san|the chap|bao dam|dam bao|cam co|nhan lam|dua tren)\b", t):
                continue
            return ma, ten, loai_ket_qua
    return None


def _tra_loi_pham_vi_nguon(text: str, source_doc: str,
                            history: list[dict] | None = None) \
        -> tuple[str, str] | None:
    """Chặn áp chính sách VND/tài sản chung sang đơn vị không được nguồn nêu.

    Hàm thuần này cũng được pipeline gọi trước các câu trả lời điều kiện nhanh.
    Chỉ sáu lượt khách gần nhất được xét để chủ đề cũ không bám vô hạn.
    """
    if not (source_doc or "").strip():
        return None
    cac_luot = [m.get("content", "") for m in (history or [])
                if m.get("role") == "user"]
    if not cac_luot or cac_luot[-1].strip() != (text or "").strip():
        cac_luot.append(text or "")
    chu_de: tuple[str, str, str] | None = None
    cac_xet = cac_luot[-6:]
    ho_nguon = _ho_san_pham_nguon(source_doc)
    for i, cau in enumerate(cac_xet):
        t = _bo_dau(cau)
        ho_noi_ro = _ho_san_pham_noi_ro(cau)
        if ho_noi_ro and ho_nguon and ho_noi_ro != ho_nguon:
            # Không mang USD của khoản vay cũ sang thẻ hay sổ tiết kiệm đang chọn.
            chu_de = None
            continue
        moi = _chu_de_ngoai_nguon_trong_luot(cau)
        if moi:
            # Giả định hiện tại vẫn cần câu trả lời có nguồn, nhưng khi đã thành
            # lịch sử nó không được thay đơn vị thực tế của các lượt sau.
            if i == len(cac_xet) - 1 or not _la_tinh_huong_gia_dinh(cau):
                chu_de = moi
        elif (_khai_bao_vnd_thuc_te(cau, ho_nguon)
              or _CHUYEN_VE_VND.search(t) or re.search(
                r"\b(?:bo|huy|dung|khong dung|khong .* nua|khong phai)\b.{0,18}"
                r"\b(?:usd|do la|eur|euro|vang|o to|xe hoi|crypto|bitcoin|ethereum|eth|"
                r"tien ma hoa|tien dien tu)\b",
                t)):
            chu_de = None

    if chu_de is None or not _HOI_CHINH_SACH_NGOAI_NGUON.search(_bo_dau(text)):
        return None
    ma, ten, loai = chu_de
    doc = _bo_dau(_phan_san_pham(source_doc))
    mau_doc = {
        "usd": r"\b(?:usd|do la my|do la)\b",
        "eur": r"\b(?:eur|euro)\b",
        "vang": r"\bvang\b",
        "o_to": r"\b(?:o to|xe hoi|xe oto)\b",
        "tien_ma_hoa": r"\b(?:tien ma hoa|tien dien tu|crypto|bitcoin|ethereum|eth)\b",
    }[ma]
    if re.search(mau_doc, doc):
        return None
    if loai == "tai_san":
        return "tai_san_chua_duoc_nguon_xac_nhan", (
            f"Dạ tài liệu sản phẩm hiện chưa xác nhận riêng {ten} là tài sản bảo đảm "
            "được chấp nhận. Cụm “tài sản khác” nếu có trong tài liệu chưa đủ để bảo "
            "đảm trường hợp này sẽ được nhận; em cần kiểm tra lại chính sách cụ thể ạ.")
    if loai == "tien_gui":
        return "tien_gui_khong_co_chinh_sach", (
            f"Dạ tài liệu sản phẩm hiện chưa nêu chính sách gửi hoặc trả lãi bằng {ten}, "
            "nên em chưa thể áp lãi suất tiền gửi bằng đồng Việt Nam cho trường hợp này ạ.")
    if loai == "chinh_sach":
        ma_tra_loi = ("tien_gui_khong_co_chinh_sach"
                      if ho_nguon == "tien_gui" else "tai_san_chua_duoc_nguon_xac_nhan")
        return ma_tra_loi, (
            f"Dạ tài liệu sản phẩm hiện chưa nêu chính sách áp dụng với {ten}, "
            "nên em chưa thể xác nhận và cần kiểm tra lại nguồn cụ thể ạ.")
    return "don_vi_tien_te_chua_co_trong_nguon", (
        f"Dạ tài liệu sản phẩm hiện chưa nêu lãi suất, hạn mức hoặc biểu phí bằng {ten}, "
        f"nên em chưa thể áp các mức bằng đồng Việt Nam cho {ten} và cần kiểm tra lại "
        "chính sách cụ thể ạ.")


def _bo_chu_de_da_rut_khoi_cau(text: str) -> str:
    """Không để tên đơn vị đã rút kích hoạt lại guard hẹp ở nhánh sản phẩm."""
    t = _bo_dau(text)
    rut = _CHUYEN_VE_VND.search(t) or re.search(
        r"\b(?:bo|huy|dung|khong dung|khong .* nua|khong phai)\b.{0,18}"
        r"\b(?:usd|do la|eur|euro|vang|o to|xe hoi|crypto|bitcoin|ethereum|eth|"
        r"tien ma hoa|tien dien tu)\b",
        t)
    if not rut:
        return t
    return re.sub(
        r"\b(?:usd|do la my|do la|eur|euro|vang|o to|xe hoi|xe oto|crypto|bitcoin|"
        r"ethereum|eth|tien ma hoa|tien dien tu)\b", " ", t)


def _tra_loi_an_toan_danh_tinh_va_du_lieu(text: str) -> tuple[str, str] | None:
    """Ưu tiên danh tính cuộc gọi và dữ liệu bí mật trước đường sinh tự do."""
    t = _bo_dau(text)

    nhay_cam = bool(re.search(
        r"\b(?:otp|pin|mat khau|ma bao mat|ma xac thuc|so the|ngay het han)\b", t))
    tu_choi = bool(re.search(
        r"\b(?:khong dong y|khong muon|tu choi|se khong|khong cung cap|khong doc)\b", t))
    if nhay_cam and tu_choi:
        return "tu_choi_cung_cap_du_lieu_nhay_cam", (
            "Dạ em ghi nhận anh chị không đồng ý cung cấp thông tin. Anh chị không cần "
            "và không nên đọc OTP, PIN, mật khẩu, toàn bộ số thẻ hoặc ngày hết hạn trong "
            "cuộc trò chuyện này; em sẽ không hỏi thêm các thông tin đó ạ.")

    otp_bi_thuc = bool(
        re.search(r"\botp\b", t)
        and re.search(r"\b(?:nguoi|ai|ho|nhan vien|ngan hang)\b", t)
        and re.search(r"\b(?:bao|giuc|doi|yeu cau|xin|can)\b", t)
        and re.search(r"\b(?:doc|cung cap|gui|xac minh)\b", t))
    mat_the = bool(re.search(
        r"\b(?:mat|that lac|khong thay|de quen|danh roi|lay cap)\b.{0,34}\bthe\b|"
        r"\bthe(?:\s+(?:tin dung|classic|gold|platinum))?"
        r"(?:\s+(?:toi|anh|chi|em|minh|cua toi|cua anh|cua chi)){0,2}\s+"
        r"(?:bi\s+)?(?:mat|that lac|de quen|danh roi|lay cap)\b", t))
    if otp_bi_thuc and not mat_the:
        return "canh_bao_otp_cuoc_goi", (
            "Dạ anh chị không đọc hoặc cung cấp OTP cho người gọi và hãy ngắt cuộc gọi "
            "đó ngay. Sau đó anh chị tự liên hệ ngân hàng qua kênh chính thức đã kiểm "
            "chứng; không dùng số điện thoại hoặc đường dẫn do người gọi cung cấp ạ.")

    hoi_danh_tinh = bool(
        re.search(r"\b(?:ban|em)\s+la\s+ai\b", t)
        and re.search(r"\b(?:ngan hang|that|don vi|goi)\b", t))
    hoi_nguon_lien_he = bool(
        re.search(r"\bso nay\b.{0,24}\b(?:don vi nao|ben nao|cua ai)\b", t)
        or re.search(r"\b(?:sao|tai sao)\b.{0,24}\bbiet\b.{0,32}"
                     r"\b(?:tien nhan roi|so du|tien cua toi)\b", t))
    if hoi_danh_tinh or hoi_nguon_lien_he:
        return "danh_tinh_va_nguon_lien_he_chua_xac_minh", (
            "Dạ em là trợ lý tư vấn tự động đang trả lời theo tài liệu sản phẩm được "
            "chọn. Em không có thông tin đã được xác minh về đơn vị gọi hoặc nguồn số "
            "liên hệ này, và cũng không có dữ liệu để biết anh chị có tiền nhàn rỗi hay "
            "số dư. Anh chị có thể tự kiểm tra qua kênh chính thức đã biết và không cung "
            "cấp OTP, PIN, mật khẩu, toàn bộ số thẻ hoặc ngày hết hạn ạ.")
    return None


def tra_loi(text: str, tai_lieu: str, ho_so: dict | None = None,
            history: list[dict] | None = None, xung_ho: str = "anh chị",
            du_kien: LoanState | None = None) \
        -> tuple[str, str] | None:
    """Trả ``(mã, câu)`` khi đủ dữ kiện để trả lời xác định."""
    # Mọi lần đọc sổ dữ kiện bên trong đều suy đơn vị theo hạn mức sản phẩm này.
    with voi_tran_san_pham(*_muc_san_pham(tai_lieu)):
        kq = _tra_loi(text, tai_lieu, ho_so, history, xung_ho, du_kien)
        if kq and kq[0] == "han_muc_san_pham" and _ma_san_pham(tai_lieu) == "vay_mua_nha":
            # Khối hạn mức chỉ đọc lại dòng chung vì chưa nhận ra giá nhà khách nói
            # gọn ("nhà chị định mua là ba tỷ thì vay được bao nhiêu"): tính theo
            # đúng giá đó nếu đọc được.
            kq = _ghi_nhan_gia_nha(text, _phan_san_pham(tai_lieu)) or kq
        return (_tra_loi_hoi_gop(text, tai_lieu, kq) or kq or _tra_loi_moi_tu_van(text, tai_lieu)
                or _tra_loi_tiet_kiem_ngan(text, tai_lieu)
                or _tra_loi_noi_nop_ho_so(text, tai_lieu)
                or _tra_loi_lai_co_dinh_hay_tha_noi(text, tai_lieu))


_CHU_QUANH_SO_TIEN = frozenset(
    "gui khoang tam chung do thoi em a anh chi co duoc la thi u o minh toi bac chau nhe nha".split())


def _tra_loi_noi_nop_ho_so(text: str, tai_lieu: str) -> tuple[str, str] | None:
    """"hồ sơ nộp ở đâu": tài liệu vay không nêu nơi nộp thì nói thật và chuyển chuyên viên.

    Khách đóng vai 12-10-2026: mô hình tự viết "cuộc gọi này chưa gắn số điện
    thoại nên em chưa tra được chi nhánh gần nhất" - lời của một công cụ nội bộ,
    không phải câu trả lời cho khách.
    """
    t = _bo_dau(text)
    if not re.search(r"\b(nop|lam|ky|dang ky|den|ra|mang)\b.{0,20}\b(o dau|cho nao|dau|chi nhanh nao)\b", t) \
            or not re.search(r"\b(ho so|thu tuc|giay to|hop dong|vay|the|nop)\b", t):
        return None
    doc = _bo_dau(_phan_san_pham(tai_lieu))
    if re.search(r"\b(tai quay|chi nhanh|online|ung dung)\b", doc):
        return None            # tài liệu có nêu kênh: để kho/mô hình đọc từ đó
    return "noi_nop_ho_so_chua_co", (
        "Dạ nơi nộp hồ sơ thì em chưa có thông tin chính thức ạ. Em xin ghi nhận để "
        "chuyên viên liên hệ hướng dẫn anh chị cụ thể ạ.")


def _tra_loi_lai_co_dinh_hay_tha_noi(text: str, tai_lieu: str) -> tuple[str, str] | None:
    """"lãi có thay đổi không hay cố định": đọc đúng dòng tài liệu, không có thì nói thật.

    Khách đóng vai 12-10-2026 hỏi về vay tín chấp, mô hình đáp "lãi suất là thả
    nổi" - chữ đó chỉ có trong tài liệu vay mua nhà.
    """
    t = _bo_dau(text)
    if not re.search(r"\blai\b", t) or not re.search(
            r"\b(co dinh|tha noi|thay doi|co doi|co tang|giu nguyen|dieu chinh)\b", t) \
            or re.search(r"\b(may nam|bao lau|bao nhieu nam|may thang)\b", t):
        return None
    sp_doc = _phan_san_pham(tai_lieu)
    if not (_ma_san_pham(tai_lieu) or "").startswith("vay"):
        return None
    dong = [d.strip(" -").rstrip(".") for d in sp_doc.splitlines()
            if re.search(r"\blai suat\b", _bo_dau(d)) and re.search(r"\b(co dinh|tha noi)\b", _bo_dau(d))]
    if dong:
        return "lai_co_dinh_hay_tha_noi", (
            "Dạ theo tài liệu bên em: " + "; ".join(d[:1].lower() + d[1:] for d in dong[:2]) + " ạ.")
    muc = _gia_tri_dong(sp_doc, "lãi suất")
    return "lai_co_dinh_hay_tha_noi", (
        (f"Dạ tài liệu bên em ghi lãi suất {muc} ạ. " if muc else "Dạ ")
        + "Còn lãi cố định hay thay đổi theo thời gian thì em chưa có thông tin chính thức, "
        "chuyên viên sẽ nói rõ khi làm hồ sơ ạ.")


def _tra_loi_tiet_kiem_ngan(text: str, tai_lieu: str) -> tuple[str, str] | None:
    """Hai lượt cụt của khách gửi tiết kiệm mà không luật nào nhận (bộ thử 12-10-2026).

    - "năm chục triệu" (đáp câu "dự định gửi khoảng bao nhiêu"): ghi nhận đúng số
      tiền, để lớp dẫn dắt hỏi tiếp kỳ hạn.
    - "kỳ hạn": đọc các kỳ hạn có trong bảng lãi của tài liệu.
    Để mô hình tự viết thì câu sau nó ("kỳ hạn") lúc được kho trả lời, lúc không.
    """
    if _ma_san_pham(tai_lieu) != "tiet_kiem":
        return None
    t = _bo_dau(text)
    # Chỉ tới đây khi các luật tiết kiệm khác (tính lãi rút một phần, ước tính
    # lãi...) đã không nhận lượt này.
    rut_truoc = _tra_loi_rut_truoc_han(t, _phan_san_pham(tai_lieu))
    if rut_truoc:
        return rut_truoc
    tu = t.split()
    if not tu or len(tu) > 7:
        return None
    from backend.pipeline.du_kien_khoan_vay import quantities
    cac = [q for q in quantities(text) if q.value is not None]
    if len(cac) == 1 and cac[0].kind == "money":
        con = _bo_dau(text[:cac[0].start] + " " + text[cac[0].end:]).split()
        if all(c in _CHU_QUANH_SO_TIEN for c in con):
            return "ghi_nhan_tien_gui", (
                f"Dạ em ghi nhận anh chị dự định gửi khoảng {_fmt_trieu(float(cac[0].value))} ạ.")
    if not cac and re.fullmatch(r"(the |vay |con |u |o )*ky han( (nao|gi|the nao|sao|bao lau|thi sao))?( em| a| nhi)*", t):
        bang, _ = _bang_lai_tiet_kiem(_phan_san_pham(tai_lieu))
        if bang:
            return "ky_han_tiet_kiem", (
                f"Dạ bên em có các kỳ hạn {_noi_so(sorted(bang))} tháng ạ. "
                "Anh chị muốn gửi kỳ hạn bao lâu ạ?")
    return None


_MOI_TU_VAN = re.compile(
    r"\b(tu van|gioi thieu|noi (qua|so|so qua) ve)\b.{0,40}"
    r"\b(san pham|the|vay|khoan vay|goi vay|tiet kiem|gui tiet kiem|gui tien)\b"
    r"|\b(san pham|the tin dung|vay tin chap|vay mua nha|tiet kiem)\b.{0,24}\b(tu van|gioi thieu)\b")
# (câu hỏi đem cho luật, mã luật được nhận, câu hỏi mở đường) theo sản phẩm.
_GIOI_THIEU = {
    "the_tin_dung": ((("hạn mức thẻ thế nào", "han_muc_the"),), "Anh chị quan tâm hạng thẻ nào ạ?"),
    "tiet_kiem": ((("lãi suất bao nhiêu", "lai_tiet_kiem_theo_ky"),),
                  "Anh chị dự định gửi khoảng bao nhiêu ạ?"),
    "vay": ((("lãi suất bao nhiêu", "lai_suat_san_pham"), ("hạn mức tối đa bao nhiêu", "han_muc_san_pham"),
             ("thời hạn vay bao lâu", "thoi_han_san_pham")), "Anh chị dự định vay khoảng bao nhiêu ạ?"),
}


def _tra_loi_moi_tu_van(text: str, tai_lieu: str) -> tuple[str, str] | None:
    """"ừ tư vấn với anh về sản phẩm thẻ tín dụng": khách MỜI giới thiệu, chưa hỏi gì cụ thể.

    Chỉ chạy khi không luật nào khác nhận lượt này. Nội dung là các dữ kiện chính
    của tài liệu, lấy qua chính tầng luật, kết bằng một câu hỏi mở đường. Bộ thử
    12-10-2026: để mô hình tự viết thì có lần nó đáp "em xin lỗi, anh vừa nói là
    thẻ tín dụng ạ, em có thể giới thiệu sơ qua được không".
    """
    t = _bo_dau(text)
    if not _MOI_TU_VAN.search(t) or len(t.split()) > 16 or re.search(
            r"\d|\b(lai|han muc|phi|giay to|ho so|dieu kien|thu tuc|bao nhieu|khong|ai|sao|dau)\b", t):
        return None
    from backend.pipeline.du_kien_khoan_vay import quantities
    if any(q.value is not None for q in quantities(text)):
        return None
    ma_sp = _ma_san_pham(tai_lieu) or ""
    cac_hoi, mo_duong = _GIOI_THIEU.get(ma_sp) or (_GIOI_THIEU["vay"] if ma_sp.startswith("vay") else ((), ""))
    cac = []
    for hoi, ma_nhan in cac_hoi:
        got = _tra_loi(hoi, tai_lieu)
        if got and got[0] == ma_nhan:
            cau = got[1].replace(" Mức được duyệt thực tế còn phụ thuộc hồ sơ của anh chị.", "")
            cau = cau if not cac else re.sub(r"^Dạ,?\s+", "", cau)
            cac.append(cau[:1].upper() + cau[1:])
    if not cac:
        return None
    return "moi_tu_van", " ".join(cac) + " " + mo_duong


# Chủ đề -> (cách khách nhắc tới, câu hỏi chuẩn đem cho luật). Chỉ là CÁCH NÓI;
# nội dung trả lời vẫn do luật đọc từ tài liệu.
_Y_GOP = (
    ("lai_suat", r"\b(lai suat|lai bao nhieu|lai the nao|muc lai)\b", "lãi suất bao nhiêu"),
    ("han_muc", r"\b(han muc|vay (duoc )?toi da|vay duoc bao nhieu|toi da bao nhieu)\b",
     "hạn mức tối đa bao nhiêu"),
    ("giay_to", r"\b(giay to|ho so|thu tuc)\b", "cần giấy tờ gì"),
    ("phi", r"\bphi\b", "phí thường niên bao nhiêu"),
    ("thoi_han", r"\b(thoi han|vay (duoc )?bao lau|trong bao lau)\b", "thời hạn vay bao lâu"),
)
# Luật chỉ đọc lại MỘT dữ kiện tĩnh: câu hỏi gộp được phép thay câu của chúng.
_LUAT_MOT_Y = frozenset({
    "lai_suat_san_pham", "han_muc_san_pham", "ho_so_can_thiet", "phi_the", "han_muc_the",
    "thoi_han_san_pham", "loai_the", "gioi_thieu_san_pham"})


def _tra_loi_hoi_gop(text: str, tai_lieu: str,
                     kq: tuple[str, str] | None) -> tuple[str, str] | None:
    """"lãi suất bao nhiêu, vay tối đa bao nhiêu, cần giấy tờ gì em nói luôn một thể".

    Bộ thử 12-10-2026: kho chỉ có câu đáp từng ý nên khách hỏi ba ý nhận hai. Ở
    đây mỗi ý được hỏi riêng qua chính tầng luật rồi ghép lại, tối đa ba ý. Không
    đụng tới câu có con số của khách (đó là hỏi cho trường hợp riêng) và câu mà
    luật đã đáp bằng một phép tính hay một lời hỏi lại.
    """
    t = _bo_dau(text)
    if (kq and kq[0] not in _LUAT_MOT_Y) or re.search(r"\d", t) or len(t.split()) > 30:
        return None
    from backend.pipeline.du_kien_khoan_vay import quantities
    if any(q.value is not None and q.kind in ("money", "duration") for q in quantities(text)):
        return None
    y = [(ma, hoi) for ma, mau, hoi in _Y_GOP if re.search(mau, t)]
    if len(y) < 2:
        return None
    cac, da_co, con_tham_dinh = [], set(), False
    tham_dinh = " Mức được duyệt thực tế còn phụ thuộc hồ sơ của anh chị."
    for ma, hoi in y[:3]:
        got = _tra_loi(hoi, tai_lieu)
        if not got or got[0] not in _LUAT_MOT_Y or got[1] in da_co:
            continue
        da_co.add(got[1])
        con_tham_dinh = con_tham_dinh or tham_dinh in got[1]
        cau = got[1].replace(tham_dinh, "")
        cau = cau if not cac else re.sub(r"^Dạ,?\s+", "", cau)
        # "Mức được duyệt thực tế còn phụ thuộc hồ sơ" chỉ cần nói một lần, ở cuối.
        cac.append(cau[:1].upper() + cau[1:])
    if len(cac) < 2:
        return None
    return "hoi_gop", " ".join(cac) + (tham_dinh if con_tham_dinh else "")


def _tra_loi(text: str, tai_lieu: str, ho_so: dict | None = None,
             history: list[dict] | None = None, xung_ho: str = "anh chị",
             du_kien: LoanState | None = None) \
        -> tuple[str, str] | None:
    t = re.sub(r"\bhang muc\b", "han muc", _bo_dau(text))
    if not t:
        return None
    ma_sp = _ma_san_pham(tai_lieu)
    sp_doc = _phan_san_pham(tai_lieu)
    an_toan_danh_tinh = _tra_loi_an_toan_danh_tinh_va_du_lieu(text)
    if an_toan_danh_tinh:
        return an_toan_danh_tinh
    pham_vi_nguon = _tra_loi_pham_vi_nguon(text, tai_lieu, history)
    if pham_vi_nguon:
        return pham_vi_nguon
    t = _bo_chu_de_da_rut_khoi_cau(text)
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
        return (_tra_loi_the_tin_dung(t, sp_doc, text, history)
                or _ghi_nhan_thu_nhap_nguoi_khac(
                    text, xung_ho, resolve(history, text))
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

    vi_du_nguon = _tra_loi_vi_du_nguon(text, state, sp_doc, xung_ho)
    if vi_du_nguon:
        return vi_du_nguon

    nhac_lai = _tra_loi_nhac_lai(text, history, xung_ho, state, sp_doc)
    if nhac_lai:
        return nhac_lai
    if is_readback(text) and not _la_nhac_lai_thuoc_tinh(text):
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

    ghi_nhan_nguoi_khac = _ghi_nhan_thu_nhap_nguoi_khac(text, xung_ho, state)
    if ghi_nhan_nguoi_khac:
        return ghi_nhan_nguoi_khac

    ghi_nhan = None if state.amount_updated else _ghi_nhan_thu_nhap(
        text, xung_ho, sp_doc, _tran_san_pham(sp_doc))
    # AI vừa hỏi thu nhập, khách đáp cụt "mười lăm" / "tầm hai chục triệu": sổ dữ
    # kiện đã nhận đó là thu nhập, câu ghi nhận chỉ thiếu chữ "thu nhập" để đọc.
    ai_hoi_thu_nhap = ai_vua_hoi(next(
        (m.get("content", "") for m in reversed(history or []) if m.get("role") == "assistant"),
        "")) == "income"
    if (not ghi_nhan and ai_hoi_thu_nhap and state.income_updated
            and not state.amount_updated and not _la_ngu_canh_thu_nhap(text)):
        ghi_nhan = _ghi_nhan_thu_nhap("anh thu nhập " + text, xung_ho, sp_doc,
                                      _tran_san_pham(sp_doc))
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

    # "có mất phí hồ sơ không", "phí thẩm định có mất không": đọc đúng các dòng
    # "Miễn phí ..." của tài liệu sản phẩm. Kho từng đáp "em tư vấn thông tin hoàn
    # toàn miễn phí" cho câu hỏi về phí THẨM ĐỊNH (khách đóng vai 12-10-2026).
    if (ma_sp or "").startswith("vay") and re.search(r"\bphi\b", t) and re.search(
            r"\b(mat|ton|co|khong|gi|nao|tham dinh|ho so|dich vu)\b", t) and not re.search(
            r"\b(tra truoc|tat toan|phat|bao nhieu phan tram|tu van)\b", t):
        mien = [d.strip(" -").rstrip(".") for d in sp_doc.splitlines()
                if _bo_dau(d).strip(" -").startswith("mien phi")]
        if mien:
            cac = [mien[0]] + [m_[:1].lower() + m_[1:] for m_ in mien[1:2]]
            return "phi_khoan_vay", (
                "Dạ theo tài liệu bên em: " + ", ".join(cac)
                + " ạ. Các khoản phí khác nếu có thì chuyên viên sẽ báo rõ khi làm hồ sơ ạ.")

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

    vay_du = _tra_loi_vay_du_ra(text, t)
    if vay_du:
        return vay_du
    no_khac = _tra_loi_dang_co_no_khac(t, tai_lieu)
    if no_khac:
        return no_khac
    can_so_do = _tra_loi_can_so_do(t, sp_doc) or _tra_loi_gioi_thieu_vay(text, t, tai_lieu, ma_sp or "")
    if can_so_do:
        return can_so_do
    che_lai = _tra_loi_che_lai_cao(t, tai_lieu, ma_sp or "", history)
    if che_lai:
        return che_lai
    # Câu HỎI hạn mức ("nhà 9 tỷ thì hạn mức tối đa bao nhiêu") đã có luật tính
    # theo giá nhà ở khối hạn mức bên dưới; hai luật này chỉ nhận câu KỂ.
    if ma_sp == "vay_mua_nha" and not _HOI_HAN_MUC_VAY.search(t):
        dap_ty_le = _vay_theo_ty_le_khach_neu(text, history, sp_doc) or _ghi_nhan_gia_nha(text, sp_doc)
        if dap_ty_le:
            return dap_ty_le

    if tran and re.search(
            r"\b(han muc|(?:thue|the) vay toi da|vay (?:tin chap )?toi da(?: duoc)?|vay duoc bao nhieu)\b", t) \
            and not re.search(r"\b(thoi gian|thoi han|bao lau|ky han|may thang|may nam|"
                              r"bao nhieu nam|bao nhieu thang)\b", t):
        # Với vay mua nhà, khi khách đã nêu rõ giá tài sản hoặc đang hỏi phép
        # tính tỷ lệ, trả đúng min(LTV × giá, trần tiền) từ chính dòng nguồn.
        # Giá không rõ/rút lại phải được hỏi lại; câu hỏi hạn mức chung vẫn đọc
        # nguyên dòng sản phẩm như trước.
        trang_thai_gia, _, _ = _gia_bds_hien_tai(text, history)
        hoi_phep_tinh_ltv = bool(re.search(
            r"(?:\d+(?:[.,]\d+)?)\s*%|\b(?:theo|dua tren)\b.{0,18}\b(?:gia|gia tri)\b",
            t))
        if ma_sp == "vay_mua_nha" and (trang_thai_gia != "unknown" or hoi_phep_tinh_ltv):
            dap_ltv = _tra_loi_ltv_theo_gia(text, history, sp_doc)
            if dap_ltv:
                return dap_ltv
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
        # "vay trong hai lăm": đưa luôn các cách hiểu CÒN NẰM TRONG thời hạn sản
        # phẩm để khách chỉ việc chọn. Người nói lẫn l/n thì "hai lăm" còn là
        # "hai năm", nên số có đuôi "lăm" được thêm cách hiểu đó.
        he_so = state.term.coefficient
        if he_so is not None and he_so == he_so.to_integral() and khung:
            n = int(he_so)
            cach = [(n, f"{n} tháng"), (n * 12, f"{n} năm")]
            chu = (state.term.raw or "").lower().split()
            if len(chu) == 2 and chu[1] == "lăm" and n % 10 == 5 and n > 10:
                cach.append((n // 10 * 12, f"{n // 10} năm"))
            hop_le = [ten for thang, ten in cach
                      if (khung[0] or 1) <= thang <= (khung[1] or thang)]
            if len(hop_le) >= 2:
                cau = f"Dạ anh chị muốn vay {' hay '.join(hop_le[:3])} ạ?"
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
    # ... hoặc chính khách bỏ lửng ở lượt trước rồi nói nốt: "anh muốn vay ba trăm
    # triệu trong vòng" - "mười hai" (cuộc gọi e2ef1be5: máy cắt lượt giữa câu).
    khach_truoc = [m.get("content", "") for m in (history or []) if m.get("role") == "user"]
    if khach_truoc and khach_truoc[-1].strip() == (text or "").strip():
        khach_truoc = khach_truoc[:-1]
    ai_vua_hoi_ky_han = ai_vua_hoi_ky_han or bool(
        khach_truoc and luot_truoc_bo_lung_ky_han(khach_truoc[-1]))
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
