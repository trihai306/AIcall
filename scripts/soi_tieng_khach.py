"""Tieng "khach" toi sinh ra co du chu khong? Kiem chinh bo test truoc khi tin no."""
import base64, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid, wave
import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
CAU=["Anh muốn vay mua nhà","Anh không quan tâm đâu","Thôi để hôm khác đi"]
def sinh(t,g,qdt):
    d=urllib.parse.urlencode({"text":t,"voice_name":g,"qua_dien_thoai":"true" if qdt else "false"}).encode()
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
def dai(b64):
    with wave.open(io.BytesIO(base64.b64decode(b64))) as w: return w.getnframes()/w.getframerate()
print(f"{'giọng khách':<14}{'kênh':<10}{'dài':>7}   nghe ra")
print("-"*74)
for g in ("giong_nam","giong_heu","giong_ngan"):
    for qdt in (False, True):
        for c in CAU[:2]:
            r=sinh(c,g,qdt)
            if r.get("error"): print(f"{g:<14}{'thoại' if qdt else 'gốc':<10}{'':>7}   LỖI {r['error'][:40]}"); continue
            print(f"{g:<14}{'thoại' if qdt else 'gốc':<10}{dai(r['audio']):6.2f}s   {nghe(r['audio'])[:44]}")
    print()
