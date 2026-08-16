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
dò gì. KÉO GIẢN phần đuôi cho ngắn lại, giữ nguyên cao độ.

>>> BẢN ĐẦU CẮT-VÀ-NỐI, ĐÃ HỎNG. Đừng làm lại. <<<

Bản đầu cắt một lát giữa nguyên âm rồi nối bằng chuyển tiếp mềm, với lý do "giữ
nguyên dạng sóng, an toàn hơn kéo giãn". SAI, và sai vì một lẽ rất tiếng Việt:
THANH ĐIỆU nằm ở ĐƯỜNG CONG CAO ĐỘ trải trên nguyên âm. Cắt một lát ở giữa là
cắt mất một khúc của đường cong đó - chữ đổi luôn thanh, tức đổi nghĩa.

Người dùng nghe ra ngay, và STT xác nhận từng chỗ:

    "ngân hàng quân đội"  ->  "ngân hàng quân ___"   (mất hẳn "đội")
    "một năm nhé"         ->  "một năm nha"          (sắc -> ngang)
    "gần nhất thôi ạ"     ->  "gần nhất thôi ___"    (mất hẳn "ạ")

Kéo giãn (phase vocoder) thì giữ nguyên HÌNH DẠNG đường cong, chỉ nén nó lại -
nên thanh điệu còn nguyên. Đúng ngược với lập luận ban đầu.

GIỮ LẠI ĐOẠN TẮT CUỐI. Đụng vào phần âm lượng giảm dần thì nghe cụt lủn - đúng
lỗi mà `trim_silence` từng gây ra. Nên chừa `GIU_CUOI_MS`.
"""
import logging

import numpy as np

logger = logging.getLogger(__name__)

# Chỉ nén khi đuôi thực sự dài. Âm tiết thường ~200ms; dưới ngưỡng này thì mảnh
# đó vốn đã bình thường, đụng vào chỉ tổ làm hỏng.
TOI_THIEU_MS = 300.0

# Nén còn ngần này. 0.72 = ngắn đi 28%.
#
# Bảo thủ có chủ ý: bản đầu cắt tới 220ms và ăn mất cả chữ. Kéo giãn quá tay thì
# nguyên âm nghe "máy", mà chữ ở ranh giới vế vốn ĐƯỢC PHÉP dài hơn một chút -
# đó là ngữ điệu thật, nén sạch thì hai vế dính vào nhau.
TI_LE_NEN = 0.72

# Chừa lại đoạn cuối để giữ phần tắt dần tự nhiên.
GIU_CUOI_MS = 90.0

# Chuyển tiếp mềm ở chỗ nối, tính bằng ms. Ngắn quá thì nghe "tạch".
CHUYEN_TIEP_MS = 18.0

# Ngưỡng để coi là "đáng nén". Dưới mức này thì đuôi vốn bình thường.
NGUONG_NGAN_MS = 380.0

# CỬA SỔ NÉN, tính từ cuối. CHỈ nén chừng này, không nén cả đoạn có tiếng.
#
# Bản trước nén NGUYÊN đoạn có tiếng cuối cùng, mà tiếng Việt nối âm nên đoạn đó
# gồm NHIỀU CHỮ - kết quả là nén nhầm cả nội dung thật và làm mất chữ:
#     "...sáu phẩy năm phần trăm một năm nhé"  ->  mất "một năm"
# Đây đúng là cái bẫy đã gặp khi đi dò âm ngân: "đoạn có tiếng dài" KHÔNG đồng
# nghĩa với "một âm tiết". Nên phải chặn cứng bằng cửa sổ tính từ cuối.
CUA_SO_MS = 380.0


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
    """Kéo giãn phần ngân ở đuôi cho ngắn lại. Nguyên bản nếu đuôi vốn đã ngắn."""
    if pcm.size == 0:
        return pcm
    dau = _doan_co_tieng_cuoi(pcm, sr)
    dai_ms = (len(pcm) - dau) / sr * 1000
    if dai_ms < NGUONG_NGAN_MS:
        return pcm

    giu = int(GIU_CUOI_MS * sr / 1000)
    ct = int(CHUYEN_TIEP_MS * sr / 1000)
    het = len(pcm) - giu
    # Chặn cứng: chỉ nén CUA_SO_MS cuối, dù đoạn có tiếng có dài tới đâu.
    dau = max(dau, het - int(CUA_SO_MS * sr / 1000))
    if het - dau < int(TOI_THIEU_MS * sr / 1000) or het <= dau:
        return pcm

    try:
        import librosa
    except ImportError:                      # không có thư viện thì thôi, đừng cắt bừa
        logger.debug("nen_duoi: thiếu librosa — bỏ qua")
        return pcm

    truoc = pcm[:dau].astype(np.float64)
    than = pcm[dau:het].astype(np.float64) / 32768.0
    duoi = pcm[het:].astype(np.float64)
    try:
        # rate>1 = ngắn lại. Giữ nguyên cao độ nên THANH ĐIỆU còn nguyên.
        nen = librosa.effects.time_stretch(than.astype(np.float32),
                                           rate=1.0 / TI_LE_NEN)
    except Exception as e:
        logger.warning("nen_duoi: kéo giãn hỏng (%s) — giữ nguyên", e)
        return pcm
    nen = np.asarray(nen, dtype=np.float64) * 32768.0
    if len(nen) < ct * 2:
        return pcm

    # Chuyển tiếp mềm ở CẢ HAI mối nối, để không nghe "tạch".
    w = np.linspace(0.0, 1.0, ct)
    if len(truoc) >= ct:
        nen[:ct] = truoc[-ct:] * (1 - w) + nen[:ct] * w
        truoc = truoc[:-ct]
    nen[-ct:] = nen[-ct:] * (1 - w) + duoi[:ct] * w
    ra = np.concatenate([truoc, nen, duoi[ct:]])
    return np.clip(ra, -32768, 32767).astype(np.int16)
