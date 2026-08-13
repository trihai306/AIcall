"""Bo nghe duyet SAU KHI SUA: 24kHz = dung thu khach nghe. 30 ngan + 30 dai."""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
GIONG="giong_heu"; MOI=moi_tu_vung("nam")
RA=Path(r"C:\Users\Admin\Desktop\Check giọng\DA SUA NHIP 13-08")
src=open(r"C:\duan\chat-ai\scripts\nghe_lai_30_cau.py",encoding="utf-8").read()
exec("NGAN=["+src.split("CAU=[")[1].split("]\n")[0]+"]")
dai=open(r"C:\duan\chat-ai\scripts\cau_dai_30.py",encoding="utf-8").read()
exec("DAI=[\n"+dai.split("CAU=[\n")[1].split("\n]\n")[0]+"\n]")
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
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
    sm=difflib.SequenceMatcher(None,A,B,autojunk=False); m=[];t=[]
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): m+=A[i1:i2]
        if op in ("insert","replace"): t+=B[j1:j2]
    return (len(m)+len(t))/(2*max(1,len(A))), m, t
def chay(bo,thu_muc,nhan):
    d=RA/thu_muc; d.mkdir(parents=True,exist_ok=True)
    e=[];nh=[];g_=[];hong=[]
    for i,c in enumerate(bo,1):
        b64,j=sinh(c)
        if not b64: print(f"  {i} LỖI {j.get('error','')[:50]}"); continue
        mong=normalize_for_tts(c); ra=nghe(b64); x,m,t=do(mong,ra); e.append(x)
        g=j["duration_ms"]/1000; g_.append(g); nh.append(len(chuan(mong).split())/g*60)
        (d/f"{i:02d} - {re.sub(r'[^0-9A-Za-zÀ-ỹ ]','',c)[:46].strip()}.wav").write_bytes(base64.b64decode(b64))
        if x>0.05: hong.append((i,ra,m,t))
    print(f"{nhan:<12}{sum(x<=0.05 for x in e):>3}/{len(e)} câu   {sum(e)/len(e)*100:5.1f}% từ sai   "
          f"{sum(nh)/len(nh):.0f} âm tiết/phút   dài {min(g_):.1f}-{max(g_):.1f}s")
    for i,ra,m,t in hong: print(f"    {i}. nghe: {ra[:96]}\n       mất={m[:8]} thừa={t[:8]}")
    return sum(x<=0.05 for x in e), len(e)
RA.mkdir(parents=True,exist_ok=True)
a=chay(NGAN,"1 - cau ngan","câu ngắn"); b=chay(DAI,"2 - cau dai","câu dài")
(RA/"GHI CHU.txt").write_text(f"""DA SUA NHIP - 13/08/2026, giong giong_heu
==============================================

TOAN BO file trong thu muc nay la 24kHz FULL, va nhip cua chung DUNG BANG nhip
khach nghe qua dien thoai. Truoc hom nay thi khong: nghe o 24kHz ra 283 am
tiet/phut con cuoc goi doc 347 - cham hon 28%, nen duyet giong o 24kHz la duyet
nham. Nay nghe thu bang cuoc goi, chi khac o cho chua ha bang thong 8kHz.

KET QUA (may nghe lai, nguong duoi 5% tu sai)
    cau ngan  {a[0]}/{a[1]}
    cau dai   {b[0]}/{b[1]}

DA SUA HAI CHO
--------------
1. MOT CO DIEU KHIEN HAI THU. `qua_dien_thoai` vua nhan he so toc vua ha bang
   thong, nen khong the nghe dung nhip o 24kHz. Nay no chi con mot nghia: ha
   bang thong. Nhip luon theo cuoc goi.

2. HE SO TOC THOAI 1.28 -> 1.00. He so nay sinh ra de chong "dinh chu" tren kenh
   8kHz, nhung no lam doc NHANH hon 28% - nguoc voi chinh lap luan cua no - va
   do ra thi no gay dung cai no dinh chong. Do qua dung kenh 8kHz, 30 cau dai:
        he so 1,28 (347 am tiet/phut)   23/30 cau   2,8% tu sai
        he so 1,00 (283 am tiet/phut)   30/30 cau   0,4% tu sai

CHUA LAM DUOC
-------------
Chua nghe kiem tren CUOC GOI THAT qua SIM. Ban mo phong kenh chi ha bang thong,
CHUA nen AMR - nen goi that se te hon moi so o tren.
""",encoding="utf-8")
print(f"\nFile: {RA}")
