"""Ghép các mẩu thu thành MỘT file dài, để thử luồng "upload bản thu dài".

Máy hiện không có sẵn bản thu liền mạch 30-60 phút, mà đó chính là tình huống
cần kiểm: người dùng có một file dài và muốn hệ thống tự cắt, tự phiên âm, tự
train. Ghép ngược các mẩu đã cắt lại cho ra đúng loại đầu vào đó, bằng GIỌNG
THẬT của dự án chứ không phải tiếng tổng hợp.

Chèn 400ms lặng giữa các mẩu để bộ cắt có chỗ ngắt - thu thật cũng luôn có
khoảng nghỉ giữa các câu.

    python scripts/ghep_thanh_file_dai.py --input data\\giong_nam_cat --out data\\thu_dai_kiemthu.wav
"""

import argparse
import sys
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main() -> int:
    import soundfile as sf

    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang-ms", type=int, default=400)
    ap.add_argument("--toi-da-phut", type=float, default=0, help="0 = lấy hết")
    a = ap.parse_args()

    d = Path(a.input)
    tep = sorted(list(d.glob("*.wav")) + list(d.glob("*.mp3")))
    if not tep:
        print(f"  không thấy file nào trong {d}")
        return 1

    khuc, sr = [], None
    tong = 0.0
    for p in tep:
        y, s = sf.read(str(p), dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        if sr is None:
            sr = s
        elif s != sr:
            print(f"  bỏ {p.name}: {s}Hz khác {sr}Hz")
            continue
        khuc.append(y)
        tong += len(y) / sr
        if a.toi_da_phut and tong >= a.toi_da_phut * 60:
            break

    lang = np.zeros(int(sr * a.lang_ms / 1000), dtype="float32")
    ra = np.concatenate([k for i, x in enumerate(khuc) for k in ((x,) if i == 0 else (lang, x))])

    o = Path(a.out)
    o.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(o), ra, sr, subtype="PCM_16")
    print(f"  ghép {len(khuc)} mẩu -> {o}")
    print(f"  {len(ra)/sr/60:.1f} phút @ {sr}Hz, {o.stat().st_size/1048576:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
