import asyncio, io, sys
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.pipeline.text_chunker import nhip_nghi_sau, tach_manh
from backend.services.audio_utils import chen_lang_dau_wav
from backend.services.tts_service import F5TTSService
VAN=("Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức "
     "lên đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến sáu mươi "
     "tháng, và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm ạ. Anh chị "
     "chuẩn bị giúp em chứng minh nhân dân, sổ hộ khẩu và sao kê lương ba tháng "
     "gần nhất thì bên em xử lý rất nhanh ạ.")
from pathlib import Path
RA=Path(r"C:/tmp/abspeed"); RA.mkdir(parents=True,exist_ok=True)
svc=F5TTSService(); svc.load()
ten=svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
ra,dem=[],""
for t in VAN.split():
    dem+=" "+t
    m,dem=tach_manh(dem, first_chunk=(not ra))
    if m: ra.append(m)
if dem.strip(): ra.append(dem.strip())
print(f"\n  {len(ra)} manh\n")
print(f"  {'speed':>6} {'tong dai':>10}  tep")
print("  "+"-"*40)
for sp in (1.20, 1.35, 1.50):
    ws, nghi = [], 0.0
    for c in ra:
        b=asyncio.run(svc.synthesize(c, voice=ten, speed=sp))
        if nghi>0: b=chen_lang_dau_wav(b, nghi)
        nghi=nhip_nghi_sau(c)
        x,srr=sf.read(io.BytesIO(b),dtype="float32")
        ws.append(x.mean(axis=1) if x.ndim>1 else x)
    y=np.concatenate(ws); d=float(np.abs(y).max())
    if d>1.0: y/=d
    p=RA/f"speed_{sp:.2f}.wav"; sf.write(p,y,srr)
    print(f"  {sp:>6.2f} {len(y)/srr:>9.2f}s  {p.name}")
print("  "+"-"*40)
