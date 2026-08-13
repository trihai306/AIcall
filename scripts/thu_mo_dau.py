"""Cach mo dau nao F5 doc CHAC? Do tren duong 8kHz that, 6 than cau."""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
GIONG="giong_heu"; MOI=moi_tu_vung("nam")
THAN=["hạn mức vay lên đến 500 triệu đồng ạ.",
      "lãi suất vay tín chấp bên em từ 7,9% một năm ạ.",
      "phí trả nợ trước hạn là 2% trên số tiền trả trước ạ.",
      "hẹn gặp lại anh chị ạ.",
      "bên MBBank cũng có gói tương tự ạ.",
      "em hiểu ạ, vậy em xin phép gọi lại anh chị vào dịp khác ạ."]
MO=[("Dạ","Dạ {t}"),("Vâng","Vâng {t}"),("Dạ vâng","Dạ vâng {t}"),
    ("Thưa anh chị","Thưa anh chị {t}"),("(không có)","{t}")]
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r:
        j=json.load(r)
    return None if j.get("error") else j["audio"]
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
def tu(s): return [t for t in re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split() if t]
def cer(a,b):
    A,B=" ".join(tu(a))," ".join(tu(b)); return 1-difflib.SequenceMatcher(None,A,B).ratio()
print(f"{'mở đầu':<16}{'chữ đầu đúng':>13}{'CER':>9}   nghe ra chữ đầu")
print("-"*74)
for ten,mau in MO:
    d=0; e=[]; nghe_dau=[]
    for t in THAN:
        c=mau.format(t=t); mong=normalize_for_tts(c); b64=sinh(c)
        if not b64: continue
        ra=nghe(b64); a,b=tu(mong),tu(ra)
        ok=bool(a) and bool(b) and a[0]==b[0]; d+=ok
        e.append(cer(mong,ra)); nghe_dau.append(b[0] if b else "∅")
    print(f"{ten:<16}{d:>8}/{len(THAN)}{sum(e)/len(e)*100:8.1f}%   {' '.join(nghe_dau)}")
