"""Mo ba nhom loi cua Lan 7."""
import io, re, sys, unicodedata, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
from backend.services.stt_service import moi_tu_vung
D=Path(r"C:\Users\Admin\Desktop\Check giọng\Lan 7")
dev,ct=_pick_device()
stt=WhisperModel(r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2",device=dev,compute_type=ct)
MOI=moi_tu_vung("nam")
def doc(p):
    with wave.open(str(p)) as w:
        return w.getframerate(), np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
def rms(x): return float(np.sqrt(np.mean(x**2))) if len(x) else 0.0
def tu_thoi(p):
    segs,_=stt.transcribe(str(p),language="vi",word_timestamps=True,
                          initial_prompt=MOI,vad_filter=False,beam_size=5)
    return [w for s in segs for w in (s.words or []) if w.end>w.start]

print("=== NHÓM 'hợp' cuối câu (thư mục 5, 6): soi 800ms cuối")
for f in [D/"5"/"1 vẫn nghe 'hợp' ở cuối câu, sau chữ 'nhé' và 'ạ'.wav",
          D/"6"/"1 chữ 'ạ' cuối nghe bị 'hợp'.wav"]:
    if not f.exists(): print("  không thấy", f.name); continue
    sr,x=doc(f); tu=tu_thoi(f)
    print(f"\n  {f.parent.name}/  {len(x)/sr:.2f}s")
    print(f"     5 chữ cuối máy nghe: {[w.word.strip() for w in tu[-5:]]}")
    for w in tu[-3:]:
        a,b=int(w.start*sr),int(w.end*sr)
        print(f"       {w.word.strip()!r:<12} {w.start:5.2f}-{w.end:5.2f}s  RMS {rms(x[a:b]):.4f}")
    o=int(sr*0.010); d=[rms(x[len(x)-(i+1)*o:len(x)-i*o]) for i in range(80)][::-1]
    mx=max(d) or 1
    print("     800ms cuối (10ms/ô): " + "".join(
        "█" if v>.5*mx else "▓" if v>.25*mx else "░" if v>.08*mx else "·" for v in d))
    # nghe rieng 500ms cuoi
    b=io.BytesIO()
    with wave.open(b,"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((x[-int(sr*0.5):]*32767).astype(np.int16).tobytes())
    b.seek(0)
    segs,_=stt.transcribe(b,language="vi",vad_filter=False,beam_size=5)
    print(f"     nghe RIÊNG 500ms cuối: {' '.join(s.text.strip() for s in segs)!r}")

print("\n=== NHÓM 'đọc bị nhanh' (thư mục 2, 4): nhịp từng chữ")
for f in sorted(list((D/"2").glob("*.wav"))+list((D/"4").glob("*.wav"))):
    sr,x=doc(f); tu=tu_thoi(f)
    if not tu: continue
    nhip=[]
    for i in range(len(tu)):
        d=tu[i].end-tu[i].start
        if d>0: nhip.append((tu[i].word.strip(), 60.0/d))
    tb=sum(v for _,v in nhip)/len(nhip)
    nhanh=sorted(nhip,key=lambda t:-t[1])[:6]
    print(f"\n  {f.parent.name}/{f.name[:44]}")
    print(f"     nhịp trung bình {tb:.0f} âm tiết/phút · 6 chữ NHANH nhất: "
          + ", ".join(f"{w}({v:.0f})" for w,v in nhanh))

print("\n=== NHÓM 'lương' -> 'lượng' (thư mục 3)")
f=D/"3"/"1 đọc sai 'lương' thì đọc là 'lượng'.wav"
if f.exists():
    segs,_=stt.transcribe(str(f),language="vi",initial_prompt=MOI,vad_filter=False,beam_size=5)
    print("     máy nghe:", " ".join(s.text.strip() for s in segs))
