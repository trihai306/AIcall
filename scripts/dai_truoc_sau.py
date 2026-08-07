"""So phổ TRƯỚC và SAU khi qua đường thoại thật, theo từng dải tần.

Hai tín hiệu khác tần số lấy mẫu nên khác số mẫu; cộng phổ thô rồi so là sai
(công suất FFT tỉ lệ với N^2). Phải chuẩn mỗi phổ theo TỔNG CỦA CHÍNH NÓ để so
hình dạng, và so RMS riêng để biết mức âm lượng.
"""
import sys, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))
import numpy as np

DAI = [(0, 300, "dưới 300Hz (âm cơ bản, độ dày giọng)"),
       (300, 1000, "300Hz-1kHz (nguyên âm)"),
       (1000, 3400, "1-3.4kHz (phụ âm, độ rõ)"),
       (3400, 12000, "trên 3.4kHz (âm gió, độ sáng)")]

def doc(p):
    with wave.open(str(p)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x.astype("float32") / 32768, sr

def ty_le_dai(x, sr):
    ph = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    tong = ph.sum() or 1e-12
    return np.array([ph[(f >= lo) & (f < hi)].sum() / tong for lo, hi, _ in DAI])

d = P / "logs" / "kenh_thoai"
files = sorted(d.glob("c*_1_goc.wav"))
G = np.zeros(len(DAI)); A = np.zeros(len(DAI))
rms_g, rms_a, n = [], [], 0
for fg in files:
    fa = fg.with_name(fg.name.replace("_goc", "_amr"))
    if not fa.exists():
        continue
    xg, srg = doc(fg); xa, sra = doc(fa)
    G += ty_le_dai(xg, srg); A += ty_le_dai(xa, sra)
    rms_g.append(float(np.sqrt((xg**2).mean())))
    rms_a.append(float(np.sqrt((xa**2).mean())))
    n += 1

G /= n; A /= n
print(f"So trên {n} câu. Tỉ lệ năng lượng theo dải (mỗi bên chuẩn theo tổng của chính nó):\n")
print(f"{'dải tần':<40}{'gốc':>9}{'qua AMR':>10}")
print("-" * 59)
for i, (_, _, ten) in enumerate(DAI):
    print(f"{ten:<40}{G[i]*100:>8.1f}%{A[i]*100:>9.1f}%")
print("-" * 59)
print(f"\nMức âm lượng (RMS): gốc {np.mean(rms_g):.4f} -> qua AMR {np.mean(rms_a):.4f}"
      f"  ({np.mean(rms_a)/np.mean(rms_g):.2f} lần"
      f", {20*np.log10(np.mean(rms_a)/np.mean(rms_g)):+.1f} dB)")
