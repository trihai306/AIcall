"""Đường thoại GSM lấy mất bao nhiêu chất lượng của F5-TTS?

Câu hỏi thực dụng: nâng cấp TTS thì khách gọi điện có nghe khác không, hay công
sức đó bị codec 8kHz nuốt sạch. Đo bằng cách đẩy chính tiếng TTS qua ba mức suy
giảm rồi chấm lại bằng PhoWhisper:

    1. gốc 24kHz          - thứ trình duyệt nghe
    2. hạ về 8kHz         - băng thông đường thoại
    3. qua codec AMR-NB   - đúng thứ GSM dùng thật (12.2 kbps)

Kèm phân bố năng lượng theo dải tần: phần trên 4kHz là phần đường thoại VỨT ĐI
hoàn toàn, đo được nó chiếm bao nhiêu thì biết mất mát thật sự là bao nhiêu.

    python scripts/do_kenh_thoai.py
    python scripts/do_kenh_thoai.py --runs 3
"""

import argparse
import io
import re
import subprocess
import sys
import tempfile
import unicodedata
import wave
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

CAU_TEST = [
    "Dạ anh chị chuẩn bị chứng minh nhân dân và sao kê lương ba tháng gần nhất ạ",
    "Dạ lãi suất vay tín chấp từ sáu phẩy năm phần trăm một năm ạ",
    "Dạ hạn mức cho vay lên đến năm trăm triệu đồng, thời hạn tối đa sáu mươi tháng",
    "Dạ số điện thoại của mình là không chín tám bốn hai một ba năm sáu bảy ạ",
]


def chuan_hoa(s: str) -> str:
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"[.,!?;:\"'()\[\]…-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cer(goc: str, nhan: str) -> float:
    a, b = chuan_hoa(goc), chuan_hoa(nhan)
    if not a:
        return 0.0
    truoc = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        sau = [i]
        for j, cb in enumerate(b, 1):
            sau.append(min(truoc[j] + 1, sau[j - 1] + 1, truoc[j - 1] + (ca != cb)))
        truoc = sau
    return truoc[-1] / len(a)


def doc_wav(b: bytes):
    import numpy as np
    with wave.open(io.BytesIO(b)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x.astype("float32") / 32768, sr


def ghi_wav(x, sr) -> bytes:
    import numpy as np
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def ha_8k(x, sr):
    import numpy as np
    n = int(len(x) / sr * 8000)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype("float32")


def qua_amr(wav8k: bytes) -> bytes:
    """Đẩy qua đúng codec AMR-NB 12.2kbps mà GSM dùng, rồi giải mã ngược."""
    with tempfile.TemporaryDirectory() as d:
        p_in = Path(d) / "in.wav"
        p_amr = Path(d) / "m.amr"
        p_out = Path(d) / "out.wav"
        p_in.write_bytes(wav8k)
        for cmd in (
            ["ffmpeg", "-y", "-i", str(p_in), "-ar", "8000", "-ac", "1",
             "-c:a", "libopencore_amrnb", "-b:a", "12.2k", str(p_amr)],
            ["ffmpeg", "-y", "-i", str(p_amr), "-ar", "8000", "-ac", "1", str(p_out)],
        ):
            r = subprocess.run(cmd, capture_output=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.decode("utf-8", "replace")[-300:])
        return p_out.read_bytes()


def nang_luong_theo_dai(x, sr):
    """Tỉ lệ năng lượng dưới/trên 4kHz - trên 4kHz là phần đường thoại vứt đi."""
    import numpy as np
    ph = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    tong = ph.sum() or 1e-12
    return {
        "dưới 300Hz": float(ph[f < 300].sum() / tong),
        "300Hz-3.4kHz (đường thoại giữ)": float(ph[(f >= 300) & (f < 3400)].sum() / tong),
        "3.4-4kHz": float(ph[(f >= 3400) & (f < 4000)].sum() / tong),
        "trên 4kHz (đường thoại VỨT)": float(ph[f >= 4000].sum() / tong),
    }


def main() -> int:
    import numpy as np
    import requests

    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--stt", default="http://127.0.0.1:8178")
    args = ap.parse_args()

    import asyncio

    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    tts.load()
    loop = asyncio.new_event_loop()
    sess = requests.Session()
    out = PROJECT / "logs" / "kenh_thoai"
    out.mkdir(parents=True, exist_ok=True)

    def nghe(wav: bytes, ten: str) -> str:
        try:
            r = sess.post(f"{args.stt}/inference",
                          files={"file": (ten, wav, "audio/wav")},
                          data={"language": "vi", "response_format": "json",
                                "temperature": "0"}, timeout=60)
            return r.json().get("text", "").strip()
        except Exception as e:
            return f"[STT lỗi: {e}]"

    print(f"{len(CAU_TEST)} câu x {args.runs} lượt, chấm CER ở ba mức suy giảm\n")
    print(f"{'câu':<6}{'lượt':<6}{'gốc 24kHz':>12}{'hạ 8kHz':>11}{'qua AMR-NB':>13}")
    print("-" * 50)

    gom = {"goc": [], "8k": [], "amr": []}
    dai = None

    for i, cau in enumerate(CAU_TEST, 1):
        for lan in range(1, args.runs + 1):
            w24 = loop.run_until_complete(tts.synthesize(cau, use_cache=False))
            x24, sr = doc_wav(w24)
            if dai is None:
                dai = nang_luong_theo_dai(x24, sr)

            w8 = ghi_wav(ha_8k(x24, sr), 8000)
            wamr = qua_amr(w8)

            (out / f"c{i}_{lan}_goc.wav").write_bytes(w24)
            (out / f"c{i}_{lan}_8k.wav").write_bytes(w8)
            (out / f"c{i}_{lan}_amr.wav").write_bytes(wamr)

            e = {
                "goc": cer(cau, nghe(w24, "a.wav")),
                "8k": cer(cau, nghe(w8, "a.wav")),
                "amr": cer(cau, nghe(wamr, "a.wav")),
            }
            for k, v in e.items():
                gom[k].append(v)
            print(f"{i:<6}{lan}/{args.runs:<4}{e['goc']*100:>11.1f}%"
                  f"{e['8k']*100:>10.1f}%{e['amr']*100:>12.1f}%")

    print("-" * 50)
    tb = {k: sum(v) / len(v) * 100 for k, v in gom.items()}
    print(f"{'TRUNG BÌNH':<12}{tb['goc']:>11.1f}%{tb['8k']:>10.1f}%{tb['amr']:>12.1f}%")

    print("\nNăng lượng của giọng F5-TTS theo dải tần:")
    for k, v in dai.items():
        print(f"  {k:<34} {v*100:5.1f}%")

    print("\nKết luận từ số liệu:")
    mat = dai["trên 4kHz (đường thoại VỨT)"] + dai["3.4-4kHz"]
    print(f"  - Đường thoại vứt {mat*100:.1f}% năng lượng (phần trên 3.4kHz).")
    print(f"  - CER tăng {tb['goc']:.1f}% -> {tb['amr']:.1f}% sau khi qua codec thật.")
    print(f"  Audio ba mức để nghe so sánh: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
