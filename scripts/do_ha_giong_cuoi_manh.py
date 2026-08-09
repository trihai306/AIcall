"""Manh co bi HA GIONG KET CAU o cuoi khong - do sao cho khu duoc thanh dieu.

Ban do truoc SAI: no so F0 cua 200ms cuoi manh N voi 200ms dau manh N+1, roi goi
chenh lech do la "vot". Nhung TIENG VIET CO THANH DIEU - cao do doi o moi am tiet
theo dau sac/huyen/nang. Hai cua so 200ms bat ky luon lech nhau 30-50Hz du chang
co loi gi. Bang chung: ban sinh MOT LAN, khong he co cho noi, cung "vot" 40Hz
trung binh y het ban cat manh.

Cach do khu duoc thanh dieu: so cuoi manh voi CHINH GIUA manh do.
    ha = F0(200ms cuoi manh) - F0(trung vi ca manh)
Cung mot manh nen cung phan bo thanh dieu. Neu F5 that su "ha giong ket cau" o
cuoi moi manh thi so nay am MOT CACH HE THONG. Ban sinh mot lan lam moc: cung
tinh nhu the tai cac vi tri tuong duong, ky vong quanh 0.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_ha_giong_cuoi_manh.py
"""
import asyncio
import sys
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

VAN = (
    "Dạ em chào anh chị, em gọi từ ngân hàng để tư vấn về gói vay tín chấp dành "
    "cho khách hàng có thu nhập ổn định. Anh chị sẽ nhận được tiền trong vòng "
    "24 giờ sau khi phê duyệt hồ sơ, bên em xử lý rất nhanh ạ. Lãi suất áp dụng "
    "từ bảy phẩy chín phần trăm một năm, tính trên dư nợ giảm dần nên càng về "
    "sau tiền lãi càng ít đi. Hạn mức tối đa là năm trăm triệu đồng, thời hạn "
    "vay linh hoạt từ mười hai đến sáu mươi tháng tuỳ theo nhu cầu của anh chị."
)


def f0_day(x, sr):
    if len(x) < sr // 20:
        return np.array([])
    try:
        f = librosa.yin(x.astype(np.float32), fmin=80, fmax=450, sr=sr)
    except Exception:
        return np.array([])
    return f[np.isfinite(f)]


def tv(x, sr):
    f = f0_day(x, sr)
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
    rw, rs, rt = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    from f5_tts.infer.utils_infer import infer_batch_process

    def sinh(text):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [bo_dau_cau_cho_f5(text)], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                fix_duration=thoi_luong_ep(text, rw.shape[-1] / rs, sp),
                device=svc._model.device))
        return trim_silence(np.asarray(y), sr), sr

    manh_text = cat(VAN)
    print(f"\n  giọng {ten}   {len(VAN.split())} từ -> {len(manh_text)} mảnh\n")

    # --- cat manh: ha giong o cuoi TUNG manh ------------------------------
    ha_manh = []
    for c in manh_text:
        y, sr = sinh(c)
        n = int(sr * 0.2)
        if len(y) < 3 * n:
            continue
        cuoi, giua = tv(y[-n:], sr), tv(y, sr)
        if cuoi > 0 and giua > 0:
            ha_manh.append(cuoi - giua)

    # --- sinh mot lan: cung phep tinh tai vi tri tuong duong ---------------
    x1, sr = sinh(VAN)
    n = int(sr * 0.2)
    buoc = len(x1) // max(len(manh_text), 1)
    ha_mot = []
    for i in range(1, len(manh_text) + 1):
        het = min(i * buoc, len(x1))
        doan = x1[max(0, het - buoc):het]
        if len(doan) < 3 * n:
            continue
        cuoi, giua = tv(doan[-n:], sr), tv(doan, sr)
        if cuoi > 0 and giua > 0:
            ha_mot.append(cuoi - giua)

    print(f"  {'bản':<26} {'hạ TB':>8} {'trung vị':>9} {'số lượt hạ':>12}")
    print("  " + "-" * 60)
    for nhan, v in (("sinh MỘT LẦN (mốc)", ha_mot), ("cắt mảnh", ha_manh)):
        if not v:
            print(f"  {nhan:<26} không đo được")
            continue
        am = sum(1 for x in v if x < -10)
        print(f"  {nhan:<26} {np.mean(v):>+7.0f} {np.median(v):>+8.0f}"
              f" {am:>9}/{len(v)}")
    print("  " + "-" * 60)
    print("\n  'hạ' = F0 200ms cuối TRỪ F0 trung vị của chính đoạn đó.")
    print("  Cùng một đoạn nên cùng phân bố thanh điệu - khử được thanh.")
    print("  Âm nhiều VÀ âm hơn hẳn bản sinh một lần = đúng là hạ giọng kết câu.")
    print("  Hai bên xấp xỉ nhau = cắt mảnh KHÔNG gây hạ giọng.")


if __name__ == "__main__":
    main()
