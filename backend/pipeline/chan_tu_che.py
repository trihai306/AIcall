"""Chặn ba kiểu câu mô hình TỰ CHẾ mà không lưới số nào thấy (không có con số sai).

Cả ba lộ ra ở bộ thử 156 lượt ngày 12-10-2026, đều ở lượt mô hình tự viết:

- Tự cúp máy: khách than "dậy thôi hả kỳ dậy" (thất vọng, chưa hề từ chối), mô
  hình đáp "Em xin lỗi đã làm phiền ạ. Em xin phép kết thúc cuộc gọi."
- Tự phán theo thu nhập: "Với thu nhập hiện tại, anh có thể vay tối đa 500
  triệu" - hạn mức sản phẩm bị nói thành mức khách được duyệt.
- Tự đặt quy định phụ thuộc: "lãi suất cụ thể còn phụ thuộc vào hồ sơ và thu
  nhập" - tài liệu không có chữ nào nói lãi suất tuỳ hồ sơ.

Cùng khuôn với `chan_kenh`: bỏ đúng CÂU vi phạm, phần còn lại quá ngắn mới dùng
câu mẫu. Thứ ghi cứng ở đây là CÁCH NÓI trong tiếng Việt; có được nói hay không
thì vẫn do tài liệu và lời khách quyết định.
"""

import re

from backend.pipeline.chan_kenh import _bo_dau, tach_cau
from backend.pipeline.luot_thuong_gap import y_dinh_dung_tu_van

CAU_GIU_KHACH = ("Dạ em hiểu ạ. Em xin ghi nhận trường hợp của anh chị để chuyên viên "
                 "xem kỹ và hỗ trợ thêm ạ.")
CAU_GHI_NHAN = "Dạ phần này em xin ghi nhận để chuyên viên trao đổi cụ thể với anh chị ạ."

_NGUOI = r"(?:anh chi|anh|chi|bac|co|chu|ong|ba|minh|quy khach)"
_CUP_MAY = re.compile(
    r"\b(ket (thuc )?cuoc goi|(dung|ngat|ngung) cuoc goi|ket thuc tai day|xin phep dung may|"
    r"xin phep (ket thuc|dung|ngung)( (tai|o) day)?\s*$|"
    r"xin phep cup may|xin loi (vi )?da lam phien|khong lam phien (them|nua)|"
    r"tam biet|hen gap lai|chuc " + _NGUOI + r" (mot ngay|moi dieu|suc khoe|ngay moi|buoi)|"
    r"lam (mat|ton) thoi gian|lam " + _NGUOI + r" (mat|ton) thoi gian|"
    r"cam on " + _NGUOI + r" da (goi|nghe may|lang nghe|danh thoi gian|quan tam))\b")
# Khách tự khép cuộc gọi thì AI chào lại là đúng.
_KHACH_CHAO = re.compile(
    r"\b(tam biet|chao em|chao chau|bye|cup may|the thoi nhe|thoi nhe|thoi nha|"
    r"cam on em nhe|cam on em nha|cam on chau|the nhe|vay nhe|vay nha|khong can nua|"
    r"khong vay nua|khong lam nua|khong gui nua)\b")

_PHAN_THEO_THU_NHAP = re.compile(
    r"\b(voi|theo|dua tren|can cu)\b[^.?!]{0,25}\b(thu nhap|muc luong|luong|ho so)\b"
    r"[^.?!]{0,40}\b(co the|se|du dieu kien|duoc)\b[^.?!]{0,15}"
    r"\b(vay|duyet|mo the|cap han muc|cap the)\b")
# Câu đã nói rõ còn phải thẩm định thì không phải lời phán.
_CON_THAM_DINH = re.compile(r"\b(tham dinh|tuy ho so|chuyen vien|chua the xac nhan|can doi chieu)\b")

