"""Gia co dinh moi lan goi F5 co ti le voi DO DAI DOAN MAU khong?

Gia thuyet: F5 sinh ca doan mau kem cau dich moi lan roi vut di, nen doan mau
cang dai thi moi manh cang ton - va voi manh 5 tu thi cai gia do tra 50 lan.

Do thoi gian THUAN TUY: cat doan mau ngan dan, giu nguyen cau dich va phan sinh.
Tieng ra se HONG (loi mau khong con khop) - khong sao, day la phep do CHI PHI.
"""
import asyncio, sys, time, statistics as st
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, torch
from backend.config import settings
from backend.services import tts_service as T
from f5_tts.infer.utils_infer import infer_batch_process

CAU = "anh cần chuẩn bị chứng minh nhân dân"
LAP = 5

async def main():
    svc = T.F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    rw, rs, rt = svc._voices[ten]; sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
    goc = rw.shape[-1] / rs
    print(f"\n  doan mau hien tai: {goc:.2f}s")
    print(f"\n  {'mẫu':>7} {'sinh':>8} {'so voi 5.45s':>14}")
    print("  " + "-"*34)
    mo = None
    for ti in (1.0, 0.8, 0.6, 0.4):
        n = int(rw.shape[-1] * ti)
        rw2 = rw[..., :n]; dai = n / rs
        fix = dai + 1.6           # phan sinh giu nguyen 1.6s o moi muc
        t = []
        for _ in range(LAP + 1):
            t0 = time.perf_counter()
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                next(infer_batch_process((rw2, rs), rt, [CAU], svc._model, svc._vocoder,
                     mel_spec_type="vocos", progress=None, nfe_step=nfe, speed=sp,
                     fix_duration=fix, device=svc._model.device))
            t.append((time.perf_counter() - t0) * 1000)
        ms = st.median(t[1:])     # bo lan dau (nguoi)
        if mo is None: mo = ms
        print(f"  {dai:>6.2f}s {ms:>7.0f}ms {ms/mo*100:>13.0f}%")
    print("  " + "-"*34)
asyncio.run(main())
