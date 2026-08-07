"""Tiếng khách thu về có thật sự nhiều tạp âm không, và tạp âm nằm ở đâu?

Phải đo trước khi chỉnh bộ lọc. Lọc nhiễu trên kênh vốn đã sạch chỉ làm hỏng
thêm - đã có tiền lệ trong dự án này: bộ lọc Wiener cho tiếng AI làm HNR TỆ ĐI
(5.1 -> 5.0) nên phải tắt.

Đo trên KÊNH KHÁCH của bản ghi cuộc gọi thật (stereo: trái khách, phải AI):

  - SNR: mức lúc có tiếng so với lúc im. Trên 25dB là kênh sạch, dưới 15dB mới
    đáng lọc.
  - PHỔ lúc im: nhiễu trắng đều dải, ù điện lưới dồn ở dưới 200Hz, nhiễu lượng
    tử của bộ mã dồn ở trên 3kHz. Ba loại cần ba cách xử khác nhau.
  - BĂNG THÔNG lúc có tiếng: kênh thoại cắt trên 3400Hz, nên nếu năng lượng đã
    tắt từ 3kHz thì nới dải lọc lên cũng vô ích.

    python scripts/do_tap_am_that.py
    python scripts/do_tap_am_that.py --file data/recordings/2026-08-05/abc.opus
"""

import argparse
import sys
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def db(x: float) -> float:
    return 20 * np.log10(max(x, 1e-9))


def pho_dai(x: np.ndarray, sr: int) -> list[tuple[str, float]]:
    """Năng lượng theo từng dải, tính bằng % tổng."""
    if x.size < 512:
        return []
    F = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    dai = [("0-200Hz", 0, 200), ("200-500", 200, 500), ("500-1k", 500, 1000),
           ("1k-2k", 1000, 2000), ("2k-3k", 2000, 3000), ("3k-3.4k", 3000, 3400),
           ("3.4k+", 3400, sr / 2 + 1)]
    tong = F.sum() or 1.0
    return [(ten, 100.0 * F[(f >= a) & (f < b)].sum() / tong) for ten, a, b in dai]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="")
    a = ap.parse_args()

    import soundfile as sf

    if a.file:
        f = Path(a.file)
    else:
        goc = PROJECT / "data" / "recordings"
        tep = sorted(goc.rglob("*.opus")) + sorted(goc.rglob("*.wav"))
        if not tep:
            print(f"  không thấy bản ghi nào trong {goc}")
            return 1
        f = max(tep, key=lambda p: p.stat().st_mtime)

    x, sr = sf.read(str(f), dtype="float32", always_2d=True)
    khach = x[:, 0]
    print(f"\n  {f.name}: {len(khach)/sr:.1f}s @ {sr}Hz (kênh khách)")

    # Tách khung có tiếng / im, theo đúng ngưỡng VAD của đường thoại.
    N = sr * 20 // 1000
    khung = np.array([khach[i:i + N] for i in range(0, len(khach) - N, N)])
    rms = np.sqrt((khung ** 2).mean(axis=1)) * 32768
    co = rms >= 700
    if not co.any():
        print("  Không có khung nào vượt ngưỡng VAD 700 - bản ghi này không có "
              "tiếng khách, đo tiếp là vô nghĩa.")
        return 1

    # "Im" = phân vị 20 thấp nhất, tránh lấy nhầm đuôi câu.
    nguong_im = np.percentile(rms, 20)
    im = rms <= nguong_im

    m_tieng, m_im = rms[co].mean(), max(rms[im].mean(), 1e-9)
    print(f"  khung có tiếng: {co.sum()}/{len(rms)} ({100*co.mean():.1f}%)")
    print(f"  mức khi nói : {db(m_tieng/32768):6.1f} dBFS")
    print(f"  mức khi im  : {db(m_im/32768):6.1f} dBFS")
    print(f"  SNR         : {db(m_tieng/32768) - db(m_im/32768):6.1f} dB", end="")
    snr = db(m_tieng / 32768) - db(m_im / 32768)
    print("   <- trên 25dB là kênh SẠCH, lọc nhiễu gần như vô ích"
          if snr >= 25 else "   <- dưới 15dB thì lọc mới đáng")

    print("\n  Phổ khi IM (tạp âm nằm ở đâu):")
    for ten, pct in pho_dai(np.concatenate(khung[im][:60]) if im.any() else khach, sr):
        print(f"    {ten:>8}: {pct:5.1f}%  {'#' * int(pct / 2)}")

    print("\n  Phổ khi CÓ TIẾNG (băng thông thật của kênh):")
    for ten, pct in pho_dai(np.concatenate(khung[co][:60]), sr):
        print(f"    {ten:>8}: {pct:5.1f}%  {'#' * int(pct / 2)}")

    print("\n  Đọc kết quả: nếu 3.4k+ gần 0% thì kênh đã bị nhà mạng cắt sẵn,")
    print("  nới dải lọc lên cao vô ích. Nếu 0-200Hz chiếm nhiều lúc im thì đó")
    print("  là ù nền, cắt trầm sẽ ăn thua.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
