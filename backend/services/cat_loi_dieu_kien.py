"""Khách gây tiếng trong lúc AI nói: có đáng dừng AI không?

Luật cũ dừng ngay khi có 80ms tiếng liên tục vượt ngưỡng (`VAD_ON_FRAMES=4`
trong `phone_call_service`). Ngưỡng đó bắt được cả tiếng ho, tiếng "dạ" khách
đế theo khi đang nghe, và tiếng AI vọng ngược vào micro của khách - ba thứ
không ai muốn cắt lời vì chúng.

Luật mới: dừng khi khách nói CÓ NGHĨA, hoặc nói QUÁ DÀI.

Module thuần - không đụng tiếng, không đụng mạng - để test được mà không cần GPU.
"""
import re

# Tiếng đế: khách phát ra trong lúc ĐANG NGHE để báo "tôi vẫn theo", không phải
# để giành lượt nói. Câu chỉ gồm những từ này thì dù dài bao nhiêu cũng không cắt.
TIENG_DE = {
    "dạ", "vâng", "ừ", "ừm", "à", "ờ", "ơ", "ok", "okê", "okay", "alo", "à lô",
    "hử", "hả", "hở", "rồi", "đúng", "phải", "vậy", "thế", "nghe", "em", "anh",
    "chị", "ạ", "à ừ", "uh", "um", "mm", "hmm",
    # "a lô" khi AI đang nói là khách thử đường truyền, không phải giành lượt.
    "a", "lô", "alô", "lo",
}

# Dưới ngưỡng này thì hai câu trùng nhau rất dễ là ngẫu nhiên, không đủ để kết
# luận là vọng tiếng AI.
_VONG_MIN_TU = 3
# Tỉ lệ từ của câu khách nằm trong lời AI, từ mức này coi là vọng.
_VONG_TI_LE = 0.7


def _chuan(chu: str) -> list[str]:
    """Về chữ thường, bỏ dấu câu, tách từ."""
    return re.sub(r"[^\w\sÀ-ỹ]", " ", (chu or "").lower()).split()


def la_tieng_de(chu: str) -> bool:
    """Câu chỉ gồm tiếng đế? Câu rỗng KHÔNG tính - chưa biết gì thì chưa kết luận."""
    tu = _chuan(chu)
    return bool(tu) and all(t in TIENG_DE for t in tu)


def la_vong_ai(chu: str, chu_ai: str) -> bool:
    """Câu nghe được thật ra là lời AI vọng ngược vào micro của khách?

    Đo 05-09-2026 (`scripts/do_dem_truoc.py`): vọng AI ở mức 30% làm PhoWhisper
    chép thẳng lời AI thành lời khách - CER 0,481 ở 500ms và 0,896 ở 800ms.
    Không có lưới này thì AI tự cắt lời chính nó.
    """
    tu = _chuan(chu)
    tu_ai = _chuan(chu_ai)
    cua_ai = set(tu_ai)
    if len(tu) == 2 and cua_ai:
        # Bản phiên âm tạm lúc phải quyết định thường mới có HAI từ. Cuộc gọi
        # 08-10-2026: AI nói "Dạ gói này hỗ trợ...", kênh khách nghe ra 'dạ
        # gói' sau 420ms và AI tự cắt lời mình - 5 lần trong một cuộc, kiểu
        # 'dạ phần', 'dạ cảm', 'dạ câu'. Hai từ trùng rời rạc thì dễ là ngẫu
        # nhiên, nên đòi chúng nằm LIỀN NHAU ĐÚNG THỨ TỰ trong lời AI. Khách nói
        # tiếp thì bản tạm dài ra và được xét lại theo tỉ lệ bên dưới.
        return any(tu_ai[i:i + 2] == tu for i in range(len(tu_ai) - 1))
    if len(tu) < _VONG_MIN_TU or not cua_ai:
        return False
    trung = sum(1 for t in tu if t in cua_ai)
    return trung / len(tu) >= _VONG_TI_LE


