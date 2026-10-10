"""Chọn mẩu NÓI TRƯỚC cho lượt mô hình phải tự viết, và ghép nó với câu mô hình viết.

Lượt kho/luật trả lời bằng tiếng dựng sẵn sau vài chục ms. Lượt mô hình viết thì
khách nghe im ~1,5s (chờ chữ đầu + gom câu đầu + dựng tiếng mảnh đầu). Trong
quãng đó AI nói trước một mẩu ĐÃ CÓ TIẾNG lấy từ nhóm câu chung của kho câu đệm
(`streaming_pipeline._noi_truoc_luot_sinh`).

Mẩu nói trước KHÔNG được đổi nội dung câu trả lời. Đã thử nhét mẩu vào miệng mô
hình cho nó viết nối (prefill) trên bộ thử 304 lượt ngày 09-10-2026 và bỏ:

  - "Dạ vâng, em nói luôn ạ," ép mô hình phải khẳng định, mất hẳn các câu mở
    hợp cảnh nó vốn tự viết ("Dạ em hiểu ạ", "Em xin lỗi ạ", "Vâng, cảm ơn anh");
  - lịch sử toàn câu mở đầu giống nhau làm nó chép lại câu trả lời lượt trước
    (khách hỏi "em tên gì" nhận lại nguyên câu giới thiệu lãi suất);
  - mẩu hứa "nói luôn" đứng trước câu "em xin phép kiểm tra lại rồi báo lại".

Nên ở đây mô hình viết đúng như khi không có mẩu nói trước; phần ghép chỉ là
chọn mẩu hợp với KIỂU lời khách và bỏ tiếng lễ phép lặp ở đầu câu mô hình viết.

Hai kiểu lời khách, hai kiểu mẩu:

  khách HỎI          -> mẩu báo sắp trả lời  ("Dạ em trả lời anh chị ạ,")
  khách KỂ / CHÊ ... -> mẩu chỉ nhận lời     ("Dạ vâng ạ,")

Không dùng "Dạ vâng ạ," cho câu hỏi: trước một câu trả lời "chưa được" thì chữ
"vâng" nghe thành đồng ý. Không dùng "em trả lời anh chị ạ" cho lời kể: khách có
hỏi gì đâu. Không dùng mẩu hứa NGAY ("em nói luôn ạ", "em thông tin luôn ạ"):
câu mô hình viết có khi là "em chưa có thông tin" hoặc bị lưới chặn số đổi thành
"em xin phép kiểm tra lại rồi báo lại" - đo trên bộ thử là 5/28 lượt khách hỏi.
"""
from __future__ import annotations

import re

_TU_LE_PHEP = frozenset({"dạ", "vâng", "ạ"})

# Tiếng lễ phép mở đầu câu mô hình viết: "Dạ", "Dạ vâng ạ,", "Vâng,".
_LE_PHEP_DAU = re.compile(r"^\s*(?:dạ(?:\s+vâng)?|vâng)(?:\s+ạ)?\b[\s,;:.!?]*", re.I)

# Tiểu từ cuối câu không mang nghĩa hỏi: bỏ đi rồi mới xét chữ cuối.
_TIEU_TU_CUOI = frozenset({
    "em", "ạ", "anh", "chị", "vậy", "thế", "nha", "nhé", "ta", "đấy", "đó",
    "ơi", "a", "á", "ha", "nhở", "bạn", "cháu", "cô", "chú",
})
# Chữ cuối tự nó là dấu hỏi.
_HOI_CUOI = frozenset({"à", "hả", "hở", "nhỉ", "ư", "hử", "chăng"})
_HOI_CUOI_SAU_TIEU_TU = frozenset({"không", "chưa", "ai", "mấy"})
_HOI_HAI_CHU_CUOI = frozenset({
    "bao nhiêu", "bao lâu", "bao giờ", "khi nào", "thế nào", "ra sao",
    "như nào", "làm sao", "thì sao", "tính sao", "ở đâu", "chỗ nào", "cái nào",
    "loại nào", "là gì", "những gì", "cái gì",
})
_HOI_GIUA_CAU = re.compile(
    r"\b(?:bao nhiêu|bao lâu|bao giờ|khi nào|thế nào|ra sao|làm sao|tại sao|vì sao"
    r"|sao lại|được không|phải không|có được|là sao|như thế nào|tính sao|thì sao"
    r"|có phải|chỗ nào|cái nào|loại nào)\b"
    r"|\b(?:tên|là|làm|gồm|những|cái) gì\b(?!\s+(?:đó|đấy|ấy)\b)"
    r"|\bcó\b.{0,60}\bkhông\b(?!\s+(?:có|cần|phải|biết|tin|thích|muốn|được)\b)"
    r"|\bsao\b(?!\s+kê\b).*\b(?:vậy|thế)$"
    r"|^(?:thế |vậy |ủa |ơ )?sao\b(?!\s+kê\b)")
