"""Nối tiếng cuộc gọi trên điện thoại phone farm vào pipeline hội thoại.

Điện thoại chạy app Voice Bridge (tools/voicebridge/) mở một cổng TCP; adb
forward đưa cổng đó về máy tính qua chính sợi cáp USB. Hai chiều đều là PCM
thô 8kHz mono 16-bit, khung 20ms.

    khách nói  -> điện thoại -> TCP -> đây -> STT -> LLM -> TTS
    tiếng AI   <- điện thoại <- TCP <- đây <-----------------+

Pipeline hiện có chỉ nói chuyện với `ws.send_json(...)`, nên thay vì sửa nó,
lớp PhoneAudioSink dưới đây **giả làm WebSocket**: nhận đúng bản tin mà pipeline
gửi cho trình duyệt, rồi bẻ luồng audio xuống điện thoại. Nhờ vậy đường thoại
thật và đường thử trên trình duyệt dùng chung một pipeline, không phân nhánh.
"""

import asyncio
import base64
import io
import logging
import time
import wave

import numpy as np

from backend.config import settings
from backend.services.audio_utils import (
    compute_rms, float32_to_int16, int16_to_float32, resample_audio,
    resample_lien_tuc,
)
from backend.services.gender_detect import doan_gioi_tinh
from backend.services.recorder import GhiAmCuocGoi
from backend.services.voicemail_detect import BoDoHopThuThoai

logger = logging.getLogger(__name__)

# HAI CHIỀU CÓ TẦN SỐ RIÊNG. Trước đây dùng chung một hằng PHONE_RATE=8000 với
# lý do "đường thoại GSM 8kHz là trần" - đúng, nhưng chỉ đúng cho MỘT đích đến.
# Máy trộn âm ở 48kHz, đo được AudioTrack chạy 24kHz sạch (0 underrun), nên khi
# tiếng ra thẳng loa máy hoặc qua app VoIP thì 8k là tự bóp mình.
RATE_XUONG = settings.phone_rate_xuong     # tiếng AI -> điện thoại
RATE_LEN = settings.phone_rate_len         # micro -> STT, gửi NGUYÊN tần số này
FRAME_MS = 20

# Cùng 20ms nhưng số mẫu khác nhau vì tần số khác nhau: 8k->160 mẫu, 24k->480.
# Lẫn hai cái này là tiếng sai tốc độ, nên đặt tên rõ chiều thay vì FRAME_BYTES.
FRAME_SAMPLES_XUONG = RATE_XUONG * FRAME_MS // 1000
FRAME_BYTES_XUONG = FRAME_SAMPLES_XUONG * 2
FRAME_SAMPLES_LEN = RATE_LEN * FRAME_MS // 1000
FRAME_BYTES_LEN = FRAME_SAMPLES_LEN * 2

# Trên ngưỡng này thì đường xuống coi là băng rộng: tiếng ra thẳng loa máy chứ
# không qua loa thoại hẹp băng, nên bộ bù cho loa thoại phải tắt.
NGUONG_HEP_BANG = 16000

# Ngưỡng nhận biết có tiếng. Đo trên int16: nền im lặng của đường thoại thường
# dưới 200, giọng nói bình thường vài nghìn.
VAD_RMS_ON = 700.0
VAD_RMS_OFF = 400.0        # ngưỡng thấp hơn để không cắt giữa câu (hysteresis)
# Im bao lâu thì coi là khách nói xong. Đây là phần lớn nhất của độ trễ CẢM
# NHẬN được: STT và LLM đã được `speculate()` chạy sẵn trong lúc khách còn nói,
# nên sau khi dứt lời gần như chỉ còn chờ đúng quãng im này rồi TTS.
# Đã thử hạ xuống 500ms rồi PHẢI NÂNG LẠI: người nghe báo "khách nói chưa xong
# đã nhảy vào mồm". Người ta ngừng giữa câu để nghĩ lâu hơn nửa giây, nên 500ms
# bắt nhầm quãng ngập ngừng thành dứt lời.
#
# Đúng là cắt nhầm KHÔNG mất nội dung (lượt sau `ghep_cau_bi_cat()` nối lại),
# nhưng khách vẫn nghe AI chen ngang - thứ đó khó chịu hơn nhiều so với việc
# chờ thêm hai phần mười giây.
#
# ĐO LẠI 2026-08-05 trên chính bản ghi cuộc gọi thật (98 khoảng nghỉ GIỮA CÂU,
# 9 bản ghi, đã loại các quãng chờ giữa lượt) - scripts/do_khoang_nghi_khach.py:
#
#     khoảng nghỉ giữa câu: trung vị 120ms, phân vị 75 = 200ms, phân vị 90 = 800ms
#     ngưỡng 750ms -> chen ngang 10 lần (10.2%)
#     ngưỡng 500ms -> chen ngang 14 lần (14.3%)
#
# Tức hạ 750 -> 500 chỉ thêm 4 lần chen ngang, đổi lấy 250ms nhanh hơn ở MỌI
# lượt. Người dùng chọn 500 sau khi xem số này.
#
# ĐỌC TỪ CẤU HÌNH, không phải hằng số cứng: con số đúng phụ thuộc cách nói của
# từng nhóm khách, nên phải chỉnh được ngoài hiện trường. Đọc lúc NẠP MODULE nên
# sửa .env xong phải khởi động lại dịch vụ.
SILENCE_END_MS = settings.phone_silence_end_ms
MAX_TURN_MS = 15000        # chốt chặn: không để một lượt kéo dài vô hạn
# Ngắn hơn thế thì coi là tiếng động, không phải lời nói.
# Hạ 300 -> 170 (2026-08-04): người dùng báo nói "alo" hoặc "không" mà máy không
# phản hồi. Một TỪ ĐƠN chỉ dài ~200-280ms, nên ngưỡng 300 vứt sạch - mà "alo",
# "vâng", "không", "đúng rồi" đều là câu trả lời hợp lệ trong hội thoại bán hàng.
# Không sợ nhận nhầm tiếng động: muốn tới được đây đã phải qua VAD_ON_FRAMES=4
# (80ms LIÊN TỤC trên ngưỡng), rồi còn qua bộ lọc `avg_logprob` của STT.
#
# Hạ tiếp 170 -> 130 (2026-08-05): cuộc gọi thật (phiên 2de9bd92) vứt HAI lượt
# ngay sát ngưỡng - 160ms và 140ms, tức thiếu đúng 10-30ms. Người dùng nghe ra
# thành "AI im" và báo hội thoại đứt quãng. 130ms vẫn dài hơn hẳn 80ms mà
# VAD_ON_FRAMES đòi, nên không mở thêm cửa cho tiếng động.
MIN_TURN_MS = 130
# Phải NHIỀU khung liên tiếp vượt ngưỡng mới coi là khách bắt đầu nói. Một khung
# thôi thì mọi tiếng gõ bàn, tiếng ho, tiếng xe ngoài đường đều mở một lượt mới -
# đo trong phòng làm việc: nền ~1235 so với ngưỡng 700, cứ vài giây lại kích một
# lần và cắt luôn câu AI đang nói dở.
VAD_ON_FRAMES = 4          # 80ms liên tục

# Khách im bấy nhiêu thì bắn NGAY một lượt đoán trên TOÀN BỘ câu, không đợi hết
# SILENCE_END_MS. Quãng `SILENCE_END_MS` vốn là thời gian chết hoàn toàn: audio
# đã đủ cả câu nằm trong đệm, GPU và TTS đều rảnh, mà không ai làm gì.
#
# Đo trên cuộc gọi thật 07-08: khách nói 2380ms và 1020ms, TTFA 3633ms và
# 2456ms, và KHÔNG lượt nào dùng được bản đoán - lượt 1020ms còn ngắn hơn cả
# ngưỡng khởi động cũ (1250ms) nên chưa từng được đoán. Bắn ở đây thì bản đoán
# phủ trọn câu, `_answer_hit` gần như chắc trúng, cắt được cả STT lẫn RAG lẫn
# LLM khỏi đường găng.
#
# 300ms chứ không 200: đo được khoảng nghỉ GIỮA CÂU của khách có trung vị 120ms
# và phân vị 75 là 200ms, nên bắn ở 200ms là đoán nhầm quãng ngập ngừng rất
# nhiều lần. Đoán nhầm không sai kết quả (bản đoán bị huỷ và làm lại) nhưng tốn
# GPU vô ích. 300ms vẫn còn 200ms trong quãng im để bản đoán chạy.
SPEC_CUOI_MS = 300

# Hệ số nhân trên nền kênh đo được. Nền thoại EDGE dao động nhiều nên phải cách
# nó một quãng rộng, không thì tiếng ồn cũng mở lượt.
VAD_HE_SO_ON = 3.0
VAD_HE_SO_TAT = 1.8

# Sàn của bộ làm sạch: không hạ vạch nhiễu xuống dưới mức này. Hạ sạch hoàn toàn
# thì sinh tiếng "lanh canh" (musical noise) còn khó chịu hơn chính nhiễu nền.
SAN_LAM_SACH = 0.15
# Sàn cho bộ lọc TIẾNG KHÁCH. Thấp hơn bản dùng cho TTS vì mục tiêu khác hẳn:
# ở đây không cần nghe tự nhiên, chỉ cần STT đọc đúng, nên hạ nhiễu mạnh tay
# hơn được. Nhưng không hạ tới 0: nhiễu "lanh canh" còn làm Whisper bịa chữ.
SAN_LAM_SACH_STT = 0.06
# Dải tiếng nói của kênh thoại. Ngoài dải này chỉ có ù nguồn và rít, bỏ đi thì
# STT bớt nhiễu mà không mất chữ nào - kênh vốn không mang gì ngoài dải đó.
STT_DAI_DUOI = 250.0
STT_DAI_TREN = 3600.0


