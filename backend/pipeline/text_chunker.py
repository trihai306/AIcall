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
# ĐÃ LÀ 3, ĐỔI THÀNH 4 ngày 13-08-2026. Đây là chỗ hai lần góp ý của người dùng
# đánh nhau, và cả hai đều về ĐÚNG một câu:
#     Lần 4: "đoạn 'em là dương, chuyên viên tư vấn' không ngắt dấu phẩy"
#     Lần 5: "bị giật cục chữ 'Dương' giây 2"
# Ngưỡng 3 tách được đúng chỗ họ muốn, nhưng vế đầu chỉ 3 từ nên nửa giây đầu bị
# chẻ làm ba mẩu. Đo (`scripts/thu_nguong_phay.py`), cùng câu, chỉ đổi ngưỡng:
#     ngưỡng 3   3 mảnh [4, 3, 10 từ]   quãng lặng 0,80s(200ms) VÀ 1,45s(125ms)
#     ngưỡng 4+  2 mảnh [4, 13 từ]      quãng lặng 0,80s(200ms)
# Hai chỗ dừng trong 1,5 giây đầu chính là thứ nghe ra "giật cục".
#
# Ngưỡng 4 KHÔNG bỏ hết chỗ ngắt phẩy - vế dài vẫn tách. Câu người dùng gửi kèm
# ở Lần 5 ("Dạ, đối với mục đích kinh doanh hoặc tiêu dùng sửa nhà,") có vế đầu
# 12 từ, vẫn tách như cũ, và họ không kêu chỗ đó.
#
# Chặn dưới có ý nghĩa thật: "Dạ," một từ mà tách riêng thì tốn trọn một lượt
# gọi F5 (~250ms chi phí cố định) để sinh 0,3 giây tiếng, và F5 sinh mỗi mảnh
# như một phát ngôn TRỌN VẸN nên vế cụt nghe tách hẳn khỏi câu nó thuộc về.
TOI_THIEU_TU_MOI_VE = 4

# Tiếng đáp mở đầu lượt được MIỄN ngưỡng trên và tách thành mảnh riêng.
#
# Vì sao phải miễn: người dùng báo ba lần liền "sau chữ 'dạ'/'vâng' có dấu phẩy
# nhưng đọc liền" (Lần 4, Lần 6 hai lần). Đo ra thì KHÔNG CÓ CƠ CHẾ NÀO tạo được
# quãng nghỉ ở đó: F5 lờ dấu phẩy (đo 0/6), còn nhịp nghỉ do code chèn thì chỉ
# chèn GIỮA HAI MẢNH - mà "Dạ," một từ thì không bao giờ đủ ngưỡng để thành mảnh.
# Hai chỗ đều đúng luật của mình, chỗ hỏng nằm ở giữa.
#
# Chỉ miễn cho ĐÚNG mấy tiếng đáp này, không nới ngưỡng chung: ngưỡng 4 sinh ra
# để chữa "giật cục chữ Dương" ở Lần 5, hạ nó xuống là lỗi đó quay lại.
#
# Vế sau vẫn phải đủ dài - không thì "Dạ, vâng ạ." tách thành hai mẩu cụt.
#
# GỠ "vâng ạ" và "dạ vâng ạ" ngày 15-08-2026. Chúng kết bằng "ạ", mà tách ở đó
# chính là lỗi người dùng báo: "voice cái chữ 'ạ' ở cuối cũng rất hay bị tách,
# nghe lạc quê hẳn". Xem `_ket_bang_tieu_tu` để biết vì sao tách sau "ạ" là hỏng.
# "dạ" / "vâng" / "dạ vâng" GIỮ NGUYÊN - quãng nghỉ sau chúng là thứ người dùng
# đòi ba lần liền, gỡ nốt là lỗi cũ quay lại.
MO_DAU_TACH_RIENG = frozenset({"dạ", "vâng", "dạ vâng"})


