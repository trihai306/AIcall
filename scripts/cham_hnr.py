"""Chấm HNR của nhiều file một lượt, cả trước và sau khi qua AMR-NB.

Dùng để trả lời: giọng mẫu (người thật) có HNR bao nhiêu so với đầu ra của F5?

  giọng mẫu cao, F5 thấp  -> vocoder của F5 làm mất, phải đổi vocoder
  cả hai đều thấp         -> chính giọng mẫu kém, phải thu giọng mẫu mới

    python scripts/cham_hnr.py a.wav b.wav ...
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mo_phong_amr import RA, doc_wav, hnr, qua_amr  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="+")
    a = ap.parse_args()

    RA.mkdir(parents=True, exist_ok=True)
    print(f"    {'file':<34}{'HNR 8kHz':>10}{'sau AMR':>10}{'giây':>7}")
    for f in a.file:
        p = Path(f)
        if not p.exists():
            print(f"    {p.name:<34}  (không có)")
            continue
        g8 = RA / f"{p.stem}_8k.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(p),
                        "-ar", "8000", "-ac", "1", str(g8)],
                       capture_output=True, timeout=180)
        x, _ = doc_wav(g8)
        y, _ = doc_wav(qua_amr(g8, RA / f"{p.stem}_amr.wav"))
        print(f"    {p.name:<34}{hnr(x, 8000):>10.2f}{hnr(y, 8000):>10.2f}"
              f"{x.size / 8000:>7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
