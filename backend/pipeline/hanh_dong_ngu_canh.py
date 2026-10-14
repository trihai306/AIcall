"""Chọn HÀNH ĐỘNG nối sau câu trả lời theo NGỮ CẢNH cuộc gọi, không theo phiếu.

Bên A gửi bảng mẫu 13-10-2026 (Khách | Mình | Context | Action). Mỗi lượt gồm:
một câu trả lời thật ngắn, rồi một hành động chọn theo những gì khách đã lộ ra
trong cuộc:

    khách đang hỏi thông tin (quan tâm)  -> ĐỒNG TÌNH + HỎI  "Anh đã từng vay tín chấp chưa ạ?"
    khách chê (cao thế, thấp thế, rườm rà) -> TRẤN AN + HỎI    nêu một điểm lợi rồi hỏi

Trước đó lớp dẫn dắt hỏi theo chuỗi cố định số tiền -> kỳ hạn -> thu nhập bất
kể khách vừa nói gì; cuộc gọi thật 13-10 nghe như điền phiếu.

Tệp này KHÔNG mang dữ kiện ngân hàng: câu trấn an đọc từ chính dòng tài liệu
sản phẩm (mục ưu đãi, dòng giải ngân), tài liệu không có thì chỉ còn câu hỏi.
Các câu trong bảng của bên A như "thuộc top lãi thấp" là chữ minh hoạ, không
dùng vì tài liệu không nói vậy.
"""
from __future__ import annotations

import re
import unicodedata

# Mã luật được BỎ LỜI RÀO lặp lại ở mọi lượt ("hạn mức thực tế vẫn cần thẩm định
# theo hồ sơ", "bên em cho vay từ 12 đến 60 tháng"). Chỉ bỏ đúng những câu khớp
# `_LOI_RAO`: bản đầu giữ mỗi câu đầu nên cắt luôn cả câu hỏi chốt thời hạn và
# câu xác nhận số tiền đứng sau (bộ 156 lượt, 13-10-2026).
GON_LOI_RAO = frozenset({
    "han_muc_san_pham", "nhu_cau_vay", "ky_han_trong_khung", "phi_khoan_vay",
})
_LOI_RAO = re.compile(
    r"^(ben em cho vay (toi da|tu|dai nhat)|muc duoc duyet|cac khoan phi khac)")
_DUOI_RAO = re.compile(r",\s*còn hạn mức thực tế thì cần thẩm định theo hồ sơ", re.IGNORECASE)


