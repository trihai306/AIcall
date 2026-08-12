"""Dung ban nghe thu A/B cho HE_SO_BU_LANG, di DUNG duong cua pipeline that.

Cat manh bang chinh `tach_manh` dang chay (CAT_THEO_CAU), sinh bang
`svc.synthesize` (co trim_silence + cat_lang_bia), noi lai bang dung nhip nghi
ma `nhip_nghi_sau` tra ve. Khac voi cac script do truoc: khong cat cung 20 tu.

Xuat moi he so mot file WAV de NGHE, kem so lieu quang lang.

    .venv\\python.exe scripts\\dung_ab_he_so_cap.py --he-so 1.11 0.85
"""
import argparse
import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402

import backend.services.tts_service as mod                       # noqa: E402
from backend.pipeline.text_chunker import nhip_nghi_sau, tach_manh   # noqa: E402
from backend.services.tts_service import F5TTSService            # noqa: E402

KHUNG_MS = 20.0

VAN = ("Dạ vâng ạ, bên em đang có chương trình vay tín chấp, anh không cần thế "
       "chấp gì hết. Lãi suất hiện tại từ bảy phẩy chín phần trăm một năm, cố "
       "định suốt kỳ vay chứ không thả nổi. Hạn mức cao nhất là năm trăm triệu, "
       "thời hạn thì anh chọn từ mười hai đến sáu mươi tháng. Điều kiện đơn "
       "giản thôi ạ, anh có thu nhập ổn định từ năm triệu một tháng trở lên là "
       "được rồi.")


def cat_manh_that(van: str) -> list[str]:
    """Chay dung vong cat cua streaming_pipeline."""
    ra, dem, buf = [], 0, ""
    for t in van.split():
        buf += t + " "
        while True:
            manh, buf = tach_manh(buf, n=40, first_chunk=(dem == 0))
            if manh is None:
                break
            ra.append(manh)
            dem += 1
    if buf.strip():
        ra.append(buf.strip())
    return ra


def cac_quang_lang(x, sr, toi_thieu_ms=150.0):
    n = max(1, int(sr * KHUNG_MS / 1000))
    k = len(x) // n
    if k < 3:
        return []
    kh = x[: k * n].reshape(k, n).astype(np.float64)
    rms = np.sqrt((kh * kh).mean(axis=1))
    dinh = float(rms.max())
    im = rms < dinh * 0.20
    day = dinh * 0.07
    ra, i = [], 0
    while i < k:
        j = i
        while j < k and im[j] == im[i]:
            j += 1
        dai = (j - i) * KHUNG_MS
        if im[i] and i > 0 and j < k and dai > toi_thieu_ms and float(rms[i:j].min()) < day:
            ra.append(dai)
        i = j
    return ra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--he-so", type=float, nargs="+", default=[1.11, 0.85])
    ap.add_argument("--ra", default="data/ab_he_so")
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    goc = mod.HE_SO_BU_LANG

    manh = cat_manh_that(VAN)
    Path(a.ra).mkdir(parents=True, exist_ok=True)
    print(f"\n  giọng {ten}   BO_DAU_CAU={mod.BO_DAU_CAU}   {len(manh)} mảnh")
    for i, m in enumerate(manh):
        print(f"    {i + 1}. ({len(m.split())} từ, nghỉ sau {nhip_nghi_sau(m):.0f}ms) {m[:58]}")
    print()
    print(f"  {'hệ số':>7} {'dài':>7} {'lỗ ≥360':>9} {'lỗ ≥150':>9} {'tổng lỗ':>9}  tệp")
    print("  " + "-" * 66)

    for hs in a.he_so:
        mod.HE_SO_BU_LANG = hs
        # Xoa cache cau: khoa cache khong co HE_SO nen doi he so ma khong xoa
        # thi lay lai dung ban cu -> hai cot giong het nhau, do ra vo nghia.
        svc._cache.clear() if hasattr(svc, "_cache") else None
        for ten_c in list(getattr(svc, "_sentence_cache", {})):
            svc._sentence_cache.pop(ten_c, None)
        khuc, sr = [], 24000
        for i, m in enumerate(manh):
            b = asyncio.run(svc.synthesize(m, voice=ten, use_cache=False))
            y, sr = sf.read(io.BytesIO(b), dtype="float32")
            if y.ndim > 1:
                y = y.mean(axis=1)
            if i > 0:
                ms = nhip_nghi_sau(manh[i - 1])
                if ms > 0:
                    khuc.append(np.zeros(int(sr * ms / 1000), dtype=np.float32))
            khuc.append(y)
        het = np.concatenate(khuc)
        f = Path(a.ra) / f"he_so_{str(hs).replace('.', '_')}.wav"
        sf.write(str(f), het, sr, subtype="PCM_16")
        q360 = cac_quang_lang(het, sr, 360.0)
        q150 = cac_quang_lang(het, sr, 150.0)
        print(f"  {hs:>7.2f} {len(het) / sr:>6.2f}s {len(q360):>4}/{sum(q360):>4.0f}ms"
              f" {len(q150):>4}/{sum(q150):>4.0f}ms {sum(q150):>7.0f}ms  {f}")

    mod.HE_SO_BU_LANG = goc
    print("  " + "-" * 66)
    print("  'lỗ' = quãng lặng nằm GIỮA mảnh, tức chỗ F5 tự bịa ra quãng dừng.")
    print("  Quãng nghỉ ở ranh giới mảnh do code chèn KHÔNG tính vào đây vì nó")
    print("  rơi đúng ranh giới câu - đó là nghỉ đúng chỗ.\n")


if __name__ == "__main__":
    main()
