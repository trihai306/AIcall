"""Chặn câu nêu KÊNH LÀM VIỆC mà tài liệu không có (online, ứng dụng, Zalo...).

Lỗi thật 12-10-2026: khách hỏi "apply online được không" về thẻ tín dụng, kho
không có câu phù hợp, mô hình tự viết "Anh chị có thể nộp hồ sơ trực tuyến trên
ứng dụng hoặc website của ngân hàng ạ" - tài liệu thẻ không có chữ nào về nộp hồ
sơ online. Các lưới số không thấy vì câu không có con số.

Kênh nào ĐƯỢC nói là do tài liệu quyết định: tài liệu tiết kiệm ghi "gửi tại
quầy hoặc gửi online", "trên ứng dụng" nên với tiết kiệm hai kênh đó qua lưới;
với thẻ tín dụng thì không. Thứ duy nhất ghi cứng ở đây là CÁCH NÓI về kênh
trong tiếng Việt, không phải dữ liệu sản phẩm.

Bắt được thì bỏ đúng CÂU đó; bỏ hết mới dùng câu mẫu (cùng cách với
`thuoc_tinh.sua_theo_tai_lieu`, để không sinh lại lỗi "trả lời một kiểu").
"""

import re
import unicodedata

# nhóm kênh -> các cách nói (đã bỏ dấu). Một nhóm được phép khi tài liệu có BẤT
# KỲ cách nói nào của nhóm đó.
KENH = {
    "online": ("online", "truc tuyen", "qua mang", "website", "trang web", "tren web",
               "internet banking"),
    "ung_dung": ("ung dung", "app"),
    "mang_xa_hoi": ("zalo", "facebook", "messenger", "viber"),
    "tin_nhan": ("tin nhan", "sms"),
    "tan_noi": ("tai nha", "tan noi", "den tan nha", "den nha anh", "den nha chi"),
    "hotline": ("hotline", "tong dai"),
    "qua_dien_thoai": ("qua dien thoai",),
}
# Câu KHÔNG khẳng định kênh: nói chưa có/không có, hoặc chỉ nhắc lại lời khách.
_KHONG_KHANG_DINH = re.compile(
    r"\b(chua co thong tin|khong co thong tin|chua ro|chua ho tro|khong ho tro|"
    r"chua ap dung|khong ap dung|khong qua|khong gui|khong the gui|chua the|khong the|"
    r"khong yeu cau|khong can)\b")
# AI không gửi được gì cho khách: lời hứa gửi là bịa bất kể tài liệu.
_HUA_GUI = re.compile(
    r"\bem (se |xin |xin phep |da )*(gui|chuyen|nhan|email)\b[^.?!]{0,40}"
    r"\b(link|duong dan|file|bieu mau|hop dong|bang tinh|bao gia|"
    r"zalo|email|e mail|tin nhan|sms|qua ung dung|qua app)\b")
# "gửi thông tin" trong lời tư vấn thường chỉ là "nói cho nghe" nên không bắt;
# chỉ bắt khi có PHƯƠNG TIỆN gửi. Xin email/số điện thoại của khách cũng không
# phải nêu kênh làm thủ tục, nên email không nằm trong bảng KENH.

CAU_CHUA_CO_KENH = ("Dạ phần này em chưa có thông tin chính thức ạ. Em xin ghi nhận để "
                    "chuyên viên hướng dẫn anh chị cách thuận tiện nhất ạ.")


