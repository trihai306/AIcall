import asyncio
import logging
import zlib
import re
import time
import concurrent.futures
from collections import OrderedDict
from contextlib import nullcontext
from pathlib import Path
import numpy as np
import soundfile as sf

from backend.config import settings
from backend.pipeline.text_normalizer import dong_dau_cuoi, normalize_for_tts
from backend.services.audio_utils import float32_to_int16, resample_audio, pcm_to_wav
from backend.core.logging_config import Timer
from backend.core.device import DEVICE
from backend.services.filler_store import CauDuoi, Kho, van_tay
from backend.services.filler_pick import chon as _chon_filler, ghep

logger = logging.getLogger(__name__)

# Below this peak amplitude a reference clip is treated as an empty recording.
SILENCE_PEAK = 1e-3

# Tiếng câu đệm cất ở đây để khởi động không phải gọi F5 lại. Tên file mang vân
# tay: đổi nfe/speed/giọng là vân tay lệch -> dựng lại đúng câu đó.
THU_MUC_FILLER = Path("data/fillers_wav")

# --- Ép thời lượng theo ÂM TIẾT ------------------------------------------
#
# Người dùng: "nó đọc kiểu không đồng bộ tốc độ, lúc nhanh lúc chậm". Đo được
# các câu ra từ 194 đến 500 âm tiết/phút - chênh hơn 2,5 lần, cùng một cấu hình.
#
# Gốc nằm ngay trong công thức của F5:
#     duration = ref_len + int(ref_len / ref_text_BYTES * gen_text_BYTES / speed)
# F5 cấp thời lượng theo số BYTE của chữ, nhưng tai nghe nhịp theo ÂM TIẾT. Chữ
# tiếng Việt có dấu tốn 3 byte ("ạ") trong khi chữ không dấu tốn 1. Nên hai câu
# CÙNG số âm tiết nhưng khác mật độ dấu được cấp thời lượng khác hẳn.
#
# Đo đối chứng (scripts/do_nhip_theo_byte.py, 8 câu chọn theo mật độ dấu):
#     tương quan byte/âm tiết với nhịp đọc ra: -0.74
#     "Anh cho em xin so tai khoan ngan hang nhe"  (4.10 byte/âm tiết) -> 366
#     "Hạn mức tối đa năm trăm triệu, thời hạn..." (6.08 byte/âm tiết) -> 259
#
# Chữa: tự tính thời lượng theo ÂM TIẾT rồi ép bằng `fix_duration`.
#     lệch nhịp giữa các câu: 38% -> 6%
#
# ĐÃ LOẠI trước khi đi tới đây: kích thước mảnh (lệch 31-42% ở MỌI mức, 5 từ
# còn đều nhất) và câu đệm dựng sẵn ở tốc cũ (khớp -11%).
#
# Nhịp chuẩn đo trên 20,2 phút bản thu gốc của chính người đó, phần CÓ TIẾNG.
NHIP_CHUAN_AM_TIET_PHUT = 294.0
# `speed` bao nhiêu thì cho ra nhịp chuẩn ở trên. Giữ mốc này để `speed` không
# mất ý nghĩa: đặt tốc riêng cho giọng, hay hệ số tốc cho đường thoại, vẫn ăn.
SPEED_CHUAN = 1.20
# Hệ số CẤP thời lượng. 1.11 -> 0.85 ngày 2026-08-12.
#
# Tên cũ là "bù lặng" vì bản đầu nghĩ đây là phần `trim_silence` cắt mất ở hai
# đầu mảnh. Sai chỗ đó: phần cắt ở hai đầu gần như KHÔNG đổi theo độ dài mảnh,
# còn hệ số này thì NHÂN - nên mảnh càng dài, thời lượng cấp thừa càng nhiều về
# tuyệt đối, mà từ 2026-08-11 mảnh đã là NGUYÊN CÂU.
#
# Điều quyết định, đo được: F5 KHÔNG đọc chậm lại khi được cấp dư thời lượng -
# nó lấy IM LẶNG tiêu chỗ thừa. Quét trên mảnh 20 từ, 3 lượt mỗi mức
# (scripts/chan_doan_manh_dai.py):
#
#   hệ số   cấp dư   F5 tự bịa quãng dừng   còn sót sau khi lọc   nhịp phát âm
#   0.85      16%       2 quãng /  820ms      14 quãng / 3460ms       341
#   1.11      34%      12 quãng / 6080ms      34 quãng / 6820ms       297
#
# Cấp dư gấp đôi thì quãng lặng bịa ra gấp SÁU, trong khi nhịp phát âm chỉ nhích
# 297 -> 341. Tức dưới ~300 âm tiết/phút thì F5 không chịu đọc chậm hơn nữa, mọi
# giây cấp thêm đều rơi thành lỗ hổng giữa câu. Đó chính là bốn thứ người dùng
# báo ngày 2026-08-12: "đọc bị cách ra dù không có dấu chấm phẩy", "đoạn sau đọc
# giãn giữa các từ", "lắp từ", "đọc sai từ".
#
# Đo lại trên ĐÚNG đường pipeline (cắt theo câu, giữ dấu, có cat_lang_bia -
# scripts/dung_ab_he_so_cap.py): 1.11 cho 11 lỗ / 2900ms trong 20,14s; 0.85 cho
# 8 lỗ / 2520ms trong 17,21s. Chênh nhỏ hơn hẳn bản đo cắt cứng 20 từ, vì dấu
# phẩy giữ lại đã tự cho F5 chỗ nghỉ hợp lệ.
#
# 0.75 thì cấp dư chỉ còn 7% và chữ bắt đầu sai (đo 1 lượt: 7 chữ) - hết chỗ dự
# trữ thì F5 nhồi cho kịp. 0.85 là mức thấp nhất còn an toàn.
#
# ĐỔI 0.85 -> 0.95 ngày 14-08-2026, vì người dùng báo "đọc bị nhanh" ở vài chỗ
# (Lần 7, hai thư mục). Đo nhịp TỪNG CHỮ trên 122 chữ (`do_nhip_giat_cuc.py`):
#     hệ số   chữ >600   chữ >800   nhanh nhất   nhịp TB   giây
#     0.85      4/122      2/122       1500        333     24.6
#     0.95      2/122      0/122        750        300     26.8
#     1.05      1/123      0/123        750        273     28.7
# 0.85 nén vài âm tiết xuống dưới 75ms - đó đúng là chỗ nghe thành "lướt qua".
# 0.95 dập hết mức trên 800 mà chỉ dài thêm 9%; 1.05 gần như không hơn nữa mà
# tốn thêm 8% nữa.
#
# GIÁ PHẢI TRẢ, ghi cho rõ: âm tiết CUỐI MẢNH có thể kém đi (đo 35 mảnh: 0.85
# cho 25-26/35, 0.95 cho 22/35). Con số này KHÔNG chắc - cùng cấu hình 0.85 đo
# hai lần ra 26 rồi 25, tức có nhiễu ±1, và trong buổi này đã bốn lần một phép
# đo hẹp cho kết luận ngược với bộ rộng. Ai đo lại thì dùng bộ ĐỦ RỘNG.
#
# KHÔNG phải cần gạt cho lỗi âm tiết cuối mảnh: đo riêng 0.85/0.95/1.05/1.15
# cho 9/13, 10/13, 12/13, 9/13 trên bộ hẹp nhưng 26/35 y hệt nhau trên bộ rộng.
#
# ĐỔI SỐ NÀY LÀ PHẢI TĂNG `PHIEN_BAN` bên filler_store: câu đệm dựng sẵn nằm
# trên đĩa theo vân tay cũ, không đổi vân tay thì khách nghe câu đệm ở nhịp cũ
# nối thẳng vào câu trả lời ở nhịp mới.
HE_SO_BU_LANG = 0.95
# Dưới ngưỡng này thì để F5 tự lo: mảnh 1 âm tiết mà ép thời lượng thì sai số
# một âm tiết đã là 100%.
TOI_THIEU_AM_TIET_DE_EP = 3

_CHU_SO_RE = re.compile(r"\d")

# Dấu câu bỏ khỏi chữ ĐƯA VÀO F5. Không bỏ khỏi chữ dùng ở nơi khác - nhịp nghỉ
# giữa các mảnh vẫn tính từ dấu câu gốc (`nhip_nghi_sau` ở text_chunker), bản
# ghi lưu lại cũng vẫn có dấu.
_DAU_CAU_BO_RE = re.compile(r"[,.;:!?…]")

# Có xoá dấu câu trước khi đưa vào F5 hay không. TẮT từ 2026-08-11 - xem
# `bo_dau_cau_cho_f5`. Giữ cờ chứ không xoá hàm để còn đường lùi: bật lại True là
# hành vi cũ quay về nguyên vẹn, không phải sửa mã.
#
# ĐỔI CÙNG LÚC với `CAT_THEO_CAU` bên text_chunker. Bật cờ này mà vẫn cắt cứng
# theo số từ là quay về đúng lỗi cũ (nhịp đọc lệch 44% giữa các mảnh 5 từ, vì dấu
# rơi vào chỗ tuỳ tiện - mảnh này kết bằng phẩy, mảnh kia không).
BO_DAU_CAU = False


def bo_dau_cau_cho_f5(text: str) -> str:
    """Bỏ dấu chấm/phẩy khỏi chữ đưa vào F5.

    Vì sao, và vì sao chỉ đúng từ khi cắt mảnh 5 từ:

    F5 nghỉ ở dấu câu. Khi mảnh là CẢ CÂU thì dấu nằm đúng chỗ và nghỉ là đúng.
    Nhưng cắt cứng 5 từ một thì dấu rơi vào chỗ tuỳ tiện - mảnh này kết bằng dấu
    phẩy, mảnh kia không - nên hai mảnh cạnh nhau ra hai nhịp khác hẳn. Đó chính
    là thứ người dùng nghe thành "lúc nhanh lúc chậm".

    Đo trên 16 mảnh 5 từ (scripts/thu_bo_dau_cau_tren_manh.py):
        giữ nguyên dấu  : lệch nhịp 44%,  chữ đọc đúng 95%
        bỏ dấu chấm/phẩy: lệch nhịp 20%,  chữ đọc đúng 98%
    Vừa đều nhịp hơn gấp đôi, vừa đọc ĐÚNG HƠN.

    Chỗ ngắt câu KHÔNG mất: nhịp nghỉ giữa các mảnh do code chèn
    (`nhip_nghi_sau` + `chen_lang_dau_wav`), tính từ chữ gốc còn nguyên dấu.

    Cảnh báo nếu sau này quay lại cắt mảnh DÀI: lúc đó bỏ dấu là sai, vì F5 lại
    cần dấu để ngắt nhịp trong lòng mảnh. Đo trên cả câu thì bỏ dấu không được
    gì (lệch 7% -> 8%).
    ĐÃ TẮT 2026-08-11, người dùng chốt "bỏ cơ chế bỏ dấu câu". Cùng lúc với
    `CAT_THEO_CAU` bên text_chunker - hai nửa của một thay đổi, bật một nửa là vô
    nghĩa. Lý do gỡ: xoá dấu thì F5 KHÔNG CÒN MỐC NÀO để nghỉ. Đo 2026-08-11 trên
    đoạn 60 từ có 4 dấu, ngưỡng -40dB/20ms: bản đang chạy chỉ 2 quãng lặng (35ms,
    38ms) trong 13,8 giây, còn người thật 22 quãng trong 16 giây.

    Cảnh báo cũ vẫn còn giá trị và chính là lý do phải đổi CẢ HAI nửa: bỏ dấu
    chỉ ĐÚNG khi mảnh bị cắt cứng theo số từ, vì lúc đó dấu rơi vào chỗ tuỳ tiện.
    Cắt theo nguyên câu thì dấu lại nằm đúng chỗ của nó, nên giữ dấu là đúng.
    """
    if not text or not BO_DAU_CAU:
        return text
    return re.sub(r"\s+", " ", _DAU_CAU_BO_RE.sub(" ", text)).strip()


