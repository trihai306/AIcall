"""Quyết định khi nào dồn đủ chữ để giao cho TTS.

Vì sao chỗ cắt quan trọng hơn vẻ ngoài của nó: F5-TTS mỗi lần gọi sinh ra MỘT
PHÁT NGÔN TRỌN VẸN - có đường lên mở đầu và đường xuống kết thúc. Cắt giữa mệnh
đề thì nửa đầu được đọc như đã nói xong, nửa sau mở ra như câu mới. Đo được
(2026-08-03) trên câu 43 từ bị cắt thành 7 mảnh: mảnh GIỮA CÂU kết thúc với độ
dốc F0 -4.14 nửa cung/100ms, gần như không phân biệt được với mảnh kết câu thật
(-4.31). Và tệ nhất là cắt vỡ cụm số:

    "bên em hiện tại là sáu phẩy năm" | "phần trăm một năm,"
    "áp dụng cho khoản vay từ năm mươi" | "triệu trở lên,"

NGÂN SÁCH THỜI GIAN: chỉ MẢNH ĐẦU ảnh hưởng tới thời gian khách chờ tiếng đầu
tiên. Các mảnh sau được sinh trong lúc mảnh trước đang phát, mà TTS chạy ~15 lần
thời gian thực (mảnh 20 từ ~ 5s tiếng, sinh mất ~330ms) - tức mảnh sau to lên
gần như miễn phí. Nên mảnh đầu cắt gắt cho nhanh, mảnh sau cắt thưa cho tự nhiên.
"""

import re

FLUSH_PUNCTUATION = {".", "!", "?", ",", ":", ";", "..."}
VI_SENTENCE_ENDERS = {"ạ", "ạ.", "ạ,", "nhé", "nhé.", "nhỉ", "ạ?"}

# Từ mà sau nó gần như chắc chắn còn phần nữa của cùng một cụm số/đơn vị. Cắt
# ngay sau những từ này là bẻ đôi con số - "năm mươi" | "triệu", "sáu phẩy năm" |
# "phần trăm". Chỉ chặn khi buffer KHÔNG kết thúc bằng dấu câu: có dấu câu nghĩa
# là cụm đã đóng ("phần trăm một năm," cắt được).
SO_DEM = {
    "không", "một", "mốt", "hai", "ba", "bốn", "tư", "năm", "lăm", "sáu",
    "bảy", "tám", "chín", "mười", "mươi", "trăm", "nghìn", "ngàn", "triệu",
    "tỷ", "tỉ", "phẩy", "phết", "rưỡi", "linh", "lẻ",
    # mở đầu đơn vị hai chữ: "phần trăm", "phần nghìn" - cắt sau "phần" là hỏng
    "phần",
    # đứng TRƯỚC số: cắt sau chúng là tách số khỏi thứ bổ nghĩa cho nó
    # ("khoảng | năm triệu", "từ | năm mươi triệu")
    "khoảng", "gần", "hơn", "trên", "dưới", "tầm", "chừng", "từ", "đến", "tới",
}

# Mảnh sau: ngưỡng an toàn thôi, KHÔNG phải chỗ cắt mong muốn. Chỗ cắt mong muốn
# luôn là dấu câu. Để 8 như trước là cắt giữa mệnh đề ở gần như mọi câu dài.
GIOI_HAN_AN_TOAN = 24

# Mảnh đầu: chỗ DUY NHẤT đánh đổi ngữ điệu lấy thời gian khách chờ tiếng đầu.
# Để 6 như trước thì bẻ cả từ ghép ("... thì trả" | "góp 36 tháng") và chỉ 1/6
# mảnh đầu kết thúc ở dấu câu. Đo trên 6 câu tổng đài thật:
#     6 từ -> 1/6 mảnh đầu kết ở dấu câu
#     9 từ -> 2/6,  tốn thêm  +55ms
#    12 từ -> 4/6,  tốn thêm +107ms   <- đang dùng
# Giá đo bằng scripts/do_gia_manh_dau.py (16 mẫu/mức, xen kẽ, bỏ lượt khởi động),
# gồm cả phần LLM phải sinh thêm chữ. TTFA trước đó 739-825ms, trần 1000ms.
GIOI_HAN_MANH_DAU = 12

