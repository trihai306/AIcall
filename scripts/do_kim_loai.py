"""Vì sao qua điện thoại giọng nghe kim loại và như người khác?

AMR-NB không nén sóng như MP3 - nó là VOCODER: phân tích tiếng thành "bộ lọc
thanh quản + nguồn kích thích" rồi DỰNG LẠI ở đầu kia theo mô hình tiếng người.
Mô hình đó được luyện trên giọng người thật. Tiếng TTS khuếch tán có nhiễu nền
rộng dải mà mô hình không biết xử lý -> dựng lại thành âm kim loại, và các đặc
trưng nhận dạng người nói bị bóp méo -> nghe ra người khác.

CER không bắt được thứ này (vẫn nghe ra chữ), nên phải đo bằng thước khác:

  - Độ phẳng phổ (Wiener entropy): nhiễu thì phổ phẳng, giọng có thanh thì phổ
    gồ ghề. Càng phẳng càng "xì", càng dễ bị vocoder dựng sai.
  - Tỉ số hài trên nhiễu (HNR): phần tuần hoàn của giọng so với phần nhiễu.
    Càng cao giọng càng "sạch", vocoder càng dựng đúng.

    python scripts/do_kim_loai.py
    python scripts/do_kim_loai.py --nfe 8 16 32
"""

import argparse
import asyncio
import io
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

CAU = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp "
       "lãi suất ưu đãi từ sáu phẩy năm phần trăm một năm.")


def doc(b: bytes):
    import numpy as np
    with wave.open(io.BytesIO(b)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x.astype("float32") / 32768, sr


def ghi(x, sr: int) -> bytes:
    import numpy as np
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def qua_gsm(x8):
    with tempfile.TemporaryDirectory() as d:
        pi, pa, po = Path(d) / "i.wav", Path(d) / "m.amr", Path(d) / "o.wav"
        pi.write_bytes(ghi(x8, 8000))
        for c in (["ffmpeg", "-y", "-i", str(pi), "-ar", "8000", "-ac", "1",
                   "-c:a", "libopencore_amrnb", "-b:a", "12.2k", str(pa)],
                  ["ffmpeg", "-y", "-i", str(pa), "-ar", "8000", "-ac", "1", str(po)]):
            subprocess.run(c, capture_output=True)
        return doc(po.read_bytes())[0]


def do_phang_pho(x, sr) -> float:
    """Wiener entropy trung bình trên các khung CÓ tiếng. 0 = thuần thanh, 1 = nhiễu."""
    import numpy as np
    N, H = 1024, 512
    ra = []
    for k in range(0, len(x) - N, H):
        w = x[k:k + N]
        if np.sqrt((w ** 2).mean()) < 0.01:      # bỏ khung im
            continue
        ph = np.abs(np.fft.rfft(w * np.hanning(N))) ** 2 + 1e-12
        f = np.fft.rfftfreq(N, 1 / sr)
        ph = ph[(f >= 200) & (f < 3400)]          # chỉ dải đường thoại giữ
        ra.append(float(np.exp(np.log(ph).mean()) / ph.mean()))
    return float(np.mean(ra)) if ra else 0.0


def do_hnr(x, sr) -> float:
    """Tỉ số hài/nhiễu, dB. Dùng tự tương quan: đỉnh tại chu kỳ cơ bản cho biết
    phần tuần hoàn mạnh bao nhiêu so với phần còn lại."""
    import numpy as np
    N, H = 1024, 512
    ra = []
    for k in range(0, len(x) - N, H):
        w = x[k:k + N]
        if np.sqrt((w ** 2).mean()) < 0.01:
            continue
        w = w - w.mean()
        ac = np.correlate(w, w, mode="full")[N - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        lo, hi = int(sr / 400), int(sr / 70)      # F0 người: 70-400Hz
        if hi >= len(ac):
            continue
        r = float(ac[lo:hi].max())
        r = min(max(r, 1e-6), 0.999999)
        ra.append(10 * np.log10(r / (1 - r)))
    return float(np.mean(ra)) if ra else 0.0


async def main() -> int:
    import numpy as np

    ap = argparse.ArgumentParser()
    ap.add_argument("--nfe", type=int, nargs="+", default=[8, 12, 16, 24, 32])
    ap.add_argument("--out", default=str(PROJECT / "logs" / "kim_loai"))
    args = ap.parse_args()

    from backend.config import settings
    from backend.services.audio_utils import resample_audio
    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"):
        f.unlink()

    goc = settings.f5tts_nfe_step
    print("Nhiễu của mô hình khuếch tán làm vocoder AMR dựng sai giọng.")
    print("Càng ÍT phẳng phổ và càng CAO HNR thì qua điện thoại càng ít kim loại.\n")
    print(f"{'nfe':>5}{'thời gian':>11}"
          f"{'phẳng phổ gốc':>15}{'sau AMR':>10}"
          f"{'HNR gốc':>10}{'sau AMR':>10}")
    print("-" * 62)

    import time
    for nfe in args.nfe:
        settings.f5tts_nfe_step = nfe
        t0 = time.perf_counter()
        w = await tts.synthesize(CAU, use_cache=False)
        ms = (time.perf_counter() - t0) * 1000
        x, sr = doc(w)
        x8 = resample_audio(x, sr, 8000)
        y8 = qua_gsm(x8)
        (out / f"nfe{nfe:02d}_qua_dien_thoai.wav").write_bytes(ghi(y8, 8000))
        print(f"{nfe:>5}{ms:>9.0f}ms"
              f"{do_phang_pho(x, sr):>15.4f}{do_phang_pho(y8, 8000):>10.4f}"
              f"{do_hnr(x, sr):>9.1f}dB{do_hnr(y8, 8000):>9.1f}dB")
    settings.f5tts_nfe_step = goc
    print("-" * 62)
    print(f"\nMẫu qua điện thoại để nghe: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
