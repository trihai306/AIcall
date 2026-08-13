"""Gom MOI file co chu doc lech ra mot thu muc rieng, kem ban doi chieu.

Dung lai chinh cac wav da sinh (hat giong co dinh nen sinh lai ra y het), chi
chay lai STT. Xep theo muc do nang dan xuong.
"""
import base64, difflib, io, json, re, shutil, sys, unicodedata, uuid, urllib.request
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
STT="http://127.0.0.1:8178/inference"; MOI=moi_tu_vung("nam")
GOC=Path(r"C:\Users\Admin\Desktop\Check giọng\DA SUA NHIP 13-08")
RA=GOC/"3 - CAC FILE DOC SAI"
src=open(r"C:\duan\chat-ai\scripts\nghe_lai_30_cau.py",encoding="utf-8").read()
exec("NGAN=["+src.split("CAU=[")[1].split("]\n")[0]+"]")
dai=open(r"C:\duan\chat-ai\scripts\cau_dai_30.py",encoding="utf-8").read()
exec("DAI=[\n"+dai.split("CAU=[\n")[1].split("\n]\n")[0]+"\n]")
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
def doi(a,b):
    """Tra danh sach (tu_dung -> tu_nghe_ra) va so tu lech."""
    A,B=chuan(a).split(),chuan(b).split()
    sm=difflib.SequenceMatcher(None,A,B,autojunk=False); c=[];n=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op=="replace": c.append((" ".join(A[i1:i2])," ".join(B[j1:j2]))); n+=max(i2-i1,j2-j1)
        elif op=="delete": c.append((" ".join(A[i1:i2]),"∅")); n+=i2-i1
        elif op=="insert": c.append(("∅"," ".join(B[j1:j2]))); n+=j2-j1
    return c, n, len(A)
if RA.exists(): shutil.rmtree(RA)
RA.mkdir(parents=True)
sai=[]
for thu_muc,bo,nhan in (("1 - cau ngan",NGAN,"ngắn"),("2 - cau dai",DAI,"dài")):
    for p in sorted((GOC/thu_muc).glob("*.wav")):
        i=int(p.name[:2]); c=bo[i-1]
        mong=normalize_for_tts(c); ra=nghe(p.read_bytes())
        ds,n,tong=doi(mong,ra)
        if n: sai.append((n/tong,n,nhan,i,c,mong,ra,ds,p))
sai.sort(key=lambda x:-x[0])
dong=[]
for k,(ty,n,nhan,i,c,mong,ra,ds,p) in enumerate(sai,1):
    ten=f"{k:02d} ({int(round(ty*100))}pt sai) {nhan} {i:02d} - {re.sub(r'[^0-9A-Za-zÀ-ỹ ]','',c)[:40].strip()}.wav"
    shutil.copy2(p, RA/ten)
    dong.append(f"{k:02d}. [{nhan} {i:02d}]  {n} tu lech / {tong if False else ''}{ty*100:.0f}% tu\n"
                f"    VIET   : {c}\n    F5 DOC : {mong}\n    NGHE RA: {ra}\n"
                f"    LECH   : " + ", ".join(f"{a} -> {b}" for a,b in ds) + "\n")
    print(f"{k:02d} [{nhan} {i:02d}] {ty*100:4.0f}%  " + ", ".join(f"{a}→{b}" for a,b in ds)[:66])
(RA/"BAN DOI CHIEU.txt").write_text(
    "CAC FILE DOC SAI - 13/08/2026, giong giong_heu, toc 0.90, he so thoai 1.00\n"
    "==========================================================================\n\n"
    f"{len(sai)} file tren tong 60 co it nhat MOT chu doc lech. Xep nang truoc.\n"
    "Ten file da ghi san muc do (pt = phan tram tu lech).\n\n"
    "Cach doc: VIET la cau goc, F5 DOC la ban sau chuan hoa (so -> chu, viet tat\n"
    "-> danh van), NGHE RA la thu may nghe duoc tu chinh file wav do.\n\n"
    "LUU Y: may nghe khong phai tai nguoi. Co cho may nghe sai ma nguoi nghe van\n"
    "ra dung - nhat la chu cuoi cau. Nghe truc tiep de phan dinh.\n\n"
    + "\n".join(dong), encoding="utf-8")
print(f"\n{len(sai)}/60 file có chữ lệch → {RA}")