# Trần cho phép chặn-vì-đang-giữa-cụm-số kéo dài. Không có trần thì một chuỗi
# toàn từ số ("một hai ba bốn...") giữ buffer mãi không giao - mảnh đầu mà kẹt
# thế thì khách chờ tiếng đầu lâu hẳn ra.
# PHẢI CAO HƠN ngưỡng cắt, không phải bằng: để bằng thì guard hết hiệu lực đúng
# lúc ngưỡng cắt kích hoạt, và cụm số vẫn bị bẻ ("... là sáu" | "phẩy năm ...").
# Chênh 4 từ là đủ cho cụm số dài nhất thường gặp ("sáu phẩy năm phần trăm").
TRAN_CHO_CUM_SO_DAU = GIOI_HAN_MANH_DAU + 4
TRAN_CHO_CUM_SO_SAU = GIOI_HAN_AN_TOAN + 12


# Nhịp nghỉ cần trả lại sau mỗi mảnh, tính bằng ms. ĐO TỪ CHÍNH MODEL chứ không
# chọn cho đẹp: sinh cả câu một lần rồi đo quãng lặng bên trong
# (scripts/do_nhip_nghi.py, 5 câu mỗi loại) - dấu phẩy trung vị 356ms (dải
# 260-573), dấu chấm 411ms (dải 198-596).
# Trừ đi ~50ms vì trim_silence đã chừa lại 25ms ở mỗi đầu mảnh, ranh giới sẵn có
# chừng đó rồi.
NGHI_PHAY_MS = 305.0
NGHI_CHAM_MS = 360.0

DAU_KET_CAU = (".", "!", "?", "…")
DAU_NGAT_Y = (",", ";", ":")


def nhip_nghi_sau(chunk_text: str) -> float:
    """Sau mảnh này thì cần nghỉ bao lâu (ms) trước khi vào mảnh kế?"""
    t = chunk_text.rstrip()
    if t.endswith(DAU_KET_CAU):
        return NGHI_CHAM_MS
    if t.endswith(DAU_NGAT_Y):
        return NGHI_PHAY_MS
    return 0.0          # cắt giữa chừng vì hết ngưỡng - không có nhịp nghỉ nào cả


def _dang_giua_cum_so(stripped: str, words: list[str], tran: int) -> bool:
    """Buffer có đang dừng giữa một cụm số không?

    Có dấu câu ở cuối nghĩa là cụm đã đóng ("phần trăm một năm," cắt được).
    Quá `tran` từ thì thôi không giữ nữa - lúc đó nhiều khả năng không phải cụm số.
    """
    if stripped.endswith(tuple(FLUSH_PUNCTUATION)):
        return False
    if len(words) >= tran:
        return False
    cuoi = words[-1].strip(".,!?:;").lower()
    return cuoi in SO_DEM or cuoi.isdigit()


def _dang_giua_con_so(stripped: str) -> bool:
    """Dấu chấm/phẩy cuối đệm có phải dấu PHÂN CÁCH NGHÌN không?

    Tiếng Việt viết tiền là "142.500.000". Bộ cắt thấy đệm kết thúc bằng "142."
    là tưởng hết câu và cắt luôn -> TTS đọc "một trăm bốn mươi hai" rồi mới tới
    "năm trăm nghìn", và bản ghi lưu thành "142. 500.000".

    Bắt được 2026-08-06 ngay lượt đầu tiên bot đọc đúng dư nợ tra từ CSDL - tức
    lỗi này chỉ lộ ra khi hệ thống bắt đầu nói ra số tiền thật.
    """
    return bool(_SO_CHUA_XONG_RE.search(stripped))


# "… 142." hoặc "… 142,"  - chữ số ngay trước dấu, không có khoảng trắng.
_SO_CHUA_XONG_RE = re.compile(r"\d[.,]$")


