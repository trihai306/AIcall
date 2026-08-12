import asyncio, io, sys, hashlib
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf, torch
from backend.config import settings
from backend.services.tts_service import (F5TTSService, bo_dau_cau_cho_f5,
                                          thoi_luong_ep, trim_silence)
svc=F5TTSService(); svc.load()
ten=svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
rw,rs,rt=svc._voices[ten]; sp,nfe=svc.toc_do_cua(ten),settings.f5tts_nfe_step
from f5_tts.infer.utils_infer import infer_batch_process

print("\n  [1] CHU DUA VAO F5 sau khi qua bo_dau_cau_cho_f5")
for c in ["Dạ vâng ạ, em nghe.", "anh cứ yên tâm nhé.", "Được ạ, số điện thoại"]:
    print(f"      {c!r:<34} -> {bo_dau_cau_cho_f5(c)!r}")

print("\n  [2] SINH cung mot cau, CO dau va KHONG dau - co giong nhau khong")
print("      (F5 lay mau ngau nhien nen khong the trung khit; so DO DAI va nhip)")
torch.manual_seed(0)
def sinh(t, seed):
    torch.manual_seed(seed)
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        y,sr,_=next(infer_batch_process((rw,rs),rt,[bo_dau_cau_cho_f5(t)],
            svc._model,svc._vocoder,mel_spec_type="vocos",progress=None,
            nfe_step=nfe,speed=sp,
            fix_duration=thoi_luong_ep(t, rw.shape[-1]/rs, sp),
            device=svc._model.device))
    return trim_silence(np.asarray(y),sr), sr
for a,b in [("Dạ vâng ạ, em nghe rồi.", "Dạ vâng ạ em nghe rồi")]:
    ya,sr=sinh(a,7); yb,_=sinh(b,7)
    same = np.allclose(ya, yb, atol=1e-4) if len(ya)==len(yb) else False
    print(f"      {a!r}")
    print(f"      {b!r}")
    print(f"      dai {len(ya)/sr:.3f}s vs {len(yb)/sr:.3f}s   tieng TRUNG KHIT: {same}")

print("\n  [3] Quang lang BEN TRONG manh ket bang dau phay")
NG,KH=0.015,0.02
def lang(x,sr,tt=150):
    n=max(1,int(sr*KH)); k=len(x)//n
    to=np.abs(x[:k*n].reshape(k,n)).max(axis=1); im=to<NG; ra=[]; i=0
    while i<k:
        if im[i]:
            j=i
            while j<k and im[j]: j+=1
            if i>0 and j<k and (j-i)*20>=tt: ra.append((j-i)*20)
            i=j
        else: i+=1
    return ra
for c in ["Dạ vâng ạ, em nghe.", "anh cứ yên tâm nhé.", "hạn mức tối đa là,"]:
    y,sr=sinh(c,11)
    print(f"      {c!r:<28} lang>150ms ben trong: {lang(y,sr) or 'khong co'}")