def _la_tieng_dap_mo_dau(manh: str) -> bool:
    """Mảnh này có phải tiếng đáp mở đầu lượt không (đã kèm dấu phẩy)."""
    return manh.strip().rstrip(",;:").strip().lower() in MO_DAU_TACH_RIENG


# Tiểu từ lễ phép cuối vế. KHÔNG được cắt mảnh ngay sau chúng.
#
# Vì sao: F5 sinh MỖI MẢNH như một phát ngôn trọn vẹn. Tiểu từ tiếng Việt không
# đứng một mình được - nó bám vào vế trước nó. Cắt ngay sau "ạ" thì "ạ" trở
# thành âm tiết cuối của một câu riêng, và code chèn thêm NGHI_PHAY_MS vào ngay
# sau đó, nên khách nghe nó rời hẳn ra.
#
# Đo 15-08-2026 trên máy Windows, CÙNG một câu, chỉ khác dấu phẩy:
#     "Vâng ạ, lãi suất … một năm ạ."   2 mảnh, LẶNG 210ms ngay sau "ạ"
#     "Vâng ạ lãi suất … một năm ạ."    1 mảnh, KHÔNG quãng lặng nào
#     "Được 500 triệu đồng ạ, hạn mức…" 2 mảnh, LẶNG 230ms ngay sau "ạ"
#
# ĐÃ BÁC BỎ hai giả thuyết khác, đừng đo lại: F5 KHÔNG kéo dài âm cuối mảnh ("ạ"
# cuối 220ms so với giữa 240ms), và F5 KHÔNG tự chèn quãng nghỉ trước chữ cuối
# (soi mảnh đơn kết bằng "ạ"/"trăm"/"nhé": 0 quãng lặng ở cuối cả ba). Lỗi nằm ở
# LUẬT CẮT, không nằm trong model - nên đừng đụng vào nfe hay tốc đọc.
#
# Chỉ chặn ở dấu PHẨY. Dấu chấm vẫn cắt bình thường: hết câu thì "ạ." đáng được
# hạ giọng, đó là ngữ điệu đúng chứ không phải lỗi.
TIEU_TU_CUOI_VE = frozenset({"ạ", "nhé", "nha", "nhá", "nhỉ", "à", "ấy"})


def _ket_bang_tieu_tu(manh: str) -> bool:
    """Vế này có kết bằng tiểu từ lễ phép không (bỏ dấu phẩy ở cuối ra)."""
    tu = manh.rstrip(",;: ").split()
    return bool(tu) and tu[-1].strip(".,!?:;\"'").lower() in TIEU_TU_CUOI_VE

def nen_duoi_manh_nay(manh: str) -> bool:
    """Có nên nén đuôi mảnh này không? CHỈ khi nó kết bằng tiểu từ.

    Bên A nghe ra (17-08): *"chữ ạ nó cứ nặng kiểu gì á, ạ nặng cái rồi mới
    nói"*. Đo trên tệp 4 bộ Lần 9: chữ "ạ" cuối mảnh dài **480ms, tức 2,4 lần**
    âm tiết thường - F5 kéo dài âm cuối mảnh, và ở tiểu từ thì nghe thành một
    tiếng nặng trịch rồi mới đi tiếp.

    ĐÃ LOẠI: bốn thước đo về CHẤT giọng đều không tách được bản bên A chê khỏi
    bản bên A khen - độ dài tuyệt đối (380ms chê / 600ms khen), đường cao độ (cả
    hai đi lên), cao độ so với giọng câu (+22% / +30%), và độ rè (9,2% chê /
    14,4% khen, tức bản KHEN còn rè hơn). Nên vấn đề không phải âm sắc mà là
    NHỊP: tiểu từ bị kéo quá dài.

    VÌ SAO CHỈ TIỂU TỪ. Nén mọi đuôi mảnh thì WER 0,94% -> 1,79% mà tổng chỗ
    ngân chỉ giảm 17 -> 15. Tiểu từ ("ạ", "nhé"...) không mang nội dung nên nén
    an toàn; còn từ nội dung ở cuối câu thì kéo dài là ngữ điệu ĐÚNG, đụng vào
    là vừa mất tự nhiên vừa mất chữ.
    """
    return _ket_bang_tieu_tu(manh)


