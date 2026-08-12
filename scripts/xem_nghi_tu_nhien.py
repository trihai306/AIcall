import asyncio, io, sys
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.services.tts_service import F5TTSService
NG, KH = 0.015, 0.02
VAN=("Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn "
     "mức lên đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến "
     "sáu mươi tháng, và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm "
     "tính trên dư nợ giảm dần ạ. Anh chị chuẩn bị giúp em chứng minh nhân "
     "dân, sổ hộ khẩu và sao kê lương ba tháng gần nhất thì bên em xử lý rất "
     "nhanh ạ.")
svc=F5TTSService(); svc.load()
ten=svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
b=asyncio.run(svc.synthesize(VAN, voice=ten))
x,sr=sf.read(io.BytesIO(b),dtype="float32")
if x.ndim>1: x=x.mean(axis=1)
n=max(1,int(sr*KH)); k=len(x)//n
im=np.abs(x[:k*n].reshape(k,n)).max(axis=1)<NG
ra=[]; i=0
while i<k:
    if im[i]:
        j=i
        while j<k and im[j]: j+=1
        if i>0 and j<k: ra.append(((j-i)*KH*1000, i*KH))
        i=j
    else: i+=1
ra.sort(reverse=True)
print(f"\n  F5 tu nghi khi sinh CA CAU mot lan ({len(x)/sr:.2f}s, {len(ra)} quang):")
print(f"  {'dai':>7}  {'o giay':>8}")
print("  "+"-"*22)
for d,t in ra:
    print(f"  {d:>5.0f}ms  {t:>7.2f}s")
print("  "+"-"*22)
print(f"\n  tong im lang giua cau: {sum(d for d,_ in ra):.0f}ms")
print(f"  van ban co {VAN.count(',')} dau phay va {VAN.count('.')} dau cham")
