"""Đo tiếng nổ khi cắt lời: tắt phựt so với vuốt nhỏ dần 30ms.

Tiếng 'tách' là một bậc nhảy trong tín hiệu, mà bậc nhảy thì trải năng lượng ra
TOÀN dải tần. Nên đo bằng năng lượng dải cao (>4kHz) quanh điểm cắt, so với
chính đoạn tiếng ngay trước đó - giọng người gần như không có gì trên 4kHz.
Đo bậc mẫu-kề-mẫu là sai: phần lớn con số đó là dao động bình thường của sóng.
"""
import asyncio, io, sys, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))
import numpy as np

SR, VUOT_S = 24000, 0.03

def nang_luong_cao(x):
    """Năng lượng phần trên 4kHz của đoạn x."""
    ph = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return float((ph[f > 4000] ** 2).sum())

async def main():
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()
    b = await tts.synthesize("Dạ anh chị chuẩn bị chứng minh nhân dân và sao kê lương",
                             use_cache=False)
    with wave.open(io.BytesIO(b)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768

    n = int(VUOT_S * SR)
    cua_so = int(0.010 * SR)     # 10ms quanh điểm cắt
    print(f"Vuốt {VUOT_S*1000:.0f}ms ({n} mẫu). Năng lượng >4kHz trong 10ms quanh chỗ tắt,")
    print("lấy tỉ số so với chính đoạn tiếng ngay trước đó (1.0 = không có gì bất thường):\n")
    print(f"{'cắt ở':>7}{'biên độ':>10}{'tắt phựt':>12}{'có vuốt':>11}")

    for vi_tri in (0.2, 0.35, 0.5, 0.65, 0.8):
        k = int(len(a) * vi_tri)
        nen = nang_luong_cao(a[k - cua_so:k]) or 1e-12   # đoạn tiếng trước điểm cắt

        phut = np.concatenate([a[k - cua_so // 2:k], np.zeros(cua_so // 2, np.float32)])
        vuot_full = np.concatenate([a[k:k + n] * np.linspace(1, 0, n, dtype=np.float32),
                                    np.zeros(cua_so, np.float32)])
        # cửa sổ 10ms bắc ngang đúng chỗ tiếng tắt hẳn
        vuot = vuot_full[n - cua_so // 2: n + cua_so // 2]

        print(f"{vi_tri*100:>6.0f}%{abs(a[k]):>10.4f}"
              f"{nang_luong_cao(phut)/nen:>11.1f}x{nang_luong_cao(vuot)/nen:>10.2f}x")

    print("\nTắt phựt: bậc nhảy dội năng lượng lên dải cao -> nghe 'tách'.")
    print("Có vuốt : mẫu cuối bị nhân với 0 nên không còn bậc nào.")

asyncio.run(main())
