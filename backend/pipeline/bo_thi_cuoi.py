"""Bỏ chữ "thì" ở cuối câu đệm. MỘT hàm cho mọi nguồn câu đệm.

VÌ SAO. Người dùng 13-09-2026 sau cuộc gọi 5 phút `7db3f780`: *"Cả cái chỗ nó cứ
'thì' ở cuối câu nối, xem có cách nào khắc phục triệt để"*. Kho tình huống trên
máy Win có 34/154 mẩu mở đầu kết bằng "thì," ("Dạ về lãi suất thì,"), và 15/27
lượt của cuộc gọi đó phát câu đệm theo tình huống. Câu đệm phát xong thì câu trả
lời chưa chắc đã tới: giữa hai bên luôn có một quãng chờ, và chữ "thì" treo lơ
lửng đúng chỗ đó - nghe như AI bỏ dở câu. Lặp lại cả cuộc gọi thì thành tật.

VÌ SAO LÀ HÀM CHỨ KHÔNG CHỈ SỬA DỮ LIỆU. Câu đệm đến từ bốn chỗ: kho tình huống
người vận hành gõ, bảng hỏi-đáp, câu đệm do LLM sinh, và dữ liệu gieo. Sửa tay
dữ liệu hôm nay thì mai người vận hành gõ lại "thì" là tật quay về. Nên cả bốn
đường gọi hàm này lúc nạp/lúc sinh.

CÁCH BỎ. Chỉ bỏ "thì" rồi để trống thì còn "Dạ lãi suất bên em," - một chủ ngữ
chờ vị ngữ, vẫn treo. Nên đổi về khung CHỦ ĐỀ "về ...", thứ đứng được một mình
trước một quãng nghỉ:

    "Dạ về lãi suất thì,"          -> "Dạ về lãi suất,"
    "Dạ lãi suất bên em thì,"      -> "Dạ về lãi suất bên em,"
    "Dạ nếu anh chị trả sớm thì,"  -> "Dạ về việc anh chị trả sớm,"

Chuỗi không kết bằng "thì" trả lại NGUYÊN TỪNG BYTE: vân tay clip tiếng tính
theo chuỗi chữ, đổi một khoảng trắng là dựng lại clip bằng F5.
"""
from __future__ import annotations

import re

# Lễ phép đầu câu: "Dạ", "Dạ vâng,", "Vâng ạ". Giữ nguyên, chỉ xử phần sau nó.
_LE_PHEP = re.compile(r"^(?:\s*(?:dạ|vâng|ạ)\b[\s,]*)+", re.IGNORECASE)
# "thì" là TỪ cuối cùng, trước dấu câu (nếu có). Ranh giới từ để khỏi bắt "thìa".
_THI_CUOI = re.compile(r"\s*\bthì\b(?P<dau>[\s,.;:!?…]*)$", re.IGNORECASE)
# Mở đầu mệnh đề điều kiện/mục đích: bỏ "thì" rồi vẫn là nửa câu, đổi "về việc".
_DIEU_KIEN = re.compile(r"^(?:nếu|để)\s+", re.IGNORECASE)
# Đã là khung đứng được một mình: không chèn thêm "về".
_KHUNG_SAN = re.compile(r"^(?:về|với|còn|em|anh|chị|mình|bên em)\b", re.IGNORECASE)


def bo_thi_cuoi(cau: str) -> str:
    """Câu đệm không còn "thì" ở cuối. Không có "thì" cuối thì trả nguyên."""
    if not cau:
        return cau
    m = _THI_CUOI.search(cau)
    if not m:
        return cau
    dau = m.group("dau").strip()
    than = cau[:m.start()]
    le = _LE_PHEP.match(than)
    dau_cau = le.group(0) if le else ""
    noi_dung = than[len(dau_cau):].strip(" ,")
    if not noi_dung:
        # "Dạ thì," -> "Dạ,"
        return dau_cau.rstrip(" ,") + (dau or "")
    if _DIEU_KIEN.match(noi_dung):
        noi_dung = "về việc " + _DIEU_KIEN.sub("", noi_dung, count=1)
    elif not _KHUNG_SAN.match(noi_dung):
        noi_dung = "về " + noi_dung[0].lower() + noi_dung[1:]
    if not dau_cau:
        # Không có "Dạ" đứng trước: chữ đầu câu viết hoa như bản gốc.
        if cau.lstrip()[:1].isupper():
            noi_dung = noi_dung[0].upper() + noi_dung[1:]
        return noi_dung + dau
    # "Dạ " hay "Dạ vâng, " - giữ nguyên dấu phẩy/khoảng trắng người viết đặt.
    if not dau_cau.endswith((" ", ",")):
        dau_cau += " "
    elif dau_cau.endswith(","):
        dau_cau += " "
    return dau_cau + noi_dung + dau


def bo_thi_cuoi_ca_danh_sach(cac: list[str] | tuple[str, ...]) -> list[str]:
    """Chuẩn hoá cả danh sách mẩu mở đầu, bỏ bản trùng sinh ra SAU khi chuẩn hoá.

    "Dạ về lãi suất thì," và "Dạ về lãi suất," cùng một kho thì sau khi bỏ "thì"
    là hai mẩu y hệt - để nguyên thì bộ xoay vòng tưởng có hai lựa chọn.
    """
    ra: list[str] = []
    for c in cac:
        moi = bo_thi_cuoi(c)
        if moi not in ra:
            ra.append(moi)
    return ra
