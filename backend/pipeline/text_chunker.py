"""Quyết định khi nào dồn đủ chữ để giao cho TTS.

Luật hiện tại (2026-08-11): cắt theo **NGUYÊN CÂU** - giao khi thấy dấu kết câu
(. ! ? …), trần chặn `TRAN_TU_MOT_CAU` từ nếu mãi không có dấu. Xem `CAT_THEO_CAU`
để biết vì sao, và `BO_DAU_CAU` bên tts_service cho nửa còn lại của thay đổi.

Ba lối cắt cùng tồn tại, cờ trên đè cờ dưới:
    CAT_THEO_CAU = True   cắt theo nguyên câu        <- đang chạy
    CAT_DON_GIAN = True   cắt cứng 5 từ, nối thẳng   (test_cat_don_gian.py)
    cả hai False          cắt thông minh ở dấu câu   (test_cat_manh.py)

Ba ràng buộc, cả ba đều từ lỗi thật đo được, đừng gỡ mà không đo lại:

1. KHÔNG bẻ đôi cụm số - "năm mươi" | "triệu" là hỏng nghĩa.
2. KHÔNG cắt ngay sau dấu phân cách nghìn - "142." | "500.000".
3. KHÔNG cắt vào token dở dang - LLM đẩy "ngay" thành "ng" rồi "ay".

Đuôi lượt ngắn hơn `TOI_THIEU_TU_MANH_CUOI` được `streaming_pipeline` gộp vào
mảnh trước, không gửi riêng: F5 sinh mỗi mảnh như một câu trọn vẹn, nên mảnh
"nhé." một từ nghe tách hẳn khỏi câu nó vốn thuộc về.
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
# 5 -> 16 TỪ (2026-08-10). Lý do bắt phải cắt nhỏ đã HẾT HIỆU LỰC: khi chọn 5 từ
# thì chưa có `cat_lang_bia` (bộ cắt quãng dừng F5 bịa). Đo lại sau khi có nó,
# trên đoạn 32 giây, cả ba mức đều 0 quãng bịa:
#
#   cắt      mảnh   mối nối   quãng bịa   chỗ ngắt nghe được   cứ ? giây
#   5 từ       29        28           0                   28       1,13s
#   10 từ      17        16           0                   18       1,78s
#   16 từ      15        14           0                   16       2,04s
#
# Người dùng: "khi nói 5 từ thì nó tự nhiên ngắt 1 tí rồi mới nói tiếp" - đúng,
# vì mỗi ranh giới mảnh được chèn NGHI_GIUA_CUM_MS. Mảnh 5 từ nghe 2 phút là
# hơn 100 lần ngắt, thành nhịp máy móc. Nghe ngắn thì không lộ.
#
# Mảnh to hơn còn giữ được nhiều ngữ điệu TRONG LÒNG mảnh - F5 sinh mỗi mảnh
# như một phát ngôn trọn vẹn, nên càng ít mảnh càng ít chỗ bị bẻ ngữ điệu.
#
# 16 -> 5 TỪ (2026-08-10), người dùng chốt: "bỏ hết logic tách đi, giờ dùng mỗi
# F5 tạo rồi nối 5 từ 1". Xem `CAT_DON_GIAN`.
GIOI_HAN_TU_MANH = 5

# Cắt MÁY MÓC hay cắt thông minh.
#
# Bật (mặc định, người dùng chốt 2026-08-10): cứ đủ `GIOI_HAN_TU_MANH` từ là
# giao, KHÔNG cắt sớm ở dấu câu, KHÔNG né cụm số, và KHÔNG chèn nhịp nghỉ nào
# giữa các mảnh - F5 sinh xong thì nối thẳng.
#
# Tắt: quay lại lối cắt thông minh mô tả ở khối chú thích trên.
#
# Một thứ được giữ lại ở CẢ HAI chế độ: chốt chặn cắt-giữa-token
# (`_tu_cuoi_da_tron`). Nó không phải luật cắt mà là chống hỏng chữ - LLM đẩy
# "ngay" thành "ng" rồi "ay", bỏ nó ra thì khách nghe đọc rời "ng" rồi "ay"
# (đã xảy ra trên máy thật, không phải giả định).
#
# Cái MẤT khi bật: cụm số bị bẻ đôi ("hai mươi" | "hai", "142." | "500.000").
# Đây là lỗi đã từng bắt được ngoài đời chứ không phải rủi ro lý thuyết. Muốn
# giữ riêng chốt chặn số mà vẫn cắt máy móc thì đặt CHAN_CUM_SO = True.
CAT_DON_GIAN = True
CHAN_CUM_SO = False

# Cắt theo NGUYÊN CÂU. Người dùng chốt 2026-08-11. ĐÈ LÊN cả hai cờ trên.
#
# Vì sao đổi lần nữa: đo quãng lặng trên đoạn 60 từ có 4 dấu (2 phẩy, 2 chấm),
# ngưỡng -40dB, tối thiểu 20ms:
#
#   bản đang chạy (tăng dần 5/10/20)   2 quãng   35ms, 38ms
#   người thật, 16 giây                22 quãng  21…1068ms, đông nhất 30-220ms
#
# Máy gần như không nghỉ ở đâu. Ba cơ chế cùng triệt tiêu quãng nghỉ, mỗi cái tự
# nó đã đủ: `bo_dau_cau_cho_f5` xoá sạch [,.;:!?…] nên F5 không còn dấu nào để
# nghỉ; `CAT_DON_GIAN` khiến `nhip_nghi_sau` trả 0; `trim_silence` dọn nốt quãng
# ở rìa mảnh. Cả ba đều thêm vào để chữa lỗi khác, đây là tác dụng phụ.
#
# Cắt theo câu chữa hai chỗ cùng lúc: dấu câu tới được F5 (xem `BO_DAU_CAU` bên
# tts_service) nên nó tự nghỉ ở phẩy, và mọi chỗ nối rơi đúng ranh giới câu -
# chỗ ĐÁNG hạ giọng - nên kiểu hỏng "hạ giọng kết câu giữa chừng" hết về mặt
# cấu trúc, không cần đo cũng biết.
#
# CÁI GIÁ, cả hai đều đã biết trước chứ không phải rủi ro lý thuyết:
#
#   TTFA. Cắt 5 từ bảo đảm tiếng ra sau ~295ms bất kể câu chữ thế nào. Cắt theo
#   câu thì phải đợi LLM nhả tới dấu chấm đầu tiên - câu đầu dài là khách chờ
#   lâu hơn hẳn. Đo trước khi tin.
#
#   Mảnh dài thì F5 TỰ BỊA quãng dừng giữa câu - 19 quãng 300-1600ms trên bản
#   ghi 111 giây (đo 2026-08-09). `cat_lang_bia` sinh ra để chặn đúng chỗ đó và
#   hiện đang thất nghiệp: đo 2026-08-11 nó không đổi một con số nào (CER, HNR,
#   độ dài đều y nguyên) vì đã không còn quãng lặng nào cho nó cắt. Cắt theo câu
#   là trả việc lại cho nó.
CAT_THEO_CAU = True

# Dấu kết câu.
DAU_KET_CAU_RE = re.compile(r"[.!?…]$")

# Dấu ngắt Ý giữa câu.
DAU_NGAT_Y_RE = re.compile(r"[,;:]$")

# TÁCH THÊM Ở DẤU PHẨY khi cả hai vế đủ dài.
#
# Bản trước để phẩy ở lại trong mảnh, với lý do "dấu câu tới được F5 nên nó tự
# nghỉ ở phẩy" - và ghi thẳng là "không cần đo cũng biết". ĐO RA THÌ SAI.
#
# Đối chứng 12-08-2026 (`scripts/do_nghi_o_phay.py`, hai cặp câu có/không phẩy,
# 3 lần mỗi bản, ngưỡng 8% đỉnh, tối thiểu 60ms):
#
#   "Em là Dương, chuyên viên…"  phẩy ở ~0,60s -> quãng nghỉ ở 1,49 / 1,62 / 1,65s
#   bản BỎ phẩy                                -> 1,56+1,75 / 1,62 / (không có)
#   "…cứ yên tâm, hồ sơ…"        phẩy ở ~1,0s  -> 0,34 / (không có) / 0,24s
#   bản BỎ phẩy                                -> 1,38 / 0,29+1,42+1,77 / (không có)
#
# KHÔNG quãng nào rơi vào vị trí dấu phẩy; số quãng hai bản gần như nhau (5 so
# với 7 trên 6 lượt) và vị trí đổi ngẫu nhiên mỗi lần sinh. Tức F5 nhận được
# phẩy nhưng LỜ nó, còn những quãng xuất hiện là nó tự bịa chỗ khác - đúng hai
# lời phàn nàn "đọc bị giãn giữa các từ" và "cảm giác đè lên nhau".
#
# Mà phẩy không phải chỗ cắt mảnh nên `nhip_nghi_sau` cũng không chèn gì. Kết
# quả: KHÔNG cơ chế nào tạo quãng nghỉ ở dấu phẩy. Người dùng nghe ra trước khi
# có số ("Đoạn 'em là dương, chuyên viên tư vấn' không ngắt dấu phẩy.wav").
TACH_O_PHAY = True

# Mỗi vế phải có ít nhất ngần này từ thì mới tách ở phẩy.
#
# Vì sao 3 chứ không phải 4: vế đầu của chính câu hỏng - "Em là Dương," - đúng 3
# từ. Lấy 4 thì ca hỏng đã báo vẫn không được chữa. Trùng luôn
# `TOI_THIEU_TU_MOT_CAU` nên hai luật cùng một quan niệm về "mảnh quá cụt".
#
# Chặn dưới có ý nghĩa thật: "Dạ," một từ mà tách riêng thì tốn trọn một lượt
# gọi F5 (~250ms chi phí cố định) để sinh 0,3 giây tiếng, và F5 sinh mỗi mảnh
# như một phát ngôn TRỌN VẸN nên vế cụt nghe tách hẳn khỏi câu nó thuộc về.
TOI_THIEU_TU_MOI_VE = 3

# NGẮT MỀM: câu dài mà KHÔNG có dấu phẩy nào thì tách trước một từ nối.
#
# Vì sao cần: câu dài không dấu phẩy thì `TACH_O_PHAY` không có chỗ nào để tách,
# mảnh giữ nguyên 20+ âm tiết và F5 đọc nhịp KHÔNG ĐỀU - lúc nhanh lúc chậm
# trong cùng một mảnh. Người dùng nghe ra trước khi có số: "'em nhận được thông
# tin' tự nhiên đọc nhanh hơn hẳn" và "giây 10-11 bị đè chữ".
#
# Đo 13-08-2026 (`scripts/do_nhip_theo_thoi_gian.py`, bộ đếm âm tiết đã kiểm
# chuẩn lệch 2%): trên câu 12,8 giây nhịp trung bình 320 âm tiết/phút nhưng vọt
# lên 404-468 ở hai chỗ, đúng hai chỗ khách chỉ ra, và hai chỗ đó nằm trong hai
# mảnh DÀI NHẤT (19 và 22 âm tiết).
#
# NGƯỠNG ĐẶT Ở ĐÂU: đo đối chứng nguyên-mảnh so với tách-đôi
# (`scripts/do_dai_manh.py`, 4 lần mỗi bản, độ lệch nhịp trong mảnh):
#
#   19 âm tiết:  nguyên 32%  |  tách 34%   <- tách KHÔNG giúp gì
#   22 âm tiết:  nguyên 49%  |  tách 33%   <- tách giúp rõ
#
# Nên chỉ đụng tới mảnh THẬT SỰ dài. 16 từ ≈ 20+ âm tiết (từ tiếng Việt nhiều
# chữ là 2 âm tiết), nằm giữa hai mốc đo được.
TRAN_TU_TRUOC_NGAT_MEM = 16

# Tách TRƯỚC những từ này - chỗ người thật cũng lấy hơi. Chỉ nhận từ nối MỆNH
# ĐỀ, không nhận từ nối trong lòng một cụm.
#
# Đã thử rồi loại: "của", "cho" (bẻ giữa cụm danh từ); "để" và "rồi" (dính vào
# động từ đứng trước - "vay ĐỂ làm gì", "gọi ĐỂ giới thiệu" là một ý liền, bẻ ở
# đó nghe gãy hơn là để nguyên câu dài). Bản đầu có "để" và nó cướp chỗ tách của
# "và" ngay trong câu mẫu, vì vòng quét đi từ trái sang.
TU_NGAT_MEM = {"và", "nhưng", "hoặc", "còn", "nên", "vì", "nếu"}

# Vế ĐẦU của ngắt mềm phải đủ dài. `TOI_THIEU_TU_MOI_VE` (3) là chặn dưới cho
# dấu phẩy - người viết đặt phẩy ở đâu là có ý ở đó. Ngắt mềm thì KHÔNG có ý
# người viết, nó là máy tự bẻ, nên chỉ được bẻ khi đã đọc được một quãng dài:
# bẻ ở từ thứ 3 của câu 20 từ là cắt vụn vô cớ.
TOI_THIEU_TU_VE_DAU_NGAT_MEM = 8

# Câu ngắn hơn ngần này thì GỘP vào câu sau thay vì giao riêng. "Dạ." một từ mà
# giao riêng thì tốn trọn một lượt gọi F5 (~250ms chi phí cố định cho đoạn mẫu)
# để sinh 0,3 giây tiếng, và F5 sinh mỗi mảnh như một phát ngôn trọn vẹn nên nó
# nghe tách hẳn khỏi câu vốn thuộc về.
TOI_THIEU_TU_MOT_CAU = 3

# Trần cắt cưỡng bức khi mãi không thấy dấu kết câu. Không có trần thì LLM nói
# lan man không chấm là giữ đệm mãi, khách nghe im.
#
# Vì sao 40: mảnh 11,5 giây tiếng là mức đo được F5 bắt đầu bịa quãng dừng
# (2026-08-09). Ở nhịp chuẩn 294 âm tiết/phút thì 11,5 giây ≈ 56 âm tiết. Lấy 40
# từ để còn khoảng dự trữ, vì từ tiếng Việt nhiều chữ là 2 âm tiết.
# CHƯA ĐO LẠI SAU KHI ĐỔI SANG CẮT THEO CÂU - đây là suy ra, không phải đo được.
TRAN_TU_MOT_CAU = 40

# Trần cho chốt chặn cụm số ở mốc cắt CƯỠNG BỨC. Phải có riêng vì
# `TRAN_CHO_CUM_SO_SAU` chỉ có 9 - nó tự TẮT khi mảnh quá 9 từ ("quá tran từ thì
# thôi không giữ nữa"), mà mốc cưỡng bức nằm ở 40. Dùng trần cũ thì chốt chặn
# vô hiệu hoàn toàn và "hai mươi | triệu" lại bị bẻ.
TRAN_CUM_SO_KHI_CUONG_BUC = TRAN_TU_MOT_CAU + 4

# Thiếu khoảng trắng sau dấu kết câu thì bộ cắt KHÔNG thấy ranh giới câu:
# `buffer.split()` coi "ạ.Dạ" là MỘT mẩu, không mẩu nào kết bằng dấu chấm, nên
# cả đoạn dồn lại tới khi chạm trần rồi bị cắt cưỡng bức GIỮA câu - mà cắt cưỡng
# bức thì `nhip_nghi_sau` trả 0, tức không có nhịp nghỉ nào.
#
# Đo 2026-08-12 trên đoạn 3 câu, cùng một nội dung:
#     "nghìn ạ.Dạ lãi suất"  -> 2 mảnh, quãng lặng 22ms       (khách nghe dính chữ)
#     "nghìn ạ. Dạ lãi suất" -> 3 mảnh, quãng lặng 227 + 211ms
#
# Chỉ thêm cách khi sau dấu là CHỮ CÁI, không phải chữ số: "7.9" và "142.500.000"
# phải giữ nguyên, thêm cách vào đó là bẻ đôi con số - lỗi thật đã gặp 2026-08-06.
_THIEU_CACH_RE = re.compile(r"([.!?…])(?=[^\W\d_])")


def them_cach_sau_dau(s: str) -> str:
    """Trả `s` với khoảng trắng chèn sau dấu kết câu khi thiếu. Số giữ nguyên."""
    return _THIEU_CACH_RE.sub(r"\1 ", s)

# Cỡ mảnh TĂNG DẦN theo thứ tự, thay vì cố định. Mảnh thứ i lấy cỡ thứ i, hết
# bảng thì giữ nguyên cỡ cuối.
#
# Vì sao: người dùng nghe thấy ở chỗ nối hai mảnh "có 1 điểm chậm và vẫn có dấu
# chấm". Đúng - F5 sinh MỖI MẢNH như một câu trọn vẹn nên cuối mảnh nó hạ giọng
# kết câu rồi kéo dài âm cuối, giữa lúc câu chưa hết. Càng nhiều mảnh càng nhiều
# chỗ như thế.
#
# CHỈ MẢNH ĐẦU cần nhỏ. Khi nó đã phát rồi thì máy còn cả giây tiếng trong tay,
# mà TTS sinh nhanh gấp 3,5 lần thời gian phát - nên mảnh sau tha hồ to.
#
# Đo trên đoạn 65 từ, 2 lượt mỗi cách (scripts/so_cach_tao_voice.py):
#
#   cách            mảnh  chỗ nối    TTFA  tổng sinh  âm cuối tệ nhất
#   đều 5 từ          13      12    298ms     3961ms      2,33x
#   đều 16 từ          5       4    439ms     1939ms      1,79x
#   TĂNG DẦN           4       3    296ms     1652ms      1,00x   <- chọn
#   cả câu một lần     1       0   1019ms     1020ms      1,05x
#
# "âm cuối" = âm tiết cuối mảnh dài gấp mấy lần âm tiết thường; to nghĩa là đang
# hạ giọng kết câu giữa chừng. Tăng dần ăn cả ba trục: tiếng đầu ra nhanh y hệt
# cắt 5 từ, ít hơn bốn lần chỗ nối, và hết sạch chỗ hạ giọng giả.
#
# Không để cỡ cuối là "hết phần còn lại": thế thì mảnh cuối phải đợi LLM sinh
# xong cả lượt mới giao được, tức đổi ngữ điệu lấy độ trễ ở đúng chỗ không nên.
CO_MANH_TANG_DAN = (5, 10, 20)


def co_manh(thu_tu: int) -> int:
    """Cỡ mảnh (số từ) cho mảnh thứ `thu_tu`, đếm từ 0."""
    if not CO_MANH_TANG_DAN:
        return GIOI_HAN_TU_MANH
    return CO_MANH_TANG_DAN[min(max(thu_tu, 0), len(CO_MANH_TANG_DAN) - 1)]

# Giữ tên cũ cho chỗ nào còn gọi tới; nay chỉ là trần chặn cụm số kéo dài.
GIOI_HAN_AN_TOAN = GIOI_HAN_TU_MANH

# Cắt ở dấu câu thì phải có ít nhất bấy nhiêu từ. Không có sàn này thì "Dạ," ra
# một mảnh 1 từ: tốn trọn một lượt gọi F5 (~250ms chi phí cố định cho đoạn mẫu)
# để sinh 0,3 giây tiếng, và mảnh quá ngắn thì sinh không kịp phát - đo được 3
# từ/mảnh gây 21 lần đói khung khi Ollama đang chạy.
TOI_THIEU_TU_KHI_CAT_O_DAU = 3

# Đuôi lượt ngắn hơn bấy nhiêu từ thì GỘP vào mảnh trước thay vì gửi riêng.
# Cắt cứ 5 từ một nên phần dư cuối lượt là bao nhiêu còn lại - thường 1-2 từ.
# Đo trên bản ghi 10 lượt: 3 lượt kết bằng mảnh 1-2 từ ("nhé.", "nhé ạ."), F5
# sinh chúng như MỘT CÂU HOÀN CHỈNH nên nghe tách hẳn khỏi câu trước.
TOI_THIEU_TU_MANH_CUOI = 3

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
# ĐẶT CỨNG từ 2026-08-09, không còn đo từ model nữa. Lý do: dấu câu đã bị bỏ
# khỏi chữ đưa vào F5 (`bo_dau_cau_cho_f5`) nên F5 không tự nghỉ ở dấu nào cả -
# toàn bộ nhịp nghỉ giờ do code chèn. Chèn bằng con số cố định thì mọi chỗ ngắt
# đều y hệt nhau, không còn chuyện chỗ nghỉ 160ms chỗ nghỉ 320ms tuỳ F5.
#
# Giá trị cũ (305/360) là ĐO TỪ MODEL - đúng khi F5 tự nghỉ và ta chỉ trả lại
# phần `trim_silence` cắt mất. Nay ta chèn TOÀN BỘ quãng nghỉ nên phải nhỏ hơn.
NGHI_PHAY_MS = 100.0
NGHI_CHAM_MS = 200.0

# Nghỉ ở ranh giới mảnh KHÔNG có dấu câu. Trước để 0 - và đó là chỗ hở.
#
# Đo F5 sinh cả câu một lần (19,32s, scripts/xem_nghi_tu_nhien.py): nó tự nghỉ ở
# 12 chỗ, dài nhất chỉ 120ms, và phần lớn nằm GIỮA CỤM TỪ chứ không ở dấu câu -
# đó là chỗ lấy hơi tự nhiên. Bản ghép mảnh chỉ nghỉ ở 4-6 chỗ có dấu, còn
# `trim_silence` thì cắt sạch lặng ở mọi mép mảnh. Kết quả: tiếng chạy liền một
# hơi, tổng ngắn hơn bản sinh một lần 1,6 giây trên cùng chữ.
#
# Người dùng nghe 0/40/60/90ms và thấy 40 lẫn 60 đều ổn. Chọn 50 - giữa hai
# mức đó, nhích về phía 40 vì đo ở 60ms cho ra 15 chỗ nghỉ trong khi bản sinh
# một lần chỉ có 8, tức hơi quá đà. Dải nghỉ tự nhiên đo được là 20-120ms.
NGHI_GIUA_CUM_MS = 50.0

DAU_KET_CAU = (".", "!", "?", "…")
DAU_NGAT_Y = (",", ";", ":")


def nhip_nghi_sau(chunk_text: str) -> float:
    """Sau mảnh này thì cần nghỉ bao lâu (ms) trước khi vào mảnh kế?"""
    if CAT_THEO_CAU:
        # Ranh giới mảnh là chỗ đáng nghỉ. Phải chèn chứ không nối thẳng:
        # `trim_silence` vừa dọn sạch quãng lặng hai đầu mảnh, không trả lại thì
        # hai câu dính vào nhau.
        #
        # Phẩy nghỉ NGẮN HƠN chấm. Trước đây nhánh này chỉ xét dấu kết câu, vì
        # tin rằng F5 tự nghỉ ở phẩy - đo ra thì nó LỜ hẳn, xem `TACH_O_PHAY`.
        t = chunk_text.rstrip()
        if t.endswith(DAU_KET_CAU):
            return NGHI_CHAM_MS
        if TACH_O_PHAY and t.endswith(DAU_NGAT_Y):
            return NGHI_PHAY_MS
        return 0.0
    if CAT_DON_GIAN:
        return 0.0          # nối thẳng, không chèn gì
    t = chunk_text.rstrip()
    if t.endswith(DAU_KET_CAU):
        return NGHI_CHAM_MS
    if t.endswith(DAU_NGAT_Y):
        return NGHI_PHAY_MS
    # Cắt giữa chừng vì hết ngưỡng từ. VẪN phải nghỉ một chút: F5 sinh cả câu
    # cũng tự nghỉ ở giữa cụm từ, mà trim_silence đã cắt mất chỗ đó.
    return NGHI_GIUA_CUM_MS


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


def _tach_theo_cau(tu: list[str], co_the: int,
                   buffer: str) -> tuple[str | None, str]:
    """Tách TRỌN MỘT CÂU ra khỏi đệm, hoặc `(None, buffer)` nếu chưa thấy hết câu.

    `co_the` là số mẩu chắc chắn đã viết xong - mẩu cuối chỉ trọn khi đã có token
    mới bắt đầu sau nó (xem `_tu_cuoi_da_tron`). Nhờ vậy dấu chấm vừa tới nơi
    KHÔNG được tin ngay: "ạ." có thể còn là nửa của "ạ..." đang gõ dở.
    """
    # Quét từ ngắn tới dài nên chỗ ngắt tới TRƯỚC luôn thắng, bất kể là dấu kết
    # câu hay dấu phẩy.
    for k in range(min(TOI_THIEU_TU_MOT_CAU, TOI_THIEU_TU_MOI_VE), co_the + 1):
        manh = " ".join(tu[:k])
        # "142." KHÔNG phải hết câu mà là dấu phân cách nghìn - lỗi thật
        # 2026-08-06, bản ghi lưu thành "142. 500.000". Cùng lưới này chặn luôn
        # "7,9": tiếng Việt dùng phẩy làm dấu thập phân.
        if _dang_giua_con_so(manh):
            continue
        if DAU_KET_CAU_RE.search(manh) and k >= TOI_THIEU_TU_MOT_CAU:
            return manh, " ".join(tu[k:])
        # Tách ở phẩy chỉ khi CẢ HAI vế đủ dài. Vế sau đếm trên phần đã chắc
        # chắn viết xong (`co_the`), nên lúc token còn đang chảy về thì hàm trả
        # None và đợi thêm - chứ không giao ra một vế cụt rồi mới biết là hụt.
        if (TACH_O_PHAY and DAU_NGAT_Y_RE.search(manh)
                and k >= TOI_THIEU_TU_MOI_VE
                and co_the - k >= TOI_THIEU_TU_MOI_VE):
            return manh, " ".join(tu[k:])
        # Ngắt mềm: câu DÀI mà chưa gặp dấu nào -> tách trước một từ nối.
        #
        # Điều kiện xét trên `co_the` (độ dài cả câu đang có) chứ KHÔNG xét vị
        # trí từ nối: từ nối thường rơi vào giữa câu, nên xét vị trí thì câu 23
        # từ có "và" ở từ thứ 15 vẫn trượt ngưỡng 16 và không bao giờ tách. Đúng
        # lỗi bản đầu tôi viết.
        if (co_the >= TRAN_TU_TRUOC_NGAT_MEM
                and k >= TOI_THIEU_TU_VE_DAU_NGAT_MEM
                and co_the - k >= TOI_THIEU_TU_MOI_VE
                and tu[k].strip(".,!?:;\"'").lower() in TU_NGAT_MEM):
            return manh, " ".join(tu[k:])

    # Chưa thấy dấu kết câu nào. Đợi thêm token, TRỪ KHI đã quá trần: LLM nói lan
    # man không chấm thì đợi mãi là khách nghe im.
    if co_the < TRAN_TU_MOT_CAU:
        return None, buffer

    k = TRAN_TU_MOT_CAU
    while (_dang_giua_cum_so(" ".join(tu[:k]), tu[:k], TRAN_CUM_SO_KHI_CUONG_BUC)
           or _dang_giua_con_so(" ".join(tu[:k]))):
        k += 1
        if k > co_the:
            return None, buffer
    return " ".join(tu[:k]), " ".join(tu[k:])


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
    # Vá chữ dính TRƯỚC khi tách mẩu: `split()` coi "ạ.Dạ" là một mẩu nên không
    # mẩu nào kết bằng dấu chấm, và mọi luật bên dưới mù với ranh giới câu.
    # Đặt ở đây, trong `tach_manh`, để CẢ đường gọi thật lẫn trang nghe thử cùng
    # được vá - `normalize_for_tts` chạy trong `synthesize`, tức SAU khi cắt, nên
    # sửa ở đó không giúp gì cho việc cắt.
    buffer = them_cach_sau_dau(buffer)
    tu = buffer.split()
    if not tu:
        return None, buffer

    # Đệm kết thúc bằng khoảng trắng/dấu câu thì mẩu cuối cũng đã trọn.
    co_the = len(tu) if _tu_cuoi_da_tron(buffer) else len(tu) - 1

    # Cắt theo NGUYÊN CÂU đè lên mọi luật đếm từ. `n` bị bỏ qua ở chế độ này -
    # bên gọi vẫn truyền `co_manh(idx)` nhưng cỡ mảnh giờ do dấu câu quyết định,
    # chỉ còn `TRAN_TU_MOT_CAU` làm trần chặn.
    if CAT_THEO_CAU:
        return _tach_theo_cau(tu, co_the, buffer)

    if CAT_DON_GIAN:
        if co_the < n:
            return None, buffer
        if not CHAN_CUM_SO:
            return " ".join(tu[:n]), " ".join(tu[n:])
        k = n
        while _dang_giua_cum_so(" ".join(tu[:k]), tu[:k], TRAN_CHO_CUM_SO_SAU) \
                or _dang_giua_con_so(" ".join(tu[:k])):
            k += 1
            if k > co_the:
                return None, buffer
        return " ".join(tu[:k]), " ".join(tu[k:])

    # Cắt Ở DẤU CÂU nếu dấu tới trước mốc `n` từ.
    #
    # Vì sao cần: từ 2026-08-09 dấu câu bị bỏ khỏi chữ đưa vào F5
    # (`bo_dau_cau_cho_f5`) để nhịp đọc đều. Nhưng thế thì dấu nằm GIỮA mảnh
    # mất luôn quãng nghỉ - F5 không nghỉ nữa, mà code cũng không chèn vì chỗ đó
    # không phải ranh giới mảnh. Câu nọ dính câu kia.
    #
    # Cắt ở dấu thì dấu luôn rơi vào ranh giới mảnh, và `nhip_nghi_sau` chèn
    # đúng lượng lặng cố định. Không tốn thêm lượt gọi F5 nào - vẫn là cắt, chỉ
    # là cắt sớm hơn vài từ.
    if co_the >= TOI_THIEU_TU_KHI_CAT_O_DAU:
        for k in range(TOI_THIEU_TU_KHI_CAT_O_DAU, min(co_the, n) + 1):
            manh = " ".join(tu[:k])
            if manh.endswith(tuple(FLUSH_PUNCTUATION)) and not _dang_giua_con_so(manh):
                return manh, " ".join(tu[k:])

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
