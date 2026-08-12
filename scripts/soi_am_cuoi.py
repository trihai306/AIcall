import asyncio, io, sys
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf, torch
from pathlib import Path
from backend.config import settings
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services import tts_service as T
CAU = "Anh muốn vay tín chấp thì lãi suất sẽ là từ 7.9%/năm nha."
RA = Path(r"C:/tmp/soinha"); RA.mkdir(parents=True, exist_ok=True)
svc = T.F5TTSService(); svc.load()
ten = svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
rw, rs, rt = svc._voices[ten]; sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
from f5_tts.infer.utils_infer import infer_batch_process
n_chu = normalize_for_tts(CAU)
print(f"\n  chu vao F5 : {n_chu}")
print(f"  am tiet dem: {T.so_am_tiet(n_chu)}")
NG, KH = 0.015, 0.02
def am_cuoi(y, sr):
    """Do dai doan CO TIENG cuoi cung - chinh la chu 'nha' neu truoc no co nghi."""
    n=max(1,int(sr*KH)); k=len(y)//n
    co=np.abs(y[:k*n].reshape(k,n)).max(axis=1)>=NG
    i=k-1
    while i>=0 and not co[i]: i-=1
    j=i
    while j>=0 and co[j]: j-=1
    return (i-j)*KH*1000
print(f"\n  {'cach cap thoi luong':<24} {'cap':>7} {'ra':>7} {'am cuoi':>9}")
print("  "+"-"*54)
for nhan, he in (("hien tai (bu 1.11)", 1.11), ("bo bu (1.00)", 1.00),
                 ("bot 10% (0.90)", 0.90), ("khong ep", None)):
    fix = None
    if he is not None:
        cu = T.HE_SO_BU_LANG; T.HE_SO_BU_LANG = he
        fix = T.thoi_luong_ep(n_chu, rw.shape[-1]/rs, sp)
        T.HE_SO_BU_LANG = cu
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        y,sr,_ = next(infer_batch_process((rw,rs),rt,[T.bo_dau_cau_cho_f5(n_chu)],
            svc._model,svc._vocoder,mel_spec_type="vocos",progress=None,
            nfe_step=nfe,speed=sp,fix_duration=fix,device=svc._model.device))
    y = T.trim_silence(np.asarray(y), sr)
    cap = (fix - rw.shape[-1]/rs) if fix else 0
    sf.write(RA/f"{nhan.split()[0]}_{he or 'none'}.wav", y/max(1.0,float(np.abs(y).max())), sr)
    print(f"  {nhan:<24} {cap:>6.2f}s {len(y)/sr:>6.2f}s {am_cuoi(y,sr):>7.0f}ms")
print("  "+"-"*54)
print("\n  'am cuoi' = doan co tieng cuoi cung. Chu 'nha' ngan dai thi so nay to.")
