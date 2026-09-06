"""Phân biệt GIÓ với TIẾNG NÓI trên một khung 20ms của kênh thoại.

VÌ SAO CÓ FILE NÀY. Cuộc gọi thật `f2f61c42` (06-09-2026): câu chào của AI dài
2,83 giây nhưng khách chỉ nghe được 1,4 giây. Đo từng khung 20ms của kênh khách
trong giây đầu:

    giây   mức   dưới-300Hz   tiếng AI
    1,40  1201      98,6%     đang phát
    1,44  1507      99,1%     -> đủ 3 khung, CẮT LỜI
    1,60   256      98,7%     đã tắt hẳn

VAD chỉ xét RMS (`VAD_RMS_ON = 700`), nên một cơn gió thổi vào micro cũng vượt
ngưỡng và bị coi là "khách bắt đầu nói" -> `drop_pending_audio()` xoá tiếng AI
đang phát. Khách nghe câu chào cụt ngay ấn tượng đầu tiên.

CHỖ TÁCH BẠCH: tiếng nói và gió cách nhau rất xa trên trục này, đo trên chính
cuộc gọi đó:

    gió       92 - 99 %  năng lượng dưới 300Hz
    tiếng nói  0,3 - 21 %

Nên ngưỡng 70% nằm giữa một khoảng trống rộng, không phải con số chỉnh tay.

ĐÂY KHÔNG PHẢI "lọc tạp âm". Đã đo và bác bỏ hướng đó: cắt dải thấp không sửa
được câu nào mà còn làm hỏng thêm (xem bộ nhớ `chat-ai-loc-tap-am-vo-ich`). Ở
đây tín hiệu KHÔNG bị đụng tới - chỉ dùng phổ để quyết định "khung này có đáng
coi là khách đang nói không".

KHÔNG import torch/soundfile ở đây: module bị `phone_call_service` kéo vào và
phải chạy được trên máy không GPU để test.
"""
import numpy as np

# Trên ngưỡng này thì khung coi như KHÔNG phải tiếng nói.
#
# 70% nằm giữa khoảng trống 21%..92% đo được trên cuộc gọi thật. Đừng hạ xuống
# sát 21%: giọng nam trầm qua kênh 8kHz vẫn dồn khá nhiều năng lượng xuống thấp,
# và bỏ sót lời khách đắt hơn nhiều so với bỏ sót một cơn gió.
NGUONG_THAP = 0.70

# Ranh giới "dải thấp". 300Hz là chỗ tiếng nói qua kênh thoại bắt đầu có năng
# lượng thật (đo được 74-82% năng lượng nằm ở 300-1000Hz).
CAT_HZ = 300.0


def ty_le_dai_thap(khung: np.ndarray, sr: int) -> float:
    """Tỉ lệ năng lượng dưới `CAT_HZ` của một khung. Trả 0.0 khi khung rỗng/lặng."""
    if khung is None or len(khung) < 8:
        return 0.0
    x = np.asarray(khung, dtype=np.float64)
    x = x - x.mean()                      # bỏ lệch một chiều, nếu không thì
    if not np.any(x):                     # vạch 0Hz nuốt hết tỉ lệ
        return 0.0
    pho = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    tan = np.fft.rfftfreq(len(x), 1.0 / sr)
    tong = pho.sum()
    if tong <= 0:
        return 0.0
    return float(pho[tan < CAT_HZ].sum() / tong)


def la_gio(khung: np.ndarray, sr: int, nguong: float = NGUONG_THAP) -> bool:
    """Khung này là gió/tiếng thổi chứ không phải tiếng nói?

    Dùng để KHÔNG mở lượt và KHÔNG cắt lời AI vì một cơn gió. Cố ý chỉ trả lời
    câu hỏi đó - không sửa gì vào tín hiệu.
    """
    return ty_le_dai_thap(khung, sr) >= nguong
