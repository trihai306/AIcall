"""Cham lai 30 cau dai bang thuoc do DUNG - khong sinh lai tieng.

Loi cua thuoc do cu: difflib.SequenceMatcher bat autojunk khi chuoi >= 200 ky tu,
coi ky tu nao xuat hien tren 1% la "rac" va bo qua. Cau 16 sai DUNG MOT CHU ma
bao CER 62,7%. Moi phep do CER tren cau dai deu dinh loi nay.
Chua: autojunk=False, va do bang khoang cach tu (word-level) cho de doi chieu.
"""
import base64, difflib, io, json, re, sys, unicodedata, uuid, urllib.request
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
STT="http://127.0.0.1:8178/inference"; MOI=moi_tu_vung("nam")
RA=Path(r"C:\Users\Admin\Desktop\Check giọng\CAU DAI 10-12s 13-08")
src=open(r"C:\duan\chat-ai\scripts\cau_dai_30.py",encoding="utf-8").read()
exec("CAU=[\n"+src.split("CAU=[\n")[1].split("\n]\n")[0]+"\n]")
def nghe(wav):
    ranh=uuid.uuid4().hex; b=io.BytesIO()
    w=lambda s: b.write(s if isinstance(s,bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(wav); w("\r\n")
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
    """Tra (ty le chu SAI, chu mat, chu thua) - tinh tren TU, autojunk TAT."""
    A,B=chuan(a).split(),chuan(b).split()
    sm=difflib.SequenceMatcher(None,A,B,autojunk=False)
    mat=[];them=[]
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): mat+=A[i1:i2]
        if op in ("insert","replace"): them+=B[j1:j2]
    return (len(mat)+len(them))/(2*max(1,len(A))), mat, them
wav=sorted(RA.glob("*.wav"))
print(f"{'#':>3}{'từ':>5}{'sai':>7}  chữ đọc lệch")
print("-"*94)
e=[];hong=[]
for p in wav:
    i=int(p.name[:2]); c=CAU[i-1]
    mong=normalize_for_tts(c); ra=nghe(p.read_bytes())
    x,m,t=do(mong,ra); e.append(x)
    doi=[f"{a}→{b}" for a,b in zip(m,t)][:6]
    print(f"{i:>3}{len(chuan(mong).split()):>5}{x*100:6.1f}% {'✓' if x<=0.05 else '✗'} "
          f"{', '.join(doi) if doi else ('mất '+str(m) if m else '—')}")
    if x>0.05: hong.append((i,c,ra,m,t))
print("-"*94)
print(f"ĐỌC ĐÚNG {sum(x<=0.05 for x in e)}/{len(e)} câu (≤5% từ sai)   "
      f"tỷ lệ từ sai trung bình {sum(e)/len(e)*100:.1f}%")
for i,c,ra,m,t in hong:
    print(f"\n  {i}. viết : {c[:120]}")
    print(f"     nghe : {ra[:120]}")
    print(f"     mất={m[:10]}  thừa={t[:10]}")
