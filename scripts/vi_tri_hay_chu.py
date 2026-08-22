"""Loi o CHU "Da", hay o VI TRI am tiet dau?

Cung mot cau, doi chu dau. Neu moi chu dau deu sai ~cung ti le -> loi VI TRI,
khong chua duoc bang cach doi chu. Neu chi "Da" sai -> chua duoc.
"""
import base64, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
DUOI = "lãi suất cố định trong suốt thời gian vay ạ."
DAU = ["Dạ", "Vâng", "Thưa anh", "Em xin phép nói", "Hiện tại", "Báo anh", "Kính thưa anh"]
N = 3
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":"giong_heu"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r: return json.load(r)
def nghe(b64):
    ranh=uuid.uuid4().hex; b=io.BytesIO()
    w=lambda s: b.write(s if isinstance(s,bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(base64.b64decode(b64)); w("\r\n")
    for k,v in (("language","vi"),("response_format","json")):
        w(f"--{ranh}\r\n"); w(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{ranh}--\r\n")
    req=urllib.request.Request(STT,data=b.getvalue(),headers={"Content-Type":f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(req,timeout=300) as r: return json.load(r).get("text","").strip()
def tu(s):
    s=unicodedata.normalize("NFC",s); return re.sub(r"[^\w\s]"," ",s.lower()).split()
print(f"{'chữ mở đầu':<20}{'âm tiết ĐẦU đúng':>20}   nghe ra")
print("-"*72)
for d in DAU:
    cau = f"{d} {DUOI}"
    mong = tu(normalize_for_tts(cau))
    ok=0; vd=[]
    for i in range(N):
        # doi nhe cuoi cau de hat giong khac nhau moi lan
        r=sinh(cau + (" " * i))
        if r.get("error"): continue
        ra=tu(nghe(r["audio"]))
        dung = bool(ra) and ra[0]==mong[0]
        ok += dung
        if not dung and len(vd)<2: vd.append(" ".join(ra[:3]))
    print(f"{d:<20}{f'{ok}/{N}':>20}   {'; '.join(vd)}")
