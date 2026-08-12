"""Cach nao lam chu "Da" dau cau va "a" cuoi cau doc DUNG nhat?

"Da"/"a" la hai tu day dac nhat trong kich ban, va chung nam dung hai vi tri F5
kem on dinh nhat: am tiet DAU (cho chuyen tu doan mau sang chu moi) va am tiet
CUOI (cho model goi lai).

Thu 4 cach tren 8 cau, cho STT nghe lai, dem so lan doc dung.
"""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
GIONG="giong_heu"

GOC = [
 "Dạ lãi suất cố định trong suốt thời gian vay ạ.",
 "Dạ hạn mức thẻ tín dụng từ mười triệu đến năm trăm triệu đồng ạ.",
 "Dạ phí thường niên năm đầu miễn phí ạ.",
 "Dạ vâng em nghe anh chị ạ.",
 "Dạ em ghi nhận, khi nào tiện anh chị nhắn em ạ.",
 "Dạ anh chị muốn trả trong bao lâu ạ?",
 "Dạ dư nợ hiện tại của anh chị là một trăm bốn mươi hai triệu đồng ạ.",
 "Dạ em xin phép trao đổi ngắn với anh chị ạ.",
]

def bien(cau, kieu):
    t = cau
    if kieu == "phay":   t = re.sub(r"^Dạ\s+", "Dạ, ", t)
    if kieu == "cham":   t = re.sub(r"^Dạ\s+", "Dạ. ", t)
    if kieu == "bo_da":  t = re.sub(r"^Dạ[,.]?\s+", "", t)
    return t

def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG}).encode()
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
    s=unicodedata.normalize("NFC",s); s=re.sub(r"[^\w\s]"," ",s.lower())
    return s.split()

print(f"{'cách':<22}{'Dạ đúng':>10}{'ạ cuối đúng':>14}{'CER tb':>9}")
print("-"*56)
for kieu,nhan in (("nguyen","nguyên xi (Dạ + cách)"),("phay","Dạ, (đang chạy)"),
                  ("cham","Dạ. (dấu chấm)"),("bo_da","BỎ chữ Dạ")):
    da_ok=a_ok=0; cers=[]; n_da=n_a=0
    for cau in GOC:
        t=bien(cau,kieu)
        r=sinh(t)
        if r.get("error"): continue
        from backend.pipeline.text_normalizer import normalize_for_tts
        mong=tu(normalize_for_tts(t)); ra=tu(nghe(r["audio"]))
        a=" ".join(mong).replace(" ",""); b=" ".join(ra).replace(" ","")
        cers.append(1-difflib.SequenceMatcher(None,a,b).ratio())
        if mong and mong[0]=="dạ":
            n_da+=1; da_ok += (bool(ra) and ra[0]=="dạ")
        if mong and mong[-1]=="ạ":
            n_a+=1; a_ok += (bool(ra) and ra[-1]=="ạ")
    print(f"{nhan:<22}{f'{da_ok}/{n_da}':>10}{f'{a_ok}/{n_a}':>14}{sum(cers)/len(cers)*100:>8.1f}%")