_PHU_THUOC = re.compile(
    r"\b(lai suat|muc lai|phi)\b[^.?!]{0,50}\b(phu thuoc|tuy thuoc|tuy vao|tuy theo|"
    r"tuy tung|con tuy|can cu vao|dua tren|theo tung)\b[^.?!]{0,40}"
    r"\b(ho so|thu nhap|diem tin dung|lich su tin dung|tung khach|khach hang|nang luc)\b")


def _bo_cau(doan: str, vi_pham, cau_mau: str) -> tuple[str, str]:
    giu, bo = [], []
    for c in tach_cau(doan or ""):
        (bo if vi_pham(c) else giu).append(c)
    if not bo:
        return doan, ""
    con = "".join(giu).strip()
    mo_ta = "; ".join(repr(c.strip()[:60]) for c in bo)
    return (con if len(_bo_dau(con).split()) >= 5 else cau_mau), mo_ta


def khach_muon_dung(khach_noi: str) -> bool:
    return bool(y_dinh_dung_tu_van(khach_noi or "")) or bool(
        _KHACH_CHAO.search(_bo_dau(khach_noi)))


def chan_tu_cup_may(doan: str, khach_noi: str) -> tuple[str, str]:
    """Bỏ câu AI tự khép cuộc gọi khi khách chưa hề từ chối hay chào.

    Trả (phần CÒN LẠI, mô tả); phần còn lại có thể rỗng. Nơi gọi tự chèn
    `CAU_GIU_KHACH` MỘT lần mỗi lượt: mô hình thường khép bằng hai ba câu liền
    ("xin lỗi đã làm mất thời gian", "cảm ơn anh đã gọi"), mỗi câu là một mảnh.
    """
    if khach_muon_dung(khach_noi):
        return doan, ""
    giu, bo = [], []
    for c in tach_cau(doan or ""):
        (bo if _CUP_MAY.search(_bo_dau(c)) else giu).append(c)
    if not bo:
        return doan, ""
    return "".join(giu).strip(), "; ".join(repr(c.strip()[:60]) for c in bo)


def chan_phan_theo_thu_nhap(doan: str) -> tuple[str, str]:
    """Bỏ câu phán khách vay được bao nhiêu dựa trên thu nhập/hồ sơ của khách."""
    def vi_pham(c: str) -> bool:
        t = _bo_dau(c)
        return ("?" not in c and bool(_PHAN_THEO_THU_NHAP.search(t))
                and not _CON_THAM_DINH.search(t))
    return _bo_cau(doan, vi_pham, CAU_GHI_NHAN)


# Câu KHÔNG nhắc chữ lãi suất: "Mức cụ thể còn phụ thuộc vào hồ sơ và thu nhập".
# Nó nói về lãi hay về hạn mức là do câu đứng trước quyết định.
_PHU_THUOC_TRON = re.compile(
    r"\b(muc|con so|ty le)\b[^.?!]{0,25}\b(phu thuoc|tuy thuoc|tuy vao|tuy theo|con tuy)\b"
    r"[^.?!]{0,40}\b(ho so|thu nhap|diem tin dung|lich su tin dung|tung khach|khach hang)\b")
_VE_HAN_MUC = re.compile(r"\b(han muc|duyet|vay duoc|so tien vay|khoan vay)\b")


