"""Cao do co BI TUT roi VOT LEN o ranh gioi manh khong?

Nguoi dung: "doan '24 gio sau khi phe duyet ho so' tu ha tram roi noi cao len".

Nghi van: F5 sinh MOI MANH DOC LAP nen manh nao cung co duong net "mo dau roi
ket thuc" - ha giong o cuoi manh, roi manh sau lai bat dau o cao do cao. Cat 5 tu
thi chuyen do xay ra cu moi 5 tu.

Do: sinh cung mot cau theo hai cach roi so cao do (F0) o CHO NOI.
    - mot lan duy nhat  : khong co cho noi, day la moc chuan
    - cat 5 tu roi ghep : do F0 200ms cuoi manh N va 200ms dau manh N+1

Neu cuoi manh tut xuong va dau manh sau vot len thi dung la loi ranh gioi.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_ngu_dieu_ranh_manh.py
"""
import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import librosa                  # noqa: E402

from backend.pipeline.text_chunker import tach_manh          # noqa: E402
from backend.services.tts_service import F5TTSService        # noqa: E402

RA = Path("C:/tmp/ngudieu")
CAU = ("Anh chị sẽ nhận được tiền trong vòng 24 giờ sau khi phê duyệt hồ sơ, "
       "bên em xử lý rất nhanh ạ")
BIEN = 120.0     # Hz, dai F0 giong nu


def f0_trung_vi(x: np.ndarray, sr: int) -> float:
    """F0 trung vi cua doan, bo cac khung khong ro cao do."""
    if len(x) < sr // 20:
        return 0.0
    try:
        f = librosa.yin(x.astype(np.float32), fmin=80, fmax=450, sr=sr)
    except Exception:
        return 0.0
    f = f[np.isfinite(f)]
    return float(np.median(f)) if len(f) else 0.0


def cat_nhu_pipeline(van: str) -> list[str]:
    ra, dem = [], ""
    for t in van.split():
        dem += " " + t
        m, dem = tach_manh(dem, first_chunk=(not ra))
        if m:
            ra.append(m)
    if dem.strip():
        ra.append(dem.strip())
    return ra


def main():
    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    RA.mkdir(parents=True, exist_ok=True)

    def sinh(t):
        b = asyncio.run(svc.synthesize(t, voice=ten))
        x, sr = sf.read(io.BytesIO(b), dtype="float32")
        return (x.mean(axis=1) if x.ndim > 1 else x), sr

    manh_text = cat_nhu_pipeline(CAU)
    print(f"\n  giọng {ten}   câu {len(CAU.split())} từ -> {len(manh_text)} mảnh\n")

    # --- moc chuan: sinh mot lan ------------------------------------------
    x1, sr = sinh(CAU)
    sf.write(RA / "mot_lan.wav", x1 / max(1.0, float(np.abs(x1).max())), sr)
    n = int(sr * 0.2)
    # Lay F0 tai cac moc tuong duong "cuoi manh" neu chia deu - de doi chieu
    buoc = len(x1) // max(len(manh_text), 1)
    goc = [f0_trung_vi(x1[max(0, i*buoc - n):i*buoc], sr)
           for i in range(1, len(manh_text))]
    goc = [g for g in goc if g > 0]
    print(f"  [1] SINH MỘT LẦN (không có chỗ nối)")
    print(f"      F0 tại các mốc tương đương: {[f'{g:.0f}' for g in goc]}")
    if len(goc) >= 2:
        print(f"      chênh lệch lớn nhất giữa hai mốc liền nhau: "
              f"{max(abs(goc[i+1]-goc[i]) for i in range(len(goc)-1)):.0f} Hz")

    # --- cat manh roi ghep -------------------------------------------------
    print(f"\n  [2] CẮT MẢNH RỒI GHÉP - đo F0 ở CHỖ NỐI")
    print(f"      {'mảnh':<26} {'F0 cuối':>9} {'F0 đầu sau':>12} {'vọt':>7}")
    print("      " + "-" * 62)
    wavs, vots = [], []
    for c in manh_text:
        y, sr = sinh(c)
        wavs.append(y)
    for i in range(len(wavs) - 1):
        cuoi = f0_trung_vi(wavs[i][-n:], sr)
        dau = f0_trung_vi(wavs[i+1][:n], sr)
        if cuoi > 0 and dau > 0:
            vot = dau - cuoi
            vots.append(vot)
            co = "  <== VỌT" if abs(vot) > 40 else ""
            print(f"      {manh_text[i][:24]:<26} {cuoi:>8.0f} {dau:>11.0f}"
                  f" {vot:>+6.0f}{co}")
    ghep = np.concatenate(wavs)
    sf.write(RA / "cat_manh.wav", ghep / max(1.0, float(np.abs(ghep).max())), sr)

    print("      " + "-" * 62)
    if vots:
        print(f"\n      vọt trung bình : {np.mean(np.abs(vots)):.0f} Hz")
        print(f"      vọt lớn nhất   : {max(np.abs(vots)):.0f} Hz")
        print(f"      số chỗ vọt > 40Hz: {sum(1 for v in vots if abs(v) > 40)}/{len(vots)}")
    print(f"\n  Tai người nghe ra bước nhảy cao độ từ khoảng 30-40 Hz.")
    print(f"  wav ở {RA} - nghe mot_lan.wav rồi cat_manh.wav sẽ thấy khác.")


if __name__ == "__main__":
    main()