# NGẮT MỀM: TẮT. Giữ code lại vì lý do bên dưới đáng ghi hơn là xoá.
#
# Bật ngày 13-08 rồi TẮT cùng ngày. Nó được quyết định trên số đo lấy từ một bản
# code ĐÃ HỒI QUY: nhánh này thiếu bản vá `HE_SO_BU_LANG` 1.11 -> 0.85 của main,
# và tôi còn đẩy bản cũ đó đè lên máy Windows nên đo trên chính bản sai.
#
# Cấp dư thời lượng thì F5 nhồi im lặng, nên mảnh dài "hỏng" theo một kiểu khác
# hẳn - và tách đôi trông như có ích. Đo lại sau khi gộp main (hạt giống đã cố
# định nên số tất định, 4/4 lần giống nhau):
#
#   19 âm tiết:  nguyên 35%  |  tách 13%
#   22 âm tiết:  nguyên 26%  |  tách 36%   <- tách LÀM TỆ HƠN
#
# Trên bản hồi quy tôi đo ra ngược hẳn (19 không giúp, 22 giúp rõ). Câu 22 âm
# tiết chính là câu ngắt mềm sinh ra để chữa, mà nó làm tệ thêm 10 điểm.
#
# Muốn thử lại thì phải đo TRÊN CODE ĐÚNG và tìm ngưỡng từ chính số đo mới, đừng
# lấy lại con số 16 - nó không có căn cứ nào còn hiệu lực.
NGAT_MEM = False

# Câu dài mà KHÔNG có dấu phẩy nào thì tách trước một từ nối.
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
#
# SIẾT LẠI 15-08-2026. Luật cũ ("sau dấu là chữ cái") bắt quá rộng và ĐANG PHÁ
# bốn kiểu chữ khác nhau. Đo trên 1653 lượt trả lời thật trong `data/app.db`:
#
#   chữ thật            luật cũ làm gì        hậu quả nghe được
#   TP.HCM          ->  "TP. HCM"             cắt mảnh giữa tên -> lặng 350ms
#   support@vnpt.com->  "support@vnpt. com"   đọc rời tên miền
#   2.năm           ->  "2. năm"              bẻ đôi con số
#   Ng?n h?ng       ->  "Ng? n h? ng"         bẻ đôi từ đã lỗi mã sẵn
#
# Và số ca nó CHỮA ĐƯỢC trong cùng 1653 lượt đó: **0**. Ca duy nhất khớp mẫu
# "chữ hoa đứng sau dấu chấm" lại chính là `TP.HCM`.
#
# Luật mới đòi HAI điều kiện cùng lúc, vì hết câu thật thì cả hai đều đúng:
#   - chữ ngay TRƯỚC dấu không phải chữ HOA  (loại "TP.", "Q.", "TT.")
#   - chữ ngay SAU dấu là chữ HOA            (loại "vnpt.com", "2.năm", "Ng?n")
# Ca gốc sinh ra luật này, "nghìn ạ.Dạ lãi suất", vẫn khớp: "ạ" thường + "D" hoa.
#
# Dùng `str.isupper()` chứ không dùng lớp [A-Z]: tiếng Việt có Ạ, Ế, Ô, Đ… mà
# lớp ASCII không bắt được.
_THIEU_CACH_RE = re.compile(r"(\w)([.!?…])(\w)")