def lam_sach_cho_vocoder(x: np.ndarray, sr: int) -> np.ndarray:
    """Hạ nhiễu nền giữa các hài, để bộ mã hoá của mạng dựng lại giọng đúng hơn.

    AMR-NB không nén sóng như MP3 - nó là VOCODER: phân tích tiếng thành "bộ lọc
    thanh quản + nguồn kích thích" rồi dựng lại ở đầu kia theo mô hình tiếng
    người. Mô hình đó luyện trên giọng người thật, nên phần nhiễu rộng dải của
    mô hình khuếch tán làm nó dựng sai -> nghe kim loại, và đặc trưng nhận dạng
    người nói bị bóp méo -> nghe ra người khác.

    Đo được: HNR (tỉ số hài trên nhiễu) của tiếng TTS chỉ 4.5-4.9 dB, trong khi
    giọng người bình thường 15-25 dB. Đó chính là phần vocoder không xử lý được.
    Tăng nfe KHÔNG giúp - đã đo từ nfe 8 tới 32, phẳng phổ và HNR gần như không đổi.

    Cách làm: ước lượng nền nhiễu theo từng vạch tần số (phân vị thấp theo thời
    gian - chỗ nào cũng có năng lượng kể cả lúc im thì đó là nhiễu), rồi nhân
    theo kiểu Wiener để hạ những vạch bị nhiễu áp đảo mà giữ nguyên vạch có hài.
    """
    from scipy import signal as _sg

    N, H = 512, 128
    f, t, Z = _sg.stft(x, fs=sr, nperseg=N, noverlap=N - H, window="hann")
    P = np.abs(Z) ** 2

    # Nền nhiễu = phân vị 15% theo thời gian cho từng vạch. Lấy trung vị thì dính
    # cả tiếng nói vào nền; lấy min thì bắt phải khung im bất thường.
    nen = np.percentile(P, 15, axis=1, keepdims=True)

    # Hệ số Wiener: vạch nào tỉ số tín/nhiễu cao thì giữ, thấp thì hạ. Chặn sàn
    # để không hạ tới 0 - hạ sạch thì sinh tiếng "lanh canh" còn khó chịu hơn nhiễu.
    snr = np.maximum(P / (nen + 1e-12) - 1.0, 0.0)
    G = np.maximum(snr / (snr + 1.0), SAN_LAM_SACH)

    _, y = _sg.istft(Z * G, fs=sr, nperseg=N, noverlap=N - H, window="hann")
    y = y[:len(x)]
    if len(y) < len(x):                      # istft có thể trả ngắn hơn vài mẫu
        y = np.pad(y, (0, len(x) - len(y)))
    return y.astype(np.float32)


def lam_sach_tieng_khach(x: np.ndarray, sr: int) -> np.ndarray:
    """Lọc tiếng khách trước khi đưa vào STT.

    Khác hẳn `lam_sach_cho_vocoder` dù cùng kỹ thuật: bản kia lọc tiếng AI để
    NGƯỜI nghe nên phải giữ tự nhiên, còn bản này lọc để MÁY đọc nên hạ nhiễu
    mạnh tay hơn được và cắt hẳn ngoài dải tiếng nói.

    Vì sao cần: đường thoại EDGE có nền ồn cao, cộng tiếng phòng bên khách.
    Whisper BỊA CHỮ trên nhiễu - một cuộc gọi thật cho ra bốn lượt toàn chữ bịa.
    Bộ lọc `avg_logprob` chặn được phần lớn, nhưng chặn xong là MẤT lượt; lọc
    sạch đầu vào thì giữ được lượt thật của khách.

    Ba bước:
      1. cắt ngoài 250-3600Hz - kênh thoại không mang gì ngoài dải đó
      2. hạ nhiễu theo từng vạch tần số (Wiener, nền = phân vị thấp theo thời gian)
      3. chuẩn mức - STT ăn ổn định hơn khi mức đều
    """
    from scipy import signal as _sg

    if x.size < 512:
        return x

    # Dùng dạng KHÂU BẬC HAI (sos), đừng dùng dạng b/a: tần số cắt chuẩn hoá ở
    # đây chỉ 0.031 (250Hz trên 8000Hz), bậc 4 viết dạng b/a mất ổn định số và
    # cho ra rác. Đo được: CER 0.05 -> 0.86 kể cả trên tiếng gần như sạch.
    nyq = sr / 2
    cao = min(STT_DAI_TREN, nyq * 0.98)
    sos = _sg.butter(4, [STT_DAI_DUOI / nyq, cao / nyq], btype="bandpass",
                     output="sos")
    y = _sg.sosfiltfilt(sos, x).astype(np.float32)

    N, H = 512, 128
    _, _, Z = _sg.stft(y, fs=sr, nperseg=N, noverlap=N - H, window="hann")
    P = np.abs(Z) ** 2
    nen = np.percentile(P, 15, axis=1, keepdims=True)
    snr = np.maximum(P / (nen + 1e-12) - 1.0, 0.0)
    G = np.maximum(snr / (snr + 1.0), SAN_LAM_SACH_STT)
    _, y = _sg.istft(Z * G, fs=sr, nperseg=N, noverlap=N - H, window="hann")
    y = y[:x.size]
    if y.size < x.size:
        y = np.pad(y, (0, x.size - y.size))

    dinh = float(np.abs(y).max()) or 1e-9
    return (y / dinh * 0.9).astype(np.float32)


def chuan_muc_thoai(y: np.ndarray) -> np.ndarray:
    """Giới hạn đỉnh rồi chuẩn mức. Cần cho MỌI đường thoại, không riêng hẹp băng.

    Tách riêng khỏi `toi_uu_cho_thoai` vì hai việc khác hẳn nhau: bộ bù hẹp băng
    chỉ đúng khi đích đến là loa thoại, còn kiểm soát mức thì luôn cần - bộ mã
    AMR của mạng vỡ ở đỉnh y như mọi bộ mã khác. Gộp chung đã gây một lỗi thật:
    nâng rate_xuong lên 24000 làm tắt cả cụm, tiếng TTS đi thẳng ở mức đầy thang
    vào bộ trộn của codec và người nghe báo "dè".
    """
    # Giới hạn đỉnh mềm TRƯỚC khi chuẩn mức. Làm ngược lại thì bộ giới hạn nén
    # đỉnh xuống và kéo RMS lên, mức cuối cùng lệch khỏi đích. Dùng tanh chứ
    # không cắt cứng: cắt cứng sinh hài bậc lẻ nghe rè.
    dinh = float(np.abs(y).max())
    if dinh > settings.phone_dinh_toi_da:
        y = (np.tanh(y / dinh * 1.4) / np.tanh(1.4)
             * settings.phone_dinh_toi_da).astype(np.float32)

    # Chuẩn mức, nhưng không để việc chuẩn đẩy đỉnh vượt trần - thà nhỏ hơn đích
    # một chút còn hơn vỡ tiếng.
    rms = float(np.sqrt((y ** 2).mean())) or 1e-9
    dinh = float(np.abs(y).max()) or 1e-9
    he_so = min(10 ** (settings.phone_muc_dbfs / 20) / rms,
                settings.phone_dinh_toi_da / dinh)
    return (y * he_so).astype(np.float32)


def toi_uu_cho_thoai(x: np.ndarray, sr: int) -> np.ndarray:
    """Chỉnh tiếng TTS cho hợp đường thoại trước khi hạ tần số.

    Vì sao cần: giọng F5-TTS nặng dải trầm - đo được năng lượng 1-3.4kHz (nơi
    chứa phụ âm, quyết định nghe rõ) chỉ bằng 0.14-0.25 lần dải 100Hz-1kHz.
    Nghe qua tai nghe thì phần trầm cho giọng có thân, nhưng LOA ĐIỆN THOẠI
    KHÔNG PHÁT ĐƯỢC dải đó, nên tới tai khách chỉ còn phần vốn đã yếu -> mỏng
    và đục. Đây đúng là triệu chứng "bản gốc nghe ổn, sang điện thoại thì không".

    Đo sau khi bật: độ nghiêng phổ 0.14-0.25 -> 0.33-0.59, mức ổn định -19.1
    dBFS (trước dao động -16.8 tới -17.0), dự trữ đỉnh 2.4-3.9dB (trước 0.6-1.2,
    và có câu đo được đỉnh 1.041 tức ĐÃ VỠ TIẾNG).
    """
    from scipy import signal as _sg

    # 0. Hạ nhiễu nền TRƯỚC mọi thứ khác. Đây là phần bộ mã hoá của mạng dựng
    #    sai thành âm kim loại - lọc và nâng dải không chữa được nó.
    y = lam_sach_cho_vocoder(x, sr) if settings.phone_lam_sach else x

    # 1. Bỏ dải trầm. Loa điện thoại không phát được, giữ lại chỉ tốn bit của
    #    codec và đẩy mức tổng lên khiến phần nghe được phải nhỏ đi.
    b, a = _sg.butter(2, settings.phone_loc_tram_hz / (sr / 2), btype="highpass")
    y = _sg.filtfilt(b, a, y).astype(np.float32)

    # 2. Nâng dải quanh 2.2kHz - nơi chứa phụ âm.
    f0, Q = 2200.0, 0.9
    A = 10 ** (settings.phone_nang_do_ro_db / 40)
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * Q)
    bb = np.array([1 + alpha * A, -2 * np.cos(w0), 1 - alpha * A])
    aa = np.array([1 + alpha / A, -2 * np.cos(w0), 1 - alpha / A])
    y = _sg.lfilter(bb / aa[0], aa / aa[0], y).astype(np.float32)

    # 3+4. Giới hạn đỉnh rồi chuẩn mức.
    return chuan_muc_thoai(y)


def _uoc_luong_chu_ky(x: np.ndarray, sr: int, N: int, H: int,
                      nguong: float = 0.30) -> np.ndarray:
    """Chu kỳ cao độ (số mẫu) từng khung; 0 = vô thanh hoặc im.

    Ngưỡng 0.30 để chỉ nhận khung thật sự hữu thanh. Áp lọc lược lên phụ âm xát
    (s, x, ch) sẽ làm nhoè chúng, mà phụ âm mới là thứ quyết định nghe rõ.
    """
    lo, hi = int(sr / 400), int(sr / 70)
    ra = []
    for k in range(0, max(len(x) - N, 0) + 1, H):
        w = x[k:k + N]
        if len(w) < N or np.sqrt((w ** 2).mean()) < 0.01:
            ra.append(0)
            continue
        w = w - w.mean()
        ac = np.correlate(w, w, mode="full")[N - 1:]
        if ac[0] <= 0 or hi >= len(ac):
            ra.append(0)
            continue
        ac = ac / ac[0]
        seg = ac[lo:hi]
        i = int(np.argmax(seg))
        ra.append(lo + i if seg[i] > nguong else 0)
    return np.array(ra)


