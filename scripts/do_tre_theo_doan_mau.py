"""Do do tre sinh tieng theo DO DAI DOAN MAU - cung cau, cung may.

Vi sao: ODE cua F5 chay tren CA doan mau chu khong chi phan can sinh
(`generated[:, ref_audio_len:, :]` - sinh ca roi cat bo phan ref). Nen doan mau
dai gap doi la moi luot deu nang them, VINH VIEN, khong chi luot dau.

Ngay 08-09 da doi giong mac dinh tu clip 2.21s sang clip 5.45s de chua am rac.
Script nay do xem cai gia phai tra la bao nhieu.

Do dung cach:
  - Ham nong truoc (torch.compile bien dich lai khi hinh dang doi -> luot dau
    cua MOI doan mau deu cham bat thuong, tinh vao la sai het).
  - Nhieu cau dai ngan khac nhau, lay trung vi chu khong lay trung binh.
  - Do ca ms/cau lan ms tren mot giay tieng ra (RTF) - cau dai thi lau hon la
    duong nhien, RTF moi so sanh duoc.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_tre_theo_doan_mau.py
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import torch                    # noqa: E402
import torchaudio               # noqa: E402

from backend.config import settings                                  # noqa: E402
from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

CAU = [
    "Dạ vâng anh chị.",
    "Lãi suất bên em từ bảy phẩy chín phần trăm một năm.",
    "Hạn mức tối đa năm trăm triệu, thời hạn vay lên tới sáu mươi tháng ạ.",
    "Dạ em chào anh chị, em gọi từ ngân hàng để tư vấn về khoản vay tín chấp ạ.",
]
GOC = Path("models/tts/ref_voices")


def nap(wav: Path, txt: Path, dev):
    w, s = torchaudio.load(str(wav))
    return w.to(dev), s, txt.read_text(encoding="utf-8", errors="replace").strip()


def do(svc, rw, rs, rt, sp, nfe, lan):
    from f5_tts.infer.utils_infer import infer_batch_process
    ms, rtf = [], []
    for i, c in enumerate(CAU * lan):
        t0 = time.perf_counter()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process(
                (rw, rs), rt, [c], svc._model, svc._vocoder,
                mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                device=svc._model.device))
        d = (time.perf_counter() - t0) * 1000
        giay = len(trim_silence(np.asarray(y), sr)) / sr
        if i >= len(CAU):          # bo vong dau: torch.compile con dang ham nong
            ms.append(d)
            rtf.append(d / max(giay, 1e-6))
    return float(np.median(ms)), float(np.median(rtf))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", type=int, default=4, help="so vong (vong dau bi bo)")
    a = ap.parse_args()

    svc = F5TTSService()
    svc.load()
    dev = svc._model.device
    nfe = settings.f5tts_nfe_step

    bo = [
        ("clip MOI  heu_c 5.45s sp0.90",
         GOC / "giong_heu.wav", GOC / "giong_heu.txt", 0.90),
        ("clip CU   2.21s      sp0.64",
         GOC / "giong_heu.wav.bak-20260809", GOC / "giong_heu.txt.bak-20260809", 0.64),
    ]

    print(f"\n  nfe {nfe}   moi cau do {a.lan-1} vong (bo vong ham nong)\n")
    print(f"  {'cau hinh':<32} {'doan mau':>9} {'ms/cau':>9} {'ms/giay tieng':>15}")
    print("  " + "-" * 70)

    ket = []
    for nhan, w, t, sp in bo:
        if not (w.exists() and t.exists()):
            print(f"  {nhan:<32} khong thay tep, bo qua")
            continue
        rw, rs, rt = nap(w, t, dev)
        dai = rw.shape[-1] / rs
        m, r = do(svc, rw, rs, rt, sp, nfe, a.lan)
        ket.append((nhan, dai, m, r))
        print(f"  {nhan:<32} {dai:>8.2f}s {m:>8.0f}ms {r:>14.0f}")

    print("  " + "-" * 70)
    if len(ket) == 2:
        moi, cu = ket[0], ket[1]
        dm = (moi[2] - cu[2]) / cu[2] * 100
        dr = (moi[3] - cu[3]) / cu[3] * 100
        print(f"\n  Doi clip lam {'CHAM' if dm > 0 else 'NHANH'} them {abs(dm):.0f}% moi cau"
              f" ({cu[2]:.0f} -> {moi[2]:.0f} ms)")
        print(f"  Tinh tren mot giay tieng ra: {'cham' if dr > 0 else 'nhanh'} "
              f"{abs(dr):.0f}%  ({cu[3]:.0f} -> {moi[3]:.0f} ms/giay)")
        print("\n  (ms/cau co the giam du ODE nang hon, vi speed 0.90 lam cau NGAN lai."
              "\n   Cot ms/giay tieng moi phan anh dung chi phi tinh toan.)")


if __name__ == "__main__":
    main()