_PHU_DINH = frozenset({"không", "chẳng", "chả", "chưa"})
# "một tỉ rưỡi hai tỉ gì đó": "gì đó" là ước chừng, không phải hỏi.
_UOC_CHUNG_CUOI = re.compile(r"\s+gì\s+(?:đó|đấy|ấy)\s*$")


def _tu(text: str) -> list[str]:
    return re.findall(r"\w+", (text or "").casefold())


def la_cau_hoi(text: str) -> bool:
    """Lời khách có phải một câu HỎI không (chữ phiên âm, thường không có dấu "?").

    Xét dấu hiệu hỏi của tiếng Việt nói: tiểu từ cuối câu ("à", "hả", "nhỉ"),
    "không/chưa" kết câu, từ để hỏi ("bao nhiêu", "thế nào", "sao", "gì"...).
    "không" giữa câu là phủ định ("anh không tin đâu"), "sao kê" là giấy tờ,
    "không ... gì/đâu" là phủ định trọn ("không cần gì") - đều không tính.
    Đoán sai thì chỉ lệch kiểu mẩu mở đầu, câu trả lời không đổi.
    """
    tho = (text or "").strip()
    if not tho:
        return False
    if "?" in tho:
        return True
    tu = _tu(_UOC_CHUNG_CUOI.sub("", tho.casefold()))
    if not tu:
        return False
    if tu[-1] in _HOI_CUOI:
        return True
    while len(tu) > 1 and tu[-1] in _TIEU_TU_CUOI:
        tu.pop()
    cau = " ".join(tu)
    if tu[-1] in _HOI_CUOI_SAU_TIEU_TU:
        return True
    if " ".join(tu[-2:]) in _HOI_HAI_CHU_CUOI:
        return True
    if tu[-1] == "sao":
        return tu[-2:-1] != ["không"] and tu[-2:-1] != ["chẳng"]   # "không sao"
    if tu[-1] in ("gì", "nào"):
        return not (_PHU_DINH & set(tu[-3:-1]))     # "không cần gì"
    if tu[-1] == "đâu":
        return not (_PHU_DINH & set(tu[:-1]))       # "không tin đâu"
    return bool(_HOI_GIUA_CAU.search(cau))


def loai_mau(chu: str) -> str:
    """Kiểu của một mẩu mở đầu nhóm chung: "nhan_loi", "tra_loi", "hua_ngay", "ngan".

    "nhan_loi": chỉ gồm tiếng lễ phép, từ hai chữ ("Dạ vâng ạ,") - không hứa gì.
    "ngan": một chữ ("Dạ,") - 0,27s, không che được gì, không dùng để nói trước.
    "hua_ngay": hứa trả lời NGAY ("Dạ vâng, em nói luôn ạ,") - không dùng để nói
        trước, xem đầu tệp.
    "tra_loi": còn lại ("Dạ em trả lời anh chị ạ,") - báo sắp trả lời.
    """
    tu = _tu(chu)
    if tu and all(t in _TU_LE_PHEP for t in tu):
        return "nhan_loi" if len(tu) >= 2 else "ngan"
    if "luôn" in tu or "ngay" in tu:
        return "hua_ngay"
    return "tra_loi"


def hop_voi_loi_khach(loi_khach: str):
    """Hàm lọc mẩu nhóm chung hợp với lời khách (xem bảng ở đầu tệp)."""
    can = "tra_loi" if la_cau_hoi(loi_khach) else "nhan_loi"
    return lambda chu: loai_mau(chu) == can


def bo_le_phep_dau(manh: str) -> str:
    """Bỏ tiếng lễ phép lặp ở ĐẦU câu mô hình viết, vì mẩu nói trước đã nói rồi.

    "Dạ vâng ạ," + "Vâng ạ, nếu anh đang thuê..." -> giữ "nếu anh đang thuê...".
    Mảnh chỉ có mỗi tiếng lễ phép ("Dạ vâng,") thì trả "": nơi gọi bỏ mảnh đó,
    và nếu cả câu trả lời hoá ra chỉ có vậy thì nó phát lại nguyên mảnh
    (`streaming_pipeline`, biến `le_phep_da_bo`).
    Không đụng "vâng lời", không đụng chữ nào sau phần lễ phép.
    """
    con = (manh or "").strip()
    while con and not re.match(r"^vâng\s+lời\b", con, re.I):
        m = _LE_PHEP_DAU.match(con)
        if not m or not m.group(0).strip():
            break
        con = con[m.end():].strip()
    return con if any(c.isalnum() for c in con) else ""
