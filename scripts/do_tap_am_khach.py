"""Kênh khách trong bản ghi cuộc gọi THẬT có tạp âm không, và là loại gì?

Trước khi hỏi "lọc tạp âm cách nào tốt hơn" thì phải hỏi "có tạp âm không".
Ghi chú cũ đo SNR 48-51dB trên kênh thoại và kết luận không có gì để lọc, nhưng
đó là bản ghi khác. Đo lại trên bản ghi mới nhất.

Bản ghi 2 kênh: TRÁI = khách, PHẢI = AI (services/recorder.py). Phải đối chiếu
kênh AI: 8/14 "đoạn khách nói" trong lần mổ trước thật ra là VỌNG tiếng AI.
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def phan_tich(duong: Path):
    x, sr = sf.read(str(duong), dtype="float32", always_2d=True)
    khach = x[:, 0]
    ai = x[:, 1] if x.shape[1] > 1 else np.zeros_like(khach)
    print(f"\n=== {duong.name}  {len(khach)/sr:.1f}s  {sr}Hz  {x.shape[1]} kênh")

    n = int(sr * 0.02)                       # khung 20ms
    def rms_khung(v):
        m = len(v) // n
        return np.sqrt((v[:m * n].reshape(m, n) ** 2).mean(axis=1) + 1e-12)

    rk, ra = rms_khung(khach), rms_khung(ai)
    m = min(len(rk), len(ra))
    rk, ra = rk[:m], ra[:m]

    # AI im => khung đó là khách hoặc nền phòng. Đây là chỗ DUY NHẤT đo nền thật.
    ai_im = ra < np.percentile(ra, 20) * 3 + 1e-6
    k_sach = rk[ai_im]
    if len(k_sach) < 20:
        print("  quá ít khung AI im - bỏ qua")
        return
    nen = np.percentile(k_sach, 20)          # nền: phân vị thấp, xem ghi chú VAD
    dinh = np.percentile(k_sach, 99)
    noi = k_sach[k_sach > nen * 4]           # khung coi là CÓ TIẾNG
    print(f"  khung AI im: {ai_im.sum()}/{m}")
    print(f"  nền kênh khách (pv20)  {nen:.5f}   ({20*np.log10(max(nen,1e-9)):.1f} dBFS)")
    print(f"  đỉnh tiếng khách (pv99) {dinh:.5f}   ({20*np.log10(max(dinh,1e-9)):.1f} dBFS)")
    if len(noi):
        snr = 20 * np.log10(np.median(noi) / max(nen, 1e-9))
        print(f"  SNR (trung vị tiếng / nền)  {snr:.1f} dB   [{len(noi)} khung có tiếng]")
    # phổ của phần NỀN: nhiễu băng rộng hay ù tần thấp?
    im = khach[: n * m].reshape(m, n)[ai_im][k_sach < nen * 1.5]
    if len(im) > 5:
        ph = np.abs(np.fft.rfft(im * np.hanning(n), axis=1)).mean(axis=0)
        f = np.fft.rfftfreq(n, 1 / sr)
        tong = ph.sum() + 1e-12
        dai = [(0, 300), (300, 1000), (1000, 2000), (2000, 3400), (3400, sr / 2)]
        print("  phổ phần NỀN: " + "  ".join(
            f"{a}-{b}Hz {100*ph[(f>=a)&(f<b)].sum()/tong:.0f}%" for a, b in dai))


if __name__ == "__main__":
    goc = GOC / "data" / "recordings"
    ds = sorted(goc.rglob("*.opus"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not ds:
        ds = sorted(goc.rglob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in ds[:4]:
        try:
            phan_tich(p)
        except Exception as e:
            print(f"  {p.name}: đọc hỏng - {e}")
