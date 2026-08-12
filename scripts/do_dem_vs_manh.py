import asyncio, io, json, re, sys, urllib.request
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf, torch
from backend.config import settings
from backend.services.filler_store import lay_kho
from backend.services.tts_service import F5TTSService, trim_silence
NG, KH = 0.015, 0.02
def ct(x, sr):
    n=max(1,int(sr*KH)); k=len(x)//n
    if k==0: return len(x)/sr
    to=np.abs(x[:k*n].reshape(k,n)).max(axis=1)
    return float((to>=NG).sum()*KH)
def at(s): return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])

svc=F5TTSService(); svc.load()
ten=svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
sp=svc.toc_do_cua(ten)
theo_id={c.id: c.text for c in lay_kho().cau}

print(f"\n  giong {ten}   speed dang dat {sp:.2f}\n")
# 1) nhip cua CAC TEP CAU DEM tren dia
nhip_dem=[]
for p in sorted((Path("data/fillers_wav")/ten).glob("*.wav")):
    cid=p.name.split("__")[0]
    goc=theo_id.get(cid)
    if not goc: continue
    x, sr = sf.read(p, dtype="float32")
    if x.ndim>1: x=x.mean(axis=1)
    g=ct(x,sr)
    if g>0.25 and at(goc)>=2: nhip_dem.append(at(goc)/g*60)
# 2) nhip cua tieng sinh MOI, cung nhung cau do
rw,rs,rt=svc._voices[ten]
from f5_tts.infer.utils_infer import infer_batch_process
nhip_moi=[]
for c in list(theo_id.values())[:14]:
    if at(c)<2: continue
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        y,sr,_=next(infer_batch_process((rw,rs),rt,[c],svc._model,svc._vocoder,
            mel_spec_type="vocos",progress=None,nfe_step=settings.f5tts_nfe_step,
            speed=sp,device=svc._model.device))
    y=trim_silence(np.asarray(y),sr); g=ct(y,sr)
    if g>0.25: nhip_moi.append(at(c)/g*60)

for nhan, v in (("TEP CAU DEM tren dia", nhip_dem), ("sinh MOI bay gio", nhip_moi)):
    if v:
        print(f"  {nhan:<24} n={len(v):<3} trung vi {np.median(v):>5.0f}"
              f"  khoang {min(v):>4.0f}-{max(v):<4.0f} am tiet/phut")
if nhip_dem and nhip_moi:
    d=np.median(nhip_dem); m=np.median(nhip_moi)
    print(f"\n  LECH GIUA HAI BEN: {(d-m)/m*100:+.0f}%"
          f"  {'  <== cau dem dung o TOC KHAC, moi luot deu nhay nhip' if abs(d-m)/m>0.12 else '  (khop)'}")
