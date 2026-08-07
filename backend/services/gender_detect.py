"""Nhận diện giới tính người nghe máy qua cao độ giọng (Điều 6: "Nhận diện giới tính").

Dùng F0 (tần số cơ bản) thay vì một mô hình học máy riêng: chạy trên CPU trong
vài mili giây, không tốn thêm VRAM vốn đã chật vì STT + LLM + TTS, và không phải
tải thêm model nào — đúng ràng buộc "chạy offline 100%" của hợp đồng.

Cách đo: tự tương quan trên các khung hữu thanh, lấy TRUNG VỊ của F0. Trung vị
chứ không phải trung bình — một khung nhiễu cho F0 sai lệch cả trăm Hz sẽ kéo
trung bình đi, còn trung vị thì không nhúc nhích.

Ngưỡng cho tiếng Việt qua đường thoại 8 kHz. Giọng nam Việt tập trung 100-150 Hz,
nữ 200-250 Hz; khoảng 165-190 Hz là vùng chồng lấn thật sự (nam giọng cao, nữ
giọng trầm) nên trả "unknown" thay vì đoán bừa — bot vẫn xưng "anh/chị" như cũ,
không mất gì. Đoán sai giới tính rồi gọi khách sai xưng hô thì tệ hơn nhiều.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

NAM_TOI_DA = 165.0    # F0 dưới mức này: nam
NU_TOI_THIEU = 190.0  # F0 trên mức này: nữ

# Dải F0 hợp lệ của giọng người. Ngoài dải này là nhiễu hoặc bắt nhầm hài bậc 2.
F0_MIN = 70.0
F0_MAX = 400.0

# Cần bao nhiêu khung hữu thanh mới dám kết luận. Dưới mức này (khách mới "A lô"
# một tiếng) thì mẫu quá mỏng, trung vị không có ý nghĩa thống kê.
KHUNG_TOI_THIEU = 12

_NGUONG_TUONG_QUAN = 0.30   # giống _uoc_luong_chu_ky: chỉ nhận khung thật hữu thanh
_NGUONG_IM = 0.01           # RMS dưới mức này coi như im lặng


def _f0_tung_khung(x: np.ndarray, sr: int) -> np.ndarray:
    """F0 (Hz) của từng khung 32ms, bước 16ms. Khung vô thanh bị loại bỏ."""
    N = max(64, int(0.032 * sr))
    H = max(32, int(0.016 * sr))
    lo, hi = int(sr / F0_MAX), int(sr / F0_MIN)
    if hi >= N or lo < 1:
        return np.array([])

    ra = []
    for k in range(0, max(len(x) - N, 0) + 1, H):
        w = x[k:k + N]
        if len(w) < N or np.sqrt((w ** 2).mean()) < _NGUONG_IM:
            continue
        w = w - w.mean()
        ac = np.correlate(w, w, mode="full")[N - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        seg = ac[lo:hi]
        if not len(seg):
            continue
        i = int(np.argmax(seg))
        if seg[i] <= _NGUONG_TUONG_QUAN:
            continue
        chu_ky = lo + i
        if chu_ky > 0:
            ra.append(sr / chu_ky)
    return np.array(ra)


def doan_gioi_tinh(pcm: np.ndarray, sr: int = 8000) -> dict:
    """Đoán giới tính từ tiếng khách.

    `pcm` là float32 trong [-1, 1] — dùng `audio_utils.int16_to_float32` nếu
    đang cầm PCM 16-bit.

    Trả về:
        {"gioi_tinh": "male"|"female"|"unknown",
         "f0": float|None, "so_khung": int, "do_tin": float, "ly_do": str}

    `do_tin` là 0-1, tính theo khoảng cách từ F0 tới vùng chồng lấn.
    """
    trong = {"gioi_tinh": "unknown", "f0": None, "so_khung": 0,
             "do_tin": 0.0, "ly_do": ""}

    if pcm is None or len(pcm) == 0:
        return {**trong, "ly_do": "Không có tiếng"}

    x = np.asarray(pcm, dtype=np.float32)
    f0s = _f0_tung_khung(x, sr)
    trong["so_khung"] = int(len(f0s))

    if len(f0s) < KHUNG_TOI_THIEU:
        return {**trong, "ly_do": f"Khách nói quá ngắn ({len(f0s)} khung hữu thanh)"}

    f0 = float(np.median(f0s))
    trong["f0"] = round(f0, 1)

    if f0 < NAM_TOI_DA:
        # Càng xa vùng chồng lấn càng chắc. 100 Hz là mốc "rõ ràng là nam".
        do_tin = min(1.0, (NAM_TOI_DA - f0) / (NAM_TOI_DA - 100.0))
        return {**trong, "gioi_tinh": "male", "do_tin": round(max(0.0, do_tin), 2),
                "ly_do": f"F0 trung vị {f0:.0f} Hz"}
    if f0 > NU_TOI_THIEU:
        do_tin = min(1.0, (f0 - NU_TOI_THIEU) / (250.0 - NU_TOI_THIEU))
        return {**trong, "gioi_tinh": "female", "do_tin": round(max(0.0, do_tin), 2),
                "ly_do": f"F0 trung vị {f0:.0f} Hz"}

    return {**trong, "ly_do": f"F0 trung vị {f0:.0f} Hz nằm trong vùng chồng lấn "
                              f"{NAM_TOI_DA:.0f}-{NU_TOI_THIEU:.0f} Hz"}


# Dưới mức này thì coi như KHÔNG BIẾT, dù đã ra "male"/"female".
#
# Đo trên 7 giọng mẫu biết trước giới tính: đúng 6/7, ca sai duy nhất là giọng
# NỮ TRẦM (F0 136 Hz, dưới ngưỡng nam 165 Hz). Đáng chú ý: chính ca đó có độ tin
# THẤP NHẤT bảng (0.45), tức bộ dò tự biết nó không chắc - chỉ là chưa ai nghe.
#
# Gọi nhầm giới tính khách nghe rất chối và mất uy tín ngay câu đầu, còn
# "anh chị" thì trung tính và không ai để ý. Nên thà bỏ lỡ vài ca đúng.
NGUONG_TIN = 0.6


def xung_ho(gioi_tinh: str, do_tin: float | None = None) -> str:
    """Cách gọi khách theo giới tính đã đoán.

    Không chắc thì giữ "anh chị" - trung tính, không sai được với ai.
    """
    if do_tin is not None and do_tin < NGUONG_TIN:
        return "anh chị"
    return {"male": "anh", "female": "chị"}.get(gioi_tinh, "anh chị")
