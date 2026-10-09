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
    "chao_hoi", "chao_bat_may", "nghe_ro_khong", "moi_noi_tiep",
})

# Khách đang khép cuộc gọi hoặc gạt đi - nhìn trên chính lời khách.
_KHEP = re.compile(
    r"\b(cảm ơn|cám ơn|tạm biệt|thôi nhé|thôi em|để (anh|chị|tôi) (xem|nghĩ|suy nghĩ|tính)"
    r"|không cần|không quan tâm|bận|gọi lại|khi nào cần|lừa đảo|đừng gọi)\b", re.IGNORECASE)

_CO_THU_NHAP = re.compile(r"\b(lương|thu nhập)\b", re.IGNORECASE)


def _da_biet(ma: str, trang_thai, loi_khach: str) -> bool:
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
    if "?" in (cau_tra_loi or ""):
        return None
    if y_dinh_thuong_gap in KHONG_HOI_SAU or ma_luat.startswith(("kho_khong_co", "xac_nhan_")):
        return None
    if _KHEP.search(loi_khach_luot_nay or ""):
        return None
    # Lượt TRƯỚC vừa hỏi một ý mà khách chưa trả lời (họ hỏi lại chuyện khác):
    # lượt này không hỏi dồn sang ý kế tiếp. Bản đầu hỏi "vay bao nhiêu", khách
    # nói "vay tiêu dùng ấy", AI hỏi luôn "vay trong bao lâu" - nghe như máy
    # đọc danh sách. Lượt sau nữa mới hỏi tiếp.
    if vua_hoi and not _da_biet(vua_hoi, trang_thai, loi_khach_ca_cuoc):
        return None
    for ma, cau in buoc:
        if ma in da_hoi:
            continue
        if _da_biet(ma, trang_thai, loi_khach_ca_cuoc):
            continue
        if ma == "ghi_nhan" and len(da_hoi) == 0 and trang_thai.amount.status == "unknown":
            # Chưa trao đổi được gì mà đã mời làm hồ sơ là hối khách.
            return None
        if len((cau_tra_loi or "").split()) + len(cau.split()) > TOI_DA_TU:
            return None
        return ma, cau
    return None