def so_am_tiet(text: str) -> int:
    """Ước số âm tiết khi ĐỌC RA, không phải số từ viết.

    Chữ số phải quy đổi chứ không đếm là một: "2.000.000.000" viết một từ nhưng
    đọc thành "hai tỷ đồng" - đếm là 1 thì thời lượng ép ra quá ngắn và tiếng bị
    cụt. Ước 1,5 âm tiết cho mỗi chữ số là sát: "142500000" chín chữ số đọc
    thành "một trăm bốn mươi hai triệu năm trăm nghìn" - 13 âm tiết, ước 13,5.
    """
    n = 0
    for t in text.split():
        cs = len(_CHU_SO_RE.findall(t))
        n += max(1, round(cs * 1.5)) if cs else 1
    return n


def _dat_seed(_t, text: str, voice: str, toc: float) -> None:
    """Cố định nhiễu khởi tạo của F5 để CÙNG chữ luôn ra CÙNG tiếng.

    Vì sao đây mới là thứ khách kêu: ghi chú của khách viết "mỗi lần gen ra 1
    kiểu, lúc thì bị mất chữ, lúc thì đọc thừa chữ". Lỗi không phải "nhịp lệch"
    mà là KHÔNG ĐOÁN TRƯỚC ĐƯỢC - F5 là mô hình khuếch tán, mỗi lần sinh khởi
    tạo từ một mớ nhiễu ngẫu nhiên khác nhau nên cùng một câu ra mỗi lần một
    kiểu, và thỉnh thoảng rơi vào một lần hỏng.

    Cố định seed KHÔNG làm câu đọc hay hơn. Nó làm câu đọc LẶP LẠI ĐƯỢC, và đó
    mới là thứ mở đường cho việc nghiệm thu: nghe duyệt một kịch bản xong thì
    biết chắc lúc gọi thật khách nghe đúng như thế. Câu nào rơi vào bản hỏng thì
    sửa chữ trong kịch bản là hỏng luôn cố định, không phải chờ may rủi.

    Seed suy từ (chữ, giọng, tốc) chứ không phải một hằng số: hằng số thì MỌI
    câu dùng chung một mớ nhiễu, mà nhiễu khởi tạo ảnh hưởng tới cả ngữ điệu -
    dễ làm mọi câu nghe cùng một khuôn. Suy từ nội dung thì mỗi câu có mớ nhiễu
    riêng nhưng CỐ ĐỊNH của riêng nó.

    Chi phí: 0. Không thêm một phép tính nào vào đường sinh.
    """
    if settings.f5tts_seed is None:
        return          # để trống trong .env -> ngẫu nhiên như cũ
    khoa = f"{text}|{voice}|{toc:.3f}"
    _t.manual_seed((settings.f5tts_seed + zlib.crc32(khoa.encode("utf-8"))) & 0x7FFFFFFF)


def thoi_luong_ep(text: str, dai_ref_giay: float, speed: float) -> float | None:
    """Thời lượng nên ép cho mảnh này, hoặc None nếu để F5 tự tính.

    Trả về TỔNG thời lượng (đoạn mẫu + phần sinh), đúng thứ `fix_duration` cần.
    """
    n = so_am_tiet(text)
    if n < TOI_THIEU_AM_TIET_DE_EP or dai_ref_giay <= 0 or speed <= 0:
        return None
    nhip = NHIP_CHUAN_AM_TIET_PHUT * (speed / SPEED_CHUAN)
    return dai_ref_giay + n / (nhip / 60.0) * HE_SO_BU_LANG


# Bóp quãng lặng GIỮA mảnh. Ngưỡng KHÔNG chọn cho đẹp mà lấy từ hai phép đo:
#
#   nghỉ THẬT của F5 ở dấu câu (scripts/do_nghi_dau_phay.py, do_nghi_dau_cham.py,
#   10 lượt mỗi bản, ở đúng cấu hình đang chạy):
#       không dấu giữa  0ms      1 dấu phẩy  tối đa 160ms
#       1 dấu chấm      tối đa 320ms         2 dấu chấm  tối đa 260ms
#
#   quãng BỊA, đo trên bản ghi hội thoại thật: 380 - 1600ms
#
# Nên 360ms là chỗ tách: dưới nó là nhịp nghỉ thật của dấu câu, trên nó thì F5
# đang bịa. Từng thử 260ms - sai, vì nghỉ thật ở dấu chấm chạm tới 320ms và
# ngưỡng đó cắt nhầm ranh giới câu, làm hai câu dính vào nhau.
NGUONG_LANG_BIA_MS = 360.0
# Bóp về 200ms chứ không xoá hẳn: xoá hẳn thì hai từ dính sát, nghe hụt hơi.
# 200ms nằm đúng giữa dải nghỉ thật đo được ở trên.
GIU_LANG_MS = 200.0
_KHUNG_LANG_MS = 20.0

# Thế nào là "lặng". Bản đầu dùng BIÊN ĐỘ ĐỈNH < 0.015 tuyệt đối, và hàm đã
# KHÔNG chạy lần nào: đo 14 quãng nghỉ trên bản ghi cuộc gọi thật, đỉnh của
# chúng nằm trong 0.023 - 0.078, tức cao gấp 1,5 - 5 lần ngưỡng, nên hàm coi
# là "đang có tiếng" và bỏ qua sạch. Quãng nghỉ của F5 không im tuyệt đối - nó
# có hơi thở rất nhỏ, tai nghe là im nhưng đỉnh thì không.
#
# Nên đo bằng NĂNG LƯỢNG (RMS) và so với chính mảnh đó, đúng cách tai phân biệt
# to/nhỏ. Đo trên 23 quãng nghỉ của bản ghi thật: năng lượng của chúng nằm
# trong 7,6% - 14,9% năng lượng đỉnh của mảnh.
#
# Dùng HAI ngưỡng chứ không một:
#   - một ngưỡng rộng thì lấy trọn chiều dài quãng, nhưng cũng nuốt cả tiếng nhỏ
#     thật (quét thử: từ 12% trở lên là 2/18 mảnh bị STT nghe khác đi);
#   - một ngưỡng chặt thì an toàn nhưng chỉ chạm được đáy quãng, đo ra ngắn hơn
#     thực tế nên nhiều quãng không đủ 360ms và thoát.
# Nên: NGƯỠNG RỘNG kéo dài quãng, còn NGƯỠNG CHẶT là điều kiện công nhận - quãng
# phải có ít nhất một khung tụt xuống dưới nó mới tính là nghỉ. Tiếng nhỏ thật
# giữ đều năng lượng nên không bao giờ chạm đáy đó.
TI_LE_LANG = 0.20          # ngưỡng rộng: kéo dài quãng
TI_LE_DAY_LANG = 0.07      # ngưỡng chặt: phải chạm đáy này mới công nhận
# Ngưỡng cắt lặng HAI ĐẦU (`trim_silence`). Để thấp hơn hẳn ngưỡng ở giữa: hai
# đầu chỉ cần bỏ nhiễu nền (đo được 1,5-3% năng lượng tiếng), còn phụ âm bật
# hơi đầu câu vào rất nhẹ nên phải chừa khoảng an toàn rộng.
TI_LE_DAU_CUOI = 0.04

# Ngưỡng cắt lặng, TÁCH RIÊNG hai đầu. Tính theo RMS đỉnh của chính mảnh.
#
# ĐẦU mảnh giữ thấp: phụ âm bật hơi ("kh", "th", "ph") vào rất nhẹ, cắt sát là
# mất luôn tiếng đầu.
TI_LE_DAU = 0.04
#
# ĐUÔI phải cao hơn hẳn. Bên A nghe ra tiếng "hợp" rất nhẹ sau mỗi vế (bộ kiểm
# Lần 9, 17-08-2026). Máy nhận dạng không ra chữ nào - nội dung đúng hoàn toàn.
# Đo mức dB từng 20ms mới thấy F5 để lại ĐUÔI THỞ ~200ms:
#
#     sau "giảm dần,"  -27 -30 -31 -33 -38 -36 -37 -37 -37 -41  rồi mới tới im
#     giữa mảnh        không có đoạn nào như vậy
#
# Ngưỡng cũ 0.04 không bắt được: 4% RMS ĐỈNH, mà RMS đỉnh thấp hơn biên độ đỉnh
# chừng 12dB, nên sàn cắt thực tế rơi vào ~-40dB - cả đuôi thở lọt qua. Khách
# nghe thành: chữ -> hơi thở -> quãng nghỉ code chèn -> vế sau.
TI_LE_DUOI = 0.12
#
# Vuốt nhỏ dần ở chỗ cắt đuôi. Cắt thẳng vào chỗ còn -25dB nghe "cụt" - đúng lỗi
# mà trim_silence từng gây ra khi cắt quá tay.
VUOT_DUOI_MS = 30.0

# GỘP LÔ: ĐANG TẮT. Đã thi công, đo, và bác bỏ ngày 2026-08-10.
#
# Ý tưởng: `infer_batch_process` nhận danh sách nhưng chỉ LẶP qua từng câu, còn
# `CFM.sample` bên dưới nhận lô thật. Gộp lô đo được nhanh hơn thật:
#   tuần tự 300ms/mảnh | lô 2  249ms | lô 4  217ms | lô 8  217ms   (−28%)
# Trên cuộc gọi thật cũng đúng 28%: 80 mảnh hết 28,6s thay vì 39,7s.
#
# NHƯNG NÓ LÀM HỎNG TIẾNG. `CFM.sample` đệm mọi phần tử tới độ dài LỚN NHẤT
# trong lô, và mảnh ngắn không sống nổi. Cho STT nghe lại, so với sinh lẻ:
#
#   chênh độ dài trong lô   1,0x   2,0x   3,0x   4,4x
#   mảnh ngắn giống          80%    75%    33%     0%
#   mảnh dài giống          100%   100%   100%   100%
#
# Kể cả lô ĐỒNG ĐỀU cũng đã tụt (80% so với 100%). Trên bản ghi cuộc gọi đầy đủ:
# giống trung bình 92,9% -> 84,8%, số mảnh dưới 70% tăng 10% -> 21%.
# Chú thích trong chính mã F5 cũng thừa nhận: "still some difference maybe due
# to convolutional layers".
#
# Và cái giá đó mua về thứ KHÔNG THIẾU: TTS vốn đã sinh nhanh gấp 3,5 lần thời
# gian phát, khe hở giữa các mảnh đo trên bản ghi thật có trung vị 0ms. Tiết
# kiệm GPU chỉ đáng khi chạy nhiều cuộc song song - lúc đó hãy bật lại và chấp
# nhận đánh đổi, hoặc gom mảnh theo độ dài cho thật khít.
#
# Giữ nguyên mã lại để khỏi phải đo lại từ đầu. Bật bằng cách cho GOP_LO = True.
GOP_LO = False
LO_TOI_DA = 4
# Sàn tuyệt đối cho mảnh gần như im hoàn toàn: thiếu nó thì tỉ lệ của một mảnh
# rất nhỏ tụt xuống mức nhiễu số, và tiếng nhỏ bị coi là lặng.
SAN_LANG = 0.0015


