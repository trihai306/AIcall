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

# Chỉ còn dùng để nhận ra "cụm số đã đóng" trong `_dang_giua_cum_so`. Từ
# 2026-08-09 dấu câu KHÔNG còn là chỗ cắt mảnh nữa - xem `GIOI_HAN_TU_MANH`.
FLUSH_PUNCTUATION = {".", "!", "?", ",", ":", ";", "..."}

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

# Cắt CỐ ĐỊNH mỗi 5 từ - đổi từ "cắt ở dấu câu" ngày 2026-08-09.
#
# Vì sao đổi hẳn triết lý: cắt ở dấu câu cho ra mảnh dài tới 11,5 giây tiếng, mà
# F5 sinh đoạn dài thì TỰ BỊA quãng dừng giữa câu. Đo trên bản ghi hội thoại
# thật 111 giây: 19 quãng lặng 300-1600ms nằm SÂU TRONG LÒNG một mảnh, không
# phải chỗ nối mảnh. Khách nghe thành "đang nói tự nhiên dừng rồi bật lên".
#
# Đã đuổi nguyên nhân qua bốn giả thuyết và SAI cả bốn: nfe thấp, checkpoint
# fine-tune, dấu "/" và "-" trong "CMND/CCCD", và độ dài văn bản (F5 thuần sạch
# 0/8 tới 52 âm tiết). Hoá ra chỉ cần đừng đưa cho nó đoạn 11 giây.
#
# Đo đối chứng cùng một đoạn văn, cùng lúc Ollama đang sinh token
# (scripts/thu_manh_5_tu.py):
#
#   cách cắt        mảnh   tiếng đầu   tổng sinh   quãng lặng > 250ms
#   dấu câu (cũ)       6      467ms       5.14s    1  (580ms)
#   8 từ              11      574ms       8.27s    0
#   5 từ              18      724ms      12.82s    0   <- đang dùng, người dùng chọn
#   3 từ              29      648ms      19.36s    3  (940ms) + 21 chỗ đói khung
#
# Mảnh ngắn thì F5 không còn chỗ để bịa. 3 từ thì ngược lại - sinh không kịp
# phát, đói khung 21 lần. Có cả ngưỡng trên lẫn ngưỡng dưới, 5 nằm giữa.
#
# Giá phải trả: 2,5 lần thời gian GPU và tiếng đầu chậm hơn ~250ms. Người dùng
# nghe cả bốn bản rồi chọn 5 từ ("ổn hơn nhiều mấy cái kia").
GIOI_HAN_TU_MANH = 5

# Giữ tên cũ cho chỗ nào còn gọi tới; nay chỉ là trần chặn cụm số kéo dài.
GIOI_HAN_AN_TOAN = GIOI_HAN_TU_MANH

# Trần cho phép chặn-vì-đang-giữa-cụm-số kéo dài. Không có trần thì một chuỗi
# toàn từ số ("một hai ba bốn...") giữ buffer mãi không giao.
# PHẢI CAO HƠN ngưỡng cắt, không phải bằng: để bằng thì guard hết hiệu lực đúng
# lúc ngưỡng cắt kích hoạt, và cụm số vẫn bị bẻ ("... là sáu" | "phẩy năm ...").
# Chênh 4 từ là đủ cho cụm số dài nhất thường gặp ("sáu phẩy năm phần trăm").
TRAN_CHO_CUM_SO_DAU = GIOI_HAN_TU_MANH + 4
TRAN_CHO_CUM_SO_SAU = TRAN_CHO_CUM_SO_DAU


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


def tach_manh(buffer: str, n: int = GIOI_HAN_TU_MANH,
              first_chunk: bool = False) -> tuple[str | None, str]:
    """Tách `n` từ đầu ra khỏi đệm. Trả `(mảnh, phần còn lại)`.

    Trả `(None, buffer)` nếu chưa đủ chữ - lúc đó cứ dồn thêm token rồi hỏi lại.

    VÌ SAO phải tách chứ không chỉ trả lời có/không như `should_flush` cũ: LLM
    đẩy ra TOKEN chứ không phải từ, "ngay" tới nơi thành "ng" rồi "ay". Giao cả
    đệm đúng lúc đó là cắt giữa từ, khách nghe "ng" rồi "ay" (đã bắt được trên
    máy thật). Bản `should_flush` cũ chống bằng cách đòi đệm kết thúc bằng
    khoảng trắng hoặc dấu câu - nhưng token của Ollama mang dấu cách ở ĐẦU
    (" ngay"), nên điều kiện đó gần như không bao giờ đúng giữa câu, và luật cắt
    theo số từ trên thực tế chỉ chạy được ở chỗ có dấu câu.

    Cách chắc chắn: chỉ coi một từ là đã trọn khi có token MỚI bắt đầu sau nó.
    Nên khi đệm có `n+1` mẩu thì `n` mẩu đầu chắc chắn trọn - giao đúng `n` đó,
    giữ mẩu cuối lại cho lượt sau.
    """
    tu = buffer.split()
    if not tu:
        return None, buffer

    # Đệm kết thúc bằng khoảng trắng/dấu câu thì mẩu cuối cũng đã trọn.
    co_the = len(tu) if _tu_cuoi_da_tron(buffer) else len(tu) - 1
    if co_the < n:
        return None, buffer

    tran = TRAN_CHO_CUM_SO_DAU if first_chunk else TRAN_CHO_CUM_SO_SAU
    k = n
    while True:
        manh = " ".join(tu[:k])
        # Hai chỗ TUYỆT ĐỐI không được cắt vào:
        #   - giữa một cụm số: "năm mươi" | "triệu"
        #   - ngay sau dấu phân cách nghìn: "142." | "500.000"  (lỗi 2026-08-06)
        # Vướng thì lùi chỗ cắt sang phải một từ rồi thử lại.
        if not (_dang_giua_cum_so(manh, tu[:k], tran) or _dang_giua_con_so(manh)):
            break
        k += 1
        # Lùi hết chữ đang có mà vẫn vướng thì CHƯA cắt - đợi thêm token. Kiểm
        # điều kiện này SAU khi tăng k, và kiểm cả khi k mới bằng n: vòng lặp
        # bản đầu viết `while k < co_the` nên khi đệm có đúng n từ thì thân vòng
        # không chạy lần nào, hai chốt chặn trên bị bỏ qua sạch.
        if k > co_the:
            return None, buffer

    return " ".join(tu[:k]), " ".join(tu[k:])


def should_flush(buffer: str, word_threshold: int = GIOI_HAN_TU_MANH,
                 first_chunk: bool = False) -> bool:
    """Đã đủ chữ để tách được một mảnh chưa?

    Chỉ là vị từ đi kèm `tach_manh` - đường chạy thật dùng `tach_manh` vì nó còn
    trả về phần đệm còn lại. Giữ hàm này cho các script đo đang gọi tới.
    """
    return tach_manh(buffer, word_threshold, first_chunk)[0] is not None
