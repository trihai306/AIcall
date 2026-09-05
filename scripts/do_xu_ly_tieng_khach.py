"""Lọc tạp âm vs CHUẨN HOÁ MỨC, đo trên 7 lượt khách THẬT của cuộc gọi 4cd44fb7.

Tiếng này đã đi qua GSM/AMR thật, không phải giọng F5 qua kênh giả lập.

Vì sao đo cái này: kênh khách đo được SNR 30-48dB, nền -74 dBFS - RẤT SẠCH,
không có gì để lọc (`scripts/do_tap_am_khach.py`). Nhưng đỉnh tiếng khách chỉ
-19 dBFS, tức rất NHỎ. Nên giả thuyết đáng thử là chuẩn hoá MỨC chứ không phải
lọc nhiễu.

Lời gốc lấy từ lần nghe lại bản ghi trọn vẹn (ghi trong bộ nhớ dự án). Ba lượt
không chắc lời thì bỏ khỏi phần chấm điểm, vẫn in ra để đối chiếu bằng mắt.
"""
import asyncio
import sys
import unicodedata
from pathlib import Path

import numpy as np

GOC_DA = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC_DA))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from backend.services.audio_utils import pcm_to_wav          # noqa: E402
from backend.services.stt_service import STTService          # noqa: E402

THU_MUC = GOC_DA / "data" / "luot_that"
SR = 16000
# None = không chắc lời gốc, chỉ in ra không chấm điểm.
LOI_GOC = {
    1: "thủ tục như nào",
    2: None,
    3: "đúng rồi",
    4: "lãi suất bao nhiêu",
    5: "hạn mức vay tín chấp bao nhiêu",
    6: "hạn mức được bao nhiêu",
    7: "hạn mức được bao nhiêu",
}


def chuan(s):
    s = unicodedata.normalize("NFC", (s or "").lower().strip())
    return " ".join("".join(c for c in s if c.isalnum() or c.isspace()).split())


def cer(goc, ra):
    a, b = chuan(goc), chuan(ra)
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    return d[len(a)][len(b)] / max(len(a), 1)


# ---------------------------------------------------------------- cách xử lý
def khong_lam_gi(x):
    return x


def chuan_dinh(muc_db):
    def f(x):
        d = np.max(np.abs(x)) + 1e-9
        return np.clip(x * (10 ** (muc_db / 20) / d), -1, 1)
    return f


def chuan_rms(muc_db):
    def f(x):
        r = np.sqrt((x ** 2).mean()) + 1e-9
        y = x * (10 ** (muc_db / 20) / r)
        return np.clip(y, -1, 1)
    return f


def loc_co_san(x):
    from backend.services.phone_call_service import lam_sach_tieng_khach
    return lam_sach_tieng_khach(x, SR)


def cong_gate(x):
    """Cổng phổ đơn giản (spectral gating) - kiểu bộ khử nhiễu phổ thông."""
    n, h = 512, 128
    w = np.hanning(n)
    m = max(1, (len(x) - n) // h)
    S = np.array([np.fft.rfft(x[i * h:i * h + n] * w) for i in range(m)])
    bien = np.abs(S)
    nen = np.percentile(bien, 15, axis=0)
    he_so = np.clip((bien - 1.5 * nen) / (bien + 1e-9), 0, 1)
    S2 = S * he_so
    y = np.zeros(len(x), dtype=np.float64)
    dem = np.zeros(len(x), dtype=np.float64)
    for i in range(m):
        y[i * h:i * h + n] += np.fft.irfft(S2[i], n) * w
        dem[i * h:i * h + n] += w ** 2
    y[dem > 1e-9] /= dem[dem > 1e-9]
    return y.astype(np.float32)


CACH = {
    "nguyên bản": khong_lam_gi,
    "chuẩn đỉnh -3dB": chuan_dinh(-3),
    "chuẩn đỉnh -6dB": chuan_dinh(-6),
    "chuẩn RMS -20dB": chuan_rms(-20),
    "lọc nhiễu có sẵn": loc_co_san,
    "cổng phổ": cong_gate,
    "lọc + chuẩn đỉnh": lambda x: chuan_dinh(-3)(loc_co_san(x)),
}


async def main():
    stt = STTService()
    luot = []
    for i in range(1, 8):
        p = THU_MUC / f"luot_{i}.raw"
        if not p.exists():
            continue
        x = np.frombuffer(p.read_bytes(), dtype=np.int16).astype(np.float32) / 32768.0
        luot.append((i, x))
    print(f"{len(luot)} lượt khách thật, {SR}Hz")
    for i, x in luot:
        print(f"  lượt {i}: {len(x)/SR:.2f}s  đỉnh {np.max(np.abs(x)):.4f} "
              f"({20*np.log10(np.max(np.abs(x))+1e-9):.1f} dBFS)")

    kq = {}
    for ten, f in CACH.items():
        ds, dong = [], []
        for i, x in luot:
            try:
                y = np.asarray(f(x), dtype=np.float32)
            except Exception as e:
                dong.append(f"    lượt {i}: xử lý hỏng - {e}")
                continue
            wav = pcm_to_wav((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes(),
                             sample_rate=SR)
            ra = await stt.transcribe(wav)
            txt = (ra or {}).get("text", "") if isinstance(ra, dict) else str(ra or "")
            g = LOI_GOC.get(i)
            e = cer(g, txt) if g else None
            if e is not None:
                ds.append(e)
            dong.append(f"    lượt {i} [{'—' if e is None else f'{e:.2f}'}] {txt!r}")
        kq[ten] = (sum(ds) / len(ds) if ds else float("nan"), dong)

    print("\n=== CHI TIẾT ===")
    for ten, (tb, dong) in kq.items():
        print(f"\n  {ten}  (CER TB {tb:.3f})")
        for d in dong:
            print(d)
    print("\n=== XẾP HẠNG (CER thấp = tốt) ===")
    for ten, (tb, _) in sorted(kq.items(), key=lambda kv: kv[1][0]):
        print(f"  {tb:.3f}  {ten}")


if __name__ == "__main__":
    asyncio.run(main())