def _tu_cuoi_da_tron(buffer: str) -> bool:
    """Từ cuối trong đệm đã viết xong chưa?

    LLM trả về TOKEN chứ không phải từ: "ngay" tới nơi thành "ng" rồi "ay". Bộ
    đếm từ ở dưới đếm bằng split() nên coi "ng" là một từ hoàn chỉnh, và nếu vừa
    đúng lúc đó chạm ngưỡng thì mảnh bị cắt GIỮA TỪ.

    Đã bắt được trên máy thật: câu "Dạ em xin phép kiểm tra lại và báo anh chị
    ngay ạ" chạm mốc 12 từ đúng tại "ng" -> TTS nhận hai mảnh "…anh chị ng" và
    "ay ạ", tức khách nghe thấy đọc rời "ng" rồi "ay". Bản ghi lưu lại cũng thành
    "báo anh chị ng ay ạ".

    Chỉ cần đợi thêm ĐÚNG MỘT token: khi đệm kết thúc bằng khoảng trắng hay dấu
    câu thì từ cuối chắc chắn đã trọn.
    """
    return bool(buffer) and (buffer[-1].isspace() or buffer[-1] in _KY_TU_DONG_TU)


# Dấu câu đủ để khẳng định từ trước nó đã viết xong.
_KY_TU_DONG_TU = ".,!?:;…)\"'"


def should_flush(buffer: str, word_threshold: int = GIOI_HAN_AN_TOAN,
                 first_chunk: bool = False) -> bool:
    """Đã đủ chữ để giao mảnh này cho TTS chưa?

    first_chunk=True: cắt sớm để rút thời gian chờ tiếng đầu - từ 2 từ nếu gặp
    dấu câu, hoặc GIOI_HAN_MANH_DAU từ bất kể. Đây là chỗ DUY NHẤT đánh đổi ngữ
    điệu lấy tốc độ.
    Mảnh sau: chỉ cắt ở dấu câu; ngưỡng từ chỉ là van an toàn cho câu dài không
    có dấu, và vẫn không cắt giữa cụm số.
    """
    stripped = buffer.strip()
    if not stripped:
        return False

    words = stripped.split()

    if first_chunk:
        # Ngưỡng giữ nguyên như cũ: đây là cần gạt cho TTFA, không phải cho ngữ
        # điệu. Nhưng chặn cụm số thì áp cả ở đây - bẻ đôi con số là hỏng hẳn
        # nghĩa, không đáng đánh đổi lấy vài chục mili giây.
        if _dang_giua_cum_so(stripped, words, TRAN_CHO_CUM_SO_DAU):
            return False
        if len(words) >= GIOI_HAN_MANH_DAU:
            # Cắt theo ĐẾM TỪ mới cần canh: mảnh kết thúc bằng dấu câu ở dưới thì
            # tự nó đã đảm bảo từ cuối trọn vẹn.
            return _tu_cuoi_da_tron(buffer)
        if stripped.endswith(tuple(FLUSH_PUNCTUATION)):
            # "142." là dấu phân cách nghìn, không phải hết câu.
            return len(words) >= 2 and not _dang_giua_con_so(stripped)
        if words[-1].rstrip(".,!?") in VI_SENTENCE_ENDERS:
            return len(words) >= 2
        return False

    # Không bao giờ bẻ đôi một con số - kể cả khi đã quá ngưỡng an toàn. Thà mảnh
    # dài hơn vài từ còn hơn để khách nghe "năm mươi" rồi mới tới "triệu".
    if _dang_giua_cum_so(stripped, words, TRAN_CHO_CUM_SO_SAU):
        return False

    if stripped.endswith(tuple(FLUSH_PUNCTUATION)):
        return len(words) >= 3 and not _dang_giua_con_so(stripped)

    if words[-1].rstrip(".,!?") in VI_SENTENCE_ENDERS:
        return len(words) >= 2

    return len(words) >= word_threshold and _tu_cuoi_da_tron(buffer)
