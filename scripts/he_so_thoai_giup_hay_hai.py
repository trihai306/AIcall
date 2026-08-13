"""He so toc thoai 1.28 GIUP hay HAI? Do tren DUNG kenh 8kHz.

Chu thich trong ma noi: kenh GSM mat dai cao mang phu am nen "dinh chu", vi the
toc thoai phai chinh RIENG. Lap luan do dan toi CHAM lai. Ma gia tri dang dat la
1.28 - NHANH hon 28%. Do de biet ai dung.

Thuoc do: ty le TU sai, autojunk=False (difflib mac dinh bo qua ky tu hay gap khi
chuoi >= 200 ky tu, tung cham mot cau sai dung mot chu thanh 62,7%).
"""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
HS="http://127.0.0.1:8100/api/voices/phone-speed"; GIONG="giong_heu"; MOI=moi_tu_vung("nam")
src=open(r"C:\duan\chat-ai\scripts\nghe_lai_30_cau.py",encoding="utf-8").read()
exec("CAU=["+src.split("CAU=[")[1].split("]\n")[0]+"]")
dai=open(r"C:\duan\chat-ai\scripts\cau_dai_30.py",encoding="utf-8").read()
exec("CAU_DAI=[\n"+dai.split("CAU=[\n")[1].split("\n]\n")[0]+"\n]")
def dat_hs(v):
    req=urllib.request.Request(HS,data=json.dumps({"he_so":v}).encode(),
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=60) as r: return json.load(r)
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
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
    with urllib.request.urlopen(req,timeout=600) as r: return json.load(r).get("text","").strip()
VT={"vê bê banh":"vpbank","tê pê banh":"tpbank","em bê banh":"mbbank"}
def chuan(s):
    s=" ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
    for a,b in VT.items(): s=s.replace(a,b)
    return s
def do(a,b):
    A,B=chuan(a).split(),chuan(b).split()
    sm=difflib.SequenceMatcher(None,A,B,autojunk=False); m=t=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): m+=i2-i1
        if op in ("insert","replace"): t+=j2-j1
    return (m+t)/(2*max(1,len(A)))
def chay(bo,ten_bo):
    e=[];nh=[]
    for c in bo:
        b64,j=sinh(c)
        if not b64: continue
        mong=normalize_for_tts(c); e.append(do(mong,nghe(b64)))
        g=j["duration_ms"]/1000; nh.append(len(chuan(mong).split())/g*60 if g else 0)
    return (f"{ten_bo:<10}{sum(nh)/len(nh):7.0f}{sum(x<=0.05 for x in e):6}/{len(e)}"
            f"{sum(e)/len(e)*100:9.1f}%")
print(f"{'':>12}{'':<10}{'â.tiết/ph':>7}{'đạt':>9}{'từ sai':>10}")
try:
    for hs in (1.28, 1.00):
        dat_hs(hs)
        print(f"\nhệ số {hs:.2f}")
        print("  ", chay(CAU,"câu ngắn"))
        print("  ", chay(CAU_DAI,"câu dài"))
finally:
    dat_hs(1.28); print("\nĐã trả hệ số về 1.28")
