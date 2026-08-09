"""Chia manh NHO co giup khong, va co GOM ME sinh nhieu manh mot luot duoc khong.

Hai cau hoi cua nguoi dung, deu dung cho va deu chua tung do:

  1. "sao khong tao 5 tu 1, 5 tu 1 thi lam sao dut duoc"
  2. "co cach nao tao song song duoc khong phan voice"

Nghi van ve (1): ODE cua F5 chay tren CA doan mau lan phan sinh ra
(`generated[:, ref_audio_len:, :]` - sinh het roi moi cat bo phan ref). Doan mau
dang la 5.4 giay. Neu dung thi sinh 5 tu ton GAN BANG sinh 40 tu, vi phan lon
cong viec la o doan mau. Chia nho => tra phi doan mau nhieu lan => TE HON.

Ve (2): F5 khong an toan da luong (da do truoc day), nhung `infer_batch_process`
nhan mot DANH SACH text. Neu no gom thanh mot me tren GPU thi do la cach song
song dung - mot lan tra phi doan mau cho N manh.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_manh_nho_va_gom_me.py
"""
import asyncio
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import torch                    # noqa: E402

from backend.config import settings                                  # noqa: E402
from backend.services.tts_service import F5TTSService, trim_silence  # noqa: E402

NEN = ("Dạ vâng ạ với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức "
       "lên đến năm trăm triệu đồng thời hạn vay linh hoạt từ mười hai đến sáu mươi "
       "tháng và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm ạ").split()

# Bon manh rieng biet, dung de thu gom me
ME = [
    "Dạ em chào anh chị ạ.",
    "Lãi suất bên em từ bảy phẩy chín phần trăm một năm.",
    "Hạn mức tối đa năm trăm triệu đồng ạ.",
    "Anh chị cho em xin ít phút được không ạ?",
]


def main():
    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    rw, rs, rt = svc._voices[ten]
    sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    dai_ref = rw.shape[-1] / rs
    from f5_tts.infer.utils_infer import infer_batch_process

    def sinh(texts, lan=1):
        ms, giay = [], []
        for _ in range(lan):
            t0 = time.perf_counter()
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                ra = list(infer_batch_process(
                    (rw, rs), rt, texts, svc._model, svc._vocoder,
                    mel_spec_type="vocos", progress=None, nfe_step=nfe,
                    speed=sp, device=svc._model.device))
            ms.append((time.perf_counter() - t0) * 1000)
            tong = 0.0
            for y, sr, _ in ra:
                tong += len(trim_silence(np.asarray(y), sr)) / sr
            giay.append(tong)
        return st.median(ms), st.median(giay), len(ra)

    sinh(["Hâm nóng máy cho ổn định."], 2)      # ham nong torch.compile

    print(f"\n  giong {ten}   doan mau {dai_ref:.2f}s   speed {sp:.2f}   nfe {nfe}\n")

    # ---- (1) manh nho co nhanh hon ti le khong ---------------------------
    print("  [1] THOI GIAN SINH THEO DO DAI MANH")
    print(f"      {'số từ':>6} {'giây tiếng':>11} {'sinh':>8} {'ms/từ':>8}  nhận xét")
    print("      " + "-" * 62)
    goc = None
    for n in (5, 10, 20, 40):
        c = " ".join(NEN[:n])
        m, g, _ = sinh([c], 3)
        if goc is None:
            goc = m
        print(f"      {n:>6} {g:>10.2f}s {m:>7.0f}ms {m/n:>7.0f}"
              f"   {'gốc' if n == 5 else f'{m/goc:.2f}x so với 5 từ'}")

    m5 = sinh([" ".join(NEN[:5])], 3)[0]
    m40 = sinh([" ".join(NEN[:40])], 3)[0]
    print(f"\n      Sinh 40 từ một lượt : {m40:.0f}ms")
    print(f"      Sinh 8 mảnh 5 từ    : {m5*8:.0f}ms  ({m5*8/m40:.1f} lần)")
    print("      => chia nhỏ TỐN HƠN đúng bằng số lần phải trả phí đoạn mẫu.")

    # ---- (2) gom me ------------------------------------------------------
    print("\n  [2] GOM ME - sinh nhieu manh trong MOT lan goi")
    print(f"      {'cách':<28} {'sinh':>9} {'giây tiếng':>12} {'ms/giây':>9}")
    print("      " + "-" * 62)
    tong_rieng, tong_giay = 0.0, 0.0
    for c in ME:
        m, g, _ = sinh([c], 2)
        tong_rieng += m
        tong_giay += g
    print(f"      {'4 lần gọi riêng':<28} {tong_rieng:>7.0f}ms {tong_giay:>11.2f}s"
          f" {tong_rieng/max(tong_giay,1e-9):>8.0f}")

    m, g, so = sinh(ME, 2)
    print(f"      {'1 lần gọi, gom 4 mảnh':<28} {m:>7.0f}ms {g:>11.2f}s"
          f" {m/max(g,1e-9):>8.0f}")
    print(f"\n      Số mảnh trả về khi gom mẻ: {so}"
          f"  {'(GOM DUOC)' if so == len(ME) else '(KHONG gom duoc - no noi lien)'}")
    if so == len(ME) and tong_rieng > 0:
        print(f"      Gom mẻ nhanh hơn {tong_rieng/max(m,1e-9):.2f} lần")
    print()


if __name__ == "__main__":
    main()
