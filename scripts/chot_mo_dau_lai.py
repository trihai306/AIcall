"""Do LAI cach mo dau o cau hinh HIEN TAI (toc 0.90, he so thoai 1.00).

Vi sao phai do lai: moi so lieu chon "Da vang" deu do o nhip CU 347 am tiet/phut
(he so 1.28). Nhip nay da ve 283. Bia do dan co the khong con can - va chinh no
dang de ra loi moi ("vang" -> "van").

Thuoc do: ty le TU sai, autojunk=False. Do rieng CHU MO DAU va CA CAU.
"""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import backend.pipeline.text_normalizer as tn
from backend.services.stt_service import moi_tu_vung
TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
GIONG="giong_heu"; MOI=moi_tu_vung("nam")
THAN=["mức vay tối đa bằng 70% giá trị căn nhà ạ.",
      "hạn mức vay lên đến 500 triệu đồng ạ.",
      "lãi suất vay tín chấp bên em từ 7,9% một năm ạ.",
      "phí trả nợ trước hạn là 2% trên số tiền trả trước ạ.",
      "hẹn gặp lại anh chị ạ.",
      "bên MBBank cũng có gói tương tự ạ.",
      "em hiểu ạ, vậy em xin phép gọi lại anh chị vào dịp khác ạ.",
      "cho em hỏi anh chị đang làm việc ở công ty nào ạ?",
      "thu nhập hàng tháng của anh chị khoảng bao nhiêu ạ?",
      "em sẽ gửi tin nhắn xác nhận cho anh chị ngay ạ.",
      "anh vay 80 triệu trong 36 tháng thì mỗi tháng trả khoảng 2,7 triệu ạ.",
      "em là Dương, chuyên viên tư vấn tín dụng ngân hàng Quân đội ạ."]
# (nhan, chu se dat truoc than cau, so am tiet cua no)
MO=[("Dạ  (trơn)","Dạ",1),("Dạ,  (có phẩy)","Dạ,",1),("Dạ vâng  (nay)","Dạ vâng",2),
    ("Dạ vâng,","Dạ vâng,",2),("Thưa anh chị","Thưa anh chị",3),("(bỏ hẳn)","",0)]
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
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
    with urllib.request.urlopen(req,timeout=600) as r: return json.load(r).get("text","").strip()
VT={"vê bê banh":"vpbank","tê pê banh":"tpbank","em bê banh":"mbbank"}
def chuan(s):
    s=" ".join(re.sub(r"[^\w\s]"," ",unicodedata.normalize("NFC",s).lower()).split())
    for a,b in VT.items(): s=s.replace(a,b)
    return s
def ty_le_sai(a,b):
    A,B=chuan(a).split(),chuan(b).split()
    sm=difflib.SequenceMatcher(None,A,B,autojunk=False); m=t=0
    for op,i1,i2,j1,j2 in sm.get_opcodes():
        if op in ("delete","replace"): m+=i2-i1
        if op in ("insert","replace"): t+=j2-j1
    return (m+t)/(2*max(1,len(A)))
# tat quy tac noi dai de tu dat chu mo dau
goc=tn._DA_DA_DAI_RE
tn._DA_DA_DAI_RE=re.compile(r"^\s*(?:)")   # khop moi chuoi -> khong noi dai
print(f"{'mở đầu':<18}{'chữ mở đầu đúng':>16}{'cả câu sai':>12}   nghe ra chữ mở đầu")
print("-"*92)
try:
    for nhan,mo,n_am in MO:
        dung=0; e=[]; ra_dau=[]
        for t in THAN:
            c=(mo+" "+t) if mo else t
            b64=sinh(c)
            if not b64: continue
            mong=tn.normalize_for_tts(c); ra=nghe(b64)
            e.append(ty_le_sai(mong,ra))
            A,B=chuan(mong).split(),chuan(ra).split()
            k=max(1,n_am)
            dung+= A[:k]==B[:k]
            ra_dau.append(" ".join(B[:k]) if B else "∅")
        print(f"{nhan:<18}{dung:>10}/{len(e)}{sum(e)/len(e)*100:11.1f}%   "
              + ", ".join(ra_dau[:6]))
finally:
    tn._DA_DA_DAI_RE=goc
