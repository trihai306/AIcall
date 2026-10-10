"""Câu hỏi DẪN DẮT nối sau câu trả lời - thứ một tư vấn viên thật luôn làm.

VÌ SAO. Chấm 304 lượt (08-10-2026) bằng thang "trưởng nhóm tư vấn khó tính":
lỗi nhiều nhất không phải sai dữ kiện mà là BỎ SÓT Ý - 120/304 lượt. AI trả lời
đúng điều được hỏi rồi im, để khách tự nghĩ ra câu kế tiếp:

    khách "anh muốn vay khoảng ba trăm triệu"
    AI    "Dạ ... 300 triệu đồng đang nằm trong trần sản phẩm ..."        (hết)
    nên   "... Anh muốn vay trong bao lâu ạ?"

Lớp này KHÔNG mang dữ kiện ngân hàng nào: nó chỉ nhìn khách đã nói những gì (số
tiền, thời hạn, thu nhập - lấy từ `du_kien_khoan_vay.resolve`, tức chỉ từ lời
khách) rồi hỏi thứ còn thiếu kế tiếp. Vì thế nối được sau MỌI đường trả lời (luật,
kho, mô hình) mà không tạo thêm rủi ro bịa số.

BỐN RÀNG BUỘC, đừng nới:
  1. Mỗi ý chỉ hỏi MỘT lần mỗi cuộc. Khách lờ đi thì thôi, không nài.
  2. Câu trả lời đã kết bằng câu hỏi thì không nối thêm.
  3. Khách đang từ chối / bận / hẹn lại / chốt cuộc thì không hỏi.
  4. Câu trả lời + câu hỏi vượt `TOI_DA_TU` từ thì bỏ câu hỏi: nghe điện thoại
     không ai theo nổi một câu quá dài.
"""
from __future__ import annotations

import re

TOI_DA_TU = 42

# Thứ tự hỏi theo sản phẩm. Mỗi mục: (mã ý, câu hỏi).
_VAY = [
    ("so_tien", "Anh chị dự định vay khoảng bao nhiêu ạ?"),
    ("ky_han", "Anh chị muốn vay trong bao lâu ạ?"),
    ("thu_nhap", "Thu nhập hàng tháng của anh chị khoảng bao nhiêu ạ?"),
    ("ghi_nhan", "Anh chị có muốn em ghi nhận để chuyên viên hỗ trợ làm hồ sơ không ạ?"),
]
_THE = [
    ("thu_nhap", "Thu nhập hàng tháng của anh chị khoảng bao nhiêu ạ?"),
    ("ghi_nhan", "Anh chị có muốn em ghi nhận để chuyên viên hỗ trợ mở thẻ không ạ?"),
]
_TIET_KIEM = [
    ("so_tien", "Anh chị dự định gửi khoảng bao nhiêu ạ?"),
    ("ky_han", "Anh chị muốn gửi kỳ hạn bao lâu ạ?"),
]
THEO_SAN_PHAM = {
    "vay_tin_chap": _VAY, "vay_mua_nha": _VAY,
    "the_tin_dung": _THE, "tiet_kiem": _TIET_KIEM,
}

# Ý định của `luot_thuong_gap` mà sau đó KHÔNG được hỏi dồn.
KHONG_HOI_SAU = frozenset({
    "tu_choi", "dang_ban", "hen_lai", "sao_co_so", "sao_biet_ten", "ai_day",
    "danh_tinh_tu_dong", "danh_tinh_va_nguon",
    "chao_hoi", "chao_bat_may", "nghe_ro_khong", "moi_noi_tiep",
})

# Khách đang khép cuộc gọi hoặc gạt đi - nhìn trên chính lời khách.
# Từ chối/hẹn/bận do `y_dinh_dung_tu_van` ở dưới sở hữu vì cần xét phủ định,
# người thứ ba và thứ tự các vế; không dò lại các từ đó một cách mất ngữ cảnh.
_KHEP = re.compile(
    r"\b(cảm ơn|cám ơn|tạm biệt|thôi nhé|thôi em|lừa đảo)\b", re.IGNORECASE)

# Chính CÂU TRẢ LỜI đã khép cuộc hoặc hẹn chuyên viên: hỏi tiếp là tự mâu thuẫn.
# Bộ thử 10-10-2026: "em xin ghi nhận để bên em không liên hệ lại nữa ạ. Anh chị
# dự định vay khoảng bao nhiêu ạ?" và "em chào anh chị ạ. Anh chị muốn vay trong
# bao lâu ạ?".
_CAU_DA_KHEP = re.compile(
    r"em chào|tạm biệt|liên hệ lại|gọi lại|không làm phiền|không liên hệ"
    r"|khi nào (?:tiện|cần|có nhu cầu)", re.IGNORECASE)

