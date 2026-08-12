"""Soi file giọng mới: có dùng được cho F5 không, và dùng theo cách nào."""
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

F = Path(r"C:\Users\Admin\Desktop\giọng Hêu.wav")

with wave.open(str(F), "rb") as w:
    sr, nch, sw, n = (w.getframerate(), w.getnchannels(),
                      w.getsampwidth(), w.getnframes())
    print(f"\n  === {F.name} ===")
    print(f"    tần số lấy mẫu {sr} Hz | {nch} kênh | {sw*8} bit")
    print(f"    thời lượng     {n/sr/60:.1f} phút ({n/sr:.0f} giây)")
    # đọc mẫu rải đều thay vì cả file (204MB)
    doan = []
    for k in range(12):
        w.setpos(int(n * k / 12))
        b = w.readframes(min(sr * 10, n // 12))       # 10s mỗi chỗ
        a = np.frombuffer(b, dtype=np.int16).astype(np.float32)
        if nch > 1:
            a = a.reshape(-1, nch).mean(axis=1)
        doan.append(a / 32768.0)

x = np.concatenate(doan)
print(f"    đã lấy mẫu     {len(x)/sr:.0f}s rải đều 12 chỗ để chấm")

# --- có phải TIẾNG NÓI không, hay nhạc ---------------------------------
N = 2048
rms_all, f0s, phang = [], [], []
lo, hi = int(sr / 400), int(sr / 70)
for k in range(0, len(x) - N, N):
    w_ = x[k:k + N]
    r = float(np.sqrt((w_ ** 2).mean()))
    rms_all.append(r)
    if r < 0.01:
        continue
    ph = np.abs(np.fft.rfft(w_ * np.hanning(N))) ** 2 + 1e-12
    phang.append(float(np.exp(np.log(ph).mean()) / ph.mean()))
    d = w_ - w_.mean()
    ac = np.correlate(d, d, mode="full")[N - 1:]
    if ac[0] > 0 and hi < len(ac):
        ac = ac / ac[0]
        i = int(np.argmax(ac[lo:hi]))
        if ac[lo + i] > 0.35:
            f0s.append(sr / (lo + i))

rms_all = np.array(rms_all)
im = float((rms_all < 0.01).mean()) * 100
print(f"\n    tỉ lệ khoảng im   {im:.0f}%")
print(f"    độ phẳng phổ TB   {np.mean(phang):.4f}   (thấp = giọng có thanh)")
if f0s:
    f0s = np.array(f0s)
    print(f"    F0 trung vị       {np.median(f0s):.0f} Hz")
    print(f"    F0 khoảng 10-90%  {np.percentile(f0s,10):.0f} - {np.percentile(f0s,90):.0f} Hz")
    print(f"    khung có cao độ   {len(f0s)} / {len(phang)}"
          f"  ({len(f0s)/max(len(phang),1)*100:.0f}%)")

# năng lượng dưới 300Hz - phần kênh thoại cắt mất
duoi = tren = 0.0
for k in range(0, len(x) - N, N * 4):
    w_ = x[k:k + N]
    if np.sqrt((w_ ** 2).mean()) < 0.01:
        continue
    ph = np.abs(np.fft.rfft(w_ * np.hanning(N))) ** 2
    f = np.fft.rfftfreq(N, 1 / sr)
    duoi += ph[f < 300].sum()
    tren += ph[(f >= 300) & (f < 3400)].sum()
print(f"    năng lượng <300Hz {duoi/(duoi+tren+1e-12)*100:.1f}%  (kênh thoại sẽ cắt)")

# so với giọng đang dùng
ref = Path("C:/duan/chat-ai/models/tts/ref_voices/giong_ngan.wav")
if ref.exists():
    with wave.open(str(ref)) as w:
        sr2 = w.getframerate()
        y = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    print(f"\n    (giọng đang dùng {ref.name}: {sr2}Hz, {len(y)/sr2:.1f}s)")