def _bo_dau(text: str) -> str:
    s = unicodedata.normalize("NFD", (text or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"[^a-z0-9%]+", " ", s).strip()


_CHE = re.compile(
    r"\b(cao|dat|nhieu|thap|it|lau|cham|kho|phuc tap|ruom ra|lang nhang|nhieu khe)"
    r"\s+(the|vay|qua|ghe|du|nhi|phet|that)\b|"
    r"\b(cat co|chat chem|qua cao|qua thap|qua it|qua lau|co the thoi|duoc co the|chi the thoi)\b")
_CHU_DE = (
    # "lãi" xét trên chữ CÒN DẤU ở `chu_de`: bỏ dấu thì "tính lại" cũng thành "lai".
    ("lai", re.compile(r"\blai suat\b|phan tram|% (mot )?nam")),
    ("han_muc", re.compile(r"han muc|toi da|vay duoc bao nhieu|duoc bao nhieu|cho vay")),
    ("thu_tuc", re.compile(r"thu tuc|ho so|giay to|cmnd|cccd|sao ke|giai ngan|bao lau thi|may ngay")),
    ("phi", re.compile(r"\bphi\b")),
    ("uu_dai", re.compile(r"uu dai|hoan tien|cashback|tich diem|khuyen mai|qua tang")),
    ("dieu_kien", re.compile(r"dieu kien|co vay duoc khong|vay duoc khong")),
)
_THEO_LUAT = {"che_phi": "phi", "che_lai_thap": "lai", "phan_hoi_lai_thap": "lai", "phi_the": "phi", "han_muc_the": "han_muc",
              "lai_tiet_kiem_theo_ky": "lai", "che_han_muc": "han_muc", "che_thu_tuc": "thu_tuc", "che_lai_cao": "lai", "lai_suat_san_pham": "lai", "han_muc_san_pham": "han_muc",
              "ho_so_can_thiet": "thu_tuc", "phi_khoan_vay": "phi"}


def dang_che(loi_khach: str) -> bool:
    return bool(_CHE.search(_bo_dau(loi_khach)))


def chu_de(loi_khach: str, cau_ai_truoc: str = "", ma_luat: str = "") -> str:
    """Khách đang nói về gì: lời khách trước, rồi mã luật, rồi câu AI vừa nói."""
    def _tim(goc: str) -> str:
        if re.search(r"\blãi\b", unicodedata.normalize("NFC", (goc or "").lower())):
            return "lai"
        t_ = _bo_dau(goc)
        return next((ten for ten, mau in _CHU_DE if mau.search(t_)), "")
    cd = _tim(loi_khach)
    if cd:
        return cd
    if ma_luat in _THEO_LUAT:
        return _THEO_LUAT[ma_luat]
    # Chỉ xét phần KHẲNG ĐỊNH của câu AI: câu hỏi nối ở đuôi ("đang cần khoảng bao
    # nhiêu ạ?") nói về ý kế tiếp, không phải điều khách đang chê.
    return _tim(" ".join(c for c in re.split(r"(?<=[.?!])\s+", cau_ai_truoc or "")
                         if not c.strip().endswith("?")))


def ngu_canh(lich_su: list[dict] | None, loi_khach: str) -> dict:
    """Ba cờ của cột Context trong bảng: đã biết sản phẩm, quan tâm, chê."""
    khach = [m.get("content", "") for m in (lich_su or []) if m.get("role") == "user"] + [loi_khach or ""]
    ai = [m.get("content", "") for m in (lich_su or []) if m.get("role") == "assistant"]
    return {
        "da_biet_sp": len(ai) >= 2,          # lời chào + ít nhất một câu về sản phẩm
        "quan_tam": any(chu_de(k) for k in khach),
        "che": dang_che(loi_khach),
    }


def _dong(tai_lieu: str, mau: str) -> str:
    for d in (tai_lieu or "").splitlines():
        if re.search(mau, _bo_dau(d)):
            return re.sub(r"^[\s\-*•]+", "", d).strip().rstrip(".")
    return ""


_HOI_DUNG_THE = ("dt_dang_dung_the", "Anh chị đang dùng thẻ tín dụng nào chưa ạ?")
_HOI_CHI_TIEU = ("dt_chi_tieu", "Mỗi tháng anh chị chi tiêu qua thẻ khoảng bao nhiêu ạ?")
_HOI_GUI_O_DAU = ("dt_gui_o_dau", "Anh chị đang gửi tiết kiệm ở đâu chưa ạ?")
_HOI_KENH_GUI = ("dt_kenh_gui", "Anh chị quen giao dịch trên điện thoại hay ra quầy ạ?")


def _tran_an_the(cd: str, tai_lieu: str) -> tuple[str, str, str] | None:
    if cd == "phi":
        d = _dong(tai_lieu, r"^\W*mien phi thuong nien")
        return (f"Bên em đang {d[:1].lower()}{d[1:]} ạ." if d else "", *_HOI_DUNG_THE)
    if cd == "han_muc":
        return ("", *_HOI_CHI_TIEU)
    return None


def _tran_an_tiet_kiem(cd: str, tai_lieu: str) -> tuple[str, str, str] | None:
    if cd == "lai":
        d = _dong(tai_lieu, r"^\W*lai suat cong them")
        return (f"Gửi online thì {d[:1].lower()}{d[1:]} ạ." if d else "", *_HOI_KENH_GUI)
    return None


def _tran_an(cd: str, tai_lieu: str) -> tuple[str, str, str] | None:
    """(lời trấn an đọc từ tài liệu, mã câu hỏi, câu hỏi)."""
    if cd == "lai":
        d = _dong(tai_lieu, r"^\W*giam\b.*lai")
        if d and "luong qua ngan hang" in _bo_dau(d):
            return (f"Bên em đang {d[:1].lower()}{d[1:]} ạ.", "ta_luong_qua_nh",
                    "Anh chị có đang nhận lương qua ngân hàng không ạ?")
        if d:
            return f"Bên em đang {d[:1].lower()}{d[1:]} ạ.", "so_tien", "Anh chị đang cần khoảng bao nhiêu ạ?"
        return "", "so_tien", "Anh chị đang cần khoảng bao nhiêu ạ?"
    if cd == "han_muc":
        return "", "so_tien", "Anh chị đang cần khoảng bao nhiêu ạ?"
    if cd in ("thu_tuc", "dieu_kien"):
        d = _dong(tai_lieu, r"^\W*giai ngan\b")
        m = re.search(r":\s*(.+)$", d)
        loi = f"Hồ sơ đủ thì bên em giải ngân {m.group(1).strip()} ạ." if m else ""
        return loi, "dt_nghe", "Anh chị đang đi làm hưởng lương hay tự kinh doanh ạ?"
    return None


def _dong_tinh(cd: str, ma_san_pham: str) -> tuple[str, str] | None:
    if ma_san_pham == "the_tin_dung":
        if cd in ("phi", "uu_dai", "lai"):
            return _HOI_DUNG_THE
        return _HOI_CHI_TIEU if cd == "han_muc" else None
    if ma_san_pham == "tiet_kiem":
        if cd == "lai":
            return _HOI_GUI_O_DAU
        return _HOI_KENH_GUI if cd == "thu_tuc" else None
    if cd == "lai":
        if ma_san_pham == "vay_tin_chap":
            return "dt_tung_vay", "Anh chị đã từng vay tín chấp bao giờ chưa ạ?"
        return "dt_chon_nha", "Anh chị đã chọn được căn nhà nào chưa ạ?"
    if cd == "han_muc":
        return "so_tien", "Anh chị đang cần khoảng bao nhiêu ạ?"
    if cd in ("thu_tuc", "dieu_kien"):
        return "dt_nghe", "Anh chị đang đi làm hưởng lương hay tự kinh doanh ạ?"
    return None


def hanh_dong(*, ma_san_pham: str, tai_lieu: str, lich_su: list[dict] | None,
              loi_khach: str, da_hoi: set[str], da_biet_so_tien: bool,
              ma_luat: str = "") -> tuple[str, str, str, str] | None:
    """`(kiểu, mã, lời nối, riêng câu hỏi)` với kiểu là "tran_an" hoặc "dong_tinh";
    None thì để lớp dẫn dắt cũ quyết định. Mỗi mã chỉ dùng một lần mỗi cuộc.
    "Riêng câu hỏi" để người gọi lùi về khi cả lời trấn an thì quá dài."""
    if not (ma_san_pham.startswith("vay") or ma_san_pham in ("the_tin_dung", "tiet_kiem")):
        return None
    if (ma_luat or "").startswith(("tinh_", "uoc_tinh")):
        return None            # câu vừa tính ra con số đã dài: không chèn lời trấn an hay câu hỏi
    la_vay = ma_san_pham.startswith("vay")
    ai_truoc = next((m.get("content", "") for m in reversed(lich_su or [])
                     if m.get("role") == "assistant"), "")
    nc = ngu_canh(lich_su, loi_khach)
    # Câu AI vừa nói chỉ dùng để hiểu lời CHÊ trơ trọi ("cao thế"). Lượt thường
    # mà cũng suy chủ đề từ đó thì khách nói số tiền lại bị hỏi chuyện lãi.
    cd = chu_de(loi_khach, ai_truoc if nc["che"] else "", ma_luat)
    if not cd:
        return None
    if nc["che"]:
        ta = (_tran_an(cd, tai_lieu) if la_vay
              else _tran_an_the(cd, tai_lieu) if ma_san_pham == "the_tin_dung"
              else _tran_an_tiet_kiem(cd, tai_lieu))
        if not ta:
            return None
        loi, ma, hoi = ta
        if ma in da_hoi or (ma == "so_tien" and da_biet_so_tien):
            # Câu hỏi của chủ đề này đã dùng: còn lời trấn an thì nói riêng nó,
            # không thì hỏi mục đích vay - thứ chưa hỏi và hợp với mọi lời chê.
            if loi and f"ta_{cd}" not in da_hoi:
                return "tran_an", f"ta_{cd}", loi, ""
            if la_vay and "dt_muc_dich" not in da_hoi:
                hoi = "Anh chị định dùng khoản này vào việc gì ạ?"
                return "tran_an", "dt_muc_dich", hoi, hoi
            return None
        return "tran_an", ma, f"{loi} {hoi}".strip(), hoi
    if ma_san_pham == "tiet_kiem" and cd == "lai" and not da_biet_so_tien:
        return None            # chưa biết gửi bao nhiêu: hỏi số tiền (chuỗi cũ) có ích hơn
    dt = _dong_tinh(cd, ma_san_pham)
    if not dt or dt[0] in da_hoi or (dt[0] == "so_tien" and da_biet_so_tien):
        return None
    return "dong_tinh", dt[0], dt[1], dt[1]


def cau_dau(cau: str) -> str:
    """Câu đầu của `cau`. Dấu chấm trong số ("7.9%") không tính là hết câu."""
    m = re.search(r"[.?!](?=\s)", cau or "")
    return cau[:m.end()] if m else cau


def gon_cau(ma_luat: str, cau: str) -> str:
    """Bỏ lời rào khỏi câu trả lời của luật; `che_lai_cao` chỉ giữ lời nhận vì
    phần sau do lời trấn an của lớp hành động thay."""
    if not cau:
        return cau
    if ma_luat == "che_lai_cao":
        return cau_dau(cau)
    if ma_luat not in GON_LOI_RAO:
        return cau
    giu = [c for c in re.split(r"(?<=[.?!])\s+", cau)
           if c.strip().endswith("?") or not _LOI_RAO.match(_bo_dau(c))]
    return _DUOI_RAO.sub("", " ".join(giu)) if giu else cau


# Khách TRẢ LỜI câu hỏi của lớp hành động. Không có khối này thì lượt đó rơi
# xuống mô hình, và mô hình hứa bừa: "anh đã từng vay thì bên em sẽ ưu tiên
# xem xét hồ sơ" (chạy thử 13-10-2026).
_HOI_TUNG_VAY = "da tung vay tin chap bao gio chua"
_HOI_LUONG_QUA_NH = "nhan luong qua ngan hang khong"
_HOI_NGHE = "di lam huong luong hay tu kinh doanh"
_HOI_MUC_DICH = "dinh dung khoan nay vao viec gi"


def dap_cau_hoi_hanh_dong(loi_khach: str, cau_ai_truoc: str,
                          ai_ca_cuoc: str = "") -> tuple[str, str] | None:
    t, ai = _bo_dau(loi_khach), _bo_dau(cau_ai_truoc)
    if dang_che(loi_khach):
        return None             # "đắt thế" sau một câu hỏi bắt chuyện là lời chê, không phải câu trả lời
    # "rồi anh từng vay rồi" nói MUỘN một lượt, khi AI đã hỏi sang chuyện lương:
    # vẫn là câu trả lời cho câu hỏi đã từng vay. Để rơi xuống mô hình thì nó ghép
    # bừa hai ý: "đã từng vay thì bên em giảm thêm 0.5% lãi suất" (chạy thử 13-10).
    if (_HOI_TUNG_VAY in _bo_dau(ai_ca_cuoc) and len(t.split()) <= 8
            and re.search(r"\b(tung vay|vay roi|da vay|chua vay|chua tung|chua bao gio vay)\b", t)
            and not re.search(r"\b(bao nhieu|the nao|gi|sao|duoc khong)\b", t)):
        ai = _HOI_TUNG_VAY
    # "chưa dùng thẻ nào", "không có cái nào": chữ "nào" ở đây là phủ định, không phải hỏi.
    t_hoi = re.sub(r"\b(chua|khong)\b(.{0,20})\bnao\b", r"\1\2", t)
    if not t or len(t.split()) > 10 or re.search(
            r"\b(bao nhieu|the nao|ra sao|gi|nao|sao|duoc khong|co duoc|may|"
            r"co .{0,20}(khong|hong|hok|ko|k))\b", t_hoi):
        return None             # khách hỏi lại chuyện khác: không phải câu trả lời
    if len(t.split()) >= 3 and t.endswith((" khong", " hong", " hok", " ko")) \
            and not t.startswith(("khong", "chua")):
        return None             # "thủ tục nhanh không": câu hỏi có/không
    phu = bool(re.search(r"\b(chua|khong|chang|deo|ko)\b", t))
    co = bool(re.search(r"\b(roi|co|tung|u|vang|da|dung)\b", t))
    if _HOI_TUNG_VAY in ai and (phu or co):
        return ("dap_tung_vay", "Dạ không sao ạ, em nói rõ từng phần để mình dễ nắm ạ." if phu
                else "Dạ vâng ạ, vậy mình cũng quen với cách vay này rồi ạ.")
    if _HOI_LUONG_QUA_NH in ai and "vay" not in t.split() and (
            phu or co or "chuyen khoan" in t or "tien mat" in t):
        la_khong = (phu or "tien mat" in t) and "chuyen khoan" not in t
        return ("dap_luong_qua_nh", "Dạ không sao ạ." if la_khong
                else "Dạ vâng ạ, ưu đãi đó áp dụng cho khách hàng nhận lương qua ngân hàng ạ.")
    if _HOI_NGHE in ai and re.search(
            r"\b(luong|cong ty|nha nuoc|van phong|cong nhan|kinh doanh|buon ban|tu do|lam thue|vien chuc)\b", t):
        return "dap_nghe", "Dạ vâng ạ."
    if _HOI_MUC_DICH in ai and not re.search(r"\b(trieu|ty|thang|nam)\b", t):
        return "dap_muc_dich", "Dạ vâng ạ."
    # Thẻ và tiết kiệm: khách đáp gọn câu hỏi bắt chuyện thì nhận lời rồi đi tiếp.
    # Câu hỏi chi tiêu KHÔNG ở đây: khách đáp bằng con số, đã có luật gợi ý hạng thẻ.
    if "giao dich tren dien thoai hay ra quay" in ai and re.search(
            r"\b(quay|khong biet dung|khong ranh|khong quen|khong dung dien thoai)\b", t):
        # Hình thức "gửi tại quầy" là mặc định của mọi sổ tiết kiệm; khách không
        # dùng điện thoại thì nói luôn cho họ yên tâm (đóng vai 13-10: chỉ "Dạ vâng ạ").
        return "dap_kenh_quay", "Dạ vâng ạ, mình ra quầy gửi cũng được ạ."
    for dau in ("dang dung the tin dung nao chua", "dang gui tiet kiem o dau chua",
                "giao dich tren dien thoai hay ra quay"):
        if dau in ai and not re.search(r"\b(trieu|ty|phan tram)\b", t):
            return "dap_hanh_dong", "Dạ vâng ạ."
    return None
