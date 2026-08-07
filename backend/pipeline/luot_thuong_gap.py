"""Trả lời sẵn cho những lượt KHÔNG phải câu hỏi sản phẩm.

Vì sao không để mô hình lo: đo bằng `scripts/do_tra_loi_mot_kieu.py` trên
`tuvan-qwen`:

    câu hỏi sản phẩm          0/4  rơi vào khuôn thoái thác
    lượt không phải câu hỏi   5/10 rơi vào khuôn

Mô hình trả lời câu sản phẩm rất chuẩn, nhưng gặp lượt chào hỏi / dò hỏi / từ
chối thì bịa ra một khuôn "xin lỗi ... ghi nhận ... chuyên viên liên hệ lại".
Có câu sai hẳn nghĩa: "ai đấy" -> *"bên em đang có chuyên viên liên hệ lại"*;
"gọi lại sau nhé" -> *"em cảm ơn anh chị đã GỌI"* (mình gọi cho khách chứ).

Gốc rễ nằm ở bộ dữ liệu: 284/284 mẫu đều là hỏi-đáp sản phẩm, không mẫu nào dạy
xử lý lượt còn lại - mà trong cuộc gọi thật đó mới là phần lớn. Sửa gốc là thêm
mẫu rồi train lại; trong lúc chờ thì chặn ở đây.

BA RÀNG BUỘC CỐ Ý, đừng nới:
  1. Chỉ nhận lượt NGẮN (<= `TOI_DA_TU` từ). Câu dài gần như luôn có nội dung
     thật, để mô hình lo.
  2. So trên bản BỎ DẤU, vì kênh thoại 8kHz làm mất thanh điệu trước tiên
     ("ai đấy" -> "ai đây", "a lô" -> "alo").
  3. Không khớp thì trả None, đi tiếp đường cũ. Bảng này chỉ được phép làm TỐT
     HƠN hiện trạng, không được phép chặn nhầm rồi làm tệ đi.

LỜI THOẠI DƯỚI ĐÂY LÀ BẢN NHÁP - người phụ trách nghiệp vụ phải duyệt, nhất là
câu trả lời "sao em có số của anh": nói sai chỗ đó là vấn đề pháp lý, không phải
vấn đề kỹ thuật.
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

TOI_DA_TU = 8


def bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d")
    return re.sub(r"[^a-z0-9\s]+", " ", s).strip()


def _chuan(s: str) -> str:
    return re.sub(r"\s+", " ", bo_dau(s))


# (tên ý định, các mẫu nhận dạng, câu trả lời)
# Mẫu so bằng `re.search` trên chuỗi ĐÃ BỎ DẤU.
BANG = [
    ("nghe_ro_khong",
     # Cố ý để khoảng giữa "co nghe" và "khong" tự do: kênh 8kHz cho phiên âm
     # sai chính giữa câu ("có nghe TIẾNG anh nói không" -> "có nghe THEO anh
     # nói không"). Liệt kê từng từ một là chắc chắn trượt. An toàn vì cả bảng
     # chỉ chạy trên lượt <= TOI_DA_TU từ.
     # Nhánh "nghe rõ" phải để khoảng tự do Y HỆT nhánh "có nghe" - trước chỉ
     # bắt "nghe rõ không" liền nhau nên cuộc gọi thật trượt câu "nghe rõ NHỮNG
     # GÌ ANH NÓI không", rồi LLM đọc thành lời từ chối và đáp "em xin lỗi đã
     # làm phiền ạ". Một câu hỏi thành một lời xin lỗi.
     [r"\bco nghe\b.{0,22}\bkhong\b", r"\bnghe (ro|thay|duoc)\b.{0,25}\bkhong\b",
      r"\bco ro khong\b", r"\bnghe ro chua\b"],
     "Dạ em nghe rõ ạ."),

    ("ai_day",
     [r"^\s*(alo\s+|a lo\s+)?ai (day|do|the|vay|goi)", r"\bai goi (day|do|vay)\b",
      r"\bem la ai\b", r"\bben nao (day|do|vay)\b", r"\bcong ty nao\b"],
     "Dạ em là {agent} bên {bank}, em gọi để giới thiệu chương trình {product} ạ."),

    ("sao_co_so",
     [r"\bsao (em |minh )?(lai )?co (so|sdt)", r"\b(so|sdt) .*o dau (ra|the|vay)",
      r"\blay so .*o dau\b", r"\bai cho (so|sdt)\b"],
     # Câu này CHẮC CHẮN phải cho nghiệp vụ duyệt lại cho khớp thực tế.
     "Dạ số của anh chị có trong danh sách khách hàng đã đồng ý nhận thông tin "
     "của bên em ạ. Nếu anh chị không muốn nhận nữa, em xin phép ghi nhận để "
     "bên em không liên hệ lại ạ."),

    ("moi_noi_tiep",
     [r"^\s*(u+|ok|okie|duoc|vang|roi)?\s*(thi |thoi )?em noi (di|xem)\b",
      r"^\s*noi (di|xem|nghe)\b", r"^\s*(u+|vang)\s*(noi )?(di|xem)\s*$",
      r"\bco (viec|chuyen) gi (khong|the|vay)\b", r"\bgoi co viec gi\b"],
     "Dạ bên em đang có chương trình {product} ưu đãi, em xin phép giới thiệu "
     "nhanh với anh chị ạ."),

    ("dang_ban",
     # Liệt kê từng cụm thay vì bắt trơ "ban": bỏ dấu rồi thì "bận", "bạn" và
     # "bàn" trùng nhau, bắt trơ là chặn nhầm "bạn anh cũng vay bên em".
     [r"\b(dang ban|ban lam|ban qua|ban roi|ban viec|hoi ban)\b",
      r"^\s*(anh|chi|toi|em)?\s*ban\s*$",
      r"\bkhong ranh\b", r"\bdang di lam\b", r"\bdang hop\b", r"\bdang lai xe\b"],
     "Dạ em xin lỗi đã gọi không đúng lúc ạ. Em xin phép gọi lại, "
     "khoảng mấy giờ thì tiện cho anh chị ạ?"),

    ("tu_choi",
     [r"\bkhong (co )?(quan tam|nhu cau|can)\b", r"\bkhong vay (dau|gi)?\b",
      r"^\s*thoi\s*(nhe|nha|em|di)?\s*$", r"\bdung goi (nua|lai)\b"],
     "Dạ em hiểu ạ. Em cảm ơn anh chị đã nghe máy, em xin phép không làm phiền "
     "thêm ạ."),

    ("hen_lai",
     [r"\bgoi lai (sau|sau nhe|gio khac|lan sau)\b", r"\bde (anh|chi|toi) xem\b",
      r"\bkhi nao (ranh|can) (thi )?(anh|chi|toi) (goi|bao)\b",
      r"\bnhan tin (cho|qua) (anh|chi|toi)\b"],
     "Dạ vâng ạ. Em cảm ơn anh chị, em xin phép gửi thông tin qua tin nhắn để "
     "anh chị xem lúc tiện ạ."),

    # Để CUỐI: "alo" trần trụi, sau khi các ý định cụ thể hơn đã xét xong.
    ("chao_bat_may",
     [r"^\s*(a\s*lo\s*)+$", r"^\s*(alo\s*)+$", r"^\s*(nghe|toi nghe|noi di)\s*$",
      r"^\s*(a\s*lo|alo)\s+(em|anh|chi)\s*(oi|a|ah)?\s*$"],
     None),      # tuỳ lúc đầu hay giữa cuộc gọi, xem `tra_loi_san`
]

CHAO_DAU = ("Dạ em chào anh chị ạ. Em là {agent} bên {bank}, em gọi để giới "
            "thiệu chương trình {product} ưu đãi ạ.")
CHAO_GIUA = "Dạ em vẫn nghe anh chị ạ."


def nhan_dang(text: str) -> str | None:
    """Tên ý định, hoặc None nếu không phải lượt thường gặp."""
    t = _chuan(text)
    if not t or len(t.split()) > TOI_DA_TU:
        return None
    for ten, mau, _ in BANG:
        if any(re.search(m, t) for m in mau):
            return ten
    return None


def tra_loi_san(text: str, *, bank: str, agent: str, product: str,
                luot_thu: int = 0) -> tuple[str, str] | None:
    """Trả (ý định, câu trả lời) nếu đây là lượt thường gặp, không thì None."""
    ten = nhan_dang(text)
    if ten is None:
        return None
    mau = next(c for t, _, c in BANG if t == ten)
    if mau is None:      # chao_bat_may
        mau = CHAO_DAU if luot_thu == 0 else CHAO_GIUA
    return ten, mau.format(bank=bank, agent=agent, product=product)
