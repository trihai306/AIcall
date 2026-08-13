"""30 cau tu van -> F5 sinh theo DUNG luong cuoc goi -> medium nghe lai.

Duong di: cat manh nhu pipeline -> ghep kem nhip nghi -> he so toc thoai
-> ha kenh 8kHz. Do la duong khach that su nghe.

Doi chung voi normalize_for_tts(text) chu KHONG phai text goc: F5 doc ban da
chuan hoa ("VPBank" -> "ve be banh"), so voi ban goc la tu tao ra loi ao.
"""
import base64, difflib, io, json, re, sys, unicodedata, urllib.parse, urllib.request, uuid
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.api.voices import _cat_manh_nhu_pipeline
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.stt_service import moi_tu_vung

TTS="http://127.0.0.1:8100/api/voices/test-tts"; STT="http://127.0.0.1:8178/inference"
GIONG="giong_heu"
RA=Path(r"C:\duan\chat-ai\logs\nghe_lai_30"); RA.mkdir(parents=True, exist_ok=True)

CAU=[
 # mở đầu / xã giao
 "Em chào anh chị ạ.",
 "Dạ em là Dương, chuyên viên tư vấn tín dụng ngân hàng Quân đội ạ.",
 "Dạ không biết hiện tại anh chị có đang quan tâm đến gói vay nào không ạ?",
 "Dạ vâng em cảm ơn anh chị đã dành thời gian ạ.",
 # lãi suất + số
 "Dạ lãi suất vay tín chấp bên em từ 7,9% một năm ạ.",
 "Dạ hạn mức vay lên đến 500 triệu đồng ạ.",
 "Dạ anh vay 80 triệu trong 36 tháng thì mỗi tháng trả khoảng 2,7 triệu ạ.",
 "Dạ lãi suất ưu đãi 6,5% cố định trong 12 tháng đầu ạ.",
 "Dạ phí trả nợ trước hạn là 2% trên số tiền trả trước ạ.",
 "Dạ mức vay tối đa bằng 70% giá trị căn nhà ạ.",
 # tên viết tắt
 "Dạ anh chị có thể so sánh thêm với VPBank và TPBank ạ.",
 "Dạ bên MBBank cũng có gói tương tự ạ.",
 "Dạ anh chị chuẩn bị CMND hoặc CCCD và sổ hộ khẩu ạ.",
 # câu có dấu phẩy - chỗ cắt mảnh
 "Dạ anh chị yên tâm, hồ sơ bên em xử lý rất nhanh ạ.",
 "Dạ em xin phép kiểm tra lại, và báo lại anh chị ngay trong hôm nay ạ.",
 "Dạ nếu anh chị đồng ý, em sẽ gửi hồ sơ qua cho anh chị ngay ạ.",
 # câu dài
 "Dạ hiện tại bên em đang có chương trình ưu đãi dành riêng cho khách hàng có "
 "thu nhập từ 15 triệu đồng trở lên ạ.",
 "Dạ anh chị chỉ cần cung cấp giấy tờ tùy thân và sao kê lương ba tháng gần "
 "nhất là bên em có thể xét duyệt được rồi ạ.",
 "Dạ thời gian giải ngân trung bình từ hai đến ba ngày làm việc kể từ khi hồ "
 "sơ được duyệt ạ.",
 # xử lý từ chối
 "Dạ em hiểu ạ, vậy em xin phép gọi lại anh chị vào dịp khác ạ.",
 "Dạ vâng ạ, em không làm phiền anh chị nữa ạ.",
 "Dạ nếu sau này anh chị cần thì cứ liên hệ lại với em ạ.",
 # hỏi thông tin
 "Dạ cho em hỏi anh chị đang làm việc ở công ty nào ạ?",
 "Dạ thu nhập hàng tháng của anh chị khoảng bao nhiêu ạ?",
 "Dạ anh chị dự kiến vay khoảng bao nhiêu và trong thời gian bao lâu ạ?",
 "Dạ anh chị có đang có khoản vay nào ở ngân hàng khác không ạ?",
 # chốt
 "Dạ vậy em chốt hồ sơ cho anh chị luôn nhé ạ.",
 "Dạ em sẽ gửi tin nhắn xác nhận cho anh chị ngay ạ.",
 "Dạ em cảm ơn anh chị rất nhiều, chúc anh chị một ngày tốt lành ạ.",
 "Dạ hẹn gặp lại anh chị ạ.",
]

def sinh(t,i):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r:
        j=json.load(r)
    if j.get("error"): return None,j
    (RA/f"{i:02d}.wav").write_bytes(base64.b64decode(j["audio"]))
    return j["audio"],j

def nghe(b64,moi):
    ranh=uuid.uuid4().hex; b=io.BytesIO()
    w=lambda s: b.write(s if isinstance(s,bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n"); w('Content-Disposition: form-data; name="file"; filename="a.wav"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n"); w(base64.b64decode(b64)); w("\r\n")
    for k,v in (("language","vi"),("response_format","json"),("prompt",moi)):
        w(f"--{ranh}\r\n"); w(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{ranh}--\r\n")
    req=urllib.request.Request(STT,data=b.getvalue(),
        headers={"Content-Type":f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(req,timeout=300) as r: return json.load(r).get("text","").strip()

def tu(s):
    s=unicodedata.normalize("NFC",s).lower()
    return [t for t in re.sub(r"[^\w\s]"," ",s).split() if t]
def lech(a,b):
    A,B=tu(a),tu(b); mat=[];them=[]
    for op,i1,i2,j1,j2 in difflib.SequenceMatcher(None,A,B).get_opcodes():
        if op in ("delete","replace"): mat+=A[i1:i2]
        if op in ("insert","replace"): them+=B[j1:j2]
    return mat,them
def cer(a,b):
    A,B=" ".join(tu(a))," ".join(tu(b))
    return 1-difflib.SequenceMatcher(None,A,B).ratio()

MOI=moi_tu_vung("nam")
print(f"{'#':>3} {'giây':>5} {'mảnh':>4} {'â.tiết/ph':>9} {'CER':>6}  câu")
print("-"*104)
dat=0; nhip=[]; xau=[]
for i,c in enumerate(CAU,1):
    b64,j=sinh(c,i)
    if b64 is None: print(f"{i:>3}  LỖI {j.get('error','')[:70]}"); continue
    mong=normalize_for_tts(c); ra=nghe(b64,MOI)
    e=cer(mong,ra); giay=j["duration_ms"]/1000
    ampm=len(tu(mong))/giay*60 if giay else 0
    nhip.append(ampm); ok=e<=0.05; dat+=ok
    print(f"{i:>3} {giay:5.2f} {j['so_manh']:>4} {ampm:9.0f} {e*100:5.1f}% {'✓' if ok else '✗'} {c[:62]}")
    if not ok:
        m,t=lech(mong,ra)
        xau.append((i,c,mong,ra,m,t))
print("-"*104)
print(f"ĐỌC ĐÚNG {dat}/{len(CAU)} câu (CER ≤ 5%)   nhịp {min(nhip):.0f}-{max(nhip):.0f} "
      f"âm tiết/phút, trung bình {sum(nhip)/len(nhip):.0f}")
if xau:
    print(f"\n{len(xau)} câu lệch:")
    for i,c,mong,ra,m,t in xau:
        print(f"\n  {i}. viết  : {c}")
        print(f"     F5 đọc: {mong}")
        print(f"     nghe  : {ra}")
        print(f"     mất={m} thừa={t}")
print(f"\nFile wav: {RA}")
