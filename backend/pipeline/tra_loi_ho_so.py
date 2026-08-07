"""Trả lời câu hỏi về HỒ SƠ RIÊNG của khách THẲNG TỪ DỮ LIỆU, không qua LLM.

Vì sao không để mô hình làm: đây là việc có quy tắc xác định (câu hỏi -> đúng một
trường -> đọc ra), mà mô hình 3B thì không đáng tin ở đúng chỗ này. Bộ nhớ dự án
ghi lại ba lần cùng một bài học:

  - `chan_so_sai`  : mô hình đọc 7.9 thành "sáu phẩy chín", hạ nhiệt độ càng ổn
                     định ở chỗ SAI. Chặn bằng code: 2/8 -> 8/8 đúng.
  - `doc_so()`     : chuyển số sang chữ bằng code thay vì nhờ mô hình.
  - `luot_thuong_gap`: lượt chào/từ chối trả lời bằng bảng, bỏ hẳn LLM.

Và chính `data_source_service.dung_ngu_canh` ghi: hồ sơ nằm ĐÚNG trong prompt mà
mô hình 3B vẫn đáp "em chưa biết số dư cụ thể".

Đổi lại: câu chữ cố định nên nghe máy móc hơn. Mỗi ý khai vài mẫu để đỡ lặp.

Chỉ nhận câu hỏi về hồ sơ RIÊNG (dư nợ của tôi, tôi phải trả bao nhiêu). Câu hỏi
về SẢN PHẨM nói chung (lãi suất vay tín chấp bao nhiêu) KHÔNG thuộc đây - cái đó
đi qua RAG như cũ.
"""

import random
import re
import unicodedata

# (tên ý, các mẫu nhận dạng, tên trường, các câu mẫu)
#
# Mẫu viết trên chuỗi ĐÃ BỎ DẤU: kênh thoại 8kHz cho phiên âm sai dấu rất nhiều
# ("dư nợ" -> "du no", "dử nợ"), khớp có dấu là trượt.
BANG = [
    ("du_no",
     [r"\bdu no\b", r"\bno (con )?(bao nhieu|the nao)", r"\bcon no bao nhieu",
      r"\bcon (thieu|no) (bao nhieu|may)"],
     "du_no",
     ["Dạ dư nợ hiện tại của {xung_ho} là {gia_tri} ạ.",
      "Dạ {xung_ho} đang còn dư nợ {gia_tri} ạ."]),

    ("ngay_den_han",
     [r"\bden han\b", r"\bhan (tra|thanh toan)\b", r"\bbao gio.{0,12}(den han|phai tra)",
      r"\bhet han (khi nao|bao gio)"],
     "ngay_den_han",
     ["Dạ khoản này đến hạn ngày {gia_tri} ạ.",
      "Dạ hạn thanh toán của {xung_ho} là ngày {gia_tri} ạ."]),

    ("tra_hang_thang",
     [r"\b(tra|dong) (hang thang|moi thang|mot thang)", r"\bmoi thang.{0,10}(tra|dong)",
      r"\bhang thang.{0,10}bao nhieu"],
     "tra_hang_thang",
     ["Dạ mỗi tháng {xung_ho} trả {gia_tri} ạ.",
      "Dạ số tiền phải trả hàng tháng là {gia_tri} ạ."]),

    ("ky_han_con",
     [r"\bcon (bao nhieu|may) (thang|ky|kì)", r"\bky han con\b", r"\bcon lai bao lau"],
     "ky_han_con",
     ["Dạ khoản vay của {xung_ho} còn {gia_tri} ạ.",
      "Dạ còn {gia_tri} nữa là hết ạ."]),

    ("lai_suat_rieng",
     [r"\blai suat (cua |ma )?(toi|anh|chi|em) ", r"\blai suat.{0,14}(dang|hien) (ap dung|chiu)",
      r"\bdang chiu lai (suat )?bao nhieu"],
     "lai_suat_dang_ap_dung",
     ["Dạ lãi suất đang áp dụng cho {xung_ho} là {gia_tri} ạ.",
      "Dạ hợp đồng của {xung_ho} đang chịu lãi suất {gia_tri} ạ."]),

    ("han_muc_rieng",
     [r"\bhan muc (cua |da duyet cho )?(toi|anh|chi)\b", r"\bduoc duyet (bao nhieu|muc nao)",
      r"\btoi vay duoc bao nhieu\b", r"\banh vay duoc bao nhieu\b"],
     "han_muc_da_duyet",
     ["Dạ hạn mức đã duyệt cho {xung_ho} là {gia_tri} ạ.",
      "Dạ {xung_ho} được duyệt tới {gia_tri} ạ."]),
]


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.replace("đ", "d")).strip()


_DA_DICH = [(ten, [re.compile(p) for p in mau], truong, cau)
            for ten, mau, truong, cau in BANG]


def nhan_dang(text: str) -> tuple[str, str] | None:
    """(tên ý, tên trường) nếu câu hỏi về một trường hồ sơ, không thì None."""
    t = _bo_dau(text)
    if not t:
        return None
    for ten, mau, truong, _ in _DA_DICH:
        if any(m.search(t) for m in mau):
            return ten, truong
    return None


def tra_loi(text: str, ho_so: dict, xung_ho: str = "anh chị") -> tuple[str, str] | None:
    """(tên ý, câu trả lời) lấy thẳng từ hồ sơ. None = không phải câu hỏi hồ sơ.

    Trả None KHI KHÔNG CÓ DỮ LIỆU cho trường đó, để lượt rơi về đường LLM như cũ
    thay vì đọc ra một câu rỗng. Thà nói vòng còn hơn khẳng định một ô trống.
    """
    ra = nhan_dang(text)
    if ra is None:
        return None
    ten, truong = ra
    gia_tri = str((ho_so or {}).get(truong, "") or "").strip()
    if not gia_tri or gia_tri in {"-", "—", "n/a", "N/A"}:
        return None
    cau = next(c for t, _, _, c in BANG if t == ten)
    return ten, random.choice(cau).format(xung_ho=xung_ho, gia_tri=gia_tri)
