import io
import struct
import numpy as np


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Convert raw PCM bytes to WAV format."""
    buf = io.BytesIO()
    data_size = len(pcm_bytes)
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<H", 1))  # PCM
    buf.write(struct.pack("<H", channels))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", sample_rate * channels * sample_width))
    buf.write(struct.pack("<H", channels * sample_width))
    buf.write(struct.pack("<H", sample_width * 8))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(pcm_bytes)
    return buf.getvalue()


def ha_muc_neu_qua(audio: np.ndarray) -> np.ndarray:
    """Vượt trần biên độ thì hạ MỨC cả mảnh, giữ nguyên dạng sóng.

    Khác `np.clip`: clip cắt phẳng ngọn sóng nên sinh méo; hạ mức chỉ làm cả
    mảnh nhỏ đi, tai gần như không nhận ra.

    Vì sao cần (đo 08-08): F5 với đoạn mẫu ngắn trả về đỉnh 1.09-1.40, tức vượt
    trần thường xuyên. Bản ghi một cuộc hội thoại có 114 chuỗi mẫu bão hoà -
    nghe gắt ở những chỗ to nhất.

    KHÔNG khuếch đại khi tiếng nhỏ: đó là việc của bước kiểm soát mức, không
    phải của hàm này.
    """
    if audio is None or len(audio) == 0:
        return audio
    dinh = float(np.abs(audio).max())
    if dinh <= 1.0:
        return audio
    return audio / dinh


def float32_to_int16(audio: np.ndarray) -> bytes:
    """Convert float32 numpy array [-1, 1] to int16 PCM bytes."""
    audio = ha_muc_neu_qua(audio)
    audio = np.clip(audio, -1.0, 1.0)   # lưới cuối cho NaN/inf
    return (audio * 32767).astype(np.int16).tobytes()


def int16_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """Convert int16 PCM bytes to float32 numpy array."""
    return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32767.0


def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample audio to target sample rate."""
    if orig_sr == target_sr:
        return audio
    from scipy.signal import resample as scipy_resample
    num_samples = int(len(audio) * target_sr / orig_sr)
    return scipy_resample(audio, num_samples).astype(np.float32)


def resample_lien_tuc(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Đổi tần số cho tiếng cắt thành KHỐI NỐI NHAU (luồng), không phải file rời.

    Khác `resample_audio` ở chỗ dùng bộ lọc đa pha (FIR) thay cho biến đổi FFT.
    FFT giả định tín hiệu TUẦN HOÀN - mẫu cuối khối nối liền mẫu đầu khối - mà
    tiếng nói thì không, nên mỗi khối sinh một điểm gãy ở biên. Đo trên bản ghi
    cuộc gọi thật, nâng 8k->16k theo khối 100ms:
        FFT      méo 3.48%, bước nhảy tại biên gấp 5.5 lần trong lòng khối
        đa pha   méo 1.85%, gấp 2.9 lần
    (mốc 0% là đổi cả câu một lần, nhưng luồng thì không chờ hết câu được.)

    LƯU Ý ĐỪNG KỲ VỌNG QUÁ: cùng bản ghi đó, STT đọc ra Y HỆT NHAU ở cả hai cách.
    Đây là dọn dẹp cho sạch, KHÔNG phải cách chữa lỗi nghe sai lời khách.
    """
    if orig_sr == target_sr:
        return audio
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(orig_sr, target_sr)
    return resample_poly(audio, target_sr // g, orig_sr // g).astype(np.float32)


def compute_rms(audio: np.ndarray) -> float:
    """Compute RMS energy of audio signal."""
    return float(np.sqrt(np.mean(audio ** 2)))


def chen_lang_dau_wav(wav_bytes: bytes, ms: float) -> bytes:
    """Chèn `ms` mili-giây im lặng vào ĐẦU một WAV 16-bit mono.

    Dùng để trả lại nhịp nghỉ ở ranh giới mảnh TTS: mỗi mảnh bị trim_silence cắt
    sạch lặng hai đầu nên chỗ đáng lẽ có nhịp nghỉ trở thành nối thẳng, nghe hụt
    hơi (đo được bản cắt mảnh ngắn hơn bản sinh một lần 1,63s trên 43 từ).

    Chèn vào ĐẦU mảnh sau chứ không nối vào CUỐI mảnh trước, vì hai lẽ: mảnh đầu
    tiên không bao giờ bị chèn nên thời gian khách chờ tiếng đầu không đổi, và
    mảnh cuối cùng không bị thêm đuôi lặng thừa.
    """
    if ms <= 0 or len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF":
        return wav_bytes
    # Dò khối "data" thay vì cứ cắt ở byte 44: header 44 byte là đúng với WAV do
    # pcm_to_wav sinh ra, nhưng cắt mù thì hỏng câm lặng nếu nguồn đổi.
    i = wav_bytes.find(b"data", 12)
    if i < 0:
        return wav_bytes
    sr = struct.unpack("<I", wav_bytes[24:28])[0]
    kenh = struct.unpack("<H", wav_bytes[22:24])[0]
    rong = struct.unpack("<H", wav_bytes[34:36])[0] // 8
    im = b"\x00" * (int(sr * ms / 1000) * kenh * rong)
    return pcm_to_wav(im + wav_bytes[i + 8:], sample_rate=sr,
                      channels=kenh, sample_width=rong)
