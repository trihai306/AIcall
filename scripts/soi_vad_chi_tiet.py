"""Vì sao VAD không mở được lượt nào? Soi chuỗi khung vượt ngưỡng."""
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

f = next(Path("C:/duan/chat-ai/logs/tieng_khach").glob("khach*.wav"))
with wave.open(str(f)) as w:
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)

N = sr * 20 // 1000
rms = np.array([np.sqrt((x[i:i + N] ** 2).mean()) for i in range(0, len(x) - N, N)])
print(f"  {f.name}: {len(x)/sr:.1f}s, {len(rms)} khung 20ms")
print(f"  RMS: trung vị {np.median(rms):.0f}, p90 {np.percentile(rms,90):.0f}, "
      f"p99 {np.percentile(rms,99):.0f}, đỉnh {rms.max():.0f}")

for ng in (700, 500, 400, 300):
    tren = rms >= ng
    # chuỗi liên tiếp dài nhất
    dai, cur, so_chuoi4 = 0, 0, 0
    for v in tren:
        cur = cur + 1 if v else 0
        dai = max(dai, cur)
        if cur == 4:
            so_chuoi4 += 1
    print(f"  ngưỡng {ng:>4}: {tren.sum():>4} khung vượt | chuỗi dài nhất {dai:>3} khung "
          f"| số lần đạt 4 liên tiếp: {so_chuoi4}")

print("\n  20 khung to nhất nằm ở giây nào:")
idx = np.argsort(rms)[-20:][::-1]
print("   ", ", ".join(f"{i*0.02:.1f}s({rms[i]:.0f})" for i in sorted(idx)[:12]))

# nền theo thời gian
print("\n  RMS trung vị theo từng đoạn 5 giây:")
for k in range(0, len(rms), 250):
    doan = rms[k:k + 250]
    if len(doan):
        print(f"    {k*0.02:>5.0f}-{(k+len(doan))*0.02:>5.0f}s  trung vị {np.median(doan):>6.0f}"
              f"  p90 {np.percentile(doan,90):>7.0f}  đỉnh {doan.max():>7.0f}")
