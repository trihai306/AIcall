import asyncio, io, sys
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf, torch
from backend.config import settings
from backend.services import tts_service as T

print("  cat_lang_bia co trong module?  ", hasattr(T, "cat_lang_bia"))
print("  nguong dang dung             :  ", getattr(T, "NGUONG_LANG_BIA_MS", "KHONG CO"))
import inspect
src = inspect.getsource(T.F5TTSService.synthesize)
print("  synthesize co goi cat_lang_bia:", "cat_lang_bia" in src)

NG, KH = 0.015, 0.02
def lang(x, sr, tt=300):
    n=max(1,int(sr*KH)); k=len(x)//n
    to=np.array([np.abs(x[i*n:(i+1)*n]).max() for i in range(k)])
    im=to<NG; ra=[]; i=0
    while i<k:
        if im[i]:
            j=i
            while j<k and im[j]: j+=1
            if i>0 and j<k and (j-i)*20>=tt: ra.append((j-i)*20)
            i=j
        else: i+=1
    return ra

# Manh 5 tu THAT, cat tu cau tra loi that trong hoi thoai
MANH = [
    "Được ạ, với vay tín",
    "chấp, anh cần là công",
    "dân Việt Nam từ 22-60",
    "tuổi có thu nhập ổn",
    "định từ 5 triệu đồng",
    "một tháng trở lên, có",
    "hợp đồng lao động và",
    "không có nợ xấu tại",
]
svc = T.F5TTSService(); svc.load()
ten = svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))

print(f"\n  Do tren 8 manh 5 tu THAT, qua DUNG ham synthesize()\n")
print(f"  {'manh':<26} {'giay':>6} {'quang >300ms':>13}")
print("  "+"-"*52)
tong = 0
for m in MANH:
    b = asyncio.run(svc.synthesize(m, voice=ten))
    x, sr = sf.read(io.BytesIO(b), dtype="float32")
    if x.ndim > 1: x = x.mean(axis=1)
    lg = lang(x, sr)
    tong += len(lg)
    print(f"  {m[:24]:<26} {len(x)/sr:>5.2f}s {str(lg) if lg else '0':>13}")
print("  "+"-"*52)
print(f"\n  tong quang > 300ms trong 8 manh: {tong}")
