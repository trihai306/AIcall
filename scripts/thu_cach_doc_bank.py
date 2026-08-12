"""Cach doc nao cho "VPBank" la on dinh nhat? Cho STT nghe lai."""
import base64, io, json, sys, urllib.parse, urllib.request, uuid
sys.stdout.reconfigure(encoding="utf-8")
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
N=3
UNG_VIEN = [
    ("nguyen xi (dang chay)", "Em làm tại ngân hàng VPBank ạ."),
    ("ve pe bank",            "Em làm tại ngân hàng vê pê bank ạ."),
    ("ve pe banh",            "Em làm tại ngân hàng vê pê banh ạ."),
    ("ve pe ben",             "Em làm tại ngân hàng vê pê ben ạ."),
]
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
for nhan,cau in UNG_VIEN:
    print(f"--- {nhan}")
    ra=[]
    for _ in range(N):
        r=sinh(cau)
        if r.get("error"): print("   LOI",r["error"]); continue
        t=nghe(r["audio"]); ra.append(t)
        print(f"    {t}")
    print(f"    -> {len(set(ra))} ket qua khac nhau tren {len(ra)} lan\n")