def _bo_dau(text: str) -> str:
    s = unicodedata.normalize("NFD", (text or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _co(tu: str, cau: str) -> bool:
    return f" {tu} " in f" {cau} "


def _khang_dinh(tu: str, cau: str) -> bool:
    """`cau` có nêu `tu` mà KHÔNG phủ định nó trong năm từ đứng ngay trước không.

    "chưa có số Zalo của anh", "qua app chưa phải là sao kê" đều nhắc tới kênh
    nhưng không bảo khách dùng kênh đó.
    """
    dem = f" {cau} "
    vt = dem.find(f" {tu} ")
    while vt >= 0:
        truoc = dem[:vt].split()[-5:]
        sau = dem[vt + len(tu) + 2:].split()[:3]
        if not ({"chua", "khong"} & set(truoc)) and sau[:2] not in (["chua", "phai"], ["khong", "phai"]):
            return True
        vt = dem.find(f" {tu} ", vt + 1)
    return False


def kenh_duoc_phep(tai_lieu: str) -> frozenset[str]:
    """Các nhóm kênh mà tài liệu có nhắc tới."""
    tl = _bo_dau(tai_lieu)
    return frozenset(nhom for nhom, cach in KENH.items() if any(_co(t, tl) for t in cach))


def kenh_la(cau: str, tai_lieu: str) -> list[str]:
    """Nhóm kênh `cau` KHẲNG ĐỊNH mà `tai_lieu` không có; kèm "hua_gui" nếu hứa gửi."""
    c = _bo_dau(cau)
    if not c:
        return []
    la: list[str] = []
    if _HUA_GUI.search(c) and not _KHONG_KHANG_DINH.search(c):
        la.append("hua_gui")
    if _KHONG_KHANG_DINH.search(c):
        return la
    duoc = kenh_duoc_phep(tai_lieu)
    la += [nhom for nhom, cach in KENH.items()
           if nhom not in duoc and any(_khang_dinh(t, c) for t in cach)]
    return la


def tach_cau(doan: str) -> list[str]:
    """Tách câu ở dấu kết câu CÓ khoảng trắng theo sau, giữ nguyên khoảng trắng.

    Tách ở mọi dấu chấm thì "lãi suất 7.9%/năm" và "500.000đ" bị bẻ đôi - lỗi của
    chính bản đầu tệp này, lộ ra khi soi 70 câu kho: "Dạ, lãi suất từ 7."
    """
    return [c for c in re.split(r"(?<=[.?!])(?=\s)", doan) if c.strip()]


def san_pham_bi_phu_nhan(cau: str, ten_san_pham: list[str]) -> str:
    """Tên sản phẩm CÓ tài liệu mà `cau` lại bảo là ngân hàng không có.

    Lỗi thật trong bộ thử 304 lượt: khách hỏi "vay tín chấp để đặt cọc được
    không", mô hình đáp "bên em chỉ hỗ trợ vay mua nhà chứ chưa có gói vay tín
    chấp". Sản phẩm nào có là do thư mục tài liệu quyết định, không ghi ở đây.
    """
    c = _bo_dau(cau)
    for ten in ten_san_pham:
        t = _bo_dau(ten.replace("_", " "))
        m = re.search(r"\b(chua co|khong co|chua ho tro|khong ho tro|chua trien khai|"
                      r"khong cung cap|chua cung cap)\b(?P<giua>[a-z0-9 ]{0,30}?)\b" + re.escape(t) + r"\b", c)
        # Giữa chữ phủ định và tên sản phẩm chỉ được có từ nối. "không có PHÍ mở
        # thẻ tín dụng" phủ định khoản phí, không phủ nhận sản phẩm.
        if m and re.fullmatch(r"( (goi|san pham|dich vu|loai|hinh thuc|chuong trinh|khoan|cac|rieng))* ?",
                              m.group("giua")):
            return ten
    return ""


def chan_phu_nhan_san_pham(doan: str, ten_san_pham: list[str]) -> tuple[str, str]:
    """Bỏ câu phủ nhận một sản phẩm đang có tài liệu. Cùng khuôn với `chan_kenh_la`."""
    if not ten_san_pham or not (doan or "").strip():
        return doan, ""
    giu, bo = [], []
    for c in tach_cau(doan):
        ten = san_pham_bi_phu_nhan(c, ten_san_pham)
        (bo if ten else giu).append((c, ten))
    if not bo:
        return doan, ""
    con = "".join(c for c, _ in giu).strip()
    mo_ta = "; ".join(f"phủ nhận {ten}: {c.strip()[:50]!r}" for c, ten in bo)
    return (con if len(_bo_dau(con).split()) >= 5 else CAU_CHUA_CO_KENH), mo_ta


def chan_kenh_la(doan: str, tai_lieu: str) -> tuple[str, str]:
    """Bỏ những câu nêu kênh ngoài tài liệu. Trả (đoạn đã sửa, mô tả) - mô tả rỗng
    là không đụng gì. Không có tài liệu thì KHÔNG phán: thiếu căn cứ để nói câu
    nào sai, và lượt chưa biết sản phẩm đã có đường riêng.
    """
    if not (tai_lieu or "").strip() or not (doan or "").strip():
        return doan, ""
    cau = tach_cau(doan)
    giu, bo = [], []
    for c in cau:
        la = kenh_la(c, tai_lieu)
        (bo if la else giu).append((c, la))
    if not bo:
        return doan, ""
    mo_ta = "; ".join(f"{'+'.join(la)}: {c.strip()[:50]!r}" for c, la in bo)
    con = "".join(c for c, _ in giu).strip()
    # Còn lại quá ngắn ("Dạ vâng ạ,") thì đọc lên như bỏ lửng: dùng câu mẫu.
    return (con if len(_bo_dau(con).split()) >= 5 else CAU_CHUA_CO_KENH), mo_ta
