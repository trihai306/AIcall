"""Nén phần "ngân dài" ở đuôi mỗi mảnh (trừ mảnh cuối).

VÌ SAO. F5 sinh mỗi mảnh như một phát ngôn trọn vẹn nên nó kéo dài âm tiết cuối
mảnh. Ở mảnh CUỐI thì nghe tự nhiên - đó là kết câu thật. Ở các mảnh GIỮA thì
chỗ kéo dài đó rơi vào giữa câu, và người dùng nghe ra: *"lâu lâu có chữ nó đọc
kiểu ạ nhưng chữ ngân dài"*.

Đối chứng sạch, cùng chữ "nhé", cùng nội dung, chỉ khác chỗ cắt mảnh:

    "nhé" ở CUỐI MẢNH (2 mảnh)   600ms = 3.75x chữ thường
    "nhé" ở GIỮA MẢNH (1 mảnh)   240ms = 1.09x

Trên 97 tệp xuất thật, so cùng một chữ ở hai vị trí (đo bằng mốc từng chữ):

    nhé   giữa file 600ms  |  cuối file 320ms
    ạ     giữa file 360ms  |  cuối file 180ms

"Giữa file" chính là chỗ nối hai mảnh.

ĐÃ LOẠI, đừng đi lại: `thoi_luong_ep` KHÔNG phải nguyên nhân (ép theo nó cho chữ
cuối 0.80x, để F5 tự tính cho 1.14x - phần ép còn làm ngắn đi); clip mẫu cũng
không (chữ cuối của nó 0.69x); bù thêm chữ vào đuôi rồi cắt thì làm TỆ HƠN (xem
`bu_duoi.py`).

CÁCH LÀM. Ta TỰ ghép mảnh nên biết chính xác chỗ nối - không cần STT, không cần
dò gì. Cắt bớt một lát ở giữa phần ngân rồi nối lại bằng chuyển tiếp mềm.

KHÔNG dùng kéo giãn thời gian (phase vocoder): nó đụng vào cao độ và chất giọng,
mà đây là giọng đã mất công chọn và làm sạch. Cắt-và-nối giữ nguyên dạng sóng.

GIỮ LẠI ĐOẠN TẮT CUỐI. Cắt sát mép thì mất phần âm lượng giảm dần tự nhiên, nghe
thành cụt lủn - đúng lỗi mà `trim_silence` từng gây ra. Nên chừa `GIU_CUOI_MS`.
"""
import logging

import numpy as np

logger = logging.getLogger(__name__)

# Chỉ nén khi đuôi thực sự dài. Âm tiết thường ~200ms; dưới ngưỡng này thì mảnh
# đó vốn đã bình thường, đụng vào chỉ tổ làm hỏng.
TOI_THIEU_MS = 300.0

# Cắt bớt tối đa ngần này. Không cắt hết phần dôi: một chút kéo dài ở ranh giới
# vế là NGỮ ĐIỆU THẬT của tiếng Việt, cắt sạch thì hai vế dính vào nhau.
BOT_TOI_DA_MS = 220.0

# Chừa lại đoạn cuối để giữ phần tắt dần tự nhiên.
GIU_CUOI_MS = 90.0

# Chuyển tiếp mềm ở chỗ nối, tính bằng ms. Ngắn quá thì nghe "tạch".
CHUYEN_TIEP_MS = 18.0


def _doan_co_tieng_cuoi(pcm: np.ndarray, sr: int, nguong_db: float = -35.0) -> int:
    """Chỉ số mẫu nơi đoạn có tiếng CUỐI CÙNG bắt đầu."""
    h = int(sr * 0.010)
    n = (len(pcm) - h) // h
    if n < 3:
        return 0
    x = pcm.astype(np.float64)
    dinh = np.abs(x).max() or 1.0
    rms = np.sqrt(np.array([(x[i * h:i * h + h] ** 2).mean() for i in range(n)]) + 1e-12)
    db = 20 * np.log10(rms / dinh + 1e-12)
    noi = db > nguong_db
    i = n - 1
    while i > 0 and not noi[i]:          # bỏ phần lặng ở đuôi
        i -= 1
    while i > 0 and noi[i - 1]:          # lùi tới đầu đoạn có tiếng cuối
        i -= 1
    return i * h


def nen_duoi(pcm: np.ndarray, sr: int) -> np.ndarray:
    """Nén phần ngân ở đuôi. Trả nguyên bản nếu đuôi vốn đã ngắn."""
    if pcm.size == 0:
        return pcm
    dau = _doan_co_tieng_cuoi(pcm, sr)
    dai_ms = (len(pcm) - dau) / sr * 1000
    if dai_ms < TOI_THIEU_MS:
        return pcm

    bot = int(min(BOT_TOI_DA_MS, dai_ms - TOI_THIEU_MS + BOT_TOI_DA_MS * 0.4) * sr / 1000)
    giu = int(GIU_CUOI_MS * sr / 1000)
    ct = int(CHUYEN_TIEP_MS * sr / 1000)
    # Cắt lát NGAY TRƯỚC đoạn giữ lại ở cuối.
    het = len(pcm) - giu
    # +ct: chuyển tiếp mềm tiêu mất `ct` mẫu ở chỗ nối, cộng vào đây thì TỔNG
    # phần bị cắt đúng bằng `bot` - hợp đồng rõ ràng, khỏi phải trừ nhẩm.
    bat_dau = het - bot + ct
    if bat_dau - ct <= dau or bot <= ct:
        return pcm

    a = pcm[:bat_dau].astype(np.float64)
    b = pcm[het:].astype(np.float64)
    # Chuyển tiếp mềm: trộn ct mẫu cuối của a với ct mẫu đầu của b.
    w = np.linspace(0.0, 1.0, ct)
    a[-ct:] = a[-ct:] * (1 - w) + b[:ct] * w
    ra = np.concatenate([a, b[ct:]])
    return np.clip(ra, -32768, 32767).astype(np.int16)
