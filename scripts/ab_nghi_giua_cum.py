import asyncio, io, sys
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.pipeline import text_chunker as TC
from backend.services.audio_utils import chen_lang_dau_wav
from backend.services.tts_service import F5TTSService
VAN=("Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn "
     "mức lên đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến "
     "sáu mươi tháng, và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm "
     "tính trên dư nợ giảm dần ạ. Anh chị chuẩn bị giúp em chứng minh nhân "
     "dân, sổ hộ khẩu và sao kê lương ba tháng gần nhất thì bên em xử lý rất "
     "nhanh ạ.")
RA=Path(r"C:/tmp/abnghi"); RA.mkdir(parents=True,exist_ok=True)
svc=F5TTSService(); svc.load()
ten=svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
def cat(v):
    ra,dem=[],""
    for t in v.split():
        dem+=" "+t
        m,dem=TC.tach_manh(dem, first_chunk=(not ra))
        if m: ra.append(m)
    if dem.strip(): ra.append(dem.strip())
    return ra
manh=cat(VAN)
# Sinh MOT LAN moi manh, dung lai cho moi muc nghi - khoi sinh lai
kho=[asyncio.run(svc.synthesize(c, voice=ten)) for c in manh]
print(f"\n  {len(manh)} manh\n")
print(f"  {'nghi giua cum':>14} {'tong dai':>10} {'tep'}")
print("  "+"-"*46)
for muc in (0.0, 40.0, 60.0, 90.0):
    TC.NGHI_GIUA_CUM_MS = muc
    ws, nghi = [], 0.0
    for c, b in zip(manh, kho):
        bb = chen_lang_dau_wav(b, nghi) if nghi > 0 else b
        nghi = TC.nhip_nghi_sau(c)
        x, sr = sf.read(io.BytesIO(bb), dtype="float32")
        ws.append(x.mean(axis=1) if x.ndim>1 else x)
    y=np.concatenate(ws); d=float(np.abs(y).max())
    if d>1.0: y/=d
    p=RA/f"nghi_{int(muc)}ms.wav"; sf.write(p,y,sr)
    print(f"  {muc:>12.0f}ms {len(y)/sr:>9.2f}s  {p.name}")
print("  "+"-"*46)
