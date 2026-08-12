"""Sinh lai DUNG chu cua tung manh trong cuoc goi, noi thang nhu ban xuat.

Cung chu, cung cach cat, cung giong, cung toc. Chi khac DUONG DI. Neu ra 297
thi khac biet nam o pipeline; neu ra 260 thi nam o chu.
"""
import asyncio, io, sys
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.services.tts_service import F5TTSService

MANH = [l.strip() for l in Path(r"C:/tmp/manh_goi5.txt").read_text(encoding="utf-8").splitlines() if l.strip()]

def soi(y, sr):
    h = max(1,int(sr*0.01)); k=len(y)//h
    e = np.convolve(np.array([float(np.sqrt((y[i*h:(i+1)*h]**2).mean())) for i in range(k)]),
                    np.ones(3)/3, mode="same")
    ng = max(e.max()*0.06, 3e-4); co = np.nonzero(e > ng)[0]
    d0, d1 = int(co[0]), int(co[-1])
    dinh = [i for i in range(d0+3, d1-2)
            if e[i] == max(e[max(d0,i-7):min(d1,i+8)+1]) and e[i] > e.max()*0.20]
    im = 0; i = d0
    while i < d1:
        if e[i] <= ng:
            j = i
            while j < d1 and e[j] <= ng: j += 1
            if (j-i)*10 >= 120: im += (j-i)*10
            i = j
        else: i += 1
    return len(dinh), (d1-d0)*10/1000, im/1000

async def main():
    svc = F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    khuc = []
    for i, m in enumerate(MANH):
        b = await svc.synthesize(m, voice=ten, fast=(i == 0), use_cache=False)
        x, sr = sf.read(io.BytesIO(b), dtype="float32")
        khuc.append(x.mean(axis=1) if x.ndim > 1 else x)
    y = np.concatenate(khuc)
    Path(r"C:/tmp/sinhlai").mkdir(exist_ok=True)
    sf.write(r"C:/tmp/sinhlai/noi_thang.wav", y/max(1.0,float(np.abs(y).max())), sr)
    a, t, im = soi(y, sr)
    print(f"\n  {len(MANH)} manh, sinh lai roi noi thang")
    print(f"    am tiet   : {a}")
    print(f"    tieng     : {t:.2f}s")
    print(f"    im giua   : {im:.2f}s")
    print(f"    nhip      : {a/t*60:.0f} am tiet/phut")
    print(f"\n  doi chieu: goi that 260/phut im 2.38s | ban xuat 297/phut im 0.00s")
asyncio.run(main())
