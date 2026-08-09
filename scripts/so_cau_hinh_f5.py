"""Đo xem cấu hình nào của F5 cho giọng GIỐNG đoạn mẫu nhất.

Dự án đang lệch khỏi mặc định F5 ở ba chỗ cùng lúc:
    speed      0.64  (F5 mặc định 1.0)
    nfe_step   16    (F5 mặc định 32)
    độ chính xác fp16 autocast  (F5 gốc chạy fp32)

Script tách từng biến ra, mỗi lần chỉ đổi MỘT thứ, rồi đo độ giống đoạn mẫu.

Thước đo:
  - MFCC       : cosine giữa vector MFCC trung bình của đoạn mẫu và tiếng sinh ra.
                 Đây là thước đo âm sắc tiêu chuẩn. 1.00 = trùng khít.
  - Độ sáng    : trọng tâm phổ (Hz). Càng gần đoạn mẫu càng tốt.

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\so_cau_hinh_f5.py
    .venv\\python.exe scripts\\so_cau_hinh_f5.py --giong fosd_1
"""
import argparse
import asyncio
import sys
from contextlib import nullcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import torch                    # noqa: E402
import librosa                  # noqa: E402

from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

CAU = "Lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm"

# (nhãn, nfe, speed, dùng fp16)
CAU_HINH = [
    ("A  ĐANG CHẠY   nfe16 speed0.64 fp16", 16, 0.64, True),
    ("B  đổi nfe     nfe32 speed0.64 fp16", 32, 0.64, True),
    ("C  đổi speed   nfe16 speed1.00 fp16", 16, 1.00, True),
    ("D  đổi cả hai  nfe32 speed1.00 fp16", 32, 1.00, True),
    ("E  F5 GỐC      nfe32 speed1.00 fp32", 32, 1.00, False),
]


def dac_trung(x: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    """Trả (vector MFCC trung bình, trọng tâm phổ Hz)."""
    x = np.asarray(x, dtype=np.float32)
    if sr != 24000:
        x = librosa.resample(x, orig_sr=sr, target_sr=24000)
        sr = 24000
    # Bỏ hệ số 0 (chỉ là mức to), giữ 1..19 mang âm sắc.
    m = librosa.feature.mfcc(y=x, sr=sr, n_mfcc=20)[1:]
    tt = float(librosa.feature.spectral_centroid(y=x, sr=sr).mean())
    return m.mean(axis=1), tt


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giong", default=None)
    ap.add_argument("--lan", type=int, default=2, help="lặp mấy lần mỗi cấu hình")
    ap.add_argument("--ra", default="C:/tmp/socauhinh", help="thư mục xuất wav")
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = a.giong or svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]

    ref = rw.detach().cpu().numpy().squeeze() if torch.is_tensor(rw) else np.asarray(rw).squeeze()
    mfcc_ref, tt_ref = dac_trung(ref, rs)

    ra = Path(a.ra)
    ra.mkdir(parents=True, exist_ok=True)
    sf.write(ra / "00_doan_mau.wav", ref, rs)

    print(f"giọng     : {ten}")
    print(f"đoạn mẫu  : {len(ref)/rs:.2f}s   độ sáng {tt_ref:.0f} Hz")
    print(f"câu thử   : {CAU}\n")
    print(f"{'cấu hình':<38} {'MFCC':>6} {'độ sáng':>9} {'lệch':>7} {'giây':>6}")
    print("-" * 72)

    from f5_tts.infer.utils_infer import infer_batch_process
    import time

    ket = []
    for nhan, nfe, sp, fp16 in CAU_HINH:
        ds, tts, gs = [], [], []
        for i in range(a.lan):
            ctx = (torch.autocast("cuda", dtype=torch.float16)
                   if fp16 and str(svc._model.device).startswith("cuda")
                   else nullcontext())
            t0 = time.perf_counter()
            with torch.inference_mode(), ctx:
                x, sr, _ = next(infer_batch_process(
                    (rw, rs), rt, [CAU], svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None,
                    nfe_step=nfe, speed=sp, device=svc._model.device))
            gs.append(time.perf_counter() - t0)
            x = trim_silence(np.asarray(x), sr)
            m, tt = dac_trung(x, sr)
            ds.append(cosine(mfcc_ref, m))
            tts.append(tt)
            if i == 0:
                sf.write(ra / f"{nhan[0]}_nfe{nfe}_sp{sp}_{'fp16' if fp16 else 'fp32'}.wav",
                         x / max(1.0, float(np.abs(x).max())), sr)
        d, t, g = np.mean(ds), np.mean(tts), np.mean(gs)
        ket.append((nhan, d, t, g))
        print(f"{nhan:<38} {d:>6.3f} {t:>7.0f}Hz {t-tt_ref:>+7.0f} {g:>6.2f}")

    print("-" * 72)
    tot = max(ket, key=lambda r: r[1])
    hien = ket[0]
    print(f"\n  GIỐNG NHẤT : {tot[0]}   MFCC {tot[1]:.3f}")
    print(f"  đang chạy  : {hien[0]}   MFCC {hien[1]:.3f}")
    if tot[1] > hien[1]:
        print(f"\n  => đổi cấu hình cải thiện {(tot[1]-hien[1])/abs(hien[1])*100:+.1f}% độ giống,"
              f" chậm thêm {tot[3]-hien[3]:.2f}s/câu")
    else:
        print("\n  => cấu hình đang chạy đã là tốt nhất trong nhóm thử")
    print(f"\n  wav ở {ra}")


if __name__ == "__main__":
    main()
