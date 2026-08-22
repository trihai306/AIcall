"""Do lai cau moi tu vung tren nguon tieng DUNG (giong_heu), qua kenh thoai."""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
GIONG="giong_heu"
CAU=["Alô em ơi","Lãi suất vay tín chấp bao nhiêu em","Anh vay được tối đa bao nhiêu",
     "Cần giấy tờ gì không em","Bao lâu thì giải ngân","Anh cần vay tám mươi triệu",
     "Anh muốn vay mua nhà","Anh không quan tâm đâu","Thôi để hôm khác đi",
     "Giám đốc ngân hàng tên gì em"]
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r: return json.load(r)
def nghe(b64,moi):
    ranh=uuid.uuid4().hex; b=io.BytesIO()
    w=lambda s: b.write(s if isinstance(s,bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(base64.b64decode(b64)); w("\r\n")
    for k,v in (("language","vi"),("response_format","json"),("prompt",moi)):
        w(f"--{ranh}\r\n"); w(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{ranh}--\r\n")
    req=urllib.request.Request(STT,data=b.getvalue(),headers={"Content-Type":f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(req,timeout=300) as r: return json.load(r).get("text","").strip()
def ch(s): return " ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
def gn(a,b): return difflib.SequenceMatcher(None,ch(a),ch(b)).ratio()
tieng=[(c,sinh(c)) for c in CAU]
tieng=[(c,r["audio"]) for c,r in tieng if not r.get("error")]
for ten,moi in (("KHÔNG mồi",""),("mồi ngân hàng",moi_tu_vung("")),("mồi + miền Nam",moi_tu_vung("nam"))):
    d=[(c,nghe(a,moi)) for c,a in tieng]; g=[gn(c,n) for c,n in d]
    print(f"\n{ten:<18} nghe đúng {sum(g)/len(g)*100:5.1f}%   ({sum(x>=0.85 for x in g)}/{len(g)} câu đạt)")
    for (c,n),x in zip(d,g):
        if x<0.85: print(f"    {c!r:<44} → {n!r}")
