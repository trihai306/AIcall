"""Tiếng AI trong cuộc gọi có bị ĐỨT QUÃNG không, và đứt ở đâu?

Người dùng nghe thấy AI "nói bị đứt quãng". Có hai kiểu đứt hoàn toàn khác nhau,
chữa theo hai hướng ngược nhau, nên phải phân biệt trước khi sửa:

  A. ĐỨT TRONG CÂU  - giữa một câu đang nói có khoảng lặng. Nghĩa là tiếng về
     không kịp: TTS sinh chậm hơn tốc độ phát, hoặc hàng đợi bị hụt.
  B. ĐỨT GIỮA LƯỢT  - câu nói xong rồi, nhưng lượt sau đợi quá lâu. Nghĩa là
     vòng nghĩ (STT + RAG + LLM) chậm, không phải đường tiếng.

Script tách kênh AI của bản ghi, tìm các cụm nói, rồi liệt kê mọi khoảng lặng
NẰM TRONG một cụm (kiểu A) tách khỏi khoảng lặng GIỮA các cụm (kiểu B).

    python scripts/soi_dut_quang.py
    python scripts/soi_dut_quang.py --file <bản ghi>
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


def cum_noi(rms: np.ndarray, ms: int, nguong: float, noi_ms: int = 400):
    """Gộp các khung có tiếng thành cụm; lặng < `noi_ms` thì coi là trong cùng cụm."""
    co = rms > nguong
    cum, i, n_noi = [], 0, max(1, noi_ms // ms)
    while i < len(co):
        if not co[i]:
            i += 1
            continue
        j = i
        lang = 0
        k = i
        while k < len(co):
            if co[k]:
                j, lang = k, 0
            else:
                lang += 1
                if lang > n_noi:
                    break
            k += 1
        cum.append((i, j))
        i = k
    return cum


def main() -> int:
    import soundfile as sf

    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="")
    ap.add_argument("--dut-ms", type=int, default=120,
                    help="lặng trong câu dài hơn ngần này thì coi là đứt")
    a = ap.parse_args()

    if a.file:
        f = Path(a.file)
    else:
        goc = PROJECT / "data" / "recordings"
        tep = sorted(goc.rglob("*.opus")) + sorted(goc.rglob("*.wav"))
        if not tep:
            print("  không thấy bản ghi nào")
            return 1
        f = max(tep, key=lambda p: p.stat().st_mtime)

    x, sr = sf.read(str(f), dtype="float32", always_2d=True)
    if x.shape[1] < 2:
        print("  bản ghi chỉ có 1 kênh - không tách được tiếng AI")
        return 1
    ai = x[:, 1]

    MS = 20
    N = sr * MS // 1000
    rms = np.array([np.sqrt((ai[i:i + N] ** 2).mean()) * 32768.0
                    for i in range(0, len(ai) - N, N)])
    nen = float(np.percentile(rms, 20))
    nguong = max(200.0, nen * 3)
    print(f"\n  {f.name} | kênh AI | nền {nen:.0f} -> ngưỡng {nguong:.0f}\n")

    cum = cum_noi(rms, MS, nguong)
    if not cum:
        print("  KHÔNG thấy tiếng AI nào trong bản ghi")
        return 1

    n_dut = max(1, a.dut_ms // MS)
    tong_dut = 0
    for c, (bd, kt) in enumerate(cum, 1):
        doan = rms[bd:kt + 1] > nguong
        # khoảng lặng NẰM TRONG cụm
        dut, i = [], 0
        while i < len(doan):
            if doan[i]:
                i += 1
                continue
            j = i
            while j < len(doan) and not doan[j]:
                j += 1
            if j - i >= n_dut:
                dut.append(((bd + i) * MS / 1000, (j - i) * MS))
            i = j
        dai = (kt - bd + 1) * MS / 1000
        print(f"  câu {c}: {bd*MS/1000:6.2f}s -> {kt*MS/1000:6.2f}s  (dài {dai:.2f}s)")
        for t, d in dut:
            print(f"      ĐỨT tại {t:.2f}s, im {d}ms")
        tong_dut += len(dut)
        if c < len(cum):
            cho = (cum[c][0] - kt) * MS / 1000
            print(f"      -> chờ {cho:.2f}s tới câu sau")

    print(f"\n  Tổng: {len(cum)} câu, {tong_dut} chỗ đứt TRONG câu (>{a.dut_ms}ms).")
    if tong_dut:
        print("  -> Đứt TRONG câu = đường tiếng hụt (TTS sinh không kịp / hàng đợi rỗng).")
    else:
        print("  -> Không đứt trong câu. Nếu nghe thấy 'đứt quãng' thì đó là CHỜ GIỮA LƯỢT")
        print("     (vòng STT+RAG+LLM chậm), xem cột 'chờ ... tới câu sau'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
