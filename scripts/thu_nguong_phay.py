"""Cum ngan "Em la Duong," - tach hay khong tach thi hon?

Bien duy nhat: TOI_THIEU_TU_MOI_VE (nguong so tu moi ve de tach o dau phay).
Nap TTS trong tien trinh de doi hang so roi sinh lai.
"""
import asyncio, io, re, sys, wave
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.pipeline.text_chunker as tc
import backend.api.voices as V
CAU="Em chào anh chị. Em là Dương, chuyên viên tư vấn tín dụng tại ngân hàng VPBank."
def lang(x,sr,toi_thieu_ms=60):
    o=int(sr*0.025); n=len(x)//o
    env=np.array([np.abs(x[i*o:(i+1)*o]).max() for i in range(n)])
    im=env<0.02; ra=[];i=0
    while i<n:
        if im[i]:
            j=i
            while j<n and im[j]: j+=1
            if (j-i)*25>=toi_thieu_ms: ra.append((i*25/1000,(j-i)*25))
            i=j
        else: i+=1
    return ra
async def main():
    from backend.services.tts_service import F5TTSService
    tts=F5TTSService(); tts.load()
    goc=tc.TOI_THIEU_TU_MOI_VE
    for nguong in (3,4,5,6):
        tc.TOI_THIEU_TU_MOI_VE=nguong
        manh=V._cat_manh_nhu_pipeline(CAU)
        wav=await V._ghep_nhu_pipeline(tts,manh,"giong_heu",
            tts.toc_do_cua("giong_heu")*tts.he_so_thoai(),False)
        with wave.open(io.BytesIO(wav)) as w:
            sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
        q=lang(x,sr)
        print(f"ngưỡng {nguong}  {len(x)/sr:5.2f}s  {len(manh)} mảnh "
              f"[{', '.join(str(len(m.split())) for m in manh)} từ]")
        print(f"            quãng lặng: {', '.join(f'{a:.2f}s({b:.0f}ms)' for a,b in q) or 'KHÔNG CÓ'}")
        print(f"            mảnh: {' | '.join(manh)}")
    tc.TOI_THIEU_TU_MOI_VE=goc
asyncio.run(main())