def _lpc(x: np.ndarray, p: int):
    """Levinson-Durbin. Trả None khi khung suy biến."""
    r = np.correlate(x, x, mode="full")[len(x) - 1:len(x) + p]
    if len(r) < p + 1 or r[0] <= 0:
        return None
    a = np.zeros(p + 1)
    a[0], e = 1.0, r[0]
    for i in range(1, p + 1):
        acc = r[i] + (np.dot(a[1:i], r[i - 1:0:-1]) if i > 1 else 0.0)
        k = -acc / e
        moi = a.copy()
        for j in range(1, i):
            moi[j] = a[j] + k * a[i - j]
        moi[i] = k
        a = moi
        e *= (1 - k * k)
        if e <= 0:
            return None
    return a


def tang_tuan_hoan(x: np.ndarray, sr: int) -> np.ndarray:
    """Làm tín hiệu lặp lại rõ hơn theo chu kỳ cao độ, để bộ mã dựng đúng hơn.

    Vì sao khác `lam_sach_cho_vocoder` (thứ đã thử và thất bại): cái kia hạ nhiễu
    theo từng vạch phổ, nhưng AMR-NB không nhìn vào phổ - nó nhìn vào việc tín
    hiệu có LẶP LẠI đúng chu kỳ cao độ không (bộ dự đoán chu kỳ, LTP). Nên phải
    tác động đúng vào tính lặp lại đó.

    Hai bước:
      1. Lọc lược đồng bộ cao độ - cộng tín hiệu với chính nó trễ đúng một chu
         kỳ, lấy CẢ chu kỳ trước và sau. Chỉ lấy một phía thì lệch pha, nghe
         thành tiếng vọng nhẹ.
      2. Lặp lại trên PHẦN DƯ tuyến tính - tách bao phổ (LPC) ra rồi chỉ làm
         phần nguồn kích thích. Giữ nguyên bao phổ nên KHÔNG đổi âm sắc.

    Đo trên tiếng F5 thật qua AMR-NB: 6.25 -> 7.35 dB HNR (mốc người thật 7.24).

    Chạy ở tần số ĐÍCH (8kHz), không phải 24kHz: bậc LPC 10 vừa đúng cho băng
    0-4kHz, và đây cũng là tín hiệu bộ mã thật sự nhìn thấy.
    """
    from scipy import signal as _sg

    N, H, p = int(0.04 * sr), int(0.02 * sr), 10
    if len(x) < N * 2:
        return x
    chu_ky = _uoc_luong_chu_ky(x, sr, N, H)

    # 1. lọc lược
    y = x.copy()
    a_luoc = settings.phone_luoc_alpha
    for i, T in enumerate(chu_ky):
        if T <= 0:
            continue
        idx = np.arange(i * H, min(i * H + H, len(x)))
        ok = (idx - T >= 0) & (idx + T < len(x))
        if not ok.any():
            continue
        j = idx[ok]
        y[j] = (x[j] + a_luoc * x[j - T] + a_luoc * x[j + T]) / (1 + 2 * a_luoc)

    # 2. trên phần dư LP, cộng chồng khung có cửa sổ
    a_du = settings.phone_du_alpha
    ra = np.zeros(len(y), dtype=np.float32)
    dem = np.zeros(len(y), dtype=np.float32)
    cua = np.hanning(N).astype(np.float32)
    for i, T in enumerate(chu_ky):
        a0, b0 = i * H, i * H + N
        if b0 > len(y):
            break
        w = y[a0:b0] * cua
        a = _lpc(w, p) if (T > 0 and np.sqrt((w ** 2).mean()) >= 1e-4) else None
        if a is None:
            ra[a0:b0] += w
            dem[a0:b0] += cua
            continue
        du = _sg.lfilter(a, [1.0], w)
        if T < len(du):
            du[T:] = (du[T:] + a_du * du[:-T].copy()) / (1 + a_du)
        lai = _sg.lfilter([1.0], a, du)
        # giữ nguyên năng lượng khung, tránh bộ lọc kéo mức trôi
        r0 = np.sqrt((w ** 2).mean())
        r1 = np.sqrt((lai ** 2).mean()) or 1e-9
        ra[a0:b0] += (lai * (r0 / r1)).astype(np.float32)
        dem[a0:b0] += cua

    # Rìa đầu/cuối: cửa sổ Hann tắt dần về 0 nên ở đó `dem` rất nhỏ, chia cho nó
    # sinh một đỉnh khổng lồ - và bộ chặn đỉnh bên dưới sẽ kéo CẢ tín hiệu xuống
    # theo, làm câu nói nhỏ đi hàng chục lần. Ngưỡng 1e-6 quá lỏng để bắt việc
    # này. Chỗ nào cửa sổ phủ chưa đủ thì coi như chưa xử lý, giữ nguyên đầu vào.
    thieu = dem < 0.5
    dem[thieu] = 1.0
    z = (ra / dem).astype(np.float32)
    z[thieu] = y[thieu]

    # Chặn đỉnh lại cho chắc: bước chuẩn mức đã chạy TRƯỚC bước này, nên nếu bộ
    # lọc có đẩy đỉnh lên thì không còn ai kéo xuống nữa.
    dinh = float(np.abs(z).max())
    if dinh > settings.phone_dinh_toi_da:
        z = z * (settings.phone_dinh_toi_da / dinh)
    return z.astype(np.float32)