def cat_lang_bia(audio: np.ndarray, sr: int,
                 nguong_ms: float = NGUONG_LANG_BIA_MS,
                 giu_ms: float = GIU_LANG_MS,
                 ti_le_lang: float = TI_LE_LANG,
                 ti_le_day: float = TI_LE_DAY_LANG,
                 san_lang: float = SAN_LANG) -> np.ndarray:
    """Bóp mọi quãng lặng GIỮA mảnh dài quá `nguong_ms` xuống còn `giu_ms`.

    Vì sao cần: F5 tự chèn quãng dừng vào giữa câu - đo được 19 quãng
    300-1600ms trong một bản ghi hội thoại 111 giây, khách nghe thành "đang nói
    tự nhiên dừng rồi bật lên". Đã đuổi nguyên nhân qua BẢY giả thuyết và sai cả
    bảy (nfe, checkpoint, dấu "/" và "-", độ dài văn bản, kích thước mảnh, tiểu
    từ cuối câu "nha/nhé", dấu gạch chéo còn sót). Cắt mảnh 5 từ hạ được 19
    xuống 9 nhưng không hết.

    Biết chắc MỘT điều về nguyên nhân: cấp càng nhiều thời lượng thì F5 chèn
    càng nhiều nghỉ - đo liều-lượng thấy 0% ở hệ số 0.85, 2% ở 1.11, 5% ở 1.25.
    Nó lấy im lặng để tiêu thời gian thừa. Nhưng chỉnh hệ số chỉ bớt được phần
    thừa, không xoá hết, nên vẫn phải chữa ở đầu ra.

    Không cần biết vì sao F5 bịa, chỉ cần bỏ cái nó bịa. Đo đối chứng bằng cách
    cho STT nghe lại cả hai bản - 0/16 lượt rụng chữ.

    Chỉ đụng quãng nằm GIỮA. Hai đầu là việc của `trim_silence`, còn nhịp nghỉ
    nối mảnh do `chen_lang_dau_wav` chèn sau.
    """
    if audio is None or len(audio) == 0:
        return audio
    n = max(1, int(sr * _KHUNG_LANG_MS / 1000))
    k = len(audio) // n
    if k < 3:
        return audio
    # RMS chứ không phải đỉnh, và so với chính mảnh chứ không phải số tuyệt đối
    # - xem khối chú thích ở TI_LE_LANG.
    #
    # KHÔNG làm mượt qua nhiều khung: làm mượt thì hai khung ở mép quãng lặng bị
    # tiếng bên cạnh kéo lên, quãng đo ra ngắn đi 40ms và một quãng 400ms tụt
    # xuống dưới ngưỡng 360ms nên thoát. Không cần mượt vì đã có ràng buộc phải
    # dài quá 360ms mới đụng - chỗ trũng giữa hai âm tiết chỉ 20-60ms, không thể
    # chạm tới.
    khung = audio[: k * n].reshape(k, n).astype(np.float64)
    rms = np.sqrt((khung * khung).mean(axis=1))
    dinh = float(rms.max())
    im = rms < max(dinh * ti_le_lang, san_lang)
    day = max(dinh * ti_le_day, san_lang * 0.5)
    giu_khung = max(1, int(giu_ms / _KHUNG_LANG_MS))

    doan, i, co_sua = [], 0, False
    while i < k:
        j = i
        while j < k and im[j] == im[i]:
            j += 1
        # Quãng lặng, không phải ở hai đầu, dài quá ngưỡng, VÀ có chạm đáy -
        # xem khối chú thích ở TI_LE_LANG về vì sao phải có điều kiện chạm đáy.
        if (im[i] and i > 0 and j < k
                and (j - i) * _KHUNG_LANG_MS > nguong_ms
                and float(rms[i:j].min()) < day):
            doan.append(audio[i * n:(i + giu_khung) * n])
            co_sua = True
        else:
            doan.append(audio[i * n:j * n])
        i = j
    if not co_sua:
        return audio
    doan.append(audio[k * n:])          # phần lẻ chưa đủ một khung
    return np.concatenate(doan)


def trim_silence(audio: np.ndarray, sr: int, thresh: float = 0.005,
                 keep_ms: int = 25,
                 ti_le: float = TI_LE_DAU,
                 ti_le_duoi: float = TI_LE_DUOI) -> np.ndarray:
    """Cắt khoảng lặng đầu/cuối của một mảnh TTS.

    Chừa lại 25ms hai đầu: phụ âm bật hơi đầu câu ("kh", "th", "ph") vào rất
    nhẹ, cắt sát quá là mất luôn tiếng đầu.

    Bản đầu neo vào MỘT MẪU vượt biên độ 0.005, và thế là quá mong manh: đo trên
    bản ghi cuộc gọi thật, đầu mảnh có một dải nhiễu nền RMS 0.003-0.007 (tức
    -45dB so với tiếng nói, tai không nghe thấy gì) nhưng đỉnh của nó chạm
    0.041. Một gai nhiễu duy nhất là hàm dừng cắt, để lại tới 1,2 GIÂY trống
    trước khi ra chữ - khách nghe thành "sao nó lâu nói thế".

    Nên xét NĂNG LƯỢNG từng khung và so với chính mảnh, giống `cat_lang_bia`.
    `thresh` vẫn giữ vai trò sàn tuyệt đối cho mảnh nói nhỏ đều.
    """
    if audio is None or len(audio) == 0:
        return audio
    n = max(1, int(sr * _KHUNG_LANG_MS / 1000))
    k = len(audio) // n
    if k < 2:
        return audio
    khung = audio[: k * n].reshape(k, n).astype(np.float64)
    rms = np.sqrt((khung * khung).mean(axis=1))
    dinh = float(rms.max())
    co = np.nonzero(rms > max(dinh * ti_le, thresh))[0]
    if len(co) == 0:
        return audio            # cả mảnh im lặng - trả nguyên, đừng cắt thành rỗng
    # Đuôi xét bằng ngưỡng CAO hơn để cắt được hơi thở; xem TI_LE_DUOI.
    co_duoi = np.nonzero(rms > max(dinh * ti_le_duoi, thresh))[0]
    cuoi = int(co_duoi[-1]) if len(co_duoi) else int(co[-1])
    keep = int(sr * keep_ms / 1000)
    start = max(0, int(co[0]) * n - keep)
    end = min(len(audio), (cuoi + 1) * n + keep)
    ra = audio[start:end]
    # Vuốt nhỏ dần ở mép cắt để không nghe "cụt".
    v = min(int(sr * VUOT_DUOI_MS / 1000), len(ra))
    if v > 1:
        ra = ra.copy()
        ra[-v:] = (ra[-v:] * np.linspace(1.0, 0.0, v)).astype(ra.dtype)
    return ra


