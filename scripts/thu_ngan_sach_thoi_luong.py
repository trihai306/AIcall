"""Chu cuoi bi bop nghet co phai vi NGAN SACH THOI LUONG chat qua khong?

Bien duy nhat: HE_SO_BU_LANG (he so nhan vao thoi luong ep), va mot muc TAT HAN
viec ep. Do RMS chu cuoi / trung vi cac chu khac.
"""
import asyncio, io, statistics, sys, unicodedata, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.services.tts_service as TS
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
M=r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2"
CAU=["Thời gian vay tối đa hai mươi lăm năm.",
     "Anh chị chuẩn bị hồ sơ vay vốn.",
     "Hạn mức lên đến năm trăm triệu đồng.",
     "Thời hạn vay là ba mươi sáu tháng.",
     "Em cảm ơn anh chị rất nhiều.",
     "Hồ sơ được duyệt trong hai ngày làm việc."]
def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
dev,ct=_pick_device(); stt=WhisperModel(M,device=dev,compute_type=ct)
def ty_le(wav):
    with wave.open(io.BytesIO(wav)) as w:
        sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    b=io.BytesIO(wav)
    segs,_=stt.transcribe(b,language="vi",word_timestamps=True,vad_filter=False,beam_size=5)
    tu=[w for s in segs for w in (s.words or []) if w.end>w.start]
    v=[(unicodedata.normalize("NFC",w.word.strip().lower().strip(".,?!")),
        rms(x[int(w.start*sr):int(w.end*sr)])) for w in tu]
    v=[t for t in v if t[1]>0]
    if len(v)<3: return None,None
    return v[-1][1]/max(1e-9,statistics.median(t[1] for t in v[:-1])), v[-1][0]
async def main():
    tts=TS.F5TTSService(); tts.load()
    toc=tts.toc_do_cua("giong_heu")*tts.he_so_thoai()
    goc=TS.HE_SO_BU_LANG; goc_min=TS.TOI_THIEU_AM_TIET_DE_EP
    for nhan,hs,tat in (("nay (0.85)",0.85,False),("1.00",1.00,False),
                        ("1.15",1.15,False),("TẮT ép hẳn",goc,True)):
        TS.HE_SO_BU_LANG=hs
        TS.TOI_THIEU_AM_TIET_DE_EP=(10**6 if tat else goc_min)
        r=[];chu=[]
        for c in CAU:
            wav=await tts.synthesize(c,voice="giong_heu",speed=toc,use_cache=False)
            t,w=ty_le(wav)
            if t: r.append(t); chu.append(w)
        print(f"{nhan:<14} chữ cuối/trung vị = {sum(r)/len(r):.2f}  "
              f"({20*np.log10(sum(r)/len(r)):5.1f} dB)  thấp nhất {min(r):.2f}   "
              f"nghe: {' '.join(chu)}")
    TS.HE_SO_BU_LANG=goc; TS.TOI_THIEU_AM_TIET_DE_EP=goc_min
asyncio.run(main())
