"""Bo B: full 24kHz nhung dung NHIP CUA CUOC GOI (0.90 x he so thoai 1.28).

Vi sao can: he_so_thoai chi ap khi audio_rate <= 8000, tuc CHI tren cuoc goi
that. Bo A (full 24kHz, toc 0.90) nghe cham hon thu khach nghe 28% - duyet nhip
tren bo A la duyet nham. Bo B tach bach: nhip DUNG nhu cuoc goi, ma khong bi
kenh 8kHz lam ngat tieng.
"""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
TOC="http://127.0.0.1:8100/api/voices/giong_heu/speed"; GIONG="giong_heu"; MOI=moi_tu_vung("nam")
RA=Path(r"C:\Users\Admin\Desktop\Check giọng\BAN FULL 24kHz 13-08\B - dung NHIP CUOC GOI")
src=open(r"C:\duan\chat-ai\scripts\nghe_lai_30_cau.py",encoding="utf-8").read()
exec("CAU=["+src.split("CAU=[")[1].split("]\n")[0]+"]")
def dat_toc(v):
    req=urllib.request.Request(TOC,data=json.dumps({"speed":v}).encode(),
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=60) as r: return json.load(r)
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r:
        j=json.load(r)
    return (None,j) if j.get("error") else (j["audio"],j)
def nghe(b64):
    ranh=uuid.uuid4().hex; b=io.BytesIO()
    w=lambda s: b.write(s if isinstance(s,bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(base64.b64decode(b64)); w("\r\n")
    for k,v in (("language","vi"),("response_format","json"),("prompt",MOI)):
        w(f"--{ranh}\r\n"); w(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{ranh}--\r\n")
    req=urllib.request.Request(STT,data=b.getvalue(),
        headers={"Content-Type":f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(req,timeout=300) as r: return json.load(r).get("text","").strip()
VT={"vê bê banh":"vpbank","tê pê banh":"tpbank","em bê banh":"mbbank"}
def chuan(s):
    s=" ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
    for a,b in VT.items(): s=s.replace(a,b)
    return s
def cer(a,b): return 1-difflib.SequenceMatcher(None,chuan(a),chuan(b)).ratio()
HE_SO=float(Path(r"C:\duan\chat-ai\models\tts\ref_voices\_he_so_thoai.txt").read_text().strip())
TOC_GOI=round(0.90*HE_SO,3)
RA.mkdir(parents=True, exist_ok=True)
print(f"hệ số thoại {HE_SO} → tốc cuộc gọi {TOC_GOI}\n")
dat_toc(TOC_GOI)
try:
    e=[];nh=[];hong=[]
    for i,c in enumerate(CAU,1):
        b64,j=sinh(c)
        if not b64: print(f"{i:>3}  LỖI {j.get('error','')[:60]}"); continue
        mong=normalize_for_tts(c); ra=nghe(b64); x=cer(mong,ra); e.append(x)
        g=j["duration_ms"]/1000; a=len(chuan(mong).split())/g*60 if g else 0; nh.append(a)
        ten=f"{i:02d} - {re.sub(r'[^0-9A-Za-zÀ-ỹ ]','',c)[:52].strip()}.wav"
        (RA/ten).write_bytes(base64.b64decode(b64))
        if x>0.05: hong.append((i,c,mong,ra))
    print(f"BỘ B (nhịp cuộc gọi): ĐỌC ĐÚNG {sum(x<=0.05 for x in e)}/{len(e)} câu   "
          f"CER trung bình {sum(e)/len(e)*100:.1f}%   nhịp trung bình {sum(nh)/len(nh):.0f} âm tiết/phút")
    for i,c,mong,ra in hong:
        print(f"\n  {i}. viết  : {c}\n     nghe  : {ra}")
finally:
    dat_toc(0.90)
    print(f"\nĐã trả tốc giọng về 0.90. File: {RA}")
