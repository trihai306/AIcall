import asyncio, io, sys
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf, torch
from pathlib import Path
from backend.config import settings
from backend.services import tts_service as T
CAU = ["bên em là từ bảy phẩy chín phần trăm một năm nhé.",
       "gần nhất ạ.", "để hỗ trợ nhé.", "phạt phí ạ.",
       "chúc anh một ngày tốt lành!", "hàng tháng là mười tám triệu hai trăm nghìn đồng"]
RA = Path(r"C:/tmp/ngan"); RA.mkdir(parents=True, exist_ok=True)
svc = T.F5TTSService(); svc.load()
ten = svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
rw, rs, rt = svc._voices[ten]; sp, nfe = svc.toc_do_cua(ten), settings.f5tts_nfe_step
from f5_tts.infer.utils_infer import infer_batch_process
NG, KH = 0.015, 0.02
def duoi_ngan(y, sr):
    """Do dai doan CO TIENG lien tuc o CUOI - am cuoi bi ngan thi doan nay dai."""
    n=max(1,int(sr*KH)); k=len(y)//n
    co=np.abs(y[:k*n].reshape(k,n)).max(axis=1)>=NG
    i=k-1
    while i>=0 and not co[i]: i-=1
    j=i
    while j>=0 and co[j]: j-=1
    return (i-j)*KH*1000
for he_so, nhan in ((1.11, "hien tai 1.11"), (1.00, "bo bu 1.00"), (None, "khong ep")):
    ws, duoi = [], []
    for c in CAU:
        fix = None
        if he_so is not None:
            cu = T.HE_SO_BU_LANG; T.HE_SO_BU_LANG = he_so
            fix = T.thoi_luong_ep(c, rw.shape[-1]/rs, sp)
            T.HE_SO_BU_LANG = cu
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y,sr,_=next(infer_batch_process((rw,rs),rt,[T.bo_dau_cau_cho_f5(c)],
                svc._model,svc._vocoder,mel_spec_type="vocos",progress=None,
                nfe_step=nfe,speed=sp,fix_duration=fix,device=svc._model.device))
        y=T.trim_silence(np.asarray(y),sr)
        duoi.append(duoi_ngan(y,sr))
        ws.append(y/max(1.0,float(np.abs(y).max())))
        ws.append(np.zeros(int(sr*0.4),dtype=np.float32))
    p=RA/f"{nhan.replace(' ','_')}.wav"; sf.write(p,np.concatenate(ws),sr)
    print(f"  {nhan:<16} duoi tieng cuoi TB {np.mean(duoi):>5.0f}ms  dai nhat {max(duoi):>5.0f}ms  {p.name}")
