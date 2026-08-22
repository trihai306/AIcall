"""Am mui cuoi (n/ng/m) co bi F5 doc yeu bat thuong khong?

Cach do: cho model tra dau thoi gian TUNG CHU (word_timestamps), roi do nang
luong 40% CUOI cua moi chu - do la vung phu am cuoi. So:
  1. chu ket bang n/ng/m  vs  chu ket bang nguyen am (trong CUNG cau)
  2. chu o CUOI cau  vs  chu do o GIUA cau
  3. F5  vs  DOAN MAU NGUOI THAT (cung giong) - day moi la doi chung that
"""
import base64, io, json, re, sys, unicodedata, urllib.parse, urllib.request, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
TTS="http://127.0.0.1:8100/api/voices/test-tts"; GIONG="giong_heu"
M=r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2"
TMP=Path(r"C:\duan\chat-ai\logs\am_mui"); TMP.mkdir(parents=True,exist_ok=True)

# Cap cau: cung chu, mot lan o CUOI, mot lan o GIUA.
CAP=[("năm",  "Thời gian vay tối đa hai mươi lăm năm.",
              "Hai mươi lăm năm là thời hạn tối đa của gói này."),
     ("vốn",  "Anh chị chuẩn bị hồ sơ vay vốn.",
              "Hồ sơ vay vốn thì anh chị chuẩn bị giấy tờ tuỳ thân."),
     ("đồng", "Hạn mức lên đến năm trăm triệu đồng.",
              "Năm trăm triệu đồng là hạn mức tối đa bên em cấp."),
     ("tháng","Thời hạn vay là ba mươi sáu tháng.",
              "Ba mươi sáu tháng là thời hạn phổ biến nhất hiện nay."),
     ("nhàn", "Gói này giúp anh chị nhàn.",
              "Nhàn hơn nhiều so với vay ở chỗ khác đấy anh chị.")]
def sinh(t,ten):
    p=TMP/f"{ten}.wav"
    if not p.exists():
        d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
        with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
            j=json.load(r)
        if j.get("error"): return None
        p.write_bytes(base64.b64decode(j["audio"]))
    return p
def doc(p):
    with wave.open(str(p)) as w:
        return w.getframerate(), np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
dev,ct=_pick_device(); model=WhisperModel(M,device=dev,compute_type=ct)
MUI=re.compile(r"(n|ng|m|nh)$")
def soi(p):
    """Tra list (chu, rms_toan_chu, rms_40%_cuoi, la_am_mui, o_cuoi_cau)."""
    sr,x=doc(p)
    segs,_=model.transcribe(str(p),language="vi",word_timestamps=True,
                            vad_filter=False,beam_size=5)
    tu=[w for s in segs for w in (s.words or [])]
    ra=[]
    for i,w in enumerate(tu):
        a,b=int(w.start*sr),int(w.end*sr)
        if b<=a: continue
        chu=unicodedata.normalize("NFC",w.word.strip().lower().strip(".,?!"))
        doan=x[a:b]; k=int(len(doan)*0.6)
        ra.append((chu, rms(doan), rms(doan[k:]), bool(MUI.search(chu)), i==len(tu)-1))
    return ra
print(f"{'chữ':<10}{'ở đâu':<10}{'RMS cả chữ':>12}{'RMS đuôi':>11}{'đuôi/chữ':>11}")
print("-"*56)
cuoi_mui=[];giua_mui=[];khong_mui=[]
for chu,c_cuoi,c_giua in CAP:
    for nhan,cau in (("cuối câu",c_cuoi),("giữa câu",c_giua)):
        p=sinh(cau,f"{chu}_{nhan.replace(' ','_')}")
        if not p: continue
        for w,r_all,r_duoi,mui,la_cuoi in soi(p):
            if w!=chu: 
                if not mui: khong_mui.append(r_duoi/max(1e-6,r_all))
                continue
            ty=r_duoi/max(1e-6,r_all)
            (cuoi_mui if nhan=="cuối câu" else giua_mui).append(ty)
            print(f"{chu:<10}{nhan:<10}{r_all:12.4f}{r_duoi:11.4f}{ty:11.2f}")
print("-"*56)
f=lambda v: f"{sum(v)/len(v):.2f}" if v else "—"
print(f"âm mũi ở CUỐI câu: đuôi/chữ = {f(cuoi_mui)}   (n={len(cuoi_mui)})")
print(f"âm mũi ở GIỮA câu: đuôi/chữ = {f(giua_mui)}   (n={len(giua_mui)})")
print(f"chữ KHÔNG âm mũi : đuôi/chữ = {f(khong_mui)}   (n={len(khong_mui)})")
# doi chung nguoi that
ref=Path(r"C:\duan\chat-ai\models\tts\ref_voices\giong_heu.wav")
if ref.exists():
    rm=[r_duoi/max(1e-6,r_all) for w,r_all,r_duoi,mui,_ in soi(ref) if mui]
    rk=[r_duoi/max(1e-6,r_all) for w,r_all,r_duoi,mui,_ in soi(ref) if not mui]
    print(f"\nĐOẠN MẪU NGƯỜI THẬT (cùng giọng):")
    print(f"   âm mũi           = {f(rm)}   (n={len(rm)})")
    print(f"   không âm mũi     = {f(rk)}   (n={len(rk)})")
