"""Thử bộ xử lý tối ưu cho đường thoại, đo trước/sau rồi xuất mẫu để nghe."""
import asyncio, io, subprocess, sys, tempfile, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))
import numpy as np
from scipy import signal
from backend.services.audio_utils import resample_audio

MUC_DICH_DBFS = -19.0      # chuẩn thoại; to hơn thì codec méo ở đỉnh
DINH_TOI_DA = 0.89         # chừa ~1dB dự trữ

def toi_uu_cho_thoai(x, sr):
    # 1. Bỏ dưới 200Hz. Loa điện thoại không phát được dải này, giữ lại chỉ tốn
    #    bit của codec và đẩy mức tổng lên khiến phần nghe được phải nhỏ đi.
    b, a = signal.butter(2, 200 / (sr / 2), btype="highpass")
    y = signal.filtfilt(b, a, x).astype("float32")

    # 2. Nâng dải 1.6-3.2kHz. Đo được phần này yếu hơn dải trầm 4-18 lần, mà nó
    #    mới là nơi chứa phụ âm - thứ quyết định nghe rõ hay không.
    f0, Q, gain_db = 2200.0, 0.9, 6.0
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * Q)
    bq_b = [1 + alpha * A, -2 * np.cos(w0), 1 - alpha * A]
    bq_a = [1 + alpha / A, -2 * np.cos(w0), 1 - alpha / A]
    y = signal.lfilter(np.array(bq_b) / bq_a[0], np.array(bq_a) / bq_a[0], y).astype("float32")

    # 3. Giới hạn đỉnh mềm TRƯỚC khi chuẩn mức. Làm ngược lại thì bộ giới hạn
    #    nén đỉnh xuống và kéo RMS lên, mức cuối cùng lệch khỏi đích.
    #    Dùng tanh chứ không cắt cứng: cắt cứng sinh hài bậc lẻ nghe rè.
    d = float(np.abs(y).max())
    if d > DINH_TOI_DA:
        y = np.tanh(y / d * 1.4) / np.tanh(1.4) * DINH_TOI_DA

    # 4. Chuẩn mức. Không chuẩn thì câu to câu nhỏ, câu nhỏ bị nhiễu lượng tử nổi.
    #    Nhưng không để việc chuẩn mức đẩy đỉnh vượt trần - thà nhỏ hơn đích một
    #    chút còn hơn vỡ tiếng.
    rms = float(np.sqrt((y ** 2).mean())) or 1e-9
    he_so = 10 ** (MUC_DICH_DBFS / 20) / rms
    d = float(np.abs(y).max()) or 1e-9
    y *= min(he_so, DINH_TOI_DA / d)
    return y.astype("float32")

def doc(b):
    with wave.open(io.BytesIO(b)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float32")/32768, w.getframerate()

def ghi(x, sr):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x,-1,1)*32767).astype("<i2").tobytes())
    return buf.getvalue()

def qua_amr(x8):
    with tempfile.TemporaryDirectory() as d:
        pi, pa, po = Path(d)/"i.wav", Path(d)/"m.amr", Path(d)/"o.wav"
        pi.write_bytes(ghi(x8, 8000))
        subprocess.run(["ffmpeg","-y","-i",str(pi),"-ar","8000","-ac","1",
                        "-c:a","libopencore_amrnb","-b:a","12.2k",str(pa)], capture_output=True)
        subprocess.run(["ffmpeg","-y","-i",str(pa),"-ar","8000","-ac","1",str(po)], capture_output=True)
        return po.read_bytes()

def nghieng(x, sr):
    ph = np.abs(np.fft.rfft(x*np.hanning(len(x))))**2
    f = np.fft.rfftfreq(len(x), 1/sr)
    return float(ph[(f>=1000)&(f<3400)].sum() / (ph[(f>=100)&(f<1000)].sum() or 1e-12))

CAU = ["Dạ anh chị chuẩn bị chứng minh nhân dân và sao kê lương ba tháng gần nhất ạ",
       "Dạ lãi suất vay tín chấp từ sáu phẩy năm phần trăm một năm ạ",
       "Dạ hạn mức cho vay lên đến năm trăm triệu đồng, thời hạn tối đa sáu mươi tháng"]

async def main():
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    out = P/"logs"/"toi_uu_thoai"; out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"): f.unlink()

    print(f"{'câu':<5}{'':<3}{'độ nghiêng':>13}{'RMS dBFS':>11}{'đỉnh':>9}{'dự trữ':>10}")
    print("-" * 53)
    for i, c in enumerate(CAU, 1):
        w = await tts.synthesize(c, use_cache=False)
        x, sr = doc(w)
        for ten, y in (("cũ ", resample_audio(x, sr, 8000)),
                       ("mới", resample_audio(toi_uu_cho_thoai(x, sr), sr, 8000))):
            r = float(np.sqrt((y**2).mean())); d = float(np.abs(y).max())
            print(f"{i:<5}{ten:<3}{nghieng(y,8000):>13.3f}{20*np.log10(r+1e-12):>11.1f}"
                  f"{d:>9.3f}{20*np.log10(1/(d+1e-12)):>9.1f}dB")
            nhan = "cu" if ten == "cũ " else "moi"
            (out/f"c{i}_{nhan}.wav").write_bytes(qua_amr(y))
    print("-" * 53)
    print(f"\nMẫu đã qua codec AMR-NB: {out}")

asyncio.run(main())