def chan_phu_thuoc_bia(doan: str, tai_lieu: str, ngu_canh: str = "") -> tuple[str, str]:
    """Bỏ câu bảo lãi suất/phí tuỳ hồ sơ khi tài liệu không nói vậy.

    Không có tài liệu thì không phán, cùng lý do với `chan_kenh_la`. `ngu_canh`
    là lời khách và câu AI vừa nói ngay trước: câu "mức cụ thể còn phụ thuộc hồ
    sơ" chỉ bị bỏ khi mạch đang nói về LÃI. Mức được DUYỆT phụ thuộc hồ sơ thì
    đúng, các câu của luật vẫn nói vậy.
    """
    if not (tai_lieu or "").strip() or _PHU_THUOC.search(_bo_dau(tai_lieu)):
        return doan, ""
    cac, truoc = tach_cau(doan or ""), _bo_dau(ngu_canh)
    bo: set[int] = set()
    for i, c in enumerate(cac):
        t = _bo_dau(c)
        mach = f"{truoc} {_bo_dau(' '.join(cac[:i]))}"
        # Chỉ xét câu NGAY TRƯỚC và lời khách: mạch xa hơn không còn chi phối.
        if _PHU_THUOC.search(t) or (
                _PHU_THUOC_TRON.search(t) and not _VE_HAN_MUC.search(t)
                and re.search(r"\blai\b", mach) and not _VE_HAN_MUC.search(mach[-120:])):
            bo.add(i)
    if not bo:
        return doan, ""
    con = "".join(c for i, c in enumerate(cac) if i not in bo).strip()
    mo_ta = "; ".join(repr(cac[i].strip()[:60]) for i in sorted(bo))
    return (con if len(_bo_dau(con).split()) >= 5 else CAU_GHI_NHAN), mo_ta


CAU_HIEU = "Dạ em hiểu ạ."
_CHUA_CO = re.compile(
    r"\b(chua co|khong co|chua cap nhat|chua nam duoc|chua tra cuu duoc)\b[^.?!]{0,25}"
    r"\bthong tin\b[^.?!]{0,45}"
    r"\b(?P<y>lai suat|han muc|thoi han|ky han|thu nhap|giay to|ho so|so do|phi thuong nien)\b"
    r"|\bthong tin\b[^.?!]{0,30}\b(?P<y2>so do|giay to|thu nhap|lai suat|han muc)\b[^.?!]{0,30}"
    r"\b(chua tra cuu duoc|chua co|chua nam duoc)\b")


def chan_chua_co_thong_tin_sai(doan: str, tai_lieu: str) -> tuple[str, str]:
    """Bỏ câu bảo "chưa có thông tin về lãi suất/hạn mức" khi tài liệu CÓ mục đó.

    Bộ thử 12-10-2026: khách kể chuyện sửa bếp, mô hình đáp "ngân hàng chưa có
    thông tin cụ thể về mức lãi suất hay hạn mức dành riêng cho trường hợp này"
    trong khi tài liệu ghi rõ 7,9% và 500 triệu. Khách nghe ra là không tư vấn được.
    """
    tl = _bo_dau(tai_lieu)
    if not tl:
        return doan, ""

    def vi_pham(c: str) -> bool:
        m = _CHUA_CO.search(_bo_dau(c))
        y = m and (m.group("y") or m.group("y2"))
        # "chưa có thông tin về thu nhập CỦA ANH" là nói thật: AI chưa biết hồ sơ khách.
        cua_khach = m and re.search(r"\b(cua|ve) (anh|chi|anh chi|quy khach)\b|\b(anh|chi) (mong muon|dang co)\b",
                                    _bo_dau(c))
        return bool(m) and "?" not in c and not cua_khach and f" {y} " in f" {tl} "
    return _bo_cau(doan, vi_pham, CAU_HIEU)


_NHAN_LA_NGUOI = re.compile(
    r"\b(em la nguoi that|em la nhan vien that|em khong phai (la )?(may|robot|ai|tro ly ao)|"
    r"(dang )?(tro chuyen|noi chuyen) truc tiep voi \w+( \w+)? nhan vien|"
    r"em la nguoi chu khong phai)\b")


def chan_tu_nhan_la_nguoi(doan: str) -> tuple[str, str]:
    """Bỏ câu mô hình tự nhận mình là người thật.

    Bộ thử 12-10-2026, khách nói "thế máy thì biết gì mà tư vấn": "Em đang trò
    chuyện trực tiếp với Lan, nhân viên ngân hàng." Danh tính tự động là điều
    phải nói thật; câu đúng đã có ở `luot_thuong_gap.danh_tinh_tu_dong`.
    """
    return _bo_cau(doan, lambda c: bool(_NHAN_LA_NGUOI.search(_bo_dau(c))),
                   "Dạ em là trợ lý tư vấn tự động của ngân hàng ạ.")
