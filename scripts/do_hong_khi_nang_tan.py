"""Nâng 8kHz -> 16kHz THEO TỪNG KHỐI có làm hỏng tiếng khách không?

NGHI VẤN. Đường thu nâng tần bằng `scipy.signal.resample` (biến đổi FFT) trên
TỪNG KHỐI ~100ms rồi nối lại. FFT giả định tín hiệu TUẦN HOÀN: mẫu cuối khối nối
liền mẫu đầu khối. Tiếng nói không tuần hoàn, nên mỗi khối sinh một điểm gãy ở
biên - mười điểm gãy mỗi giây, nghe như tiếng lách tách rất nhỏ nhưng đủ để mô
hình nhận dạng đọc sai.

So bốn cách trên CÙNG một bản ghi thật:
    A. theo khối 100ms, FFT        - ĐANG DÙNG
    B. cả câu một lần, FFT         - bỏ điểm gãy, nhưng phải chờ hết câu
    C. theo khối 100ms, đa pha     - `resample_poly`, thiết kế cho luồng liên tục
    D. cả câu một lần, đa pha      - mốc trên

Chấm bằng hai thước: méo so với (D), và CHÍNH STT đọc ra gì.

    python scripts/do_hong_khi_nang_tan.py
    python scripts/do_hong_khi_nang_tan.py --file duong/dan.wav
"""

import argparse
import asyncio
import sys
import wave
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KHOI_MS = 100          # đúng kích thước khối của _len_16k


def theo_khoi(x: np.ndarray, sr: int, dich: int, ham) -> np.ndarray:
    n = sr * KHOI_MS // 1000
    return np.concatenate([ham(x[i:i + n], sr, dich)
                           for i in range(0, len(x), n) if len(x[i:i + n])])


def fft_rs(x, sr, dich):
    from scipy.signal import resample
    return resample(x, int(len(x) * dich / sr)).astype(np.float32)


def poly_rs(x, sr, dich):
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(sr, dich)
    return resample_poly(x, dich // g, sr // g).astype(np.float32)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(PROJECT / "logs/tieng_khach/khach.wav"))
    a = ap.parse_args()

    from backend.services.stt_service import STTService

    with wave.open(a.file) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    print(f"\n  {Path(a.file).name}: {len(x)/sr:.1f}s @ {sr}Hz -> 16000Hz\n")

    cach = {
        "A. khối 100ms + FFT  (ĐANG DÙNG)": theo_khoi(x, sr, 16000, fft_rs),
        "B. cả câu + FFT":                   fft_rs(x, sr, 16000),
        "C. khối 100ms + đa pha":            theo_khoi(x, sr, 16000, poly_rs),
        "D. cả câu + đa pha  (mốc)":         poly_rs(x, sr, 16000),
    }
    moc = cach["D. cả câu + đa pha  (mốc)"]

    stt = STTService()
    print(f"  {'cách':<34}{'méo vs mốc':>12}{'  STT đọc ra'}")
    print("  " + "-" * 92)
    for ten, y in cach.items():
        n = min(len(y), len(moc))
        d = float(np.sqrt(((y[:n] - moc[:n]) ** 2).mean()))
        muc = float(np.sqrt((moc[:n] ** 2).mean())) or 1e-9
        pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
        txt = await stt.transcribe(pcm, sample_rate=16000)
        print(f"  {ten:<34}{d/muc*100:>11.2f}%  {txt[:52]!r}")

    # điểm gãy ở biên khối: so bước nhảy tại biên với bước nhảy trong lòng khối
    print()
    for ten in ("A. khối 100ms + FFT  (ĐANG DÙNG)", "C. khối 100ms + đa pha"):
        y = cach[ten]
        n16 = 16000 * KHOI_MS // 1000
        bien = [abs(y[i] - y[i - 1]) for i in range(n16, len(y) - 1, n16)]
        trong = np.abs(np.diff(y))
        if bien:
            print(f"  {ten:<34} bước nhảy tại biên khối gấp "
                  f"{np.mean(bien)/max(float(np.mean(trong)), 1e-9):.1f} lần trong lòng khối")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
