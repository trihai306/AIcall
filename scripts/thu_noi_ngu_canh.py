"""Cho F5 nghe lai MANH TRUOC de no noi tiep, thay vi mo dau lai tu dau.

Do duoc: cat manh xong thi F0 cuoi manh tut con 177-203 Hz roi dau manh sau vot
len 222-302 Hz - vot toi 118 Hz, trong khi sinh mot lan chi dao dong 20 Hz. Do la
vi F5 sinh MOI MANH DOC LAP nen manh nao cung co duong net "mo dau roi ket thuc".

Cach chua: doan mau cua manh N+1 = doan mau goc + TIENG cua manh N, va cau mau =
cau mau goc + CHU cua manh N. F5 thay minh dang o giua mot cau dai nen no noi
tiep, khong ha giong ket cau nua.

Gia phai tra: doan mau dai them ~1.2s moi manh -> ODE chay tren nhieu khung hon
-> sinh cham hon. Script do luon phan nay.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\thu_noi_ngu_canh.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import torch                    # noqa: E402
import librosa                  # noqa: E402

from backend.config import settings                                  # noqa: E402
from backend.pipeline.text_chunker import tach_manh                  # noqa: E402
from backend.services.tts_service import (                           # noqa: E402
    F5TTSService, bo_dau_cau_cho_f5, thoi_luong_ep, trim_silence,
)

RA = Path("C:/tmp/nguucanh")
CAU = ("Anh chị sẽ nhận được tiền trong vòng 24 giờ sau khi phê duyệt hồ sơ, "
       "bên em xử lý rất nhanh ạ")


def f0(x, sr):
    if len(x) < sr // 20:
        return 0.0
    try:
        f = librosa.yin(x.astype(np.float32), fmin=80, fmax=450, sr=sr)
    except Exception:
        return 0.0
    f = f[np.isfinite(f)]
    return float(np.median(f)) if len(f) else 0.0


def cat(van):
    ra, dem = [], ""
    for t in van.split():
        dem += " " + t
        m, dem = tach_manh(dem, first_chunk=(not ra))
        if m:
            ra.append(m)
    if dem.strip():
        ra.append(dem.strip())
    return ra


def main():
    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw0, rs, rt0 = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    from f5_tts.infer.utils_infer import infer_batch_process
    RA.mkdir(parents=True, exist_ok=True)

    manh_text = cat(CAU)
    print(f"\n  giọng {ten}   {len(manh_text)} mảnh\n")

    def sinh(text, rw, rs_, rt):
        t0 = time.perf_counter()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process(
                (rw, rs_), rt, [bo_dau_cau_cho_f5(text)], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                fix_duration=thoi_luong_ep(text, rw.shape[-1] / rs_, sp),
                device=svc._model.device))
        return trim_silence(np.asarray(y), sr), sr, (time.perf_counter() - t0) * 1000

    for nhan, noi_ngu_canh in (("KHÔNG nối ngữ cảnh", False),
                               ("CÓ nối mảnh trước", True)):
        wavs, ms = [], []
        rw, rt = rw0, rt0
        for c in manh_text:
            y, sr, t = sinh(c, rw, rs, rt)
            wavs.append(y)
            ms.append(t)
            if noi_ngu_canh:
                # Doan mau = goc + tieng manh vua sinh; cau mau = goc + chu do.
                # Phai noi CA HAI, lech mot ben la F5 uoc sai thoi luong.
                them = torch.from_numpy(y.copy()).to(rw0.device).unsqueeze(0)
                if them.shape[-1] != y.shape[-1]:
                    them = them.reshape(1, -1)
                rw = torch.cat([rw0, them], dim=-1)
                rt = rt0.rstrip() + " " + bo_dau_cau_cho_f5(c)
        vots = []
        n = int(sr * 0.2)
        for i in range(len(wavs) - 1):
            a, b = f0(wavs[i][-n:], sr), f0(wavs[i+1][:n], sr)
            if a > 0 and b > 0:
                vots.append(b - a)
        g = np.concatenate(wavs)
        p = RA / ("co_noi.wav" if noi_ngu_canh else "khong_noi.wav")
        sf.write(p, g / max(1.0, float(np.abs(g).max())), sr)
        print(f"  {nhan}")
        print(f"      vọt F0 tại chỗ nối : {[f'{v:+.0f}' for v in vots]}")
        if vots:
            print(f"      trung bình {np.mean(np.abs(vots)):>5.0f} Hz"
                  f"   lớn nhất {max(np.abs(vots)):>5.0f} Hz"
                  f"   số chỗ > 40Hz: {sum(1 for v in vots if abs(v) > 40)}/{len(vots)}")
        print(f"      sinh trung bình {np.mean(ms):>6.0f} ms/mảnh"
              f"   tổng {sum(ms)/1000:.2f}s\n")

    print(f"  wav ở {RA}")


if __name__ == "__main__":
    main()
