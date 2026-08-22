"""Thu pham la dau PHAY sau "Da" hay ban than am tiet don? Vo hieu hoa regex de do."""
import base64, difflib, io, re, sys, unicodedata, uuid, urllib.request, asyncio
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.services.stt_service import moi_tu_vung
import backend.pipeline.text_normalizer as tn
STT="http://127.0.0.1:8178/inference"; MOI=moi_tu_vung("nam")
THAN=["hạn mức vay lên đến 500 triệu đồng ạ.",
      "lãi suất vay tín chấp bên em từ 7,9% một năm ạ.",
      "phí trả nợ trước hạn là 2% trên số tiền trả trước ạ.",
      "hẹn gặp lại anh chị ạ.",
      "bên MBBank cũng có gói tương tự ạ.",
      "em hiểu ạ, vậy em xin phép gọi lại anh chị vào dịp khác ạ."]
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
    with urllib.request.urlopen(req,timeout=300) as r:
        import json; return json.load(r).get("text","").strip()
def tu(s): return [t for t in re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split() if t]
def cer(a,b):
    A,B=" ".join(tu(a))," ".join(tu(b)); return 1-difflib.SequenceMatcher(None,A,B).ratio()

async def main():
    import backend.api.voices as V
    # nap TTS trong tien trinh nay
    from backend.services.tts_service import F5TTSService
    tts=F5TTSService(); tts.load()
    goc=tn._DA_DAU_CAU_RE
    for ten, tat_phay in (("CÓ phẩy (nay)", False), ("KHÔNG phẩy", True)):
        tn._DA_DAU_CAU_RE = re.compile(r"^(\s*dạKHONGKHOPBAOGIO)\s+(?=\w)") if tat_phay else goc
        d=0; e=[]; dau=[]
        for t in THAN:
            c="Dạ "+t
            manh=V._cat_manh_nhu_pipeline(c)
            wav=await V._ghep_nhu_pipeline(tts, manh, "giong_heu", tts.toc_do_cua("giong_heu")*tts.he_so_thoai(), False)
            wav=V._mo_phong_kenh_thoai(wav)
            mong=tn.normalize_for_tts(c); ra=nghe(wav)
            a,b=tu(mong),tu(ra); d+= bool(a) and bool(b) and a[0]==b[0]
            e.append(cer(mong,ra)); dau.append(b[0] if b else "∅")
        print(f"{ten:<16}chữ đầu {d}/{len(THAN)}   CER {sum(e)/len(e)*100:5.1f}%   nghe: {' '.join(dau)}")
    tn._DA_DAU_CAU_RE = goc
asyncio.run(main())