def them_cach_sau_dau(s: str) -> str:
    """Trả `s` với khoảng trắng chèn sau dấu kết câu khi thiếu.

    Giữ nguyên số ("142.500.000", "7.9"), viết tắt ("TP.HCM", "Q.1") và tên miền
    ("abcbank.com.vn") - xem khối chú thích trên để biết vì sao.
    """
    def _va(m):
        truoc, dau, sau = m.groups()
        if not truoc.isupper() and sau.isupper():
            return f"{truoc}{dau} {sau}"
        return m.group(0)

    return _THIEU_CACH_RE.sub(_va, s)

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
#
# NỚI 14-08-2026 (100/200 -> 180/320) vì người dùng báo ở Lần 6, hai chỗ: "sau
# chữ 'vâng' có dấu phẩy: không ngắt nghỉ" và "sau dấu chấm chỗ 'thẩm định':
# không ngắt nghỉ". Đo trên chính câu họ gửi thì quãng nghỉ CÓ tồn tại, 300ms -
# nhưng tai họ vẫn thấy chưa đủ, và chỗ này tai người mới là thước đo.
#
# Dựng ba mức rồi đo quãng nghỉ THẬT trong file (`scripts/dung_lai_lan6.py`),
# lấy câu "Bước tiếp theo… trả nợ. Hiện tại…":
#     phẩy 100 / chấm 200 (cũ)   nghỉ đo được 300ms
#     phẩy 180 / chấm 320        nghỉ đo được 420ms   <- chọn
#     phẩy 250 / chấm 450        nghỉ đo được 560ms
# Chọn mức giữa: mức cao làm câu bốn mảnh dài thêm gần một giây, mà cuộc gọi
# tính tiền theo phút.
#
# Quãng nghỉ là IM LẶNG CHÈN GIỮA HAI MẢNH, không đi qua F5 - nên nới nó KHÔNG
# đụng gì tới chất lượng dựng tiếng, khác hẳn `HE_SO_BU_LANG`.
NGHI_PHAY_MS = 180.0
NGHI_CHAM_MS = 320.0

