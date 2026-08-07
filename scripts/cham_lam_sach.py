"""Bộ làm sạch có thật sự giúp vocoder AMR dựng giọng đúng hơn không?

Đo bốn thứ trên cùng một câu, qua cùng một chuỗi AMR-NB:
  - HNR: tỉ số hài trên nhiễu. Càng cao vocoder càng dựng đúng.
  - Độ phẳng phổ: càng thấp càng ít "xì".
  - CER: kiểm chứng làm sạch không nuốt mất chữ.
  - Khoảng cách phổ tới bản gốc: đo mức độ "vẫn còn là giọng đó".

Chạy cả bản CÓ và KHÔNG làm sạch để so cạnh nhau, kèm mốc đối chiếu là chính
BẢN THU NGƯỜI THẬT qua cùng đường - nếu người thật cũng méo như vậy thì lỗi ở
đường thoại chứ không ở TTS.

    python scripts/cham_lam_sach.py
"""

import asyncio
import re
import sys
import unicodedata
import wave
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

CAU = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp "
       "lãi suất ưu đãi từ sáu phẩy năm phần trăm một năm.")


def gon(s: str) -> str:
    s = unicodedata.normalize("NFC", s.lower())
    return re.sub(r"\s+", " ", re.sub(r"[.,!?;:\"'()\[\]…-]", " ", s)).strip()


def cer(a: str, b: str) -> float:
    a, b = gon(a), gon(b)
    if not a:
        return 0.0
    tr = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        sa = [i]
        for j, cb in enumerate(b, 1):
            sa.append(min(tr[j] + 1, sa[j - 1] + 1, tr[j - 1] + (ca != cb)))
        tr = sa
    return tr[-1] / len(a)


def khoang_cach_pho(a, sra, b, srb) -> float:
    """Khoảng cách phổ trung bình (dB) giữa hai tín hiệu, trong dải đường thoại.
    Nhỏ = vẫn còn giống giọng gốc."""
    import numpy as np

    def bao(x, sr):
        ph = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
        f = np.fft.rfftfreq(len(x), 1 / sr)
        m = (f >= 200) & (f < 3400)
        p, fp = ph[m], f[m]
        moc = np.linspace(200, 3400, 60)
        return np.array([p[(fp >= lo) & (fp < hi)].sum() + 1e-12
                         for lo, hi in zip(moc[:-1], moc[1:])])

    pa, pb = bao(a, sra), bao(b, srb)
    pa, pb = pa / pa.sum(), pb / pb.sum()
    return float(np.abs(10 * np.log10(pa / pb)).mean())


async def main() -> int:
    import numpy as np
    import requests

    from do_kim_loai import do_hnr, do_phang_pho, ghi, qua_gsm, doc

    from backend.config import settings
    from backend.services.audio_utils import resample_audio
    from backend.services.phone_call_service import toi_uu_cho_thoai
    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    out = PROJECT / "logs" / "cham_lam_sach"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"):
        f.unlink()

    sess = requests.Session()

    def nghe(w: bytes) -> str:
        try:
            r = sess.post("http://127.0.0.1:8178/inference",
                          files={"file": ("a.wav", w, "audio/wav")},
                          data={"language": "vi", "response_format": "json",
                                "temperature": "0"}, timeout=120)
            return r.json().get("text", "").strip()
        except Exception as e:
            return f"[lỗi {e}]"

    wav = await tts.synthesize(CAU, use_cache=False)
    x, sr = doc(wav)
    (out / "0_goc_24kHz.wav").write_bytes(wav)

    ban = {}
    goc_ls = settings.phone_lam_sach
    for ten, ls in (("khong_lam_sach", False), ("co_lam_sach", True)):
        settings.phone_lam_sach = ls
        y = resample_audio(toi_uu_cho_thoai(x, sr), sr, 8000)
        ban[ten] = qua_gsm(y)
    settings.phone_lam_sach = goc_ls

    # mốc đối chiếu: bản thu NGƯỜI THẬT qua cùng đường
    ref = PROJECT / settings.f5tts_ref_audio.lstrip("./")
    if ref.exists():
        with wave.open(str(ref)) as w:
            srr = w.getframerate()
            xr = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float32") / 32768
        ban["nguoi_that"] = qua_gsm(resample_audio(xr, srr, 8000))

    print(f"{'bản':<20}{'HNR':>9}{'phẳng phổ':>12}{'CER':>8}{'lệch phổ':>11}")
    print("-" * 62)
    print(f"{'gốc 24kHz (mốc)':<20}{do_hnr(x, sr):>8.1f}dB{do_phang_pho(x, sr):>12.4f}"
          f"{cer(CAU, nghe(wav)) * 100:>7.1f}%{'—':>11}")
    for ten, y8 in ban.items():
        (out / f"{ten}.wav").write_bytes(ghi(y8, 8000))
        lech = khoang_cach_pho(x, sr, y8, 8000)
        c = cer(CAU, nghe(ghi(y8, 8000))) * 100 if ten != "nguoi_that" else float("nan")
        print(f"{ten:<20}{do_hnr(y8, 8000):>8.1f}dB{do_phang_pho(y8, 8000):>12.4f}"
              f"{c:>7.1f}%{lech:>10.2f}dB")
    print("-" * 62)
    print("\nHNR cao hơn + phẳng phổ thấp hơn = vocoder dựng đúng hơn.")
    print("Lệch phổ nhỏ = vẫn còn giống giọng gốc.")
    print("Dòng 'nguoi_that' là mốc: TTS không thể tốt hơn mốc này qua cùng đường.")
    print(f"\n{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
