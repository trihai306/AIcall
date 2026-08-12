"""Dựng giọng mẫu F5 từ file 20 phút, rồi đọc thử để so với giọng đang dùng.

F5-TTS nhân bản giọng KHÔNG cần train: chỉ cần một đoạn ~8-12s kèm đúng lời của
đoạn đó. Việc khó duy nhất là CHỌN ĐOẠN: phải bắt đầu và kết thúc ở chỗ ngắt
hơi, không cụt chữ, không lẫn tiếng nền.

Cách chọn ở đây: quét toàn file theo cửa sổ 10s, chấm mỗi cửa sổ bằng
  - hai đầu phải ĐỦ IM (không cắt giữa từ)
  - phần giữa phải ĐỦ TIẾNG (không lấy nhầm đoạn im lặng dài)
  - mức ổn định (độ lệch chuẩn RMS thấp)
rồi lấy đoạn điểm cao nhất.
"""
import asyncio
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

F = Path(r"C:\Users\Admin\Desktop\giọng Hêu.wav")
RA = Path("C:/duan/chat-ai/models/tts/ref_voices")
LOG = Path("C:/duan/chat-ai/logs/giong_moi")
DAI = 10.0          # giây mỗi đoạn ứng viên


async def main():
    from backend.config import settings
    from backend.services.audio_utils import resample_audio
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService

    # --- đọc toàn file về mono 24k (204MB -> đọc theo khối) --------------
    with wave.open(str(F), "rb") as w:
        sr, nch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        khoi = []
        buoc = sr * 30
        for p in range(0, n, buoc):
            w.setpos(p)
            b = w.readframes(min(buoc, n - p))
            a = np.frombuffer(b, dtype=np.int16).astype(np.float32)
            if nch > 1:
                a = a.reshape(-1, nch).mean(axis=1)
            khoi.append(a / 32768.0)
    x = np.concatenate(khoi)
    x24 = resample_audio(x, sr, 24000)
    sr24 = 24000
    print(f"  đã đọc {len(x24)/sr24/60:.1f} phút, đưa về {sr24}Hz mono")

    # --- chấm điểm từng cửa sổ ------------------------------------------
    N = int(0.02 * sr24)
    rms = np.array([np.sqrt((x24[i:i + N] ** 2).mean())
                    for i in range(0, len(x24) - N, N)])
    im_nguong = float(np.percentile(rms, 25))
    kh_dai = int(DAI / 0.02)
    bien = int(0.30 / 0.02)          # 300ms mỗi đầu phải im

    diem_tot, i_tot = -1e9, 0
    for i in range(0, len(rms) - kh_dai, 25):        # bước 0.5s
        w_ = rms[i:i + kh_dai]
        dau, cuoi, giua = w_[:bien], w_[-bien:], w_[bien:-bien]
        if giua.mean() < im_nguong * 3:
            continue
        # muốn hai đầu im, giữa to, mức đều
        d = (giua.mean() / (dau.mean() + cuoi.mean() + 1e-9)) \
            - 2.0 * (giua.std() / (giua.mean() + 1e-9))
        if d > diem_tot:
            diem_tot, i_tot = d, i

    t0 = i_tot * 0.02
    doan = x24[int(t0 * sr24):int((t0 + DAI) * sr24)]
    print(f"  đoạn tốt nhất: giây {t0:.0f} - {t0+DAI:.0f}  (điểm {diem_tot:.1f})")

    # --- lời của đoạn đó -------------------------------------------------
    stt = STTService()
    a16 = resample_audio(doan, sr24, 16000)
    pcm = (np.clip(a16, -1, 1) * 32767).astype("<i2").tobytes()
    loi = (await stt.transcribe(pcm, sample_rate=16000)).strip()
    print(f"  lời đọc được : {loi!r}")
    if len(loi) < 15:
        print("  [!] lời quá ngắn, đoạn này không dùng được")
        return

    RA.mkdir(parents=True, exist_ok=True)
    p_wav = RA / "giong_heu.wav"
    with wave.open(str(p_wav), "wb") as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(sr24)
        o.writeframes((np.clip(doan, -1, 1) * 32767).astype("<i2").tobytes())
    (RA / "giong_heu.txt").write_text(loi, encoding="utf-8")
    print(f"  đã lưu       : {p_wav}")

    # --- đọc thử bằng CẢ HAI giọng để so --------------------------------
    CAU = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp "
           "lãi suất ưu đãi từ sáu phẩy năm phần trăm một năm.")
    LOG.mkdir(parents=True, exist_ok=True)
    for ten, ref, txt in (("cu_giong_ngan", settings.f5tts_ref_audio, None),
                          ("moi_giong_heu", "./models/tts/ref_voices/giong_heu.wav", loi)):
        settings.f5tts_ref_audio = ref
        if txt:
            settings.f5tts_ref_text = txt
        tts = F5TTSService()
        tts.load()
        wav = await tts.synthesize(CAU, use_cache=False)
        (LOG / f"doc_thu_{ten}.wav").write_bytes(wav)
        print(f"  đã dựng      : doc_thu_{ten}.wav")


asyncio.run(main())
