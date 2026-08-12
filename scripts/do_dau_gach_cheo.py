"""Dau '/' va '()' con sot lai co lam F5 chen quang nghi khong.

bo_dau_cau_cho_f5 chi bo [,.;:!?...] - gach cheo, ngoac, gach ngang deu di
thang vao F5. LLM viet "Anh/chi" o hau het cau, nen neu dau nay sinh nghi thi
no ban vao GAN NHU MOI luot.

Doi chung: cung mot cau, chi khac dau. 3 lan moi ban.
"""
import sys, statistics as st
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, torch, asyncio
from backend.config import settings
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services import tts_service as T
from f5_tts.infer.utils_infer import infer_batch_process

CAP = [
 ("Anh/chị cần đáp ứng các điều kiện như công dân Việt Nam từ 22 đến 60 tuổi",
  "Anh chị cần đáp ứng các điều kiện như công dân Việt Nam từ 22 đến 60 tuổi"),
 ("Anh/chị cũng sẽ được giải ngân trong vòng hai mươi bốn giờ làm việc",
  "Anh chị cũng sẽ được giải ngân trong vòng hai mươi bốn giờ làm việc"),
 ("Hồ sơ gồm giấy tờ tùy thân (nếu là người lao động) và sao kê lương",
  "Hồ sơ gồm giấy tờ tùy thân nếu là người lao động và sao kê lương"),
 ("Anh chuẩn bị CMND/CCCD và hộ khẩu hoặc KT3 giúp em nhé",
  "Anh chuẩn bị CMND CCCD và hộ khẩu hoặc KT3 giúp em nhé"),
]
LAP = 3
svc = T.F5TTSService(); svc.load()
ten = svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
rw, rs, rt = svc._voices[ten]; sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
dai_ref = rw.shape[-1] / rs

def do(chu):
    n = normalize_for_tts(chu)
    f5 = T.bo_dau_cau_cho_f5(n)
    fix = T.thoi_luong_ep(f5, dai_ref, sp)
    im, sq = [], []
    for _ in range(LAP):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y, sr, _ = next(infer_batch_process((rw, rs), rt, [f5], svc._model,
                svc._vocoder, mel_spec_type="vocos", progress=None, nfe_step=nfe,
                speed=sp, fix_duration=fix, device=svc._model.device))
        y = T.trim_silence(np.asarray(y), sr)
        h = max(1, int(sr*0.01)); k = len(y)//h
        e = np.convolve(np.array([float(np.sqrt((y[i*h:(i+1)*h]**2).mean()))
                                  for i in range(k)]), np.ones(3)/3, mode="same")
        ng = max(e.max()*0.06, 3e-4); co = np.nonzero(e > ng)[0]
        t = d = 0
        if len(co) >= 5:
            d0, d1 = int(co[0]), int(co[-1]); i = d0
            while i < d1:
                if e[i] <= ng:
                    j = i
                    while j < d1 and e[j] <= ng: j += 1
                    if (j-i)*10 >= 120: t += (j-i)*10; d += 1
                    i = j
                else: i += 1
        im.append(t); sq.append(d)
    return st.mean(im), st.mean(sq), f5

print(f"\n  {LAP} lan moi ban\n")
print(f"  {'':<8} {'im giua':>8} {'quang':>6}   chu vao F5")
print("  " + "-" * 72)
co_d, khong = [], []
for a, b in CAP:
    for nhan, cau, kho in (("CÓ dấu", a, co_d), ("BỎ dấu", b, khong)):
        t, d, f5 = do(cau); kho.append(t)
        print(f"  {nhan:<8} {t:>6.0f}ms {d:>6.1f}   {f5[:46]}")
    print()
print("  " + "-" * 72)
print(f"\n  CÓ dấu / ( ) : trung binh {st.mean(co_d):.0f}ms im lang moi manh")
print(f"  BỎ dấu       : trung binh {st.mean(khong):.0f}ms")
print(f"  chenh        : {st.mean(co_d) - st.mean(khong):+.0f}ms moi manh")