def nen_dung(tieng_ms: float, chu_tam: str, chu_ai: str,
             nguong_ms: float) -> bool:
    """Có nên dừng lượt AI đang nói không?

    `chu_tam` là phiên âm TẠM (`session.spec_stt`), thường về sau 0,8-1,1 giây
    kể từ khung tiếng đầu - tức MUỘN HƠN mốc thời lượng. Nên trong thực tế vế
    thời lượng mới là vế quyết định, còn phiên âm đóng vai lưới chặn ngược: đã
    quá ngưỡng nhưng hoá ra chỉ là tiếng đế hoặc tiếng AI vọng thì vẫn nói tiếp.
    """
    if chu_tam.strip():
        if la_tieng_de(chu_tam) or la_vong_ai(chu_tam, chu_ai):
            return False
        return True
    return tieng_ms >= nguong_ms


# Khách mở lời bằng những từ này nghĩa là họ cắt VÌ AI đang nói sai hướng, chứ
# không phải chen một câu hỏi bên lề. Đọc nốt đoạn cũ lúc đó là phản tác dụng.
TU_CHUYEN_HUONG = (
    "không", "khong", "khoan", "thôi", "dừng", "dừng lại", "chờ", "đợi",
    "ý em là", "ý anh là", "ý tôi là", "nhầm", "sai rồi", "chưa phải",
)

# Bắt khách nghe lại quá lâu trước khi được đáp là đổi một cái bực lấy cái khác.
TRAN_DOC_NOT_GIAY = 3.0


def nen_doc_not(phan_do_giay: float, cau_khach: str,
                tran_giay: float = TRAN_DOC_NOT_GIAY) -> bool:
    """Có nên đọc nốt phần câu cũ khách chưa kịp nghe, trước khi đáp câu mới?"""
    if phan_do_giay <= 0 or phan_do_giay > tran_giay:
        return False
    dau = " ".join(_chuan(cau_khach))
    return not any(dau.startswith(t) for t in TU_CHUYEN_HUONG)


# Câu dừng ở những từ này là câu CÒN DỞ: khách đang nghĩ nốt con số, kỳ hạn...
# chứ chưa nhường lượt. Xem `cau_con_do`.
_TU_CON_DO = {
    "trong", "vòng", "khoảng", "tầm", "là", "thì", "với", "và", "hoặc", "hay",
    "nhưng", "mà", "của", "cho", "về", "để", "vì", "nếu", "khi", "từ", "đến",
    "tới", "hơn", "dưới", "trên", "cùng", "tức", "nghĩa", "kiểu", "như",
    # Động từ/lượng từ còn thiếu vế sau: "thì bên em cho vay ..." rồi nghỉ một
    # nhịp mới nói "tối đa bao nhiêu tháng" (cuộc d1086216). Chờ thừa 0,9s ở
    # một câu hoá ra đã trọn thì chỉ chậm một chút; chốt non thì AI đáp bừa.
    "vay", "muốn", "cần", "hỏi", "những", "các", "mỗi", "bao", "sẽ", "đang",
    "bị", "gồm",
}


def cau_con_do(chu: str) -> bool:
    """Bản phiên âm tạm dừng ở một từ nối -> khách chưa nói hết câu.

    Cuộc gọi 08-10-2026: "thế anh muốn vay ba trăm triệu trong vòng" + nghỉ
    0,8s + "mười hai". Chốt lượt sau 700ms im làm câu vỡ đôi: AI đáp nửa đầu,
    rồi hỏi lại "anh vừa nói mười hai, tính theo triệu hay tỷ". Câu một-hai từ
    không tính (chưa đủ để biết là dở).
    """
    tu = _chuan(chu)
    return len(tu) >= 3 and tu[-1] in _TU_CON_DO


def la_vong_duoi_cau(chu: str, chu_ai: str) -> bool:
    """Lượt "khách" thật ra là ĐUÔI câu AI vừa nói vọng về sau khi AI dứt lời.

    Cuộc hai máy 08-10-2026: AI chào "... em là Lan bên Ngân hàng Quân đội ạ.",
    kênh khách trả về 'quân đội ạ' thành một lượt, AI đáp câu hẹn và nuốt mất
    câu hỏi thật ngay sau đó. Chỉ nhận khi lời nghe được trùng NGUYÊN ĐUÔI câu
    AI (2-6 từ): khách nhắc lại một cụm giữa câu để hỏi lại thì không bị chặn.
    """
    tu, tu_ai = _chuan(chu), _chuan(chu_ai)
    return 2 <= len(tu) <= 6 and len(tu_ai) > len(tu) and tu_ai[-len(tu):] == tu
