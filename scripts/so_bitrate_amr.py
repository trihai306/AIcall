"""Dựng cùng một câu ở mọi chế độ AMR-NB để nghe khác biệt.

Vì sao: bản mô phỏng trước tôi mã hoá ở 12.2 kbps - chế độ TỐT NHẤT của AMR-NB -
và người nghe bảo sạch. Nhưng máy đang chạy EDGE với sóng yếu, và trong điều kiện
đó mạng tự hạ xuống 7.4, 5.9, thậm chí 4.75 kbps. Chênh lệch giữa 12.2 và 4.75
rất lớn, đủ để nghe thành "dè".

Nếu bản 4.75 hoặc 5.9 nghe giống hệt cuộc gọi thật thì nguyên nhân nằm ở điều
kiện sóng, không phải ở đường tiêm - và mọi thứ tôi chỉnh trong ABOX/codec đều
vô ích, đúng như đã quan sát.

    python scripts/so_bitrate_amr.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mo_phong_amr import RA, doc_wav, hnr  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
# Mọi chế độ AMR-NB, từ thấp nhất tới cao nhất.
MUC = ["4.75k", "5.15k", "5.9k", "6.7k", "7.4k", "7.95k", "10.2k", "12.2k"]


def main() -> int:
    goc = PROJECT / "data" / "mau_so_sanh.wav"
    if not goc.exists():
        print("Chưa có câu mẫu:", goc)
        return 1
    RA.mkdir(parents=True, exist_ok=True)

    print(f"    {'chế độ':<10}{'HNR':>8}   file")
    for m in MUC:
        ten = m.replace(".", "_")
        amr = RA / f"amr_{ten}.amr"
        wav = RA / f"amr_{ten}.wav"
        r1 = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(goc),
             "-ar", "8000", "-ac", "1", "-c:a", "libopencore_amrnb",
             "-b:a", m, str(amr)], capture_output=True, text=True, timeout=180)
        if r1.returncode != 0:
            print(f"    {m:<10}  không mã hoá được: {(r1.stderr or '')[:60]}")
            continue
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(amr),
                        "-ar", "8000", "-ac", "1", str(wav)],
                       capture_output=True, timeout=180)
        x, _ = doc_wav(wav)
        print(f"    {m:<10}{hnr(x, 8000):>8.2f}   {wav}")
    print("\n    Nghe từ 4.75k lên dần. Mức nào giống cuộc gọi thật nhất chính là")
    print("    chế độ mạng đang dùng - và nếu là mức thấp thì lỗi ở sóng, không")
    print("    phải ở đường tiêm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
