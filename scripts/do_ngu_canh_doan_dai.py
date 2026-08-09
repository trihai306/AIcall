"""Do noi ngu canh tren DOAN DAI - du mau de ket luan.

Ban do truoc chi co 4 cho noi, khong du de phan biet cai thien that voi may man.
Doan nay dai gap 5 lan, cho ~25 cho noi.

Do gi: F0 (cao do) o 200ms CUOI manh N va 200ms DAU manh N+1. F5 sinh moi manh
doc lap nen manh nao cung ha giong o cuoi roi vao cao o dau - do la thu nguoi
dung nghe thay "tu ha tram roi noi cao len".

Ba ban:
    moc chuan  - sinh MOT LAN ca doan, khong co cho noi nao
    khong noi  - cat manh nhu dang chay
    co noi     - doan mau cua manh N+1 = doan mau goc + tieng manh N

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_ngu_canh_doan_dai.py
    .venv\\python.exe scripts\\do_ngu_canh_doan_dai.py --giu 2   (nho 2 manh truoc)
"""
import argparse
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

RA = Path("C:/tmp/ngucanhdai")

VAN = (
    "Dạ em chào anh chị, em gọi từ ngân hàng để tư vấn về gói vay tín chấp dành "
    "cho khách hàng có thu nhập ổn định. Anh chị sẽ nhận được tiền trong vòng "
    "24 giờ sau khi phê duyệt hồ sơ, bên em xử lý rất nhanh ạ. Lãi suất áp dụng "
    "từ bảy phẩy chín phần trăm một năm, tính trên dư nợ giảm dần nên càng về "
    "sau tiền lãi càng ít đi. Hạn mức tối đa là năm trăm triệu đồng, thời hạn "
    "vay linh hoạt từ mười hai đến sáu mươi tháng tuỳ theo nhu cầu của anh chị. "
    "Hồ sơ chỉ cần chứng minh nhân dân, sổ hộ khẩu và sao kê lương ba tháng gần "
    "nhất, không cần thế chấp tài sản gì cả. Anh chị cho em xin ít phút để em "
    "tư vấn kỹ hơn được không ạ."
)


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


def thong_ke(vots, nhan):
    if not vots:
        print(f"  {nhan}: không đo được")
        return
    v = np.abs(vots)
    print(f"  {nhan:<22} {np.mean(v):>7.0f} {np.median(v):>9.0f} {max(v):>8.0f}"
          f" {sum(1 for x in v if x > 40):>6}/{len(v)}"
          f" {sum(1 for x in v if x > 80):>6}/{len(v)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giu", type=int, default=1,
                    help="nhớ mấy mảnh trước làm ngữ cảnh")
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw0, rs, rt0 = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    from f5_tts.infer.utils_infer import infer_batch_process
    RA.mkdir(parents=True, exist_ok=True)

    manh_text = cat(VAN)
    print(f"\n  giọng {ten}   {len(VAN.split())} từ -> {len(manh_text)} mảnh"
          f" -> {len(manh_text)-1} chỗ nối   (nhớ {a.giu} mảnh)\n")

    def sinh(text, rw, rt):
        t0 = time.perf_counter()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [bo_dau_cau_cho_f5(text)], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                fix_duration=thoi_luong_ep(text, rw.shape[-1] / rs, sp),
                device=svc._model.device))
        return trim_silence(np.asarray(y), sr), sr, (time.perf_counter() - t0) * 1000

    # --- moc chuan: sinh mot lan -----------------------------------------
    t0 = time.perf_counter()
    x1, sr, _ = sinh(VAN, rw0, rt0)
    ms1 = (time.perf_counter() - t0) * 1000
    sf.write(RA / "00_mot_lan.wav", x1 / max(1.0, float(np.abs(x1).max())), sr)
    n = int(sr * 0.2)
    # Doi chieu: F0 tai cac moc chia deu trong ban sinh mot lan
    buoc = len(x1) // max(len(manh_text), 1)
    chuan = []
    for i in range(1, len(manh_text)):
        a_, b_ = f0(x1[max(0, i*buoc - n):i*buoc], sr), f0(x1[i*buoc:i*buoc + n], sr)
        if a_ > 0 and b_ > 0:
            chuan.append(b_ - a_)

    print(f"  {'bản':<22} {'|vọt| TB':>7} {'trung vị':>9} {'lớn nhất':>8}"
          f" {'>40Hz':>7} {'>80Hz':>7}")
    print("  " + "-" * 66)
    thong_ke(chuan, "sinh MỘT LẦN (mốc)")

    for nhan, giu in (("cắt mảnh, KHÔNG nối", 0), (f"CÓ nối {a.giu} mảnh", a.giu)):
        wavs, ms, lich_su = [], [], []
        for c in manh_text:
            if giu and lich_su:
                dung = lich_su[-giu:]
                them = torch.from_numpy(
                    np.concatenate([w for w, _ in dung]).copy()
                ).to(rw0.device).reshape(1, -1)
                rw = torch.cat([rw0, them], dim=-1)
                rt = rt0.rstrip() + " " + " ".join(bo_dau_cau_cho_f5(t) for _, t in dung)
            else:
                rw, rt = rw0, rt0
            y, sr, t = sinh(c, rw, rt)
            wavs.append(y)
            ms.append(t)
            lich_su.append((y, c))
        vots = []
        for i in range(len(wavs) - 1):
            a_, b_ = f0(wavs[i][-n:], sr), f0(wavs[i+1][:n], sr)
            if a_ > 0 and b_ > 0:
                vots.append(b_ - a_)
        g = np.concatenate(wavs)
        ten_tep = "01_khong_noi.wav" if not giu else f"02_co_noi_{giu}.wav"
        sf.write(RA / ten_tep, g / max(1.0, float(np.abs(g).max())), sr)
        thong_ke(vots, nhan)
        print(f"  {'':22} sinh {np.mean(ms):.0f} ms/mảnh, tổng {sum(ms)/1000:.2f}s")

    print("  " + "-" * 66)
    print(f"\n  sinh một lần cả đoạn: {ms1/1000:.2f}s (để đối chiếu chi phí)")
    print(f"  Tai nghe ra bước nhảy cao độ từ khoảng 30-40 Hz.")
    print(f"\n  wav ở {RA}")


if __name__ == "__main__":
    main()
