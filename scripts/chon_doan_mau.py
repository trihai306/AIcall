"""Chọn đoạn mẫu + tốc độ cho giọng AI GIỐNG người thật nhất.

Gốc rễ tìm được ngày 2026-08-09:

  F5 chép ĐÚNG âm sắc — MFCC 0.992 với chính nó, 0.73 với người khác. Không hề
  có chuyện "F5 không clone được". Nhưng MFCC lấy trung bình theo thời gian nên
  MÙ với nhịp điệu, mà tai người đánh giá "có giống không" chủ yếu bằng nhịp.

  giong_heu nói 297 âm tiết/phút, nhanh nhất trong 15 giọng (các giọng khác
  ~190). Hệ thống ép speed=0.64 để kéo về 186 cho hợp telesales, tức bắt F5
  chạy ở 63% nhịp gốc. Cùng chất giọng, sai nhịp 37% => nghe ra người khác.

Cách chữa: chọn clip có NHỊP GỐC gần nhịp cần, rồi để speed sát 1.0. Script này
tính speed cho từng clip, sinh tiếng, đo lại, và xuất wav để nghe.

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\chon_doan_mau.py
    .venv\\python.exe scripts\\chon_doan_mau.py --nhip 200
"""
import argparse
import asyncio
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402
import torch                    # noqa: E402
import librosa                  # noqa: E402

from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

CAU = "Lãi suất vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm"
DAU = "lãi suất"
STT = "http://127.0.0.1:8178/inference"
RA = Path("C:/tmp/chondoanmau")
UNG_VIEN = ["giong_heu", "heu_a", "heu_b", "heu_c", "heu_d", "heu_e"]


def am_tiet(s: str) -> int:
    return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])


def mfcc(x, sr):
    x = np.asarray(x, dtype=np.float32)
    if sr != 24000:
        x = librosa.resample(x, orig_sr=sr, target_sr=24000)
    return librosa.feature.mfcc(y=x, sr=24000, n_mfcc=20)[1:].mean(axis=1)


def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def nghe_lai(x, sr) -> str:
    """Cho STT nghe lại tiếng AI. Đây là phép duy nhất bắt được âm rác ở đầu."""
    b = io.BytesIO()
    sf.write(b, x, sr, format="WAV", subtype="PCM_16")
    bd = b"----x"
    body = (b"--" + bd + b"\r\nContent-Disposition: form-data; name=\"file\"; "
            b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
            + b.getvalue() + b"\r\n--" + bd + b"--\r\n")
    r = urllib.request.Request(
        STT, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=----x"})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=180).read()).get("text", "").strip()
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nhip", type=float, default=190,
                    help="nhịp muốn AI nói, âm tiết/phút (mặc định 190)")
    ap.add_argument("--lan", type=int, default=3)
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    from f5_tts.infer.utils_infer import infer_batch_process

    RA.mkdir(parents=True, exist_ok=True)
    thu_muc = Path("models/tts/ref_voices")
    n_cau = am_tiet(CAU)

    print(f"\n  Nhịp muốn có: {a.nhip:.0f} âm tiết/phút\n")
    print(f"  {'clip':<12} {'nhịp gốc':>9} {'speed':>6} {'% gốc':>6} "
          f"{'MFCC':>6} {'rác':>5} {'tràn':>5} {'nhịp ra':>8}")
    print("  " + "-" * 72)

    ket = []
    for ten in UNG_VIEN:
        w = thu_muc / f"{ten}.wav"
        t = thu_muc / f"{ten}.txt"
        if not (w.exists() and t.exists()):
            continue
        x0, sr0 = sf.read(w)
        if x0.ndim > 1:
            x0 = x0.mean(axis=1)
        giay = len(trim_silence(np.asarray(x0, dtype=np.float32), sr0)) / sr0
        goc = am_tiet(t.read_text(encoding="utf-8")) / giay * 60
        sp = round(min(1.0, a.nhip / goc), 2)

        try:
            asyncio.run(svc.ensure_voice(ten))
        except Exception as e:
            print(f"  {ten:<12} bỏ qua: {e}")
            continue
        rw, rs, rt = svc._voices[ten]
        m_ref = mfcc(rw.detach().cpu().numpy().squeeze() if torch.is_tensor(rw)
                     else np.asarray(rw), rs)

        ds, rac, tran, nhips = [], 0, 0, []
        for i in range(a.lan):
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                y, sr, _ = next(infer_batch_process(
                    (rw, rs), rt, [CAU], svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None, nfe_step=32, speed=sp,
                    device=svc._model.device))
            y = np.asarray(y)
            tran += float(np.abs(y).max()) > 1.0
            y = trim_silence(y, sr)
            ds.append(cos(m_ref, mfcc(y, sr)))
            nhips.append(n_cau / (len(y) / sr) * 60)
            rac += not nghe_lai(y, sr).lower().startswith(DAU)
            if i == 0:
                sf.write(RA / f"{ten}_sp{sp:.2f}.wav",
                         y / max(1.0, float(np.abs(y).max())), sr)

        d, nr = float(np.mean(ds)), float(np.mean(nhips))
        ket.append((ten, goc, sp, d, rac, tran, nr))
        print(f"  {ten:<12} {goc:>9.0f} {sp:>6.2f} {sp/1.0*100:>5.0f}% "
              f"{d:>6.3f} {rac:>3}/{a.lan} {tran:>3}/{a.lan} {nr:>8.0f}")

    print("  " + "-" * 72)
    sach = [k for k in ket if k[4] == 0 and k[5] == 0]
    if sach:
        tot = max(sach, key=lambda k: k[2])   # speed cao nhất = ít bóp nhịp nhất
        print(f"\n  ĐỀ XUẤT: {tot[0]}  speed {tot[2]:.2f}  "
              f"(chạy ở {tot[2]*100:.0f}% nhịp gốc, MFCC {tot[3]:.3f}, sạch {a.lan}/{a.lan})")
        print(f"  Đang chạy: giong_heu speed 0.64 (chạy ở 64% nhịp gốc)")
    else:
        print("\n  Không clip nào sạch cả rác lẫn tràn — xem lại bản thu.")
    print(f"\n  wav ở {RA}  — nghe và so, con số chỉ để loại bớt, tai anh quyết.")


if __name__ == "__main__":
    main()
