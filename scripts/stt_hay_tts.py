"""TTS doc sai, hay STT nghe chech ve cum quen?

"da lai" -> "giam lai", "da han" -> "gia han": ca hai deu la cum ngan hang rat
thuong gap. STT co mo hinh ngon ngu nen no keo ve cum quen. Thu "Da" + tu KHONG
tao cum nao: neu nghe dung thi loi la cua STT, khong phai TTS.
"""
import base64, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid, pathlib
sys.stdout.reconfigure(encoding="utf-8")
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
THU=[("tạo cụm quen: dạ+lãi","Dạ lãi suất cố định trong suốt thời gian vay ạ."),
     ("tạo cụm quen: dạ+hạn","Dạ hạn mức thẻ tín dụng năm trăm triệu đồng ạ."),
     ("KHÔNG cụm: dạ+xe",   "Dạ xe đạp màu xanh của anh ạ."),
     ("KHÔNG cụm: dạ+bàn",  "Dạ bàn ghế gỗ ngoài sân ạ."),
     ("KHÔNG cụm: dạ+mèo",  "Dạ mèo con nhà em ạ."),
     ("đối chứng: vâng+lãi","Vâng lãi suất cố định trong suốt thời gian vay ạ.")]
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
ra_dir = pathlib.Path(r"C:\duan\chat-ai\logs\thu_da"); ra_dir.mkdir(exist_ok=True)
for nhan, cau in THU:
    d=urllib.parse.urlencode({"text":cau,"voice_name":"giong_heu"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r: rr=json.load(r)
    if rr.get("error"): print(nhan,"LOI",rr["error"]); continue
    ten = re.sub(r"[^a-z0-9]+","_",nhan.lower())[:28]
    (ra_dir/f"{ten}.wav").write_bytes(base64.b64decode(rr["audio"]))
    t=nghe(rr["audio"])
    print(f"{nhan:<24} -> {t[:64]}")
