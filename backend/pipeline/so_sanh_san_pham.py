"""Trả lời câu SO SÁNH hai sản phẩm bằng đúng dòng dữ kiện của từng tài liệu.

VÌ SAO. Bộ thử 304 lượt (08-10-2026), ba lượt so sánh đều hỏng theo ba kiểu:

    "lãi suất vay mua nhà với vay tín chấp cái nào thấp hơn"
        kho      -> đọc mỗi lãi vay tín chấp (nửa câu trả lời)
        mô hình  -> "em chưa có thông tin về lãi suất vay mua nhà" (tài liệu CÓ)
    "vay tín chấp thì vay được nhiều hơn thẻ đúng không em"
        mô hình  -> "Dạ đúng ạ ... cao hơn so với thẻ tín dụng" (cả hai cùng
                    trần 500 triệu - mô hình gật theo khách)

Gốc chung: ngữ cảnh của một lượt chỉ có tài liệu của sản phẩm phiên đang neo,
nên không ai nhìn thấy cả hai vế. Ở đây đọc thẳng dòng "- Lãi suất: ..." /
"- Hạn mức: ..." / "- Thời hạn: ..." của TỪNG tài liệu và đặt cạnh nhau. Không
kết luận "cái nào hơn" - chỉ nêu hai dữ kiện, khách tự thấy.

Lưới hẹp có chủ ý: phải nêu ĐÍCH DANH hai sản phẩm có tài liệu, có từ so sánh, và
hỏi đúng một trong ba thuộc tính đọc được. Thiếu một điều là trả None.
"""
from __future__ import annotations

import re
from typing import Callable

from backend.pipeline.danh_muc_san_pham import TEN, _CUM, _bo_dau

_SO_SANH = re.compile(
    r"\b(?:cai nao|ben nao|loai nao|goi nao|so voi|so sanh|khac (?:gi|nhau)|hay la"
    r"|(?:thap|cao|re|dat|nhieu|it|dai|ngan|loi|tot) hon)\b")

# (mã thuộc tính, cách khách hỏi - đã bỏ dấu, tiêu đề dòng trong tài liệu, nhãn đọc)
_THUOC_TINH: list[tuple[str, str, str, str]] = [
    ("lai_suat", r"\blai\b", r"Lãi suất[^:\n]*", "lãi suất"),
    ("han_muc", r"han muc|vay duoc|duoc vay|toi da|bao nhieu tien|nhieu hon", r"Hạn mức[^:\n]*", "hạn mức"),
    ("thoi_han", r"thoi han|ky han|bao lau|dai hon|may nam|may thang", r"(?:Thời hạn|Kỳ hạn)[^:\n]*", "thời hạn"),
]


def _dong(tai_lieu: str, tieu_de: str) -> str:
    """Giá trị của dòng `- <tieu_de>: <giá trị>` ĐẦU TIÊN trong tài liệu."""
    m = re.search(rf"^\s*[-*]\s*{tieu_de}:\s*(.+?)\s*$", tai_lieu or "", re.M)
    return m.group(1).strip().rstrip(".") if m else ""


def tra_loi(text: str, ma_co_tai_lieu: set[str] | None,
            lay_tai_lieu: Callable[[str], str],
            ma_phien: str = "") -> tuple[str, str] | None:
    """`(mã, câu)` khi câu là so sánh hai sản phẩm; None để đường cũ trả lời.

    `lay_tai_lieu(mã)` trả phần đầu tài liệu của sản phẩm (chỗ có khối "Thông
    tin sản phẩm"). `ma_phien` là mã sản phẩm phiên đang neo, dùng làm vế thứ
    hai khi khách chỉ nêu đích danh một sản phẩm.
    """
    if not ma_co_tai_lieu:
        return None
    t = _bo_dau(text)
    if not t or not _SO_SANH.search(t):
        return None
    sp: list[str] = []
    con = t
    for ma, cum in _CUM:           # cụm dài đứng trước, khớp rồi thì xoá khỏi câu
        if ma in ma_co_tai_lieu and re.search(rf"\b(?:{cum})\b", con):
            sp.append(ma)
            con = re.sub(rf"\b(?:{cum})\b", " ", con)
    # Khách chỉ nêu MỘT sản phẩm khác, vế còn lại là sản phẩm phiên đang tư vấn
    # ("vay tín chấp thì vay được nhiều hơn thẻ đúng không" khi đang nói về thẻ).
    if len(sp) == 1 and ma_phien and ma_phien != sp[0] and ma_phien in ma_co_tai_lieu:
        sp.append(ma_phien)
    if len(sp) != 2:
        return None
    # Giữ thứ tự khách nói.
    sp.sort(key=lambda ma: min(
        (m.start() for m in re.finditer(dict(_CUM)[ma], t)), default=len(t)))
    for ma_tt, hoi, tieu_de, nhan in _THUOC_TINH:
        if not re.search(hoi, t):
            continue
        gia_tri = [_dong(lay_tai_lieu(ma) or "", tieu_de) for ma in sp]
        if not any(gia_tri):
            return None
        ve = [f"{TEN[ma]} {nhan} {gt}" if gt
              else f"{TEN[ma]} thì em chưa có thông tin về {nhan}"
              for ma, gt in zip(sp, gia_tri)]
        return f"so_sanh_{ma_tt}", f"Dạ {ve[0]}, còn {ve[1]} ạ."
    return None
