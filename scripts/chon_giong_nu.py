"""Kho có những giọng nào, nam hay nữ, và nghe ra sao qua đường thoại?

Tên file không cho biết giọng nam hay nữ ("giong_heu", "fosd_1"...), mà nghe thử
từng cái thì mất công. Script đo CAO ĐỘ CƠ BẢN của chính file giọng mẫu để phân
loại, rồi dựng cùng một câu chào bằng mọi giọng NỮ, xuất bản đã qua kênh thoại
để nghe mà chọn.

    python scripts/chon_giong_nu.py
    python scripts/chon_giong_nu.py --moc-nu 165
"""

import argparse
import asyncio
import io
import statistics
import sys
import wave
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RA = PROJECT / "logs" / "chon_giong"
CAU = ("Dạ em chào anh chị ạ. Em là nhân viên tư vấn của ngân hàng ABC, "
       "em gọi để giới thiệu chương trình vay ưu đãi ạ.")


def f0(x: np.ndarray, sr: int) -> float:
    """Cao độ cơ bản trung vị (Hz) bằng tự tương quan trên khung hữu thanh."""
    N = int(0.04 * sr)
    lo, hi = int(sr / 320), int(sr / 60)
    ra = []
    for i in range(0, max(0, len(x) - N), N // 2):
        k = x[i:i + N]
        if np.sqrt((k ** 2).mean()) < 0.02:
            continue
        k = k - k.mean()
        r = np.correlate(k, k, mode="full")[N - 1:]
        if r[0] <= 0:
            continue
        vung = r[lo:hi]
        if vung.size == 0:
            continue
        d = int(np.argmax(vung)) + lo
        if r[d] / r[0] < 0.3:
            continue
        ra.append(sr / d)
    return float(statistics.median(ra)) if ra else 0.0


def doc_wav(p: Path):
    with wave.open(str(p)) as w:
        sr, nc = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    x = x.astype(np.float32) / 32768
    return (x.reshape(-1, nc).mean(axis=1) if nc > 1 else x), sr


def ghi(p: Path, x: np.ndarray, sr: int):
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--moc-nu", type=float, default=165.0,
                    help="Hz; trên mức này coi là giọng nữ")
    a = ap.parse_args()

    from backend.config import settings
    from backend.services import phone_call_service as PS
    from backend.services.audio_utils import resample_audio
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import lay_bo_ma_amr

    tts = F5TTSService(); tts.load()
    ds = tts.list_voices()
    dang_dung = Path(settings.f5tts_ref_audio).stem

    print(f"\n  giọng đang dùng: {dang_dung}\n")
    print(f"  {'giọng':<14}{'dài':>7}{'F0':>8}{'phân loại':>12}  lời mẫu")
    print("  " + "-" * 84)
    nu = []
    for v in ds:
        p = Path(v["wav_path"])
        if not p.exists():
            continue
        x, sr = doc_wav(p)
        h = f0(x, sr)
        loai = "NỮ" if h >= a.moc_nu else ("nam" if h else "?")
        if loai == "NỮ" and v["ref_text"]:
            nu.append(v["name"])
        dau = " <-" if v["name"] == dang_dung else "   "
        print(f"  {v['name']:<14}{v.get('duration', 0):>6.1f}s{h:>7.0f}"
              f"{loai:>11}{dau} {v['ref_text'][:38]!r}")

    if not nu:
        print(f"\n  không thấy giọng nào trên {a.moc_nu:.0f}Hz")
        return 1

    print(f"\n  Dựng câu chào bằng {len(nu)} giọng nữ: {', '.join(nu)}")
    RA.mkdir(parents=True, exist_ok=True)
    for f in RA.glob("*"):
        f.unlink()
    qua_amr, _ = lay_bo_ma_amr()

    for ten in nu:
        that = await tts.ensure_voice(ten)
        if that != ten:
            print(f"    {ten}: không nạp được, bỏ qua")
            continue
        wav = await tts.synthesize(CAU, voice=ten, use_cache=False)
        with wave.open(io.BytesIO(wav)) as w:
            sr = w.getframerate()
            x = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                 .astype(np.float32) / 32768)
        y8 = resample_audio(PS.chuan_muc_thoai(x), sr, 8000)
        if settings.phone_tang_tuan_hoan:
            y8 = PS.tang_tuan_hoan(y8, 8000)
        ghi(RA / f"{ten}_qua_dien_thoai.wav", qua_amr(y8), 8000)
        print(f"    {ten}: F0 đọc ra {f0(x, sr):.0f}Hz")

    print(f"\n  {RA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