class F5TTSService:
    """F5-TTS Vietnamese ViVoice wrapper for text-to-speech.

    Reference voices are held in a registry keyed by name, never as a single
    "current voice" on the instance: concurrent calls can be running on
    different phone lines with different voices, and a shared mutable ref would
    make one call switch voice mid-sentence. Every cache is keyed by voice for
    the same reason.
    """

    def __init__(self):
        self._model = None
        self._vocoder = None
        self._is_loaded = False
        # One worker: F5-TTS inference is GPU-bound, parallel CUDA calls just
        # interleave. Voice registration runs on the same thread, so _voices is
        # only ever mutated there.
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._default_voice = Path(settings.f5tts_ref_audio).stem
        self._voices: dict[str, tuple] = {}          # name -> (wave, sr, ref_text)
        self._filler_cache: dict[tuple[str, str, str], bytes] = {}   # (voice, id_th, id_duoi) -> wav
        self._filler_ms: dict[tuple[str, str, str], float] = {}      # (voice, id_th, id_duoi) -> ms
        self._synth_cache: "OrderedDict[tuple, bytes]" = OrderedDict()  # (voice, text, fast, sr)
        self._synth_cache_max = 256

    def load(self):
        """Load F5-TTS model and vocoder. Call once at startup."""
        if self._is_loaded:
            return

        logger.info("Loading F5-TTS Vietnamese ViVoice model...")

        try:
            import torch

            if str(DEVICE).startswith("cuda"):
                # TF32 for fp32 matmuls that fall outside the autocast region
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.set_float32_matmul_precision("high")
                torch.backends.cudnn.allow_tf32 = True
                # KHÔNG bật torch.backends.cudnn.benchmark: đã thử và nó làm CHẬM
                # HẲN. Độ dài câu TTS thay đổi liên tục nên mỗi kích thước mới lại
                # kích hoạt một lượt dò thuật toán. Đo thực tế trên 8 câu dài ngắn
                # khác nhau: 6/8 câu mất ~1420ms thay vì ~500ms.
                # cudnn.benchmark chỉ đáng bật khi kích thước đầu vào cố định.

            from f5_tts.infer.utils_infer import load_model, load_vocoder
            from f5_tts.model import DiT

            ckpt_path = settings.f5tts_ckpt_path
            vocab_path = settings.f5tts_vocab_path

            if not Path(ckpt_path).exists():
                raise FileNotFoundError(f"F5-TTS checkpoint not found: {ckpt_path}")
            if not Path(vocab_path).exists():
                raise FileNotFoundError(
                    f"F5-TTS vocab not found: {vocab_path}. "
                    "Did you rename config.json to vocab.txt?"
                )

            self._vocoder = load_vocoder(vocoder_name="vocos", device=DEVICE)
            # Arch phải khớp configs/F5TTS_Base.yaml - checkpoint ViVoice fine-tune
            # từ F5TTS_Base (bản cũ), KHÔNG phải F5TTS_v1_Base.
            # text_mask_padding và pe_attn_head chỉ đổi cách tính, không đổi shape
            # tensor, nên load_state_dict vẫn pass sạch nếu để sai - model clone
            # đúng giọng nhưng đọc ra tiếng Việt vô nghĩa, không có lỗi nào báo ra.
            # Mặc định của DiT là (True, None) = arch v1 => bắt buộc truyền tay.
            self._model = load_model(
                model_cls=DiT,
                model_cfg=dict(
                    dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512,
                    text_mask_padding=False, conv_layers=4, pe_attn_head=1,
                ),
                ckpt_path=ckpt_path,
                vocab_file=vocab_path,
                device=DEVICE,
            )

            # torch.compile gộp kernel, cắt chi phí phóng kernel. Đây đúng là nút
            # thắt của F5-TTS: 16 bước khuếch tán nối tiếp, mỗi bước một kernel nhỏ
            # -> đo được GPU chỉ đạt 73% và CPU 5%, không bên nào đầy.
            #
            # dynamic=True là BẮT BUỘC: độ dài câu thay đổi liên tục, để mặc định
            # thì mỗi shape mới lại biên dịch lại (đúng cái bẫy đã dính với
            # cudnn.benchmark: 6/8 câu chậm gấp 3).
            #
            # Tắt bằng F5TTS_COMPILE=false trong .env nếu gặp trục trặc.
            # PHẢI biên dịch self._model.transformer, KHÔNG phải self._model.
            # infer_batch_process gọi model.sample(), mà torch.compile chỉ chặn
            # forward/__call__ - bọc lớp ngoài thì .sample() đi thẳng vào bản gốc
            # chưa biên dịch, tức là không có tác dụng gì (đã thử và đo ra).
            # Bên trong sample(): odeint chạy 16 bước, mỗi bước gọi transformer 2
            # lần (classifier-free guidance) => 32 lượt. Đó mới là chỗ nóng.
            if settings.f5tts_compile and str(DEVICE).startswith("cuda"):
                try:
                    che_do = (settings.f5tts_compile_mode or "").strip()
                    self._model.transformer = torch.compile(
                        self._model.transformer, dynamic=True,
                        **({"mode": che_do} if che_do else {})
                    )
                    logger.info("F5-TTS: đã bật torch.compile cho DiT "
                                "(dynamic=True, mode=%s)", che_do or "mặc định")
                except Exception as e:
                    logger.warning(f"F5-TTS: torch.compile hỏng, chạy bản thường: {e}")

            ref_audio_path = settings.f5tts_ref_audio
            if Path(ref_audio_path).exists():
                self._register_voice_sync(
                    self._default_voice, ref_audio_path,
                    self._loi_doan_mau(ref_audio_path),
                )
                logger.info(f"Reference voice loaded: {ref_audio_path}")
            else:
                # Giọng mặc định có thể đã bị xoá qua UI. Nhận giọng đầu tiên còn
                # trên đĩa làm mặc định: ensure_voice() fallback về _default_voice
                # mỗi khi gặp tên lạ, trỏ nó vào một giọng không tồn tại thì cả
                # cuộc gọi chết chứ không chỉ riêng giọng đó.
                fallback = next(
                    (v for v in self.list_voices() if v["ref_text"] and not v["silent"]),
                    None,
                )
                if fallback:
                    self._default_voice = fallback["name"]
                    self._register_voice_sync(
                        fallback["name"], fallback["wav_path"], fallback["ref_text"]
                    )
                    logger.warning(
                        f"Không thấy {ref_audio_path}, dùng giọng '{fallback['name']}' "
                        "làm giọng mặc định."
                    )
                else:
                    logger.warning(
                        f"Reference audio not found: {ref_audio_path}, và không có "
                        "giọng mẫu nào khác. TTS sẽ không đọc được cho tới khi "
                        "upload một giọng."
                    )

            # Warmup chỉ chạy được khi đã có giọng. Trước đây gọi vô điều kiện nên
            # xoá giọng default là load() ném RuntimeError -> chết luôn cả TTS.
            if self._voices:
                logger.info(f"Warming up F5-TTS on {DEVICE} (first inference)...")
                # Chạy warmup QUA executor chứ đừng gọi thẳng. Với torch.compile,
                # lần suy luận đầu mới là lúc thật sự biên dịch (Triton sinh
                # kernel), và biên dịch ở luồng NÀY rồi chạy ở luồng KHÁC là chỗ
                # backend chết câm: không traceback, không log, tiến trình biến
                # mất - vì `load()` chạy ở luồng khởi động còn mọi lượt tổng hợp
                # sau đó chạy trong `self._executor`.
                #
                # Executor chỉ có ĐÚNG MỘT worker (bắt buộc, F5-TTS không an toàn
                # đa luồng), nên biên dịch ở đây thì mọi lượt sau dùng lại đúng
                # kernel đã biên dịch trên đúng luồng đó.
                self._executor.submit(
                    self._synthesize_sync, "xin chào", self._default_voice
                ).result()
            else:
                logger.warning("Bỏ qua warmup: chưa có giọng mẫu nào được nạp.")

            self._is_loaded = True
            logger.info("F5-TTS Vietnamese loaded successfully")

        except ImportError:
            logger.error(
                "F5-TTS not installed. "
                "Run: git clone https://github.com/nguyenthienhy/F5-TTS-Vietnamese && "
                "pip install -e F5-TTS-Vietnamese"
            )
            raise

    def unload(self) -> dict:
        """Nhả trọng số model khỏi VRAM để nhường GPU cho việc fine-tune.

        Fine-tune LLM cần 8-10GB, mà F5-TTS đang giữ một phần đáng kể. Không
        nhả ra thì train OOM.

        CHỈ bỏ model và vocoder. Giữ nguyên _voices và các cache: chúng nằm ở
        RAM thường, xoá đi không nhả thêm được VRAM nào mà lần dùng lại phải
        giải mã âm thanh từ đầu.

        Gọi load() sau đó là dùng lại được (_is_loaded về False nên load()
        không early-return).

        Người gọi phải đảm bảo không còn lượt tổng hợp nào đang chạy - executor
        chỉ có một luồng, nhưng unload() không chờ luồng đó.

        Trả về mức VRAM trước/sau (MiB) để bên gọi ghi log và quyết định có đủ
        chỗ train hay chưa.
        """
        do = {"vram_free_truoc_mib": None, "vram_free_sau_mib": None, "da_nha": False}
        if not self._is_loaded:
            do["ghi_chu"] = "F5-TTS chưa nạp, không có gì để nhả"
            return do

        try:
            import torch
            co_cuda = torch.cuda.is_available()
        except Exception:
            torch, co_cuda = None, False

        if co_cuda:
            do["vram_free_truoc_mib"] = round(torch.cuda.mem_get_info()[0] / 1024**2)

        logger.info("Nhả F5-TTS khỏi VRAM để nhường chỗ train...")
        self._model = None
        self._vocoder = None
        self._is_loaded = False

        import gc
        gc.collect()
        if co_cuda:
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            do["vram_free_sau_mib"] = round(torch.cuda.mem_get_info()[0] / 1024**2)

        do["da_nha"] = True
        if do["vram_free_truoc_mib"] is not None:
            logger.info(
                "VRAM trống: %s -> %s MiB (nhả thêm %s MiB)",
                do["vram_free_truoc_mib"], do["vram_free_sau_mib"],
                do["vram_free_sau_mib"] - do["vram_free_truoc_mib"],
            )
        return do

    # --- voice registry ------------------------------------------------------

    @staticmethod
    def probe_ref(wav_path: str | Path) -> dict:
        """Duration and peak level of a reference clip.

        F5-TTS clones the reference audio, so a silent file (peak ~0) yields
        silent speech - it synthesizes "successfully" and plays back as nothing,
        which is impossible to diagnose from the UI. Callers use this to refuse
        such a file up front.
        """
        try:
            data, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
        except Exception:
            return {"readable": False, "duration": 0.0, "peak": 0.0, "silent": False}

        mono = data.mean(axis=1)
        peak = float(np.abs(mono).max()) if len(mono) else 0.0
        return {
            "readable": True,
            "duration": round(len(mono) / sr, 2) if sr else 0.0,
            "peak": round(peak, 4),
            "silent": peak < SILENCE_PEAK,
        }

    def _register_voice_sync(self, name: str, wav_path: str, ref_text: str):
        """Preprocess a reference voice ONCE and keep it on the device.

        Disk read, mono mix, resample to 24kHz and device transfer would
        otherwise be redone by infer_process on every single synthesize call.
        Runs on the executor thread, which is the only writer of _voices.
        """
        import torch
        import torchaudio
        from f5_tts.infer.utils_infer import preprocess_ref_audio_text

        probe = self.probe_ref(wav_path)
        if probe["silent"]:
            logger.warning(
                f"Giọng mẫu '{name}' ({wav_path}) không có tiếng - mọi câu đọc bằng "
                "giọng này sẽ im lặng. Thu lại file 5-10 giây rồi upload đè."
            )

        ref_audio, processed_text = preprocess_ref_audio_text(wav_path, ref_text)

        audio, sr = torchaudio.load(ref_audio)
        if audio.shape[0] > 1:
            audio = torch.mean(audio, dim=0, keepdim=True)
        target_sr = 24000
        if sr != target_sr:
            audio = torchaudio.transforms.Resample(sr, target_sr)(audio)
            sr = target_sr
        audio = audio.to(DEVICE)

        self._voices[name] = (audio, sr, processed_text)

        duration = audio.shape[-1] / sr
        logger.info(f"Voice '{name}' cached in memory: {duration:.1f}s on {DEVICE}")
        if duration > 8:
            logger.warning(
                f"Ref audio giọng '{name}' dài {duration:.1f}s - ref càng dài mỗi lần "
                "synth càng chậm (ODE chạy trên cả ref). Khuyến nghị dùng clip 3-6s."
            )
        elif duration < 3:
            # ĐO THẬT 08-08, cùng câu, lặp 3 lần mỗi giọng, cho STT nghe lại:
            #   giong_heu (ref 2.21s): âm rác 2/3 lượt, biên độ vượt trần 3/3
            #   fosd_1    (ref 4.95s): âm rác 0/3,      vượt trần 0/3
            # Ref ngắn thì F5 thiếu ngữ cảnh, nó BỊA ra một cụm 2-5 âm tiết ở
            # ĐẦU mỗi lần sinh - khách nghe "hiếu... nhìn..." trước mỗi câu.
            # `trim_silence` không cắt được vì cụm đó rất TO (biên độ ~0.5).
            #
            # Cảnh báo chứ không chặn: giọng vẫn dùng được, chỉ là bẩn.
            logger.warning(
                "Ref audio giọng '%s' CHỈ %.1fs - NGẮN QUÁ. Đo được ref dưới 3s "
                "làm F5 bịa âm rác ở đầu ~2/3 số lượt và biên độ vượt trần. "
                "Thu lại clip 4-6s của cùng người rồi thay file, sẽ sạch.",
                name, duration,
            )

    async def ensure_voice(self, name: str) -> str:
        """Register a voice if it isn't loaded yet. Returns the usable voice name.

        Falls back to the default voice when `name` is unknown, so a bad
        voice_name degrades to the wrong-but-working voice instead of killing
        the call.
        """
        # "default" là TÊN QUY ƯỚC nghĩa là "giọng mặc định", không phải tên một
        # file giọng. Phiên mới và ô chọn giọng lúc chưa nạp xong đều gửi chuỗi
        # này. Không chặn ở đây thì mỗi mảnh audio lại đi tra danh sách giọng,
        # trượt, rồi ghi một dòng cảnh báo - log đầy rác mà chẳng có gì sai.
        if not name or name == "default" or name in self._voices:
            return self._default_voice if (not name or name == "default") else name

        voice = next((v for v in self.list_voices() if v["name"] == name), None)
        if not voice or not voice["ref_text"]:
            logger.warning(f"Voice '{name}' not found (or has no transcript), using default")
            return self._default_voice

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                self._executor, self._register_voice_sync,
                name, voice["wav_path"], voice["ref_text"],
            )
        except Exception as e:
            logger.warning(f"Failed to load voice '{name}': {e}. Using default.")
            return self._default_voice
        return name

    def drop_voice(self, name: str):
        """Forget a voice and everything synthesized with it (used after delete/retrain)."""
        self._voices.pop(name, None)
        for key in [k for k in self._synth_cache if k[0] == name]:
            del self._synth_cache[key]
        for key in [k for k in self._filler_cache if k[0] == name]:
            del self._filler_cache[key]

    # --- synthesis -----------------------------------------------------------

    def _autocast_ctx(self):
        """fp16 autocast on CUDA (~1.5-2x faster on RTX). Full precision elsewhere."""
        import torch

        if str(DEVICE).startswith("cuda"):
            return torch.autocast("cuda", dtype=torch.float16)
        return nullcontext()

    def _synthesize_sync(
        self, text: str, voice: str, nfe_step: int | None = None,
        speed: float | None = None,
    ) -> tuple[np.ndarray, int]:
        """Synchronous TTS synthesis (runs in thread executor).

        Calls infer_batch_process directly with the registered ref tensor —
        skips infer_process's per-call disk load/resample of the ref audio.
        Text is passed as a single batch (pipeline already chunks upstream).
        """
        from f5_tts.infer.utils_infer import infer_batch_process

        entry = self._voices.get(voice)
        if entry is None:
            raise RuntimeError(f"No reference audio loaded for voice '{voice}'")
        ref_wave, ref_sr, ref_text = entry
        toc = speed if speed is not None else self.toc_do_cua(voice)
        # Bỏ dấu chấm/phẩy CHỈ ở chữ đưa vào F5 - xem `bo_dau_cau_cho_f5`.
        text = bo_dau_cau_cho_f5(text)

        # inference_mode mạnh hơn no_grad: bỏ luôn version-counter và view-tracking
        # của autograd. Suy luận thuần nên không mất gì.
        import torch as _t
        _dat_seed(_t, text, voice, toc)
        with _t.inference_mode(), self._autocast_ctx():
            audio, sr, _ = next(
                infer_batch_process(
                    (ref_wave, ref_sr),
                    ref_text,
                    [text],
                    self._model,
                    self._vocoder,
                    mel_spec_type="vocos",
                    progress=None,
                    nfe_step=nfe_step or settings.f5tts_nfe_step,
                    # Truyền TAY hai núm này. Không truyền thì ăn mặc định của
                    # thư viện, và mọi chỉnh trong .env đều vô hiệu mà không
                    # báo gì - xem khối chú thích ở `config.f5tts_cfg_strength`.
                    cfg_strength=settings.f5tts_cfg_strength,
                    sway_sampling_coef=settings.f5tts_sway_sampling_coef,
                    speed=toc,
                    # Ép thời lượng theo ÂM TIẾT thay vì để F5 chia theo BYTE -
                    # xem khối chú thích ở `thoi_luong_ep`. None thì F5 tự tính
                    # như cũ (mảnh quá ngắn, hoặc tính ra không hợp lệ).
                    fix_duration=thoi_luong_ep(text, ref_wave.shape[-1] / ref_sr, toc),
                    device=DEVICE,
                )
            )
        return audio, sr

    def _synthesize_lo_sync(
        self, texts: list[str], voice: str, nfe_step: int | None = None,
        speed: float | None = None,
    ) -> tuple[list[np.ndarray], int]:
        """Sinh NHIỀU mảnh trong MỘT lần gọi model. Trả đúng thứ tự đưa vào.

        Vì sao phải viết tay thay vì gọi `infer_batch_process` với danh sách:
        hàm đó nhận danh sách nhưng chỉ LẶP qua từng câu, mỗi câu một lần gọi
        model. Còn `CFM.sample` bên dưới thì nhận lô thật - `cond` hình (b, nw),
        `text` danh sách b phần tử, `duration` cho phép mỗi phần tử một độ dài.

        Đo được (8 mảnh, RTX 5070): tuần tự 300ms/mảnh, gộp lô 4 còn 217ms -
        giảm 28%. Bão hoà ở lô 4, lô 8 không hơn.

        Lợi KHÔNG đến từ việc chia sẻ đoạn mẫu: F5 nối đoạn mẫu vào từng phần tử
        nên nó vẫn được tính b lần. Lợi đến từ lấp đầy GPU - một mảnh 5 từ quá
        nhỏ để dùng hết card.

        GIÁ PHẢI TRẢ: hàm này dựa vào nội bộ F5 (`CFM.sample`, `hop_length`,
        `target_rms`, cách cắt đoạn mẫu ra khỏi mel). F5 nâng cấp là có thể vỡ.
        `_synthesize_sync` một mảnh vẫn giữ nguyên đường cũ, nên hỏng cái này
        thì chỉ cần tắt gộp lô ở pipeline là chạy lại như trước.
        """
        import torch as _t
        import torchaudio
        from f5_tts.infer.utils_infer import (hop_length, target_rms,
                                              target_sample_rate)
        from f5_tts.model.utils import convert_char_to_pinyin

        entry = self._voices.get(voice)
        if entry is None:
            raise RuntimeError(f"No reference audio loaded for voice '{voice}'")
        ref_wave, ref_sr, ref_text = entry
        toc = speed if speed is not None else self.toc_do_cua(voice)
        dai_ref = ref_wave.shape[-1] / ref_sr
        chu = [bo_dau_cau_cho_f5(t) for t in texts]

        # Chuẩn hoá đoạn mẫu Y HỆT infer_batch_process - lệch một bước là tiếng
        # ra khác hẳn bản một mảnh, mà lệch kiểu đó rất khó nhìn ra.
        a = ref_wave
        if a.shape[0] > 1:
            a = _t.mean(a, dim=0, keepdim=True)
        rms = _t.sqrt(_t.mean(_t.square(a)))
        if rms < target_rms:
            a = a * target_rms / rms
        if ref_sr != target_sample_rate:
            a = torchaudio.transforms.Resample(ref_sr, target_sample_rate)(a)
        a = a.to(DEVICE)
        rt = ref_text + " " if len(ref_text[-1].encode("utf-8")) == 1 else ref_text
        ref_len = a.shape[-1] // hop_length

        khung = []
        for c in chu:
            ep = thoi_luong_ep(c, dai_ref, toc)
            if ep is not None:
                khung.append(int(ep * target_sample_rate / hop_length))
                continue
            # Mảnh quá ngắn để ép: dùng đúng công thức của F5, kể cả mẹo hạ tốc
            # còn 0.3 cho mảnh dưới 10 byte (nếu bỏ, mảnh "dạ" ra cụt lủn).
            toc_cuc_bo = 0.3 if len(c.encode("utf-8")) < 10 else toc
            khung.append(ref_len + int(ref_len / len(rt.encode("utf-8"))
                                       * len(c.encode("utf-8")) / toc_cuc_bo))

        # Seed cho CẢ LÔ, khoá theo nội dung cả lô. Đặt theo từng mảnh là vô
        # nghĩa ở đây: `sample` bốc nhiễu MỘT lần cho cả lô, nên mảnh nào cũng
        # dùng chung mớ nhiễu đó.
        _dat_seed(_t, "\x1f".join(chu), voice, toc)
        with _t.inference_mode(), self._autocast_ctx():
            gen, _ = self._model.sample(
                cond=a.repeat(len(chu), 1),
                text=convert_char_to_pinyin([rt + c for c in chu]),
                duration=_t.tensor(khung, device=DEVICE, dtype=_t.long),
                steps=nfe_step or settings.f5tts_nfe_step,
                # PHẢI trùng đường một mảnh. Để hai chỗ hai giá trị thì lượt ra
                # nhiều mảnh (đi đường lô này) đọc khác lượt ra một mảnh, mà
                # không có gì báo lỗi - `streaming_pipeline._try_synthesize_lo`
                # dùng đường này cho MỌI lượt nhiều hơn một mảnh, nó không bị
                # cờ `GOP_LO` chặn.
                cfg_strength=settings.f5tts_cfg_strength,
                sway_sampling_coef=settings.f5tts_sway_sampling_coef,
            )
            del _
            gen = gen.to(_t.float32)[:, ref_len:, :].permute(0, 2, 1)
            song = self._vocoder.decode(gen)
            if rms < target_rms:
                song = song * rms / target_rms
            song = song.cpu().numpy()

        # Lô được đệm tới độ dài LỚN NHẤT, nên phải cắt từng phần tử về đúng
        # phần của nó - không cắt thì mảnh ngắn kéo theo một đuôi im lặng dài.
        ra = []
        for i, k in enumerate(khung):
            ra.append(np.asarray(song[i][: (k - ref_len) * hop_length]))
        return ra, target_sample_rate

    async def synthesize_nhieu(
        self,
        texts: list[str],
        target_sr: int = 24000,
        voice: str | None = None,
        nfe_step: int | None = None,
        speed: float | None = None,
    ) -> list[bytes]:
        """Bản nhiều-mảnh của `synthesize`. Trả WAV theo đúng thứ tự đưa vào.

        Không dùng bộ nhớ đệm: gộp lô chỉ đáng khi các mảnh đều mới, mà mảnh
        trùng thì `synthesize` một mảnh đã trả tức thì rồi.
        """
        if not texts:
            return []
        if not self._is_loaded:
            self.load()
        voice = await self.ensure_voice(voice or self._default_voice)
        chu = [dong_dau_cuoi(normalize_for_tts(t)) for t in texts]

        loop = asyncio.get_event_loop()
        with Timer("TTS lô", logger) as t:
            song, sr = await loop.run_in_executor(
                self._executor, self._synthesize_lo_sync, chu, voice, nfe_step, speed
            )
        ra = []
        for x in song:
            x = cat_lang_bia(trim_silence(x, sr), sr)
            if sr != target_sr:
                x = resample_audio(x, sr, target_sr)
            ra.append(pcm_to_wav(float32_to_int16(x), sample_rate=target_sr))
        logger.info("TTS lô [%s]: %d mảnh -> %.0fms (%.0fms/mảnh)",
                    voice, len(chu), t.elapsed_ms, t.elapsed_ms / len(chu))
        return ra

    async def ham_nong_hinh_dang(self, voice: str | None = None,
                                 am_tiet=range(4, 15), co_lo=None) -> dict:
        """Sinh sẵn mỗi HÌNH DẠNG một lần để lượt gọi đầu khỏi phải biên dịch.

        `torch.compile` lưu đồ thị theo hình dạng tensor. `fix_duration` cấp thời
        lượng theo SỐ ÂM TIẾT nên mỗi số âm tiết là một hình dạng riêng, và lần
        đầu gặp phải biên dịch lại.

        Đo được: cùng một câu lặp 9 lần thì lần đầu 610ms, các lần sau phẳng lì
        312-318ms. Với 12 câu độ dài khác nhau: lần một 5280ms, lần hai (đã có
        hình dạng) 3688ms - chênh 30%.

        Không hâm thì cái giá đó rơi vào những lượt đầu của cuộc gọi đầu. Hâm ở
        đây thì nó rơi vào lúc khởi động, không ai nghe thấy. Cùng lý lẽ với
        phần hâm LLM trong `core/startup.py`.

        Hình dạng của lô là (cỡ lô, thời lượng dài nhất) - `CFM.sample` đệm mọi
        phần tử tới cái dài nhất. Nên phải hâm riêng từng cỡ lô sẽ dùng.
        """
        if not self._is_loaded:
            self.load()
        voice = await self.ensure_voice(voice or self._default_voice)
        co_lo = co_lo if co_lo is not None else ((1, LO_TOI_DA) if GOP_LO else (1,))
        t0 = time.perf_counter()
        xong, hong = 0, 0
        for n in am_tiet:
            chu = " ".join(["ta"] * n)          # chữ vô nghĩa, chỉ cần ĐỦ ÂM TIẾT
            for co in co_lo:
                try:
                    if co == 1:
                        await self.synthesize(chu, voice=voice, use_cache=False)
                    else:
                        await self.synthesize_nhieu([chu] * co, voice=voice)
                    xong += 1
                except Exception as e:
                    hong += 1
                    logger.debug("hâm hình dạng %d âm tiết lô %d hỏng: %s", n, co, e)
        ms = (time.perf_counter() - t0) * 1000
        logger.info("TTS: hâm %d hình dạng trong %.0fms (%d hỏng)", xong, ms, hong)
        return {"hinh_dang": xong, "hong": hong, "ms": round(ms)}

    async def synthesize(
        self,
        text: str,
        target_sr: int = 24000,
        fast: bool = False,
        voice: str | None = None,
        use_cache: bool = True,
        nfe_step: int | None = None,
        speed: float | None = None,
    ) -> bytes:
        """
        Synthesize text to WAV bytes (async).
        fast=True uses f5tts_nfe_step_first (fewer diffusion steps) —
        slightly lower quality, ~2x faster; used for the first chunk to cut TTFA.
        voice selects a registered reference voice; None uses the default.
        use_cache=False forces a real synthesis and skips storing the result —
        the voice-test page needs true timings, and its throwaway phrases must
        not evict the ones live calls depend on.
        """
        if not self._is_loaded:
            self.load()

        voice = await self.ensure_voice(voice or self._default_voice)

        # Chuẩn hoá ở đây, không ở từng caller: pipeline gọi, trang test gọi,
        # benchmark gọi, filler gọi - đặt một chỗ thì cả bốn cùng đi qua.
        # Đặt trước cache_key luôn để "ABC" và "abc" dùng chung một bản ghi.
        text = dong_dau_cuoi(normalize_for_tts(text))

        # Sentence cache: repeated phrases served instantly. Keyed by voice -
        # two lines saying the same sentence in different voices must not share.
        # `speed` PHẢI nằm trong khoá: thiếu nó thì đổi tốc xong đọc lại cùng
        # câu vẫn trả bản cũ, người dùng kéo thanh trượt mà không nghe khác gì.
        cache_key = (voice, text, fast, target_sr, nfe_step,
                     speed if speed is not None else self.toc_do_cua(voice))
        if use_cache:
            cached = self._synth_cache.get(cache_key)
            if cached is not None:
                self._synth_cache.move_to_end(cache_key)
                logger.info(f"TTS cache hit [{voice}]: '{text[:30]}...'")
                return cached

        loop = asyncio.get_event_loop()
        # nfe_step truyền tay chỉ dùng để ĐO (so các mức nfe với nhau).
        # Đường chạy thật luôn để None và lấy theo cấu hình.
        nfe = nfe_step or (settings.f5tts_nfe_step_first if fast
                           else settings.f5tts_nfe_step)

        with Timer("TTS", logger) as t:
            audio, sr = await loop.run_in_executor(
                self._executor, self._synthesize_sync, text, voice, nfe, speed
            )

        # F5-TTS trả về mỗi mảnh kèm khoảng lặng riêng: đo được 224-607ms ở ĐẦU
        # (trung bình 376ms) và ~38ms ở cuối. Ghép các mảnh lại thì mỗi ranh giới
        # câu có ~414ms chết -> nghe như bị vấp giữa các câu.
        # Lặng đầu của mảnh ĐẦU TIÊN còn cộng thẳng vào thời gian khách chờ:
        # TTFA 816ms nhưng phải 1150ms mới thực sự nghe thấy tiếng.
        audio = trim_silence(audio, sr)
        # F5 còn tự chèn quãng dừng vào GIỮA mảnh, thứ mà trim_silence không
        # đụng tới. Bóp trước khi đổi tần số: đổi tần rồi mới bóp thì phải đo
        # lại theo tần số đích, dễ lệch ngưỡng mà không ai thấy.
        audio = cat_lang_bia(audio, sr)

        # Resample if needed
        if sr != target_sr:
            audio = resample_audio(audio, sr, target_sr)

        pcm_bytes = float32_to_int16(audio)
        wav_bytes = pcm_to_wav(pcm_bytes, sample_rate=target_sr)

        # Store in LRU cache
        if use_cache:
            self._synth_cache[cache_key] = wav_bytes
            if len(self._synth_cache) > self._synth_cache_max:
                self._synth_cache.popitem(last=False)

        duration_ms = len(audio) / target_sr * 1000
        logger.info(f"TTS [{voice}]: '{text[:30]}...' -> {duration_ms:.0f}ms audio ({t.elapsed_ms:.0f}ms)")
        return wav_bytes

    # --- fillers -------------------------------------------------------------

    def default_voice_name(self) -> str:
        """Tên giọng mặc định THẬT SỰ đang dùng.

        Không đọc thẳng `settings.f5tts_ref_audio` ở nơi khác: khi file đó thiếu,
        `load()` rơi về giọng đầu tiên tìm được trên đĩa và ghi đè `_default_voice`
        - lấy từ cấu hình sẽ ra một cái tên không tồn tại.
        """
        return self._default_voice

    def _giong_thuc(self, voice: str | None) -> str:
        """Quy tên giọng lạ về giọng mặc định.

        Phiên mới mặc định voice_name="default" trong khi giọng thật tên theo
        file (vd "giong_ngan") - không quy về thì mọi tra cứu cache đều trượt và
        câu đệm chưa bao giờ phát.
        """
        name = voice or self._default_voice
        return name if name in self._voices else self._default_voice

    def co_filler(self, voice: str | None = None) -> bool:
        """Giọng này đã có câu đệm dựng sẵn chưa."""
        name = self._giong_thuc(voice)
        return any(k[0] == name for k in self._filler_cache)

    def _duong_dan_filler(self, voice: str, id_th: str, id_duoi: str, vt: str) -> Path:
        # id_th == "" la duoi tran (barefoot tail): dung thu muc "_bare" rieng
        # de khong nham lan voi ten tinh huong, va de glob xoa ban cu don gian.
        thu_muc = THU_MUC_FILLER / voice / (id_th if id_th else "_bare")
        return thu_muc / f"{id_duoi}__{vt}.wav"

    def _van_tay_filler(self, text: str, voice: str, toc: float | None = None) -> str:
        # Tốc và câu mẫu phải lấy từ bản riêng của giọng, không phải giá trị chung
        # trong .env. Nếu dùng settings.f5tts_speed: người dùng đặt tốc riêng giọng
        # đó -> tiếng WAV đã dựng theo tốc mới, nhưng vân tay tính từ tốc chung nên
        # không đổi -> hệ thống tưởng file còn tốt và phát câu đệm tốc cũ.
        #
        # Tham số toc để tình huống có speed riêng (t.speed) ra vân tay riêng của
        # mình, không dùng chung vân tay của giọng. Không truyền thì lấy tốc giọng.
        speed = toc if toc is not None else self.toc_do_cua(voice)
        entry = self._voices.get(voice)
        ref_text = entry[2] if entry is not None else settings.f5tts_ref_text
        return van_tay(text, voice, settings.f5tts_nfe_step, speed, ref_text)

    async def _dung_mot_filler(self, giong: str, id_th: str, id_duoi: str,
                               text: str, toc: float) -> str:
        """Dựng một clip filler và lưu vào cache + đĩa.

        Trả chuỗi trạng thái: 'cache' (đã có), 'doc_dia', 'dung_moi', 'loi'.

        Dùng `toc` từ tham số thay vì `self.toc_do_cua(giong)` để tình huống có
        speed riêng (t.speed) ra đúng vân tay của mình — vân tay dùng toc, và toc
        phải khớp với toc được truyền vào synthesize.

        Khoá là (giong, id_th, id_duoi): id_th="" là đuôi trần, id_th=<id_tinh_huong>
        là tổ hợp. Chọn theo độ dài tổng của clip đã ghép thay vì "độ dài đuôi trừ
        độ dài mở đầu" vì độ dài tiếng của mẩu mở đầu không suy được từ chuỗi chữ.
        """
        khoa = (giong, id_th, id_duoi)
        if khoa in self._filler_cache:
            return "cache"

        vt = self._van_tay_filler(text, giong, toc)
        p = self._duong_dan_filler(giong, id_th, id_duoi, vt)
        p.parent.mkdir(parents=True, exist_ok=True)

        if p.exists():
            try:
                wav = p.read_bytes()
                self._filler_cache[khoa] = wav
                self._filler_ms[khoa] = self._wav_duration_ms(wav)
                return "doc_dia"
            except OSError as e:
                logger.warning("Đọc %s hỏng, dựng lại: %s", p, e)

        try:
            wav = await self.synthesize(text, voice=giong, speed=toc)
        except Exception as e:
            logger.warning("Không dựng được clip (%s, %r, %r): %s",
                           giong, id_th, id_duoi, e)
            return "loi"

        # Xoá bản vân tay cũ của cùng (id_th, id_duoi), nếu không đĩa phình
        # mỗi lần đổi nfe.
        for cu in p.parent.glob(f"{id_duoi}__*.wav"):
            cu.unlink(missing_ok=True)
        try:
            p.write_bytes(wav)
        except OSError as e:
            logger.warning(
                "Ghi filler %r ra %s thất bại (%s) — giữ trong bộ nhớ, "
                "lần khởi động sau sẽ dựng lại.",
                id_duoi, p, e,
            )
        self._filler_cache[khoa] = wav
        self._filler_ms[khoa] = self._wav_duration_ms(wav)
        return "dung_moi"

    async def dung_fillers(self, kho: Kho, voice: str | None = None):
        """Bảo đảm mọi clip câu đệm đều có tiếng sẵn sàng cho giọng này.

        Thứ tự BẮT BUỘC: dựng rổ đuôi trần trước, rồi mới đến các tổ hợp
        (tình huống × mẩu mở đầu × câu đuôi). Đuôi trần là đường xuống cấp cuối
        cùng — dựng nó SAU thì trong lúc dựng tổ hợp, một cuộc gọi đến không có
        gì để phát, khách nghe im lặng trọn TTFA.

        Đọc từ đĩa trước, chỉ gọi F5 cho những clip còn thiếu hoặc lệch vân tay.
        Nhờ vậy khởi động lần hai trở đi KHÔNG chạm GPU — quan trọng vì
        `_warm_fillers` chạy đúng lúc cuộc gọi bắt đầu (api/websocket.py:286),
        và hàng chục lần gọi F5 nền sẽ giành GPU với chính cuộc gọi đang sống.

        Log số tổ hợp sắp dựng TRƯỚC KHI bắt đầu: Task 11 nạp 20 tình huống sẽ
        sinh hàng trăm tổ hợp (~840 clip nếu 20 tình huống × 1 mẩu × 42 đuôi);
        dòng đó cho phép dừng lại trước khi chạy hết GPU.
        """
        voice = await self.ensure_voice(voice or self._default_voice)
        toc_giong = self.toc_do_cua(voice)

        n_to_hop = sum(len(t.mo_dau) for t in kho.tinh_huong) * len(kho.duoi)
        logger.info(
            "Câu đệm [%s]: sắp dựng %d đuôi trần + %d tổ hợp (%d tình huống × "
            "%d mẩu TB × %d đuôi = %d clip tổng cộng)",
            voice, len(kho.duoi), n_to_hop,
            len(kho.tinh_huong),
            (sum(len(t.mo_dau) for t in kho.tinh_huong) // max(len(kho.tinh_huong), 1)
             if kho.tinh_huong else 0),
            len(kho.duoi),
            len(kho.duoi) + n_to_hop,
        )

        doc_dia = dung_moi = 0
        # Đường dẫn của MỌI clip đúng vân tay hiện tại. Gom lại để quét dọn ở
        # cuối hàm - xem `_don_filler_cu`.
        can_giu: set[Path] = set()

        # Thứ tự BẮT BUỘC: đuôi trần trước — đây là đường xuống cấp cuối cùng
        for d in kho.duoi:
            van = ghep("", d.text)
            can_giu.add(self._duong_dan_filler(
                voice, "", d.id, self._van_tay_filler(van, voice, toc_giong)))
            ket = await self._dung_mot_filler(voice, "", d.id, van, toc_giong)
            if ket == "doc_dia":
                doc_dia += 1
            elif ket == "dung_moi":
                dung_moi += 1

        # Sau khi đuôi trần đã sẵn sàng mới dựng tổ hợp
        for t in kho.tinh_huong:
            toc = t.speed if t.speed is not None else toc_giong
            for m in t.mo_dau:
                for d in kho.duoi:
                    van = ghep(m, d.text)
                    can_giu.add(self._duong_dan_filler(
                        voice, t.id, d.id, self._van_tay_filler(van, voice, toc)))
                    ket = await self._dung_mot_filler(voice, t.id, d.id, van, toc)
                    if ket == "doc_dia":
                        doc_dia += 1
                    elif ket == "dung_moi":
                        dung_moi += 1

        logger.info("Câu đệm [%s]: %d đọc từ đĩa, %d dựng mới, tổng %d",
                    voice, doc_dia, dung_moi,
                    sum(1 for k in self._filler_cache if k[0] == voice))
        self._don_filler_cu(voice, can_giu)

    def _don_filler_cu(self, voice: str, can_giu: set[Path]) -> int:
        """Xoá clip câu đệm còn sót từ vân tay CŨ của chính giọng này.

        Vì sao cần thêm dù `_dung_mot_filler` đã tự dọn: cơ chế ở đó chỉ xoá bản
        cũ của tổ hợp mà nó ĐANG dựng lại (`glob(f"{id_duoi}__*.wav")`). Tổ hợp
        nào không còn được gọi tới - kho đổi câu, tình huống bị bỏ - thì bản vân
        tay cũ của nó nằm lại mãi mãi. Đo được 13-08-2026: 1218 tệp trên đĩa với
        1116 vân tay khác nhau, trong khi kho chỉ cần 882.
        Chỉ tốn đĩa chứ không sai tiếng (vân tay không khớp thì hệ thống dựng mới
        chứ không dùng bản cũ), nhưng để lâu thì đĩa phình mỗi lần chỉnh tốc.
        Chỗ đúng để quét là ĐÂY: chỉ tại cuối `dung_fillers` mới biết trọn bộ vân
        tay cần giữ.

        CHỈ quét trong thư mục CỦA GIỌNG NÀY. Quét cả gốc là xoá clip của giọng
        khác - giọng đó chưa nạp nên `can_giu` không có gì của nó.
        """
        goc = THU_MUC_FILLER / voice
        if not goc.is_dir():
            return 0
        n = 0
        for p in goc.rglob("*.wav"):
            if p in can_giu:
                continue
            try:
                p.unlink()
                n += 1
            except OSError as e:
                logger.debug("Không xoá được clip cũ %s: %s", p, e)
        if n:
            logger.info("Câu đệm [%s]: dọn %d clip vân tay cũ", voice, n)
        return n

    @staticmethod
    def _wav_duration_ms(wav_bytes: bytes) -> float:
        """Độ dài tiếng của một WAV PCM 16-bit mono (bỏ 44 byte header)."""
        try:
            import struct
            sr = struct.unpack_from("<I", wav_bytes, 24)[0]
            return max(0.0, (len(wav_bytes) - 44) / 2 / sr * 1000)
        except Exception:
            return 0.0

    def do_dai_filler(self, cau_id: str, voice: str | None = None,
                      id_th: str = "") -> float:
        """Độ dài tiếng (ms) của một clip câu đệm, 0 nếu chưa dựng.

        Mặc định `id_th=""` tức tra đuôi trần: đúng với mọi bên gọi cũ trước Task 7.
        Nơi cần độ dài tổ hợp (id_th != "") truyền tường minh.
        """
        return self._filler_ms.get((self._giong_thuc(voice), id_th, cau_id), 0.0)

    def pick_filler(self, kho, voice: str | None = None,
                    min_ms: float = 0.0,
                    dem: dict[str, int] | None = None,
                    id_tinh_huong: str | None = None,
                    chi_duoi: set[str] | None = None,
                    ) -> tuple[bytes | None, str | None, str | None]:
        """Chọn clip câu đệm ĐÃ CÓ TIẾNG. Trả (wav, id_đuôi, id_tình_huống_dùng).

        Chỉ lấy từ cache, không bao giờ sinh: chờ sinh tiếng là phá đúng mục
        đích của câu đệm (che khoảng im lặng trong khi LLM đang chạy).

        Thử theo thứ tự: tình huống khớp → đuôi trần (id_th=""). Rơi về đuôi
        trần trả `id_th=None` để nơi gọi phân biệt được "dùng tình huống" hay
        "dùng đường xuống cấp" — quan trọng cho log đúng sự thật.

        `chi_duoi`: Task 8 truyền tập id đuôi được phép (lọc hop_cau_hoi); None
        là không giới hạn.

        Chọn theo ĐỘ DÀI TỔNG của clip đã ghép, không phải "độ dài đuôi trừ độ
        dài mở đầu": độ dài tiếng của mẩu mở đầu không suy được từ chuỗi chữ.
        """
        name = self._giong_thuc(voice)
        # Thử tình huống trước, rồi rơi về đuôi trần (""). None là placeholder
        # cho "bỏ qua lần thử này" (khi id_tinh_huong=None không có tình huống).
        for th in (id_tinh_huong, ""):
            if th is None:
                # id_tinh_huong=None → không có tình huống, bỏ qua lần đầu
                continue
            ung_vien = [(k[2], self._filler_ms[k]) for k in self._filler_cache
                        if k[0] == name and k[1] == th
                        and (chi_duoi is None or k[2] in chi_duoi)]
            if not ung_vien:
                continue
            chon_id = _chon_filler(ung_vien, min_ms=min_ms, dem=dem or {})
            if chon_id:
                # Trả id_th="" thành None để nơi gọi ghi log đúng: "dùng đuôi
                # trần" thay vì "dùng tình huống rỗng".
                return (self._filler_cache[(name, th, chon_id)],
                        chon_id, th or None)
        # Về tay không là khách nghe im lặng trọn TTFA — ghi rõ nguyên nhân.
        logger.warning(
            "pick_filler về tay không: xin giọng='%s' -> quy về '%s', "
            "tình huống=%s; cache giọng này %d mục",
            voice, name, id_tinh_huong,
            sum(1 for k in self._filler_cache if k[0] == name),
        )
        return None, None, None

    # --- discovery -----------------------------------------------------------


    # --- Tốc độ riêng cho từng giọng -----------------------------------------
    #
    # `settings.f5tts_speed` là MỘT số cho mọi giọng, mà F5 sao chép cả nhịp nói
    # của đoạn mẫu - nên một số chung không thể vừa cho mọi giọng. Đo trên chính
    # các đoạn mẫu đang có:
    #     giong_heu  3.44 âm tiết/giây      nam_moi1  3.01
    #     giong_nam  2.95                   nam_moi2  2.30
    # Chênh 1.5 lần giữa nhanh nhất và chậm nhất. Đặt tốc chung 0.64 cho vừa
    # giọng nữ thì giọng nam thành lê thê - đúng thứ người dùng kêu "đọc chậm".
    #
    # ĐẶT TỐC BAO NHIÊU: giữ speed càng SÁT 1.0 càng tốt, và chọn clip mẫu có
    # nhịp gốc sẵn gần nhịp mình muốn. Lý do (đo 08-09, xem
    # scripts/chon_doan_mau.py):
    #
    #   F5 chép ĐÚNG âm sắc - MFCC 0.992 giữa đoạn mẫu và tiếng nó sinh ra từ
    #   chính đoạn đó, trong khi giữa hai người khác nhau chỉ 0.73. Không hề có
    #   chuyện "F5 clone không giống".
    #
    #   Nhưng tai người nhận ra một người qua NHỊP nhiều hơn qua âm sắc, mà ép
    #   speed là bóp thẳng vào nhịp. Clip cũ của giong_heu nói 297 âm tiết/phút
    #   (nhanh nhất trong 15 giọng), ép 0.64 để về 180 tức chạy ở 61% nhịp thật
    #   -> đúng chất giọng nhưng nghe ra người khác. Thay bằng clip mà chính
    #   người đó đã nói chậm sẵn (211 âm tiết/phút) rồi để 0.90 thì ra 206 âm
    #   tiết/phút mà chạy ở 98% nhịp thật - vừa sạch vừa giống, và còn nhanh
    #   hơn bản cũ. Đây là cấu hình đang chạy.
    #
    # CẢNH BÁO khi tính speed: nhịp ra KHÔNG tỉ lệ thẳng với speed. Công thức
    # thời lượng của F5 chia theo `len(ref_text.encode())` - tức số BYTE, mà
    # tiếng Việt có dấu là 2-3 byte/chữ. Hai clip cùng số âm tiết nhưng khác số
    # dấu sẽ ra hai nhịp khác nhau ở cùng speed. Đừng suy ra, hãy đo bằng
    # scripts/do_nhip_doan_mau.py.
    #
    # Lưu vào tệp `<giọng>.speed` nằm cạnh `<giọng>.wav`: giọng là một bộ ba
    # (wav + txt + speed) đi liền nhau, chép sang máy khác là còn nguyên. Nhét
    # vào .env thì mỗi lần thêm giọng phải sửa cấu hình rồi khởi động lại.

    _TRAN_SPEED = (0.3, 2.5)

    def _tep_speed(self, voice: str | None) -> Path:
        """Tệp tốc của giọng, QUY TÊN LẠ về giọng thật trước khi tra.

        Không quy tên thì đây là một cái bẫy câm: phiên mới mặc định
        `voice_name="default"`, mà `default.speed` không bao giờ tồn tại, nên
        `toc_do_cua` rơi về `settings.f5tts_speed` - và đó là 0.64 trong .env,
        một giá trị sót lại của lần thử cũ.

        Hậu quả đã đo ngày 2026-08-10: xuất tiếng bằng script (gọi thẳng tên
        `giong_heu`) nghe đúng nhịp 1.20, còn cuộc gọi thật đọc ở 0.64 - chậm
        gấp rưỡi. Người dùng báo "sao 120 thì ổn khi xuất mà khi AI nói chuyện
        lại khác". Mọi phép đo trước đó đều đo nhầm đường xuất nên không thấy.

        `synthesize` có `ensure_voice` giải tên ngay đầu hàm, nên bản thân nó
        không dính. Chỗ dính là những nơi tra tốc TRƯỚC rồi mới truyền vào
        (`_toc_cho_phien` của pipeline, `test-tts` của trang giọng). Quy tên
        ngay tại đây thì mọi nơi gọi đều đúng, khỏi phải nhớ giải tên.

        CHỈ quy đúng bí danh "default" (và None), KHÔNG quy mọi tên lạ: hàm này
        dùng cho cả đường GHI (`dat_toc_do`). Quy tên lạ về giọng mặc định thì
        đặt tốc cho một giọng chưa nạp sẽ ghi đè lên tệp của giọng đang chạy.
        Tên lạ được xử lý ở `toc_do_cua`, nơi chỉ đọc nên an toàn.
        """
        goc = Path(settings.f5tts_ref_audio)
        ten = (self._default_voice or goc.stem) if (not voice or voice == "default") else voice
        return goc.parent / f"{ten}.speed"

    def toc_do_cua(self, voice: str | None = None) -> float:
        """Tốc của giọng này; chưa đặt riêng thì lấy tốc chung trong .env."""
        p = self._tep_speed(voice)
        # Tên không ứng với giọng nào đang nạp (phiên cũ giữ tên đã xoá) thì hỏi
        # tệp của giọng thật, đừng rơi thẳng về tốc chung - xem `_tep_speed`.
        if not p.exists() and voice and voice not in self._voices:
            p = self._tep_speed(self._giong_thuc(voice))
        if p.exists():
            try:
                v = float(p.read_text(encoding="utf-8").strip())
                lo, hi = self._TRAN_SPEED
                return min(max(v, lo), hi)
            except ValueError:
                logger.warning("Tốc giọng hỏng ở %s, dùng tốc chung", p)
        return settings.f5tts_speed

    def dat_toc_do(self, voice: str, toc: float) -> float:
        lo, hi = self._TRAN_SPEED
        toc = min(max(float(toc), lo), hi)
        self._tep_speed(voice).write_text(f"{toc:.3f}", encoding="utf-8")
        # Bộ nhớ đệm giữ tiếng đã dựng theo tốc CŨ - không dọn thì đổi tốc xong
        # vẫn nghe y như trước và tưởng nút không ăn.
        self._xoa_cache_giong(voice)
        logger.info("Đặt tốc giọng %s = %.2f", voice, toc)
        return toc

    def _xoa_cache_giong(self, voice: str):
        """Dọn tiếng đã dựng của một giọng.

        Tên biến là `_synth_cache`, KHÔNG phải `_cache` - viết nhầm thì hàm này
        chạy êm mà không dọn gì, và người dùng kéo thanh tốc xong nghe y như cũ
        rồi tưởng nút hỏng.

        Phải dọn cả `_filler_cache`/`_filler_ms`: chúng dùng khoá
        `(voice, id_tinh_huong, id_duoi)`, kiểm tra bằng `k[0] == voice`.
        KHÔNG dùng `voice in k` cho filler vì có thể trùng tên với id_th hay
        id_duoi và xoá nhầm khoá của giọng khác.
        """
        try:
            for k in [k for k in self._synth_cache if isinstance(k, tuple) and voice in k]:
                self._synth_cache.pop(k, None)
        except Exception as e:
            logger.debug("Không dọn được synth_cache giọng %s: %s", voice, e)
        try:
            for k in [k for k in self._filler_cache if k[0] == voice]:
                self._filler_cache.pop(k, None)
                self._filler_ms.pop(k, None)
        except Exception as e:
            logger.debug("Không dọn được filler_cache giọng %s: %s", voice, e)


    # --- Hệ số tốc riêng cho ĐƯỜNG THOẠI -------------------------------------
    #
    # Kênh GSM là 8kHz, nén mạnh, và mất gần hết dải cao - chính dải mang phụ âm
    # (s, x, ch, tr). Cùng một tốc, nghe trên trình duyệt thì rõ mà qua điện
    # thoại thì dính chữ. Nên tốc thoại phải chỉnh RIÊNG, không dùng chung với
    # tốc nghe trên web.
    #
    # Là HỆ SỐ NHÂN chứ không phải một số tuyệt đối: mỗi giọng đã có tốc riêng
    # (xem `toc_do_cua`), đặt số tuyệt đối cho đường thoại sẽ xoá sạch phần
    # chỉnh theo giọng và mọi giọng lại nói cùng một nhịp.
    _TEP_HE_SO_THOAI = "_he_so_thoai.txt"
    _TRAN_HE_SO = (0.6, 1.4)

    def _tep_he_so(self) -> Path:
        return Path(settings.f5tts_ref_audio).parent / self._TEP_HE_SO_THOAI

    def he_so_thoai(self) -> float:
        p = self._tep_he_so()
        if p.exists():
            try:
                v = float(p.read_text(encoding="utf-8").strip())
                lo, hi = self._TRAN_HE_SO
                return min(max(v, lo), hi)
            except ValueError:
                pass
        return 1.0

    def toc_nghe_thu(self, voice: str | None = None) -> float:
        """Tốc cho mọi nút NGHE THỬ - luôn bằng tốc của CUỘC GỌI.

        Vì sao phải có hàm riêng thay vì để mỗi nơi tự nhân: `test-tts` trước đây
        chỉ nhân hệ số khi `qua_dien_thoai=True`, mà cờ đó ĐỒNG THỜI hạ băng
        thông xuống 8kHz. Một cờ điều khiển hai thứ độc lập, nên không có cách
        nào nghe đúng nhịp cuộc gọi ở băng thông đầy đủ - bản 24kHz đọc 283 âm
        tiết/phút còn cuộc gọi đọc 347. Người duyệt giọng nghe một đằng, khách
        nghe một nẻo, và chú thích trong frontend đã phải đi cảnh báo điều đó
        thay vì sửa nó.

        Nay `qua_dien_thoai` chỉ còn nghĩa "hạ băng thông", còn NHỊP thì luôn
        theo cuộc gọi. Bất biến "nghe thử == cuộc gọi" được canh bằng
        `tests/test_nghe_thu_dung_nhip_cuoc_goi.py`, đối chiếu thẳng với
        `StreamingPipeline._toc_cho_phien`.
        """
        return self.toc_do_cua(voice) * self.he_so_thoai()

    def dat_he_so_thoai(self, he_so: float) -> float:
        lo, hi = self._TRAN_HE_SO
        he_so = min(max(float(he_so), lo), hi)
        self._tep_he_so().write_text(f"{he_so:.3f}", encoding="utf-8")
        # Dọn sạch cache: tiếng đã dựng theo hệ số cũ còn nằm đó thì đổi xong
        # vẫn nghe y như trước.
        try:
            self._synth_cache.clear()
        except Exception:
            pass
        logger.info("Đặt hệ số tốc đường thoại = %.2f", he_so)
        return he_so

    def _loi_doan_mau(self, duong_dan_wav: str) -> str:
        """Lời của đoạn mẫu, LẤY TỪ tệp `<giọng>.txt` nằm cạnh tệp wav.

        Vì sao không lấy thẳng `settings.f5tts_ref_text`: giọng mặc định từng là
        giọng DUY NHẤT lấy lời từ `.env`, mọi giọng khác đọc tệp `.txt` qua
        `list_voices()`. Thay tệp wav mà quên sửa `F5TTS_REF_TEXT` là hai thứ
        lệch nhau ngay, và lệch một cách rất khó thấy.

        Hỏng ra sao khi lệch (đo 08-09): đã thay wav sang clip mới nhưng `.env`
        còn câu cũ "…xây dựng được thương hiệu cá nhân". F5 được bảo đoạn mẫu
        nói câu đó trong khi nó nói câu khác, nên nó ĐỌC RA chính mấy chữ trong
        câu sai, chen vào đầu mỗi lượt - khách nghe "hiếu… cá nhân…" trước mỗi
        câu, 5/5 lượt, ở MỌI mức nfe (16/20/24/32).

        Vì sao khó thấy: mọi script đo gọi giọng THEO TÊN (`ensure_voice("heu_c")`)
        thì đi qua `list_voices()` nên đọc đúng `.txt` và báo SẠCH; chỉ đường
        chạy thật, dùng giọng mặc định, mới dính. Hai phép đo cùng một clip cho
        hai kết quả ngược nhau, suýt dẫn tới kết luận sai là do `nfe`.

        Tệp `.txt` đi liền tệp `.wav` nên không thể lệch. `.env` chỉ còn là
        đường lui khi thiếu `.txt`, và có cảnh báo khi hai bên khác nhau.
        """
        tep = Path(duong_dan_wav).with_suffix(".txt")
        if not tep.exists():
            logger.warning(
                "Giọng mặc định %s thiếu tệp .txt - phải lấy lời từ F5TTS_REF_TEXT "
                "trong .env. Tạo tệp .txt chép đúng câu đã đọc, an toàn hơn nhiều.",
                tep.name,
            )
            return settings.f5tts_ref_text
        loi = tep.read_text(encoding="utf-8", errors="replace").strip()
        if not loi:
            logger.warning("Tệp %s rỗng - lấy lời từ .env", tep.name)
            return settings.f5tts_ref_text
        # Chỉ kêu khi người ta THẬT SỰ đặt F5TTS_REF_TEXT, đừng kêu khi nó chỉ
        # đang mang giá trị mặc định trong config.py - lúc đó lệch là đương nhiên
        # và cảnh báo thành tiếng ồn, kêu mỗi lần khởi động.
        moi = " ".join(loi.split())
        cu = " ".join((settings.f5tts_ref_text or "").split())
        mac_dinh = " ".join(type(settings).model_fields["f5tts_ref_text"].default.split())
        if cu and cu != mac_dinh and cu.casefold() != moi.casefold():
            logger.warning(
                "F5TTS_REF_TEXT trong .env KHÔNG khớp %s - đang dùng tệp .txt. "
                ".env: %r | .txt: %r. Nên xoá F5TTS_REF_TEXT khỏi .env cho khỏi lẫn.",
                tep.name, cu[:60], moi[:60],
            )
        return loi

    def list_voices(self) -> list[dict]:
        """List available reference voices."""
        voices_dir = Path(settings.f5tts_ref_audio).parent
        voices = []
        for wav_file in sorted(voices_dir.glob("*.wav")):
            txt_file = wav_file.with_suffix(".txt")
            # encoding="utf-8" BẮT BUỘC: mặc định của Windows là cp1252, gặp chữ
            # có dấu là ném UnicodeDecodeError và kéo sập cả danh sách giọng -
            # tức là hỏng luôn ô chọn giọng và `ensure_voice` cho mọi giọng.
            # (Trước 08-09 giọng mặc định lấy lời từ .env nên không đi qua đây,
            # và lỗi náu được rất lâu. Nay nó dùng `_loi_doan_mau()`, cũng đọc
            # tệp .txt này, nên mọi giọng đi chung một đường.)
            ref_text = (txt_file.read_text(encoding="utf-8", errors="replace").strip()
                        if txt_file.exists() else "")
            voices.append({
                "name": wav_file.stem,
                "wav_path": str(wav_file),
                "ref_text": ref_text,
                "speed": self.toc_do_cua(wav_file.stem),
                "speed_rieng": (wav_file.parent / f"{wav_file.stem}.speed").exists(),
                **self.probe_ref(wav_file),
            })
        return voices
