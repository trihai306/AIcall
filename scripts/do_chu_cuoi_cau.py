"""Chu CUOI cau co bi doc nho hon han cac chu khac khong?

Do RMS tung chu (theo dau thoi gian cua model), roi lay
    RMS chu cuoi / RMS trung vi cac chu khac
   1.0 = to bang cac chu khac   ·   0.3 = nho hon 10dB   ·   0.1 = nho hon 20dB
Doi chung bang chinh DOAN MAU NGUOI THAT cung giong.
"""
import base64, io, json, re, statistics, sys, unicodedata, urllib.parse, urllib.request, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
TTS="http://127.0.0.1:8100/api/voices/test-tts"; GIONG="giong_heu"
M=r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2"
TMP=Path(r"C:\duan\chat-ai\logs\chu_cuoi"); TMP.mkdir(parents=True,exist_ok=True)
CAU=["Thời gian vay tối đa hai mươi lăm năm.",
     "Anh chị chuẩn bị hồ sơ vay vốn.",
     "Hạn mức lên đến năm trăm triệu đồng.",
     "Thời hạn vay là ba mươi sáu tháng.",
     "Lãi suất vay tín chấp là bảy phẩy chín phần trăm.",
     "Em xin phép gọi lại anh chị sau ạ.",
     "Hồ sơ được duyệt trong hai ngày làm việc.",
     "Anh chị cho em xin thông tin liên hệ.",
     "Bên em hỗ trợ vay tối đa năm trăm triệu.",
     "Em cảm ơn anh chị rất nhiều."]
def sinh(t,i):
    p=TMP/f"{i:02d}.wav"
    if not p.exists():
        d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
        with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
            j=json.load(r)
        if j.get("error"): return None
        p.write_bytes(base64.b64decode(j["audio"]))
    return p
def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
dev,ct=_pick_device(); model=WhisperModel(M,device=dev,compute_type=ct)
def do(p):
    with wave.open(str(p)) as w:
        sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    segs,_=model.transcribe(str(p),language="vi",word_timestamps=True,vad_filter=False,beam_size=5)
    tu=[w for s in segs for w in (s.words or [])]
    v=[(unicodedata.normalize("NFC",w.word.strip().lower().strip(".,?!")),
        rms(x[int(w.start*sr):int(w.end*sr)])) for w in tu if w.end>w.start]
    return [t for t in v if t[1]>0]
print(f"{'#':>3}  {'chữ cuối':<12}{'RMS cuối':>10}{'RMS trung vị':>14}{'tỷ lệ':>8}{'dB':>7}")
print("-"*60)
ty=[]
for i,c in enumerate(CAU,1):
    p=sinh(c,i)
    if not p: continue
    v=do(p)
    if len(v)<3: continue
    cuoi=v[-1][1]; giua=statistics.median(t[1] for t in v[:-1])
    r=cuoi/max(1e-9,giua); ty.append(r)
    print(f"{i:>3}  {v[-1][0]:<12}{cuoi:10.4f}{giua:14.4f}{r:8.2f}{20*np.log10(max(r,1e-6)):7.1f}")
print("-"*60)
print(f"F5: chữ cuối / trung vị = {sum(ty)/len(ty):.2f}  "
      f"({20*np.log10(sum(ty)/len(ty)):.1f} dB)   thấp nhất {min(ty):.2f}")
ref=Path(r"C:\duan\chat-ai\models\tts\ref_voices\giong_heu.wav")
if ref.exists():
    v=do(ref)
    cuoi=v[-1][1]; giua=statistics.median(t[1] for t in v[:-1])
    print(f"NGƯỜI THẬT (cùng giọng): chữ cuối {cuoi:.4f} / trung vị {giua:.4f} "
          f"= {cuoi/giua:.2f}  ({20*np.log10(cuoi/giua):.1f} dB)")
