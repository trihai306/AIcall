"""Chen khoang lang DAN VAO co cuu duoc chu dau khong? Do tren duong 8kHz that."""
import base64, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid, wave
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
GIONG="giong_heu"; MOI=moi_tu_vung("nam")
CAU=["Em chào anh chị ạ.",
     "Dạ em là Dương, chuyên viên tư vấn tín dụng ngân hàng Quân đội ạ.",
     "Dạ lãi suất vay tín chấp bên em từ 7,9% một năm ạ.",
     "Dạ hạn mức vay lên đến 500 triệu đồng ạ.",
     "Dạ anh vay 80 triệu trong 36 tháng thì mỗi tháng trả khoảng 2,7 triệu ạ.",
     "Dạ lãi suất ưu đãi 6,5% cố định trong 12 tháng đầu ạ.",
     "Dạ phí trả nợ trước hạn là 2% trên số tiền trả trước ạ.",
     "Dạ bên MBBank cũng có gói tương tự ạ.",
     "Dạ em hiểu ạ, vậy em xin phép gọi lại anh chị vào dịp khác ạ.",
     "Dạ vậy em chốt hồ sơ cho anh chị luôn nhé ạ.",
     "Dạ hẹn gặp lại anh chị ạ."]
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r:
        j=json.load(r)
    return None if j.get("error") else base64.b64decode(j["audio"])
def them_lang(wav,ms):
    if ms<=0: return wav
    with wave.open(io.BytesIO(wav)) as f:
        sr=f.getframerate(); x=np.frombuffer(f.readframes(f.getnframes()),dtype=np.int16)
    y=np.concatenate([np.zeros(int(sr*ms/1000),dtype=np.int16),x])
    b=io.BytesIO()
    with wave.open(b,"wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr); f.writeframes(y.tobytes())
    return b.getvalue()
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
    with urllib.request.urlopen(req,timeout=300) as r: return json.load(r).get("text","").strip()
def tu(s): return [t for t in re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split() if t]
import difflib
def cer(a,b):
    A,B=" ".join(tu(a))," ".join(tu(b)); return 1-difflib.SequenceMatcher(None,A,B).ratio()
goc=[(c,sinh(c)) for c in CAU]; goc=[(c,w) for c,w in goc if w]
print(f"{'lặng dẫn vào':<16}{'chữ đầu đúng':>14}{'CER trung bình':>16}")
print("-"*48)
kq={}
for ms in (0,150,300,500,800):
    d=0; e=[]
    for c,w in goc:
        mong=normalize_for_tts(c); ra=nghe(them_lang(w,ms))
        a,b=tu(mong),tu(ra)
        d+= bool(a) and bool(b) and a[0]==b[0]
        e.append(cer(mong,ra))
    kq[ms]=[(c,nghe(them_lang(w,ms))) for c,w in goc] if ms==300 else None
    print(f"{ms:>5} ms{'':<9}{d:>8}/{len(goc)}{sum(e)/len(e)*100:15.1f}%")
print("-"*48)
if kq.get(300):
    print("\nvới 300ms lặng dẫn vào:")
    for c,ra in kq[300]: print(f"  {c[:44]:<46} → {ra[:44]}")
