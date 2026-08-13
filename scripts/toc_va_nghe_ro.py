"""Toc doc doi lay do nghe ro duoc bao nhieu? 30 cau, duong 8kHz that.

Cham diem CONG BANG voi viet tat: audio doc "ve be banh" ma STT viet "vpbank"
la STT nghe DUNG, khong phai loi. Quy ca hai ve chuan roi moi so.
"""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
TOC="http://127.0.0.1:8100/api/voices/giong_heu/speed"; GIONG="giong_heu"; MOI=moi_tu_vung("nam")
exec(open(r"C:\duan\chat-ai\scripts\nghe_lai_30_cau.py",encoding="utf-8").read().split("CAU=[")[1].split("]\n")[0].join(["CAU=[","]"]))
def dat_toc(v):
    d=json.dumps({"speed":v}).encode()
    req=urllib.request.Request(TOC,data=d,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=60) as r: return json.load(r)
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"true"}).encode()
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
VT={"vê bê banh":"vpbank","tê pê banh":"tpbank","em bê banh":"mbbank",
    "vpbank":"vpbank","tpbank":"tpbank","mbbank":"mbbank","bê banh":"bank"}
def chuan(s):
    s=" ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
    for a,b in VT.items(): s=s.replace(a,b)
    return s
def tu(s): return chuan(s).split()
def cer(a,b): return 1-difflib.SequenceMatcher(None,chuan(a),chuan(b)).ratio()
import os
goc=float(os.popen('').read() or 0)
print(f"{'tốc':>6}{'â.tiết/ph':>11}{'câu đạt':>9}{'CER TB':>9}   câu hỏng")
print("-"*92)
for toc in (1.00,0.95,0.90,0.85):
    dat_toc(toc); e=[];nh=[];hong=[]
    for i,c in enumerate(CAU,1):
        b64,j=sinh(c)
        if not b64: continue
        mong=normalize_for_tts(c); ra=nghe(b64); x=cer(mong,ra); e.append(x)
        g=j["duration_ms"]/1000
        nh.append(len(tu(mong))/g*60 if g else 0)
        if x>0.05: hong.append(i)
    print(f"{toc:>6.2f}{sum(nh)/len(nh):11.0f}{sum(x<=0.05 for x in e):6}/{len(e)}"
          f"{sum(e)/len(e)*100:8.1f}%   {hong}")
dat_toc(1.00)