# Khách đang kêu KHÔNG NGHE KỊP / xin nhắc lại: việc cần làm là nói lại, không
# phải hỏi sang ý mới.
_XIN_NOI_LAI = re.compile(
    r"\b(nói (?:nhanh|chậm|lại|to)|nhắc lại|không nghe (?:rõ|kịp|được|thấy)|nghe không (?:rõ|kịp))\b",
    re.IGNORECASE)

_CO_THU_NHAP = re.compile(r"\b(lương|thu nhập)\b", re.IGNORECASE)


def _khach_da_neu(loi_khach: str, loai: str) -> bool:
    """Khách đã nói ra một số tiền / một kỳ hạn ở đâu đó trong cuộc chưa."""
    from backend.pipeline.du_kien_khoan_vay import khoang_ky_han, quantities
    if loai == "duration" and khoang_ky_han(loi_khach or ""):
        return True
    return any(q.kind == loai and q.value for q in quantities(loi_khach or ""))


def _da_biet(ma: str, trang_thai, loi_khach: str, ma_san_pham: str = "") -> bool:
    # Gửi tiết kiệm không đi qua sổ dữ kiện KHOẢN VAY (nó chỉ nhận con số có chữ
    # "vay" neo trước): khách nói "gửi hai trăm triệu kỳ hạn sáu tháng" xong vẫn
    # bị hỏi lại "dự định gửi bao nhiêu / kỳ hạn bao lâu". Với tiết kiệm, số tiền
    # và kỳ hạn khách nói ra ở đâu trong cuộc cũng là của khoản gửi.
    if ma_san_pham == "tiet_kiem" and ma in ("so_tien", "ky_han"):
        if _khach_da_neu(loi_khach, "money" if ma == "so_tien" else "duration"):
            return True
    if ma == "so_tien":
        return trang_thai.amount.status != "unknown"
    if ma == "ky_han":
        return trang_thai.term.status != "unknown"
    if ma == "thu_nhap":
        return (trang_thai.income.status != "unknown"
                or bool(_CO_THU_NHAP.search(loi_khach or "")))
    return False


def cau_hoi_tiep(*, ma_san_pham: str, trang_thai, loi_khach_ca_cuoc: str,
                 loi_khach_luot_nay: str, cau_tra_loi: str, da_hoi: set[str],
                 y_dinh_thuong_gap: str = "", ma_luat: str = "",
                 vua_hoi: str = "") -> tuple[str, str] | None:
    """`(mã ý, câu hỏi)` để nối sau `cau_tra_loi`, hoặc None nếu không nên hỏi.

    `trang_thai` là `LoanState` dựng từ lời khách; `da_hoi` là các ý đã hỏi
    trong cuộc (người gọi tự thêm mã vào sau khi dùng câu hỏi); `vua_hoi` là ý
    đã hỏi ở lượt AI NGAY TRƯỚC, rỗng nếu lượt đó không hỏi gì.
    """
    buoc = THEO_SAN_PHAM.get(ma_san_pham)
    if not buoc:
        return None
    # Dùng cùng quyết định ưu tiên với tầng trả lời sẵn. Không phụ thuộc metrics
    # đã được streaming gắn kịp hay chưa, và phủ cả câu dài/ASCII.
    from backend.pipeline.luot_thuong_gap import y_dinh_dung_tu_van
    if y_dinh_dung_tu_van(loi_khach_luot_nay or ""):
        return None
    if "?" in (cau_tra_loi or ""):
        return None
    if y_dinh_thuong_gap in KHONG_HOI_SAU or ma_luat.startswith(
            ("kho_khong_co", "xac_nhan_", "thieu_du_kien", "vuot_han_muc")):
        return None
    if _KHEP.search(loi_khach_luot_nay or "") or _XIN_NOI_LAI.search(loi_khach_luot_nay or ""):
        return None
    if _CAU_DA_KHEP.search(cau_tra_loi or ""):
        return None
    # Lượt TRƯỚC vừa hỏi một ý mà khách chưa trả lời (họ hỏi lại chuyện khác):
    # lượt này không hỏi dồn sang ý kế tiếp. Bản đầu hỏi "vay bao nhiêu", khách
    # nói "vay tiêu dùng ấy", AI hỏi luôn "vay trong bao lâu" - nghe như máy
    # đọc danh sách. Lượt sau nữa mới hỏi tiếp.
    if vua_hoi and not _da_biet(vua_hoi, trang_thai, loi_khach_ca_cuoc, ma_san_pham):
        return None
    for ma, cau in buoc:
        if ma in da_hoi:
            continue
        if _da_biet(ma, trang_thai, loi_khach_ca_cuoc, ma_san_pham):
            continue
        if ma == "ghi_nhan" and len(da_hoi) == 0 and trang_thai.amount.status == "unknown":
            # Chưa trao đổi được gì mà đã mời làm hồ sơ là hối khách.
            return None
        if len((cau_tra_loi or "").split()) + len(cau.split()) > TOI_DA_TU:
            return None
        return ma, cau
    return None
