"""STT mat dau cau: loi that, hay do bo test cua toi?

Tieng khach do TTS sinh -> trim_silence cat sach quang lang dau -> bat dau bang
am ngay lap tuc. Cuoc goi that KHONG the nao nhu vay. Thu 4 bien the.
"""
import base64, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid, wave
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
CAU=["Anh muốn vay mua nhà","Anh không quan tâm đâu","Thôi để hôm khác đi",
     "Giám đốc ngân hàng tên gì em","Ngân hàng mình có bao nhiêu chi nhánh"]
def sinh(t, qdt):
    d=urllib.parse.urlencode({"text":t,"voice_name":"giong_nam",
                              "qua_dien_thoai":"true" if qdt else "false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r: return json.load(r)
def them_lang(b64, ms):
    raw=base64.b64decode(b64)
    with wave.open(io.BytesIO(raw)) as w:
        p=w.getparams(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16)
    lang=np.zeros(int(p.framerate*ms/1000),dtype=np.int16)
    y=np.concatenate([lang,x,lang])
    b=io.BytesIO()
    with wave.open(b,"wb") as w:
        w.setnchannels(p.nchannels); w.setsampwidth(p.sampwidth); w.setframerate(p.framerate)
        w.writeframes(y.tobytes())
    return base64.b64encode(b.getvalue()).decode()
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
def ch(s):
    s=unicodedata.normalize("NFC",s); return " ".join(re.sub(r"[^\w\s]"," ",s.lower()).split())
import difflib
for nhan, qdt, lang in [("qua thoai 8k, KHONG lang (bo test cu)",True,0),
                        ("qua thoai 8k, + 300ms lang",True,300),
                        ("KHONG qua thoai, KHONG lang",False,0),
                        ("KHONG qua thoai, + 300ms lang",False,300)]:
    tong=0
    print(f"--- {nhan}")
    for c in CAU:
        r=sinh(c,qdt)
        if r.get("error"): print("   LOI",r["error"]); continue
        b64 = them_lang(r["audio"],lang) if lang else r["audio"]
        t=nghe(b64); g=difflib.SequenceMatcher(None,ch(c),ch(t)).ratio(); tong+=g
        print(f"   {g*100:3.0f}%  {t}")
    print(f"   => giong trung binh {tong/len(CAU)*100:.0f}%\n")