def _wav_to_pcm(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """Bóc WAV do TTS trả về thành mảng float32 + tần số lấy mẫu."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())
    return int16_to_float32(frames), rate


class PhoneAudioSink:
    """Giả WebSocket cho pipeline: bản tin `audio` được bẻ xuống điện thoại.

    Các bản tin khác (transcript, metrics, filler...) chỉ ghi log — đường thoại
    không có giao diện để hiển thị chúng.
    """

    def __init__(self, bridge: "PhoneCallBridge"):
        self.bridge = bridge
        self.last_transcript = ""
        self.last_reply = ""

    async def send_json(self, msg: dict):
        kind = msg.get("type")

        if kind == "audio":
            wav = base64.b64decode(msg.get("data", ""))
            if wav:
                await self.bridge.play(wav)
            return

        if kind == "transcript":
            self.last_transcript = msg.get("text", "")
            logger.info(f"{self.bridge.tag} khách: {self.last_transcript}")
            # Từ khoá hộp thư thoại chỉ lộ ra ở bản ghi, nên đây là chỗ duy nhất
            # bắt được dấu hiệu mạnh nhất trong ba dấu hiệu.
            self.bridge.soi_hop_thu_thoai(self.last_transcript)
        elif kind == "turn_complete":
            # Tên trường là `full_response`, không phải `text` - lấy nhầm thì
            # giao diện luôn hiện AI chưa nói gì dù nó đã trả lời xong.
            self.last_reply = msg.get("full_response", self.last_reply)
            logger.info(f"{self.bridge.tag} AI: {self.last_reply[:80]}")
        elif kind == "error":
            self.bridge.last_error = msg.get("message", "lỗi không rõ")
            logger.warning(f"{self.bridge.tag} pipeline báo lỗi: {self.bridge.last_error}")
        else:
            logger.debug(f"{self.bridge.tag} bỏ qua bản tin '{kind}'")


class PhoneCallBridge:
    """Một phiên tiếng với một điện thoại. Mỗi máy trong phone farm một thể."""

    def __init__(self, pipeline, session, host: str = "127.0.0.1", port: int = 8123,
                 serial: str | None = None):
        self.pipeline = pipeline
        self.session = session
        # Đường thoại đẩy tiếng GỐC 8kHz vào đệm, không nâng tần. Khai đúng tần
        # số ở đây để STT ghi đúng vào header WAV và `do_hut_tieng` đo đúng -
        # mặc định của phiên là 16kHz (đường trình duyệt).
        self.session.audio_rate = RATE_LEN
        # Nhãn nhận dạng CUỘC GỌI NÀY trong log. Bắt buộc khi chạy nhiều
        # máy: mọi dòng log trước đây đều mở đầu bằng "[phone]" trơn, nên
        # hai cuộc gọi song song trộn lẫn vào nhau và không cách nào biết
        # dòng nào của máy nào. Lấy 4 ký tự cuối của serial cho gọn - đủ
        # phân biệt trong một dàn máy, mà không làm dài mỗi dòng log.
        may = ((serial or settings.phone_serial) or "")[-4:] or "????"
        self.tag = f"[phone {may}/{session.session_id}]"
        self.host, self.port = host, port
        # Cần để dựng lại `adb forward` khi ổ cắm chết giữa cuộc gọi.
        self.serial = serial or settings.phone_serial

        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.sink = PhoneAudioSink(self)

        self._out: asyncio.Queue[bytes] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self.running = False
        # Lượt đang sinh câu trả lời. Phải giữ để HUỶ được khi khách chen ngang:
        # chỉ dọn hàng đợi thôi thì lượt cũ vẫn chạy tiếp và nạp đầy lại ngay,
        # khách nghe AI im một nhịp rồi nói tiếp như chưa có gì xảy ra.
        self._luot_task: asyncio.Task | None = None

        # thống kê để trả về cho giao diện
        self.turns = 0
        self.last_error = ""

        # Đệm mồi giữ trước ở máy, giây. Càng dày càng ít hụt tiếng nhưng cắt
        # lời càng chậm: thứ đã rời khỏi hàng đợi này thì không lấy lại được.
        self.dem_mo_s = settings.phone_dem_mo_ms / 1000.0

        # Chưa nối máy thì đường xuống chỉ có nhạc chờ / hồi âm chuông. Để
        # pipeline nghe cái đó thì STT phiên âm ra rác và AI trả lời vào hư
        # không - đúng thứ đã xảy ra ở lần gọi thử đầu ("5 lượt hội thoại" trong
        # khi chưa ai bắt máy). Bật cờ này lên là đọc để socket khỏi ứ nhưng vứt.
        self.tam_dung_nghe = False

        # Nền ồn thật của kênh, đo ngay khi bắt đầu nghe. Hằng số VAD_RMS_ON
        # được chỉnh cho micro trình duyệt; kênh thoại EDGE có nền cao hơn nên
        # dùng hằng số đó thì mọi tiếng ồn đều mở một lượt mới và Whisper bịa
        # chữ trên đó - đo được một cuộc gọi cho 4 lượt toàn chữ bịa.
        self.nen_kenh: float | None = None
        self._mau_nen: list[float] = []

        # Móc quan sát: nếu đặt, mỗi khung thu được đưa thẳng vào đây trước khi
        # qua VAD. Dùng cho các phép đo cần nhìn tiếng thô (ví dụ kiểm xem tiếng
        # AI có thật sự lên được đường lên của cuộc gọi không).
        self.theo_doi_khung = None

        # --- F7 hộp thư thoại, F8 giới tính -------------------------------
        # Cả hai chỉ chạy trong ít giây đầu cuộc gọi rồi tự tắt, nên chi phí
        # nằm ngoài đường găng của độ trễ hội thoại.
        self.bo_do_hop_thu = BoDoHopThuThoai(sr=RATE_LEN)
        self._dem_giong = bytearray()      # tiếng khách để đo cao độ
        self.da_doan_gioi_tinh = False

        # --- F12 ghi âm ----------------------------------------------------
        # None = không ghi. Bộ quay số tự động bật/tắt theo `campaigns.record_calls`.
        self.ghi_am: GhiAmCuocGoi | None = None

        # trạng thái cho phép đo độ trễ
        self._probing = False
        self._probe_first_write: float | None = None
        self._probe_hit: float | None = None
        self._probe_freq = 1000.0
        self._probe_writes = 0

    # --- vòng đời ---------------------------------------------------------

    def nguong_on(self) -> float:
        """Ngưỡng coi là khách bắt đầu nói. Lấy cái CAO HƠN giữa hằng số và nền
        kênh nhân hệ số - nền thấp thì giữ như cũ, nền cao thì tự nâng theo."""
        if self.nen_kenh is None:
            return VAD_RMS_ON
        return max(VAD_RMS_ON, self.nen_kenh * VAD_HE_SO_ON)

    def nguong_tat(self) -> float:
        if self.nen_kenh is None:
            return VAD_RMS_OFF
        return max(VAD_RMS_OFF, self.nen_kenh * VAD_HE_SO_TAT)

    async def _mo_o_cam(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        sock = self.writer.get_extra_info("socket")
        if sock is not None:
            import socket as _s
            sock.setsockopt(_s.IPPROTO_TCP, _s.TCP_NODELAY, 1)

    async def noi_lai(self, serial: str | None = None) -> bool:
        """Dựng lại ổ cắm khi nó chết giữa cuộc gọi.

        Đã xảy ra thật giữa một cuộc gọi đang chạy: máy chủ adb trên Windows tự
        khởi động lại, `adb forward` mất theo, ổ cắm đứt ngay lúc đang phát. Trước
        đây `_write_loop` gặp lỗi là thoát hẳn nên phần còn lại của cuộc gọi câm
        tiếng - người nghe chỉ thấy tiếng đứt quãng rồi im.
        """
        if not self.running:
            return False
        try:
            if self.writer is not None:
                self.writer.close()
        except Exception:
            pass
        # Dựng lại forward trước: ổ cắm chết thường vì forward mất, mở lại ổ cắm
        # mà không dựng forward thì chỉ nhận thêm một lần từ chối kết nối.
        if serial or self.serial:
            try:
                from backend.services import adb_service
                await adb_service.forward_port(serial or self.serial, self.port)
            except Exception as e:
                logger.debug(f"{self.tag} dựng lại forward không được: {e}")
        try:
            await self._mo_o_cam()
            logger.info(f"{self.tag} đã nối lại cầu tiếng")
            return True
        except Exception as e:
            logger.warning(f"{self.tag} nối lại không được: {e}")
            return False

    async def start(self, ghi_am: bool = True):
        await self._mo_o_cam()
        self.running = True
        if ghi_am:
            bo_ghi = GhiAmCuocGoi(
                self.session.session_id, settings.recordings_dir,
                sr=RATE_LEN, mau_moi_khung=FRAME_SAMPLES_LEN,
            )
            # Ghi âm hỏng thì cuộc gọi vẫn phải chạy: mất bản ghi còn hơn mất
            # cuộc gọi.
            self.ghi_am = bo_ghi if await bo_ghi.start() else None
        else:
            # Nói ra chứ đừng im lặng. Đã mất một buổi truy "vì sao 17 cuộc gọi
            # thật không có bản ghi nào" mà log không hề nhắc tới ghi âm — không
            # phân biệt được "ai đó tắt ghi âm" với "bộ ghi chạy rồi hỏng".
            logger.warning(f"{self.tag} ghi âm TẮT cho cuộc này — sẽ không có bản ghi")
        self._tasks = [
            asyncio.create_task(self._read_loop(), name="phone-read"),
            asyncio.create_task(self._write_loop(), name="phone-write"),
        ]
        logger.info(f"{self.tag} đã nối cầu tiếng {self.host}:{self.port}")

    async def stop(self):
        self.running = False
        # Huỷ lượt đang sinh trước: không thì nó chạy tiếp, gọi TTS rồi ghi vào
        # socket đã đóng - vừa phí GPU vừa đẻ lỗi sau khi đã "dừng cầu tiếng".
        await self.huy_luot_dang_chay()
        for t in self._tasks:
            t.cancel()
        self._tasks = []

        # Chốt bản ghi TRƯỚC khi đóng socket: bộ ghi còn vài trăm mili giây
        # tiếng trong hàng đợi chưa kịp mã hoá.
        if self.ghi_am is not None:
            ket_qua = await self.ghi_am.stop()
            self.ghi_am = None
            if ket_qua["duong_dan"]:
                self.session.recording_path = ket_qua["duong_dan"]
                self.session.recording_size = ket_qua["dung_luong"]
                logger.info(
                    f"{self.tag} bản ghi {ket_qua['giay']}s "
                    f"({ket_qua['dung_luong'] / 1024:.0f} KB) — {ket_qua['duong_dan']}"
                )
            elif ket_qua["loi"]:
                logger.warning(f"{self.tag} ghi âm thất bại: {ket_qua['loi']}")

        if self.writer is not None:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        logger.info(f"{self.tag} đã đóng cầu tiếng ({self.turns} lượt)")

    # --- chiều ra: tiếng AI xuống điện thoại -------------------------------

    async def play(self, wav_bytes: bytes, xu_ly: bool = True):
        """Nhận WAV từ TTS (24kHz), đưa về RATE_XUONG rồi xếp hàng gửi xuống máy.

        `xu_ly=False` gửi nguyên tiếng gốc, chỉ dùng khi đo để so sánh - đường
        thật luôn phải qua bước kiểm soát mức.
        """
        audio, rate = _wav_to_pcm(wav_bytes)
        if not xu_ly:
            if rate != RATE_XUONG:
                audio = resample_audio(audio, rate, RATE_XUONG)
            pcm = float32_to_int16(audio)
            for i in range(0, len(pcm) - FRAME_BYTES_XUONG + 1, FRAME_BYTES_XUONG):
                await self._out.put(pcm[i:i + FRAME_BYTES_XUONG])
            return
        # Bộ bù chỉ có nghĩa khi đầu kia là LOA THOẠI HẸP BĂNG. Đường xuống băng
        # rộng thì không có gì để bù, bật lên chỉ tự cắt trầm và nâng chói - đúng
        # cái tiếng "dè" mà nó sinh ra để chữa.
        # Chỉnh âm TRƯỚC khi hạ tần: lọc và nâng dải ở 24kHz thì bộ lọc có đủ độ
        # phân giải, làm sau khi đã xuống 8kHz thì dải cần nâng đã sát trần.
        if settings.phone_toi_uu_am and RATE_XUONG <= NGUONG_HEP_BANG:
            audio = toi_uu_cho_thoai(audio, rate)
        else:
            # Băng rộng thì không bù phổ, NHƯNG vẫn phải kiểm soát mức: bộ mã
            # AMR ở đầu mạng vỡ đỉnh y hệt, và tiếng TTS ra ở mức đầy thang.
            audio = chuan_muc_thoai(audio)
        if rate != RATE_XUONG:
            audio = resample_audio(audio, rate, RATE_XUONG)

        # Tăng tính tuần hoàn SAU khi đã hạ tần: chạy ở đúng tần số bộ mã nhìn
        # thấy (8kHz), và bậc LPC 10 vừa đúng cho băng 0-4kHz. Làm ở 24kHz thì
        # bậc đó quá thấp, bao phổ dựng ra sai.
        if settings.phone_tang_tuan_hoan and RATE_XUONG <= NGUONG_HEP_BANG:
            audio = tang_tuan_hoan(audio, RATE_XUONG)

        pcm = float32_to_int16(audio)

        # Cắt thành khung 20ms: gửi cả cục thì đệm của điện thoại phình lên,
        # khách nghe trễ và ngắt lời không kịp tác dụng.
        for i in range(0, len(pcm) - FRAME_BYTES_XUONG + 1, FRAME_BYTES_XUONG):
            await self._out.put(pcm[i:i + FRAME_BYTES_XUONG])

    def drop_pending_audio(self) -> int:
        """Bỏ hết tiếng AI còn xếp hàng — dùng khi khách chen ngang.

        Khung đầu tiên được giữ lại và vuốt nhỏ dần thay vì vứt luôn: cắt giữa
        sóng làm biên độ rơi thẳng về 0, trên đường thoại nghe thành tiếng
        'tách'. Đo trên đường trình duyệt: năng lượng dải cao dội lên 168-635
        lần khi tắt phựt, về 0 khi có vuốt.
        """
        khung_dau = None
        n = 0
        while not self._out.empty():
            try:
                f = self._out.get_nowait()
                if khung_dau is None:
                    khung_dau = f
                n += 1
            except asyncio.QueueEmpty:
                break

        if khung_dau is not None:
            x = int16_to_float32(khung_dau)
            x = x * np.linspace(1.0, 0.0, len(x), dtype=np.float32)
            try:
                self._out.put_nowait(float32_to_int16(x))
            except asyncio.QueueFull:
                pass
        return n

    async def _cho_luot_cu_dung(self, cho_giay: float = 2.0):
        """Chờ lượt đang bị xin dừng tới điểm an toàn, rồi mới cho lượt mới chạy.

        Không chờ thì hai lượt chồng nhau, và tệ hơn: lượt cũ chưa kịp ghi câu
        khách vào lịch sử đã bị lượt mới ghi đè cờ, mất phần để ghép.
        """
        t = self._luot_task
        if t is None or t.done() or not self.session.yeu_cau_huy:
            return
        try:
            await asyncio.wait_for(asyncio.shield(t), timeout=cho_giay)
        except asyncio.TimeoutError:
            logger.warning(f"{self.tag} lượt cũ không tới điểm an toàn sau %.1fs - cắt cứng",
                           cho_giay)
            await self.huy_luot_dang_chay()
            # Cắt cứng thật thì vẫn giữ những gì đã kịp vào lịch sử.
            self.session.danh_dau_bi_cat()
        except asyncio.CancelledError:
            # CancelledError kế thừa BaseException nên `except Exception` KHÔNG
            # bắt được. Qua shield thì lỗi này có hai nguồn: lượt cũ bị ai đó cắt
            # (bỏ qua, đi tiếp), hay chính vòng thu này đang bị dừng (phải để nó
            # lan ra, nuốt là vòng thu không bao giờ dừng được).
            if not t.cancelled():
                raise
        except Exception:
            pass

    async def _cat_cung_neu_khong_dung(self, cho_giay: float = 3.0):
        """Lượt không tự dừng sau khi xin thì cắt cứng.

        Đường bình thường là cờ `yeu_cau_huy`: pipeline thấy cờ ở điểm an toàn rồi
        tự kết thúc, giữ nguyên câu khách để ghép. Nhưng nếu LLM treo hoặc STT
        chậm bất thường thì cờ không bao giờ tới được điểm kiểm - lúc đó phải cắt.
        """
        t = self._luot_task
        if t is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(t), timeout=cho_giay)
        except asyncio.TimeoutError:
            logger.warning(f"{self.tag} lượt không tự dừng sau %.1fs - cắt cứng", cho_giay)
            await self.huy_luot_dang_chay()
            if self.session.yeu_cau_huy:
                self.session.yeu_cau_huy = False
                self.session.danh_dau_bi_cat()
        except Exception:
            pass

    async def huy_luot_dang_chay(self) -> bool:
        """Dừng lượt đang sinh câu trả lời. Trả về True nếu thật sự có lượt bị cắt."""
        t = self._luot_task
        if t is None or t.done():
            return False
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
        self._luot_task = None
        return True

    async def _write_loop(self):
        """Gửi tiếng xuống máy theo NHỊP THỜI GIAN THỰC, không gửi nhanh hết cỡ.

        Đo được: nếu cứ ghi thẳng, 3 giây tiếng chui hết vào đệm TCP trong 0,3ms
        — không có phản áp nào. Hậu quả kép: khách nghe trễ đúng bằng lượng đang
        nằm chờ, và ngắt lời thành vô dụng vì dọn hàng đợi không lấy lại được
        thứ đã rời khỏi đây.

        Giữ trước `dem_mo_s` để máy không bị hụt tiếng, còn lại bám lịch
        20ms/khung. Lịch phải ĐẶT LẠI khi có khoảng nghỉ: TTS sinh nhanh hơn thời
        gian thực nhiều lần, không đặt lại thì lịch trôi mãi về tương lai và lượt
        sau nghe như mất tiếng.

        Đệm mồi phải ĐỦ DÀY. Với 60ms, đo được AudioTrack trên máy đói dữ liệu
        20913 lần/giây trong lúc phát (lúc rảnh: 0) - người nghe báo tiếng "dè".
        Lịch tự sửa nên tốc độ trung bình vẫn đúng, nhưng đồng hồ Windows có bước
        ~15,6ms nên khung tới nơi theo cụm giật cục, và đệm 60ms cạn giữa hai cụm.
        """
        LEAD = self.dem_mo_s
        RESET_GAP = 0.5      # nghỉ quá 0,5s coi như lượt mới
        next_at: float | None = None
        try:
            while self.running:
                frame = await self._out.get()
                now = time.perf_counter()

                if next_at is None or now > next_at + RESET_GAP:
                    # TRỪ, không phải CỘNG. Đặt lịch lùi về quá khứ thì những
                    # khung đầu có delay âm và bay đi ngay - máy tích được LEAD
                    # giây tiếng làm đệm, rồi mới bám nhịp thời gian thực.
                    # Bản cũ cộng LEAD, tức HOÃN khung đầu rồi phát đúng nhịp,
                    # nên máy không bao giờ có đệm: đo được AudioTrack đói dữ
                    # liệu 0 lần/giây lúc rảnh nhưng 20913 lần/giây lúc phát, và
                    # ngay cả tiếng bíp sin thuần cũng bị chặt vụn thành tiếng rè.
                    next_at = now - LEAD
                delay = next_at - now
                if delay > 0:
                    await asyncio.sleep(delay)
                next_at += FRAME_MS / 1000.0

                # Ghi âm ĐÚNG CHỖ NÀY, không phải ở `play()`: tới đây thì khung
                # đã qua hàng đợi và chắc chắn được phát ra. Tiếng bị bỏ vì khách
                # cắt lời không bao giờ đi qua điểm này, nên bản ghi khớp với thứ
                # khách thật sự nghe thấy.
                if self.ghi_am is not None:
                    self.ghi_am.them_bot(self._xuong_8k(frame))

                try:
                    self.writer.write(frame)
                    await self.writer.drain()
                except (ConnectionError, OSError) as e:
                    logger.warning(f"{self.tag} đứt ổ cắm khi gửi: {e} — nối lại")
                    if not await self.noi_lai():
                        await asyncio.sleep(0.5)
                        continue
                    next_at = None       # đặt lại lịch, đừng bù cho quãng đã mất
                    continue
                if self._probing:
                    self._probe_writes += 1
                    if self._probe_first_write is None:
                        self._probe_first_write = time.perf_counter()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.last_error = f"luồng gửi dừng: {e}"
            logger.warning(f"{self.tag} {self.last_error}")

    # --- chiều vào: tiếng khách lên STT ------------------------------------

    # --- đo độ trễ --------------------------------------------------------

    def _co_tone(self, frame: bytes) -> bool:
        """Khung này có phải tiếng bíp của phép đo không?

        Đòi hai điều kiện: đủ to, và phần lớn năng lượng nằm đúng ở tần số đã
        phát. Chỉ xét độ to thì tiếng ồn phòng cũng qua được.
        """
        x = int16_to_float32(frame)
        if compute_rms(x) * 32768.0 < 500.0:
            return False
        spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
        tong = float(spec.sum())
        if tong <= 0:
            return False
        # Khung này đến từ chiều LÊN (micro nghe lại tiếng bíp), nên tính bin
        # theo RATE_LEN chứ không phải tần số đã phát xuống.
        k = int(round(self._probe_freq * len(x) / RATE_LEN))
        # gộp bin kề để không trượt khi tần số lệch chút
        quanh = spec[max(0, k - 1):k + 2].sum()
        return float(quanh) / tong >= 0.5

    async def probe(self, freq: float = 1000.0, burst_ms: int = 300,
                    amp: int = 14000, wait_s: float = 4.0) -> dict:
        """Đo độ trễ tiếng đi từ hệ thống xuống điện thoại.

        Tách làm hai đoạn vì bản chất khác nhau:
          - `hang_doi_ms`: từ lúc pipeline giao tiếng đến lúc khung đầu ra
            socket. Đây là phần code này chịu trách nhiệm, đo chính xác được.
          - `vong_ms`: đo âm học - tiếng phát ra loa điện thoại rồi chính micro
            của nó nghe lại. Chỉ có khi loa đủ to; nếu không nghe thấy thì trả
            None chứ không đoán bừa.
        """
        import math

        self.drop_pending_audio()
        self._probe_first_write = None
        self._probe_hit = None
        self._probe_freq = freq
        self._probe_writes = 0
        self._probing = True

        frames = max(1, burst_ms // FRAME_MS)
        ph, step = 0.0, 2 * math.pi * freq / RATE_XUONG
        t0 = time.perf_counter()
        for _ in range(frames):
            buf = bytearray()
            for _ in range(FRAME_SAMPLES_XUONG):
                buf += int(amp * math.sin(ph)).to_bytes(2, "little", signed=True)
                ph += step
            await self._out.put(bytes(buf))

        deadline = t0 + wait_s
        while time.perf_counter() < deadline and self._probe_hit is None:
            await asyncio.sleep(0.02)
        vong = round((self._probe_hit - t0) * 1000, 1) if self._probe_hit else None
        hang_doi = round((self._probe_first_write - t0) * 1000, 1) if self._probe_first_write else None

        # Đo đệm phát của điện thoại bằng tốc độ rút hàng đợi. AudioTrack nuốt
        # một hơi đầy đệm rồi mới chặn lại ở nhịp thời gian thực, nên phần
        # "nuốt trước" chính là lượng tiếng đang nằm chờ trong máy.
        n = 150                                   # 3 giây
        self._probe_writes = 0
        im = bytes(FRAME_BYTES_XUONG)
        t1 = time.perf_counter()
        for _ in range(n):
            await self._out.put(im)
        while self._probe_writes < n and time.perf_counter() - t1 < 10:
            await asyncio.sleep(0.005)
        troi_ms = (time.perf_counter() - t1) * 1000
        dem_ms = max(0.0, n * FRAME_MS - troi_ms)

        self._probing = False
        return {
            "hang_doi_ms": hang_doi,
            "dem_may_ms": round(dem_ms, 1),
            "vong_ms": vong,
            "burst_ms": burst_ms,
        }

    async def _read_loop(self):
        """Gom tiếng khách, tự cắt lượt bằng VAD rồi đẩy vào pipeline.

        Trình duyệt tự cắt lượt ở phía client rồi mới gửi lên; đường thoại
        không có ai làm hộ nên phải tự dò khoảng lặng ở đây.
        """
        spec_cho = bytearray()      # đếm nhịp để biết khi nào chạy đoán trước
        tieng_8k = bytearray()      # TOÀN BỘ tiếng 8kHz của lượt đang mở
        on_streak = 0               # số khung liên tiếp vượt ngưỡng
        speaking = False
        silence_ms = 0
        speech_ms = 0
        spec_cuoi_bytes = 0         # mốc byte của lần đoán cuối câu, 0 = chưa đoán

        try:
            while self.running:
                try:
                    frame = await self.reader.readexactly(FRAME_BYTES_LEN)
                except (asyncio.IncompleteReadError, ConnectionError, OSError) as e:
                    logger.warning(f"{self.tag} đứt ổ cắm khi thu: {e} — nối lại")
                    if not await self.noi_lai():
                        await asyncio.sleep(0.5)
                    speaking, on_streak, silence_ms, speech_ms = False, 0, 0, 0
                    spec_cho.clear()
                    continue

                if self.theo_doi_khung is not None:
                    self.theo_doi_khung(frame)

                # Vẫn phải ĐỌC cho hết chứ không được ngừng đọc: ngừng thì đệm
                # socket đầy, app trên máy nghẽn, và khi mở lại ta nhận nguyên
                # một cục tiếng cũ.
                if self.tam_dung_nghe:
                    speaking, on_streak, silence_ms, speech_ms = False, 0, 0, 0
                    spec_cho.clear()
                    # Đo lại nền cho mỗi lần mở nghe: mỗi cuộc gọi một điều kiện
                    # sóng khác nhau, giữ nền của cuộc trước là đo sai.
                    self.nen_kenh = None
                    self._mau_nen.clear()
                    continue

                rms = compute_rms(int16_to_float32(frame)) * 32768.0

                # Khi đang đo thì không cắt lượt, chỉ rình tiếng bíp quay lại.
                # Phải dò ĐÚNG TẦN SỐ chứ không chỉ nhìn độ to: phòng có tiếng
                # ồn nền vượt ngưỡng VAD, nhìn độ to thôi thì đo ra vài chục ms
                # - con số vô lý vì riêng đệm phát của điện thoại đã lớn hơn thế.
                if self._probing:
                    if self._probe_hit is None and self._co_tone(frame):
                        self._probe_hit = time.perf_counter()
                    continue

                # Đo nền kênh trong ~1,5 giây đầu sau khi mở nghe, rồi đặt
                # ngưỡng theo nó.
                #
                # PHÂN VỊ THẤP, không phải cao. Bản cũ lấy phân vị 75 và điều đó
                # làm HỎNG đúng trường hợp thường gặp nhất: người bắt máy gần như
                # ai cũng "alo?" ngay lúc nhấc, nên cửa sổ đo 1,5s đầy giọng nói.
                # Đo trên bản ghi thật:
                #     khách im 1,5s đầu  -> nền   10 -> ngưỡng  700  (nghe được)
                #     khách nói ngay     -> nền 1101 -> ngưỡng 3303  (ĐIẾC)
                # mà đỉnh giọng nói trong chính bản ghi đó chỉ 2449 - thấp hơn
                # ngưỡng, nên VAD câm suốt cuộc gọi và không lượt nào mở được.
                # Người dùng báo đúng triệu chứng: "alo liên tục không thấy trả lời".
                #
                # Phân vị 20 lấy đúng khoảng lặng GIỮA các từ - luôn tồn tại kể cả
                # khi đang nói liên tục. Cùng bản ghi: nói ngay -> nền 18, ngưỡng
                # vẫn 700. Đúng trong cả hai tình huống.
                if self.nen_kenh is None:
                    self._mau_nen.append(rms)
                    if len(self._mau_nen) < 75:            # 75 khung 20ms
                        continue
                    nen = float(np.percentile(self._mau_nen, 20))
                    self.nen_kenh = nen
                    self._mau_nen.clear()
                    logger.info(f"{self.tag} nền kênh %.0f -> ngưỡng bật %.0f / tắt %.0f",
                                nen, self.nguong_on(), self.nguong_tat())

                # Dò hộp thư thoại + giới tính. Đặt ở đây, TRƯỚC nhánh cắt lượt:
                # lời chào hộp thư thoại là một đoạn nói liền không ngắt, VAD sẽ
                # gom nó thành đúng một lượt dài, nên nếu chỉ dò ở ranh giới lượt
                # thì mãi tới lúc hộp thư nói xong mới biết - quá muộn.
                self._nghe_de_do(frame, rms >= self.nguong_tat())

                # Chiều lên là dòng liên tục 20ms kể cả lúc im lặng, nên nó là
                # ĐỒNG HỒ của bản ghi - xem services/recorder.py.
                if self.ghi_am is not None:
                    self.ghi_am.them_khach(int16_to_float32(frame))

                if not speaking:
                    on_streak = on_streak + 1 if rms >= self.nguong_on() else 0
                    if on_streak >= VAD_ON_FRAMES:
                        on_streak = 0
                        # Khách bắt đầu nói. Nếu AI đang nói dở thì đây là CẮT LỜI:
                        # phải dừng cả tiếng đang xếp hàng LẪN lượt đang sinh, rồi
                        # giữ câu nói dở để ghép vào câu sắp tới.
                        dang_noi = not self._out.empty() or (
                            self._luot_task is not None and not self._luot_task.done()
                        )
                        if dang_noi:
                            # Bỏ tiếng đang xếp hàng NGAY - khách phải nghe AI im
                            # tức thì. Còn lượt đang sinh thì xin dừng bằng cờ chứ
                            # không cắt cứng: cắt giữa lúc STT chưa xong là mất
                            # luôn câu khách vừa nói, không còn gì để ghép.
                            bo = self.drop_pending_audio()
                            self.session.yeu_cau_huy = True
                            logger.info(f"{self.tag} khách cắt lời — bỏ %d khung tiếng AI,"
                                        " xin dừng lượt đang sinh", bo)
                            # Chốt chặn: LLM treo thì cờ không tới được điểm kiểm,
                            # lúc đó mới cắt cứng. Chạy nền để vòng thu không nghẽn.
                            asyncio.create_task(self._cat_cung_neu_khong_dung())
                        speaking, silence_ms, speech_ms = True, 0, 0
                        spec_cuoi_bytes = 0
                        # Dọn tiếng thừa và bản đoán của lượt trước trước khi gom
                        # lượt mới, không thì đoán trước ăn nhầm câu cũ.
                        self.session.take_audio()
                        self.session.clear_speculation()
                        spec_cho.clear()
                        tieng_8k.clear()
                        spec_cho += frame
                        tieng_8k += frame
                    continue

                spec_cho += frame
                tieng_8k += frame
                if len(spec_cho) >= FRAME_BYTES_LEN * 5:      # ~100ms
                    # KHÔNG đổi tần ở đây. Gửi thẳng tiếng gốc 8kHz và để
                    # faster-whisper tự đổi một lần bằng bộ giải mã của nó
                    # (`pho_server` đưa nguyên file WAV vào `model.transcribe`).
                    #
                    # Trước đây tự nâng 8k->16k theo TỪNG KHỐI rồi nối. Mỗi lần
                    # gọi `resample_poly` rời không mang trạng thái bộ lọc qua
                    # ranh giới, nên mỗi mối nối là một điểm gãy và phụ âm đầu
                    # chết trước. Trên bản ghi cuộc gọi thật, CÙNG một đoạn:
                    #     gửi thẳng 8kHz  -> "anh cần vay năm mươi triệu"
                    #     nâng khối 100ms -> "anh tần vay năm mươi triệu"
                    # Đo trên 9 lượt của 2 cuộc gọi (scripts/do_gui_8k_thang.py):
                    # gửi thẳng 8kHz cho kết quả Y HỆT cách tự nâng cả đoạn, kể
                    # cả đúng lượt đã hỏng khi gọi thật. Vòng gọi STT không chậm
                    # đi (chênh 15-60ms, đảo chiều - là nhiễu đo).
                    #
                    # Bỏ hẳn khâu này còn cắt được phần việc tăng theo BÌNH
                    # PHƯƠNG độ dài lượt: đặt lại cả lượt mỗi 100ms nghĩa là
                    # nâng lại đoạn mỗi lúc một dài (lượt 10s tốn 113ms CPU,
                    # lượt 20s tốn 432ms). Giờ chỉ còn sao chép byte.
                    self.session.set_audio(bytes(tieng_8k))
                    spec_cho.clear()
                    # Đoán trước NGAY khi khách còn đang nói: phiên âm tạm + nạp
                    # sẵn RAG. Lúc này TTS đang rảnh nên gần như miễn phí, và nếu
                    # đoán trúng thì lượt thật bỏ được cả STT lẫn RAG.
                    try:
                        await self.pipeline.speculate(self.session)
                    except Exception as e:
                        logger.debug(f"{self.tag} đoán trước bỏ qua: {e}")
                speech_ms += FRAME_MS
                truoc_im = silence_ms
                silence_ms = silence_ms + FRAME_MS if rms < self.nguong_tat() else 0

                # Khách vừa ngừng tiếng -> ĐOÁN NGAY trên trọn câu, đừng để quãng
                # im cuối trôi qua vô ích. Chỉ bắn ĐÚNG MỘT LẦN mỗi lượt (mốc cắt
                # ngang SPEC_CUOI_MS), không thì cứ mỗi khung 20ms lại huỷ và
                # dựng lại một bản đoán - vừa phí vừa không bản nào kịp xong.
                if (truoc_im < SPEC_CUOI_MS <= silence_ms
                        and speech_ms - silence_ms >= MIN_TURN_MS and tieng_8k):
                    # NHỚ mốc byte đã đoán. Từ đây tới lúc lượt kết thúc còn
                    # ~200ms khung im nữa được nối vào `tieng_8k`, nên nếu lượt
                    # thật lấy cả phần đuôi đó thì độ dài lệch và bộ nhớ STT
                    # KHÔNG BAO GIỜ khớp - tức cắt được STT trên giấy mà thực tế
                    # vẫn phiên âm lại. Phần đuôi chỉ là im lặng, bỏ đi vô hại.
                    spec_cuoi_bytes = len(tieng_8k)
                    self.session.set_audio(bytes(tieng_8k))
                    try:
                        await self.pipeline.speculate(self.session, ngay=True)
                    except Exception as e:
                        logger.debug(f"{self.tag} đoán cuối câu bỏ qua: {e}")

                if silence_ms >= SILENCE_END_MS or speech_ms >= MAX_TURN_MS:
                    speaking = False
                    if tieng_8k:
                        # Cắt đúng mốc đã đoán ở trên để hai bên nhìn CÙNG một
                        # đoạn tiếng, nhờ vậy dùng lại được bản phiên âm.
                        #
                        # ĐÒI THÊM `silence_ms >= SPEC_CUOI_MS`, không chỉ có mốc
                        # là cắt: khách nghỉ giữa câu (đặt mốc) rồi nói tiếp một
                        # mạch tới MAX_TURN_MS thì lượt kết thúc bằng đường quá
                        # giờ, lúc đó mốc đã cũ và cắt theo nó là VỨT TRẮNG phần
                        # khách nói sau mốc. `silence_ms` bị đặt lại về 0 mỗi khi
                        # có tiếng, nên nó còn ≥ ngưỡng nghĩa là mốc vẫn đúng.
                        het = (spec_cuoi_bytes
                               if spec_cuoi_bytes and silence_ms >= SPEC_CUOI_MS
                               else len(tieng_8k))
                        self.session.set_audio(bytes(tieng_8k[:het]))
                    spec_cho.clear()
                    tieng_8k.clear()
                    spec_cuoi_bytes = 0
                    audio = self.session.take_audio()
                    talk_ms = speech_ms - silence_ms
                    if talk_ms >= MIN_TURN_MS:
                        # Lượt cũ còn đang chạy và đang được xin dừng: CHỜ nó tới
                        # điểm an toàn rồi mới mở lượt mới. Dọn cờ ngay ở đây là
                        # hỏng đúng trường hợp thường gặp nhất - khách nói đè rồi
                        # nói tiếp một mạch, lượt cũ chưa kịp thấy cờ đã bị xoá.
                        await self._cho_luot_cu_dung()
                        self.session.yeu_cau_huy = False
                        # Giữ tham chiếu để huỷ được khi khách cắt lời lượt sau.
                        self._luot_task = asyncio.create_task(self._handle_turn(audio))
                    else:
                        # INFO chứ không DEBUG: đây là lúc máy NGHE THẤY khách
                        # nhưng cố ý vứt đi. Để mức debug thì nhìn từ ngoài không
                        # phân biệt được với "không nghe thấy gì", và đã mất
                        # nhiều cuộc gọi để tìm ra đúng chỗ này.
                        logger.info(f"{self.tag} bỏ đoạn %dms - ngắn hơn MIN_TURN_MS=%d",
                                    talk_ms, MIN_TURN_MS)

        except (asyncio.IncompleteReadError, asyncio.CancelledError):
            pass
        except Exception as e:
            self.last_error = f"luồng thu dừng: {e}"
            logger.warning(f"{self.tag} {self.last_error}")

    @staticmethod
    def _xuong_8k(frame: bytes) -> np.ndarray:
        """Khung chiều xuống -> float32 ở RATE_LEN, để ghép vào bản ghi.

        Bản ghi lấy tần số của chiều LÊN làm chuẩn (đó là đồng hồ), nên chiều
        xuống phải hạ về cùng tần số. Ở cấu hình 24k xuống / 8k lên thì đây là
        hạ 3 lần.
        """
        x = int16_to_float32(frame)
        if RATE_XUONG == RATE_LEN:
            return x
        return resample_lien_tuc(x, RATE_XUONG, RATE_LEN)

    # --- F7 hộp thư thoại / F8 giới tính ----------------------------------

    def soi_hop_thu_thoai(self, ban_ghi: str):
        """Đưa một bản ghi STT vào bộ dò, và bắc cờ lên phiên nếu kết luận."""
        if not self.bo_do_hop_thu.con_do:
            return
        self.bo_do_hop_thu.them_ban_ghi(ban_ghi)
        if self.bo_do_hop_thu.la_hop_thu_thoai:
            # Bộ quay số tự động đọc cờ này để cúp máy - xem campaign_runner.
            self.session.la_hop_thu_thoai = True

    def _nghe_de_do(self, frame: bytes, dang_noi: bool):
        """Nuôi hai bộ dò bằng khung tiếng thô. Gọi từ vòng thu, phải rẻ.

        Cả hai đều tự tắt sau vài giây đầu, nên khi cuộc gọi vào nhịp hội thoại
        thật thì hàm này chỉ còn là hai phép so sánh boolean.
        """
        if self.bo_do_hop_thu.con_do:
            try:
                self.bo_do_hop_thu.them_tieng(int16_to_float32(frame), dang_noi)
                if self.bo_do_hop_thu.la_hop_thu_thoai:
                    self.session.la_hop_thu_thoai = True
            except Exception as e:
                logger.debug(f"{self.tag} dò hộp thư thoại bỏ qua: {e}")

        if self.da_doan_gioi_tinh or not dang_noi:
            return
        self._dem_giong += frame
        # Cần ~2,5 giây tiếng hữu thanh mới đủ mẫu cho trung vị F0 có nghĩa.
        if len(self._dem_giong) < RATE_LEN * 2 * 2.5:
            return
        self.da_doan_gioi_tinh = True
        pcm = int16_to_float32(bytes(self._dem_giong))
        self._dem_giong.clear()
        # Chạy ở luồng khác: tự tương quan trên 2,5 giây tiếng mất vài chục ms,
        # đủ để làm trễ một lượt nếu chạy thẳng trên vòng sự kiện.
        asyncio.create_task(self._doan_gioi_tinh_nen(pcm))

    async def _doan_gioi_tinh_nen(self, pcm):
        try:
            ket_qua = await asyncio.to_thread(doan_gioi_tinh, pcm, RATE_LEN)
        except Exception as e:
            logger.debug(f"{self.tag} đoán giới tính bỏ qua: {e}")
            return
        self.session.gender = ket_qua["gioi_tinh"]
        # Lưu cả độ tin: prompt cần nó để biết có dám gọi "anh"/"chị" không.
        # Thiếu nó thì mọi kết quả đều được coi như chắc chắn, kể cả ca 0.45.
        self.session.gender_do_tin = ket_qua.get("do_tin")
        logger.info(
            f"{self.tag} giới tính khách: {ket_qua['gioi_tinh']} "
            f"({ket_qua['ly_do']}, tin {ket_qua['do_tin']})"
        )

    async def _handle_turn(self, pcm16k: bytes):
        """Một lượt của khách. Tiếng đã ở 16kHz sẵn từ vòng thu."""
        try:
            self.turns += 1
            await self.pipeline.process_turn(
                audio_bytes=pcm16k,
                session=self.session,
                ws=self.sink,
            )
        except Exception as e:
            self.last_error = f"xử lý lượt lỗi: {e}"
            logger.warning(f"{self.tag} {self.last_error}", exc_info=True)


# --- quản lý phiên: một điện thoại một phiên ------------------------------------

class PhoneCallManager:
    """Giữ các phiên tiếng đang mở, khoá theo serial máy."""

    def __init__(self):
        self._calls: dict[str, PhoneCallBridge] = {}

    def get(self, serial: str) -> PhoneCallBridge | None:
        return self._calls.get(serial)

    def status(self) -> list[dict]:
        return [
            {
                "serial": s, "port": c.port, "running": c.running,
                "turns": c.turns, "last_error": c.last_error,
                "khach_noi": c.sink.last_transcript, "ai_noi": c.sink.last_reply,
            }
            for s, c in self._calls.items()
        ]

    async def start(self, serial: str, pipeline, session, port: int = 8123,
                    src: int = 3, inject: bool = True,
                    ghi_am: bool = True,
                    cho_bat_may: bool = False) -> tuple[bool, str]:
        """Mở đường tiếng cho một cuộc gọi trên máy `serial`.

        `src=3` (VOICE_DOWNLINK) — CHỈ thu tiếng đầu bên kia nói.

        ĐỪNG đổi về 4 (VOICE_CALL). Nó thu cả hai chiều TRỘN LẠI, nên AI nghe
        thấy chính tiếng mình vừa tiêm vào đường lên: STT phiên âm ra rác và VAD
        coi đó là khách nói nên tự cắt lời mình liên tục. Mặc định cũ ở đây là 4
        trong khi `scripts/goi_va_noi.py` dùng 3 - hai đường chạy khác nhau, và
        đường qua backend mới là đường thật.

        Bản ghi âm KHÔNG cần src=4: nó lấy hai chiều từ hai nguồn riêng —
        `them_bot()` gọi ở đường phát, `them_khach()` gọi ở vòng thu.
        """
        from backend.services import adb_service

        if serial in self._calls:
            return False, "Máy này đã có phiên tiếng đang chạy"

        ok, msg = await adb_service.start_bridge(serial, port=port, src=src)
        if not ok:
            return False, msg

        # KHÔNG đặt đường tiêm ở đây. Lúc này cuộc gọi mới đang quay số, và khi
        # người kia bắt máy thì HAL dựng tuyến, chạy lại `mixer_paths.xml` và
        # XOÁ SẠCH những gì ta vừa đặt. Đặt ở đây là vừa vô ích vừa tốn một lượt
        # ghi mixer. Việc đặt nằm ở `chao_khi_bat_may`, sau khi đã nối máy.
        warn = ""

        bridge = PhoneCallBridge(pipeline, session, port=port, serial=serial)
        # Gọi RA thì CHƯA ĐƯỢC NGHE cho tới khi người kia bắt máy. Không chặn
        # thì vòng thu phiên âm tiếng HỒI CHUÔNG: đo được trong một cuộc gọi
        # thật là 5 lượt rác trong 5 giây, mỗi lượt kết bằng "Không nhận dạng
        # được giọng nói" và mỗi lượt còn phát từ đệm vào cuộc gọi. Khách bấm
        # nghe đúng lúc đó thì nghe thấy tiếng lạo xạo chứ không phải lời chào.
        # `chao_khi_bat_may` mở nghe lại sau khi đã chào.
        bridge.tam_dung_nghe = cho_bat_may
        try:
            await bridge.start(ghi_am=ghi_am)
        except Exception as e:
            await adb_service.stop_bridge(serial, port=port)
            return False, f"Không nối được cầu tiếng: {e}"

        # KHÔNG chạy bộ canh đường tiêm. Đã thử và nó LÀM RỚT CUỘC GỌI: dù chỉ
        # ghi khi thấy lệch, HAL cứ ghi đè liên tục nên nó thành ra ghi mixer
        # đều đặn giữa cuộc gọi - đúng thứ đã đo được là giết cuộc gọi.
        #
        #   ghi mixer nhiều lần giữa cuộc gọi   -> rớt sau 10-19s, ERROR
        #   ghi ĐÚNG MỘT LẦN, ngay sau khi nối  -> giữ 32s, REMOTE/NORMAL
        #
        # Nên: một cuộc gọi = ĐÚNG MỘT lượt ghi mixer.
        #
        # ĐẶT Ở ĐÂU thì tuỳ cuộc gọi đã nối máy chưa:
        #   - GỌI RA: lúc này mới đang đổ chuông. Đặt bây giờ là vô ích vì dựng
        #     tuyến cuộc gọi sẽ làm HAL chạy lại mixer_paths.xml và ghi đè.
        #     `chao_khi_bat_may` đặt sau khi nối máy.
        #   - GỌI ĐẾN, hoặc bật tiếng cho một cuộc ĐANG NÓI: cuộc gọi đã lên
        #     rồi, phải đặt NGAY TẠI ĐÂY. Không có nhánh này thì đường gọi đến
        #     và endpoint gỡ lỗi ở api/devices.py không bao giờ đặt đường tiêm -
        #     micro vẫn bật, khách nghe tiếng nền của phòng đặt máy ("tiếng
        #     gió") và không nghe thấy AI.
        #
        # Tham số `inject` trước đây chỉ nằm ở dòng khai báo, KHÔNG được dùng ở
        # đâu cả - `devices.py` truyền vào và tưởng mình tắt/bật được.
        if inject and not cho_bat_may:
            ma, _ = await adb_service.precise_call_state(serial)
            if ma == 1:
                ok_i, msg_i = await adb_service.set_uplink_injection(serial, True)
                logger.info(f"{bridge.tag} %s", msg_i)
                if not ok_i:
                    warn += " | KHÔNG đặt được đường tiêm -> khách sẽ không nghe thấy AI"

        self._calls[serial] = bridge
        return True, msg + warn

    async def chao_khi_bat_may(self, serial: str, cho_toi_da: float = 45.0):
        """Chờ người bên kia BẮT MÁY rồi đọc câu mở đầu của kịch bản.

        Thiếu hàm này thì cuộc gọi RA hoàn toàn im lặng: khách bấm nghe, không ai
        nói gì, và vì AI chỉ trả lời khi khách nói trước nên cuộc gọi chết ở đó.
        Đường gọi VÀO đã có (`inbound_service._chao_khach`), đường gọi RA thì
        chưa - `opening_line` nằm trong kịch bản mà không ai gọi tới.

        Ba mốc, thứ tự bắt buộc, lấy từ `scripts/goi_va_noi.py` đã chạy thật:

        1. `precise_call_state == 1` mới là ĐÃ NỐI MÁY. `call_state` nhảy sang
           offhook ngay từ lúc quay số, dùng nó thì AI nói vào lúc còn đổ chuông.
        2. Chờ ~0,8s cho tuyến tiếng ổn định, rồi ĐẶT LẠI ĐƯỜNG TIÊM. Dựng tuyến
           cuộc gọi làm HAL chạy lại `mixer_paths.xml` và ghi đè `ABOX UAIF0 SPK`,
           nên đường tiêm đặt lúc mới quay số đã bị xoá mất.
        3. Sinh câu chào rồi phát.
        """
        from backend.services import adb_service

        bridge = self._calls.get(serial)
        if bridge is None:
            return
        session = bridge.session

        cau = (session.scenario or {}).get("opening_line", "").strip()
        if not cau:
            cau = (f"Dạ em chào anh chị ạ. Em là {settings.agent_name} bên "
                   f"{settings.bank_name}, em gọi để giới thiệu chương trình "
                   f"{session.product} ưu đãi ạ.")
        # SINH SẴN NGAY BÂY GIỜ, lúc còn đang đổ chuông. Câu chào là câu cố định,
        # không có lý do gì chờ nối máy mới sinh - đổ chuông thường 5-12 giây,
        # thừa sức che toàn bộ thời gian sinh. Sinh sau khi nối làm khách phải
        # nghe im lặng thêm ~0,6s ngay sau khi bấm nghe, và đó là ấn tượng đầu.
        wav = None
        try:
            wav = await bridge.pipeline.tts.synthesize(cau, voice=session.voice_name)
        except Exception as e:
            logger.warning(f"{bridge.tag} không sinh được lời chào: {e}")

        # HÂM NÓNG LLM trong lúc còn đổ chuông. Đo được (07-08, /api/benchmark/full):
        # lượt gọi đầu sau lúc máy nghỉ tốn 2213ms, các lượt sau chỉ 166-173ms.
        # Khoản 2 giây đó rơi trọn vào LƯỢT ĐẦU của mỗi cuộc gọi - đúng lúc ấn
        # tượng đầu tiên. Đổ chuông thường 5-12 giây nên chỗ này hoàn toàn rảnh.
        #
        # Chạy NỀN và nuốt mọi lỗi: hâm không được thì cuộc gọi vẫn phải diễn ra
        # bình thường, chỉ chậm lượt đầu như trước.
        # DỰNG CÂU ĐỆM CHO ĐÚNG GIỌNG CỦA CUỘC GỌI NÀY. Lúc khởi động chỉ dựng
        # cho giọng mặc định, nên gọi bằng giọng khác là `pick_filler` không tìm
        # thấy gì và khách nghe im lặng trọn TTFA. Đo được 07-08 trên cuộc gọi
        # thật dùng `fosd_1`: 1741 / 1067 / 1817ms im lặng, log ghi thẳng
        # "KHÔNG có filler cho giọng 'fosd_1'".
        #
        # Chạy trong lúc ĐỔ CHUÔNG - đó là khoảng 5-12 giây TTS hoàn toàn rảnh.
        # Dựng CÂU DÀI TRƯỚC: nếu chuông ngắn không kịp dựng hết thì thứ giữ lại
        # phải là thứ che được nhiều nhất.
        async def _dung_filler():
            try:
                from backend.pipeline.streaming_pipeline import FILLER_PHRASES
                if bridge.pipeline.tts.co_filler(session.voice_name):
                    return
                theo_dai = sorted(FILLER_PHRASES, key=len, reverse=True)
                await bridge.pipeline.tts.presynthesize_fillers(
                    theo_dai, voice=session.voice_name)
                logger.info(f"{bridge.tag} đã dựng câu đệm cho giọng "
                            f"'{session.voice_name}'")
            except Exception as e:
                logger.warning(f"{bridge.tag} không dựng được câu đệm: {e}")

        asyncio.create_task(_dung_filler())

        async def _ham_llm():
            try:
                async for _ in bridge.pipeline.llm.stream_response(
                        [{"role": "user", "content": "xin chào"}], "Trả lời đúng một từ."):
                    break          # có token đầu là model đã nằm sẵn, dừng ngay
                logger.info(f"{bridge.tag} đã hâm nóng LLM trong lúc đổ chuông")
            except Exception as e:
                logger.debug(f"{bridge.tag} hâm LLM bỏ qua: {e}")

        asyncio.create_task(_ham_llm())

        het = time.perf_counter() + cho_toi_da
        while time.perf_counter() < het:
            await asyncio.sleep(1.0)
            if serial not in self._calls:
                return                      # cuộc gọi bị dừng trong lúc chờ
            ma, _ = await adb_service.precise_call_state(serial)
            if ma == 1:
                break
        else:
            logger.info(f"{bridge.tag} không ai bắt máy trong %.0fs, không chào",
                        cho_toi_da)
            return

        await asyncio.sleep(0.8)
        ok_inj, msg_inj = await adb_service.set_uplink_injection(serial, True)
        logger.info(f"{bridge.tag} %s", msg_inj)
        if not ok_inj:
            logger.warning(f"{bridge.tag} KHÔNG đặt được đường tiêm -> khách sẽ không "
                           "nghe thấy AI")
        # Đọc lại để chắc HAL không giật lại ngay. Đọc là thao tác vô hại, khác
        # hẳn ghi - xem chú thích ở `PhoneCallManager.start`.
        doc = await adb_service.doc_duong_tiem(serial)
        thieu = [k for k in ("ABOX UAIF0 SPK", "AIF1TX1 Input 2")
                 if doc.get(k) in (None, "None", "RESERVED")]
        if thieu:
            logger.warning(f"{bridge.tag} đường tiêm bị HAL giật lại ngay: %s -> khách "
                           "không nghe thấy AI", ", ".join(thieu))

        try:
            if wav:
                await bridge.play(wav)
                session.add_turn("assistant", cau)
                logger.info(f"{bridge.tag} đã chào: %r", cau[:70])
        except Exception as e:
            logger.warning(f"{bridge.tag} không chào được: {e}")

        # MỞ NGHE sau khi đã chào. Mở sớm hơn thì vòng thu phiên âm tiếng hồi
        # chuông và đốt mấy lượt rác trước khi khách kịp nói câu nào.
        bridge.tam_dung_nghe = False

    async def stop(self, serial: str) -> tuple[bool, str]:
        from backend.services import adb_service

        bridge = self._calls.pop(serial, None)
        if bridge is None:
            return False, "Máy này không có phiên tiếng nào"

        await bridge.stop()
        await adb_service.set_uplink_injection(serial, False)
        await adb_service.stop_bridge(serial, port=bridge.port)
        return True, f"Đã dừng ({bridge.turns} lượt)"


phone_calls = PhoneCallManager()
