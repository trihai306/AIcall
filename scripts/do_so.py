import asyncio, sys
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, torch, soundfile as sf
from backend.config import settings
from backend.services.tts_service import F5TTSService, trim_silence
NGUONG, KH = 0.015, 0.02
def lang(x, sr, tt=250):
    n=max(1,int(sr*KH)); k=len(x)//n
    to=np.array([np.abs(x[i*n:(i+1)*n]).max() for i in range(k)])
    im=to<NGUONG; ra=[]; i=0
    while i<k:
        if im[i]:
            j=i
            while j<k and im[j]: j+=1
            if i>0 and j<k and (j-i)*20>=tt: ra.append((j-i)*20)
            i=j
        else: i+=1
    return ra
CAP=[
 ("so DAI co cham", "Hạn mức đã duyệt cho anh chị là 2.000.000.000 đồng ạ"),
 ("so do doc chu",  "Hạn mức đã duyệt cho anh chị là hai tỷ đồng ạ"),
 ("phan tram so",   "Lãi suất cho sản phẩm vay tín chấp của bên em là từ 7. 9%/năm nha"),
 ("phan tram chu",  "Lãi suất cho sản phẩm vay tín chấp của bên em là từ bảy phẩy chín phần trăm một năm nha"),
 ("viet tat cham",  "Anh Tuấn chuẩn bị giấy tờ như sau: CMND/CCCD, Hộ khẩu hoặc KT3, xác nhận thu nhập"),
 ("viet tat chu",   "Anh Tuấn chuẩn bị giấy tờ như sau: chứng minh nhân dân, hộ khẩu hoặc ca tê ba, xác nhận thu nhập"),
]
svc=F5TTSService(); svc.load()
ten=svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
rw,rs,rt=svc._voices[ten]; sp,nfe=svc.toc_do_cua(ten),settings.f5tts_nfe_step
from f5_tts.infer.utils_infer import infer_batch_process
Path(r"C:/tmp/doso").mkdir(parents=True,exist_ok=True)
print(f"\n  speed {sp:.2f}  nfe {nfe}   8 luot moi ban\n")
print(f"  {'ban':<16} {'luot co nghi':>13} {'dai nhat':>10} {'cac nghi'}")
print("  "+"-"*68)
for nhan,cau in CAP:
    ban,laus,tat=0,[],[]
    for k in range(8):
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            y,sr,_=next(infer_batch_process((rw,rs),rt,[cau],svc._model,svc._vocoder,
                mel_spec_type="vocos",progress=None,nfe_step=nfe,speed=sp,device=svc._model.device))
        y=trim_silence(np.asarray(y),sr); lg=lang(y,sr)
        ban+=bool(lg); laus.append(max(lg) if lg else 0); tat+=lg
        if k==0: sf.write(fr"C:/tmp/doso/{nhan.replace(' ','_')}.wav", y/max(1.0,float(np.abs(y).max())), sr)
    print(f"  {nhan:<16} {ban:>10}/8 {max(laus):>8.0f}ms   {sorted(set(tat),reverse=True)[:6]}")
print("  "+"-"*68)
