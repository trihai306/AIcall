"""Sinh 30 cau BAN DAY DU 24kHz (khong ha kenh thoai) de nguoi nghe tu cham.

Cham diem CONG BANG voi viet tat: audio doc "ve be banh" ma STT viet "vpbank"
la STT nghe DUNG. Khong quy chuan hai ve thi bao sai oan.
"""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.api.voices import _cat_manh_nhu_pipeline
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
GIONG="giong_heu"; MOI=moi_tu_vung("nam")
RA=Path(r"C:\Users\Admin\Desktop\Check giọng\BAN FULL 24kHz 13-08")
src=open(r"C:\duan\chat-ai\scripts\nghe_lai_30_cau.py",encoding="utf-8").read()
exec("CAU=["+src.split("CAU=[")[1].split("]\n")[0]+"]")
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
VT={"vê bê banh":"vpbank","tê pê banh":"tpbank","em bê banh":"mbbank",
    "vpbank":"vpbank","tpbank":"tpbank","mbbank":"mbbank"}
def chuan(s):
    s=" ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
    for a,b in VT.items(): s=s.replace(a,b)
    return s
def cer(a,b): return 1-difflib.SequenceMatcher(None,chuan(a),chuan(b)).ratio()
RA.mkdir(parents=True, exist_ok=True)
print(f"{'#':>3}{'giây':>6}{'mảnh':>5}{'â.tiết/ph':>10}{'CER':>7}  câu")
print("-"*100)
e=[];nh=[];hong=[]
for i,c in enumerate(CAU,1):
    b64,j=sinh(c)
    if not b64: print(f"{i:>3}  LỖI {j.get('error','')[:60]}"); continue
    mong=normalize_for_tts(c); ra=nghe(b64); x=cer(mong,ra); e.append(x)
    g=j["duration_ms"]/1000; a=len(chuan(mong).split())/g*60 if g else 0; nh.append(a)
    ten=f"{i:02d} - {re.sub(r'[^0-9A-Za-zÀ-ỹ ]','',c)[:52].strip()}.wav"
    (RA/ten).write_bytes(base64.b64decode(b64))
    print(f"{i:>3}{g:6.2f}{j['so_manh']:>5}{a:10.0f}{x*100:6.1f}% {'✓' if x<=0.05 else '✗'} {c[:56]}")
    if x>0.05: hong.append((i,c,mong,ra))
print("-"*100)
print(f"ĐỌC ĐÚNG {sum(x<=0.05 for x in e)}/{len(e)} câu (CER ≤ 5%)   "
      f"CER trung bình {sum(e)/len(e)*100:.1f}%   nhịp {min(nh):.0f}-{max(nh):.0f}, "
      f"trung bình {sum(nh)/len(nh):.0f} âm tiết/phút")
for i,c,mong,ra in hong:
    print(f"\n  {i}. viết  : {c}\n     F5 đọc: {mong}\n     nghe  : {ra}")
GC=f"""BAN DAY DU 24kHz - ngay 13/08/2026, giong giong_heu, toc 0.90
==============================================================

Day la ban CHUA ha xuong kenh thoai 8kHz. Nghe ro hon luc goi that.
Muon nghe dung thu khach nghe qua dien thoai thi xem thu muc kia
(logs\\nghe_lai_30 tren may Win) - do la ban da qua kenh 8kHz.

DA DOI GI SO VOI LAN TRUOC
--------------------------
1. TOC DOC 1.00 -> 0.90 (381 -> 347 am tiet/phut)
   Do 30 cau qua duong goi that, cho may nghe lai:
       toc 1.00  ->  23/30 cau dung, CER 2,7%
       toc 0.90  ->  28/30 cau dung, CER 1,4%
   Toc cu qua nhanh, do la ly do chinh cua viec dinh chu.

2. "Da" dau luot -> "Da vang"
   F5 dung hong chinh am tiet dau khi no dung mot minh qua ngan, VA hong
   LAN sang tu lien sau: "Da han muc vay" nghe ra "GIAM muc vay" - mat chu
   "han". Trong ngan hang thi "giam" la tu nguy hiem.
   Do 12 cau: giu "Da" dat 4/12, "Da vang" dat 9/12, bo han cung 9/12.
   Chon noi dai vi bang diem ma khong doi loi noi cua tu van vien.

CHUA LAM DUOC
-------------
- Chua nghe kiem tren CUOC GOI THAT qua SIM. Ban mo phong kenh chi ha bang
  thong, CHUA nen AMR - nen goi that se te hon so do tren.
"""
(RA/"GHI CHU.txt").write_text(GC, encoding="utf-8")
print(f"\nFile wav: {RA}")