# Nghỉ sau vế KẾT BẰNG TIỂU TỪ ("...trong hẻm ạ.", "...anh nhé.").
#
# Bên A nghe ra (17-08): *"chữ ạ nó cứ nặng kiểu gì á, ạ nặng cái rồi mới nói"*.
#
# BỐN THƯỚC ĐO TRƯỚC ĐỀU SAI CHỖ. Máy nhận dạng báo chữ "ạ" dài 480ms nên tôi đi
# tìm lỗi ngân dài rồi lỗi âm sắc, qua bốn thước đo, không cái nào tách được bản
# bị chê khỏi bản được khen. Đo lại bằng NĂNG LƯỢNG thì hoá ra:
#
#     "ạ" thật   120ms CÓ TIẾNG
#     rồi        320ms IM LẶNG TUYỆT ĐỐI  <- quãng nghỉ chính code này chèn
#
# Máy nhận dạng gộp quãng im vào chữ. Chữ "ạ" KHÔNG ngân - nó ngắn. Cái nghe
# "nặng" là âm tắc thanh hầu của dấu nặng bị cắt cụt ngay vào khoảng im, rồi
# phải đợi 320ms mới nói tiếp.
#
# 320ms là nghỉ của DẤU CHẤM - đúng cho chỗ hết ý. Nhưng tiểu từ lễ phép không
# kết thúc ý, nó chỉ đánh dấu thái độ, nên người thật đi tiếp nhanh hơn nhiều.
#
# Không hạ về 0: bỏ hẳn thì chữ sau dính vào đuôi "ạ" - đúng lỗi bên A báo trước
# đó khi bản gộp mảnh xoá mất quãng nghỉ (đo được khe hở còn 190ms là đã dính).
NGHI_TIEU_TU_MS = 180.0

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
            # Kết bằng tiểu từ thì nghỉ ngắn hơn - xem `NGHI_TIEU_TU_MS`.
            return NGHI_TIEU_TU_MS if _ket_bang_tieu_tu(t) else NGHI_CHAM_MS
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
    # Bắt đầu từ 1 chứ không phải từ ngưỡng: tiếng đáp mở đầu ("Dạ,", "Vâng,")
    # phải được xét ở k=1. Các nhánh còn lại đều tự kiểm ngưỡng của mình nên hạ
    # điểm bắt đầu không nới lỏng gì thêm - xem `MO_DAU_TACH_RIENG`.
    for k in range(1, co_the + 1):
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
                and (k >= TOI_THIEU_TU_MOI_VE or _la_tieng_dap_mo_dau(manh))
                and co_the - k >= TOI_THIEU_TU_MOI_VE
                # Vế trái kết bằng tiểu từ ("… đồng ạ,") thì KHÔNG cắt: tiểu từ
                # bị đẩy thành âm tiết cuối của một phát ngôn riêng rồi dính
                # thêm NGHI_PHAY_MS - đúng lỗi "chữ ạ bị tách". Xem
                # `TIEU_TU_CUOI_VE`.
                and not _ket_bang_tieu_tu(manh)):
            return manh, " ".join(tu[k:])
        # Ngắt mềm: câu DÀI mà chưa gặp dấu nào -> tách trước một từ nối.
        #
        # Điều kiện xét trên `co_the` (độ dài cả câu đang có) chứ KHÔNG xét vị
        # trí từ nối: từ nối thường rơi vào giữa câu, nên xét vị trí thì câu 23
        # từ có "và" ở từ thứ 15 vẫn trượt ngưỡng 16 và không bao giờ tách. Đúng
        # lỗi bản đầu tôi viết.
        if (NGAT_MEM and co_the >= TRAN_TU_TRUOC_NGAT_MEM
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


def chia_ca_luot(text: str) -> list[str]:
    """Cắt CẢ một lượt trả lời thành đúng dãy mảnh mà pipeline giao cho TTS.

    NGUỒN DUY NHẤT của luật cắt "cả lượt". Trước 16-08-2026 hàm này bị gỡ khỏi
    đây và `api/voices.py` giữ một bản CHÉP RIÊNG (`_cat_manh_nhu_pipeline`) -
    tức hai bộ luật song song cho cùng một việc. Đó đúng là kiểu hỏng đã xảy ra
    thật trong dự án này: trang nghe thử và cuộc gọi thật cắt khác nhau, người
    dùng chỉnh giọng trên web xong ra cuộc gọi nghe một kiểu khác, và không có
    gì báo lỗi. `tests/test_chia_ca_luot.py` neo hàm này vào một bản mô phỏng
    pipeline viết ĐỘC LẬP, nên lệch là đỏ ngay.

    Nạp token TỪNG TỪ chứ không đưa cả chuỗi vào `tach_manh`: cỡ mảnh lấy theo
    SỐ MẢNH ĐÃ GIAO (`co_manh`), nên đưa cả chuỗi một lần sẽ ra kết quả khác với
    lúc LLM nhả token dần - tức lại lệch khỏi đường thật.
    """
    if not text.strip():
        return []

    ra: list[str] = []
    dem = ""
    for tu in text.split():
        dem = f"{dem} {tu}" if dem else tu
        while True:
            m, dem = tach_manh(dem, n=co_manh(len(ra)))
            if m is None:
                break
            ra.append(m)

    # ĐUÔI NGẮN gộp vào mảnh trước, không giao riêng - y hệt đoạn xả đệm cuối
    # lượt của `streaming_pipeline`.
    #
    # Thiếu đúng bước này là trang nghe thử cho ra một mảnh cụt mà cuộc gọi thật
    # không hề có. F5 sinh MỖI mảnh như một phát ngôn trọn vẹn, nên mảnh "Vâng
    # ạ" một mình nghe tách hẳn khỏi câu nó thuộc về.
    du = dem.strip()
    if du and ra and len(du.split()) < TOI_THIEU_TU_MANH_CUOI:
        ra[-1] = f"{ra[-1]} {du}".strip()
    elif du:
        ra.append(du)
    return ra or [text.strip()]


# --- Gộp nhiều mảnh thành MỘT phát ngôn -----------------------------------
#
# VÌ SAO. F5 sinh mỗi mảnh như một phát ngôn trọn vẹn nên nó kéo dài âm tiết
# cuối mảnh. Ở cuối CÂU thì đúng - người thật cũng vậy. Ở GIỮA câu thì khách
# nghe ra: *"lâu lâu có chữ nó đọc kiểu ạ nhưng chữ ngân dài"*.
#
# Đo trên 12 lượt thật (đã gạt chữ ma của PhoWhisper trước khi tính, xem
# `bu_duoi.py` và sổ tay - không gạt thì trung vị tụt và số liệu sai 15 lần):
#
#                     từng mảnh   gộp lại
#     chữ ngân            447ms     332ms   (-26%)
#     tổng quãng nghỉ     629ms     316ms   (-50%)
#     WER                 1,07%     1,23%
#
# Đánh đổi đã rõ và bên A đã nghe cả hai bộ 100 câu rồi chọn bản GỘP.
#
# ĐÃ LOẠI, đừng đi lại: nâng ngưỡng tách ở dấu phẩy (đổi 1-1, bớt 12 mảnh thì
# mất đúng 12 quãng nghỉ, mà 171/212 mảnh vốn sinh từ ranh giới CÂU chứ không
# phải phẩy); bù thêm chữ vào đuôi rồi cắt (`bu_duoi.py`, làm TỆ HƠN); nén đuôi
# bằng kéo giãn (`nen_duoi_manh.py`, chỉ được -14%).

# Trần âm tiết cho MỘT phát ngôn gộp.
#
# Không phải trần chất lượng mà là trần ĐỘ TRỄ: gộp càng to thì sinh càng lâu,
# mà tiếng của mảnh trước vẫn đang phát và có thể hết trước. Ước từ số đo thật:
# sinh ~1420ms cho ~6,5s tiếng, tức ~0,22 lần thời gian thực; 32 âm tiết ≈ 6,5s
# tiếng ≈ 1,4s sinh - vừa đủ lọt trong lúc mảnh trước đang phát.
#
# Lượt trả lời trung bình của bot là ~32 âm tiết, nên trần này gộp trọn phần
# đuôi của hầu hết các lượt mà không phải chờ gì thêm.
TRAN_AM_TIET_GOP = 32


def noi_lo(manh: list[str]) -> str:
    """Nối nhiều mảnh thành một chuỗi để giao cho F5 sinh MỘT lần.

    Chỉ nối, KHÔNG tự thêm dấu câu: dấu quyết định ngữ điệu và nhịp nghỉ của
    F5, tự chèn vào là đổi cách đọc của bên A mà không ai yêu cầu.
    """
    return " ".join(m.strip() for m in manh if m and m.strip())


def gom_thanh_mot_luot(manh: list[str]) -> int:
    """Lấy được bao nhiêu mảnh đầu danh sách để gộp thành một phát ngôn.

    Luôn trả về ít nhất 1 khi có mảnh - trả 0 là bỏ rơi mảnh đó và khách mất
    hẳn đoạn tiếng ấy.
    """
    if not manh:
        return 0
    from backend.services.tts_service import so_am_tiet   # nhập muộn: tránh vòng

    n = 0
    tong = 0
    for m in manh:
        it = so_am_tiet(m or "")
        if n and tong + it > TRAN_AM_TIET_GOP:
            break
        n += 1
        tong += it
    return max(1, n)


def sap_cum_gop(dau: tuple[str, float], cho: list, het_luot: bool):
    """Xếp cụm mảnh để gộp thành một phát ngôn, và phần phải trả lại hàng đợi.

    `dau` là mảnh vừa lấy ra, `cho` là những mảnh vét thêm được, `het_luot` cho
    biết có gặp tín hiệu kết thúc trong lúc vét hay không.

    Trả về `(dan, tra_lai)`:
      - `dan`     cụm sẽ nối thành MỘT phát ngôn (ít nhất một mảnh)
      - `tra_lai` đẩy lại hàng đợi theo ĐÚNG thứ tự này, `None` (nếu có) nằm
        cuối cùng

    Tách riêng khỏi vòng tiêu thụ vì đây là chỗ dễ mất tiếng nhất: `asyncio.Queue`
    chỉ đẩy vào CUỐI, nên trả tín hiệu hết lượt trước phần dư sẽ làm vòng tiêu
    thụ dừng sớm và khách mất trắng đuôi lượt.
    """
    def co_chu(t) -> bool:
        return bool(t) and any(c.isalnum() for c in t)

    thuc = [(t, n) for t, n in cho if co_chu(t)]
    # Mảnh rỗng (thường là đúng một dấu chấm) không có chữ để nối, nhưng nhịp
    # nghỉ của nó phải chuyển sang mảnh đầu - bỏ luôn là mảnh sau mất chỗ ngắt.
    nghi_rong = max([n for t, n in cho if not co_chu(t)] or [0.0])

    # CHỈ GỘP QUA DẤU PHẨY.
    #
    # Bên A nghe ra (17-08, tệp 4 bộ Lần 9): *"chữ 'ạ' - cái đã đọc từ luôn rồi
    # mà 'ạ' còn chưa ngắt xong"*. Đo khe nghỉ thật sau "ạ":
    #
    #     bộ cũ bên A gửi   410ms
    #     gộp HẾT           190ms   <- dính chữ, đúng chỗ bên A chỉ
    #     không gộp         360ms
    #     gộp PHẨY          360ms
    #
    # Gộp xoá quãng nghỉ mà `nhip_nghi_sau` chèn, còn F5 tự cho chỉ ~190ms ở dấu
    # chấm - không đủ sau tiểu từ. Nên chỉ gộp chỗ dấu PHẨY: chỗ đó vốn không
    # đáng nghỉ dài, và cũng chính là chỗ chữ ngân rơi vào GIỮA câu.
    #
    # Không có dấu câu ở cuối mảnh (mảnh bị cắt vì chạm trần từ) thì KHÔNG gộp:
    # đoán bừa ở đó dễ bỏ mất chỗ ngắt thật.
    chuoi = [dau[0]] + [t for t, _ in thuc]
    qua_phay = 1
    while qua_phay < len(chuoi) and chuoi[qua_phay - 1].rstrip().endswith(","):
        qua_phay += 1
    lay = min(qua_phay, gom_thanh_mot_luot(chuoi))
    dan = [(dau[0], max(dau[1], nghi_rong))] + thuc[:lay - 1]
    tra_lai = list(thuc[lay - 1:])
    if het_luot:
        tra_lai.append(None)
    return dan, tra_lai


# --- Chờ gom thêm mảnh ----------------------------------------------------
#
# Gộp mảnh chỉ ăn được 25% chỗ nối trên cuộc gọi thật (4/16 chỗ, đo 16-08): lúc
# vòng tiêu thụ lấy mảnh 2 thì LLM chưa sinh xong mảnh 3. Hai mảnh liên tiếp
# cách nhau 521-1377ms, còn hàng đợi thì rỗng.
#
# Chờ thêm thì gom được nhiều hơn, nhưng chờ là ăn vào DƯ ĐỊA PHÁT - phần tiếng
# đã gửi mà khách chưa nghe tới. Hết dư địa là khách nghe quãng im, tức đổi một
# lỗi nhỏ (chữ ngân) lấy một lỗi to hơn hẳn.
#
# Đo dư địa trên cuộc gọi thật lúc sinh mảnh 2: 1070-2165ms, thấp nhất 515ms.
# Nên phải tính chứ không được chờ cứng một con số.

# Trần chờ.
# ĐÃ ĐẢO NGƯỢC 05-09-2026: 600 -> 1500. Lý do cũ (vẫn đúng lúc đó): "chờ lâu là
# kéo dài lượt nói của bot". Nhưng chờ chỉ xảy ra khi CÒN dư địa, tức tiếng
# cũ vẫn đang phát, khách không nghe im - lượt không dài thêm, chỉ gửi muộn.
# Đo 05-09 trên 12 lượt WebSocket thật: dư địa TB 2200-3360ms mà chờ đúng
# 600ms rồi hết trần, gộp được 0/1 chỗ nối ở hầu hết lượt - mảnh sau của LLM
# tới muộn hơn 600ms. Trần là chỗ chặn, không phải dư địa. Cái giá nhận về:
# tiếng gửi muộn hơn tới 1,5s nên đệm phía khách mỏng hơn; `cho_gom_ms` vẫn
# trừ thời gian sinh + JITTER nên không bao giờ chờ quá dư địa.
TRAN_CHO_MS = 1500.0

# Chừa cho dao động: mạng, GPU bận vì lượt đoán trước, ghi đĩa.
JITTER_MS = 250.0

# Ước tốc độ sinh. Đo lại 05-09-2026 sau gộp CFG + CUDA graphs
# (scripts/do_gop_cfg.py, RTX 5070, nfe 16): câu 3 âm tiết 140ms, 22 âm tiết
# 314ms - phần cố định ~120ms (16 bước khuếch tán, không phụ thuộc độ dài)
# cộng ~8ms mỗi âm tiết. Công thức cũ 45ms/âm tiết ước 15 âm tiết = 675ms,
# thật ~240ms: ước dư 400ms là bớt đúng 400ms chờ gom mỗi chỗ nối.
MS_CO_DINH = 120.0
MS_MOI_AM_TIET = 8.0


def uoc_sinh_ms(text: str) -> float:
    """Ước thời gian F5 sinh xong đoạn này."""
    from backend.services.tts_service import so_am_tiet   # nhập muộn: tránh vòng
    n = so_am_tiet(text or "")
    return MS_CO_DINH + n * MS_MOI_AM_TIET if n else 0.0


def cho_gom_ms(du_dia_ms: float, uoc_sinh: float) -> float:
    """Được phép chờ bao lâu để gom thêm mảnh. 0 nghĩa là sinh ngay.

    Trừ CẢ thời gian sinh sắp tới: chờ hết dư địa rồi mới sinh thì đúng lúc
    sinh xong khách đã nghe hết tiếng cũ.
    """
    con = du_dia_ms - uoc_sinh - JITTER_MS
    return max(0.0, min(TRAN_CHO_MS, con))


def ty_le_gop(so_manh: int, so_lan_sinh: int) -> float | None:
    """Bao nhiêu phần chỗ nối đã bị gộp mất, hoặc None nếu không có chỗ nối nào.

    Chỗ nối là nơi đẻ ra "chữ ngân" giữa câu - `so_manh - 1` chỗ. Gộp được bao
    nhiêu chỗ thì bớt bấy nhiêu lần F5 kéo dài âm cuối.

    Trả None chứ không phải 0.0 khi lượt chỉ có một mảnh: 0% nghĩa là "có cơ hội
    gộp mà trượt", khác hẳn "không có cơ hội nào". Gộp hai thứ đó vào một con số
    thì trung bình cộng bị kéo xuống bởi những lượt vốn không thể gộp, và tưởng
    là gộp đang hỏng.
    """
    cho_noi = so_manh - 1
    if cho_noi <= 0:
        return None
    da_gop = so_manh - so_lan_sinh
    return max(0.0, min(1.0, da_gop / cho_noi))
