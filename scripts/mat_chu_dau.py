"""Mat chu DAU CAU la loi cua F5 hay cua kenh 8kHz? Do doi chung."""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid, wave
from pathlib import Path
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
def sinh(t,qdt):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,
        "qua_dien_thoai":"true" if qdt else "false"}).encode()
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
def dau_ok(mong,ra):
    a,b=tu(mong),tu(ra)
    return bool(a) and bool(b) and a[0]==b[0]
def bien_do_dau(b64):
    """Bien do 150ms dau: rac thi TO (>0.3), lang thi nho."""
    with wave.open(io.BytesIO(base64.b64decode(b64))) as w:
        sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16)
    return float(np.abs(x[:int(sr*0.15)]).max())/32768 if x.size else 0.0
print(f"{'':3}{'gốc 24kHz':<34}{'qua kênh 8kHz':<34}{'|đầu|':>7}")
print("-"*82)
d_ok=k_ok=0
for i,c in enumerate(CAU,1):
    mong=normalize_for_tts(c)
    a=sinh(c,False); b=sinh(c,True)
    ra,rb=nghe(a),nghe(b)
    oa,ob=dau_ok(mong,ra),dau_ok(mong,rb); d_ok+=oa; k_ok+=ob
    print(f"{i:>2} {'✓' if oa else '✗'} {ra[:30]:<32}{'✓' if ob else '✗'} {rb[:30]:<32}{bien_do_dau(a):6.3f}")
print("-"*82)
n=len(CAU)
print(f"chữ ĐẦU đọc đúng:  bản gốc {d_ok}/{n}   qua kênh 8kHz {k_ok}/{n}")
print("(|đầu| = biên độ 150ms đầu file; >0.3 là âm rác quay lại)")
