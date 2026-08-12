"""Lo tron do dai CHENH NHAU co lam hong tieng khong?

CFM.sample dem moi phan tu toi do dai LON NHAT trong lo. Neu manh 3 am tiet nam
chung lo voi manh 20 am tiet thi no bi dem gap 6 lan. Mask co bao ve, nhung chu
thich trong ma F5 ghi "van con khac biet do cac lop tich chap".

Doi chung: cung mot bo cau, sinh LE / lo DONG DEU / lo TRON LECH.
"""
import asyncio, difflib, io, json, re, sys, unicodedata, urllib.request
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.services.tts_service import F5TTSService
from backend.pipeline.text_normalizer import normalize_for_tts

NGAN = ["dạ vâng ạ", "được anh nhé", "em ghi nhận", "vâng thưa anh"]
DAI  = ["anh chị cần đáp ứng điều kiện là công dân Việt Nam từ hai mươi hai đến sáu mươi tuổi",
        "hồ sơ gồm chứng minh nhân dân sổ hộ khẩu và sao kê lương ba tháng gần nhất của anh",
        "thời gian giải ngân trong vòng hai mươi bốn giờ kể từ khi hồ sơ được phê duyệt xong",
        "hạn mức tối đa cho vay tín chấp bên em hiện tại là năm trăm triệu đồng anh nhé"]
STT = "http://127.0.0.1:8178/inference"
def nghe(b):
    bd=b"----x"
    body=(b"--"+bd+b"\r\nContent-Disposition: form-data; name=\"file\"; "
          b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"+b+b"\r\n--"+bd+b"--\r\n")
    r=urllib.request.Request(STT,data=body,headers={"Content-Type":"multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r,timeout=300).read()).get("text","").strip()
def chuan(s):
    s=unicodedata.normalize("NFD",s.lower()); s="".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",re.sub(r"[^\w\s]"," ",s)).strip()
def diem(chu, b):
    return difflib.SequenceMatcher(None, chuan(normalize_for_tts(chu)).split(),
                                   chuan(nghe(b)).split()).ratio()*100

async def main():
    svc = F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    het = NGAN + DAI
    print(f"\n  {'cách':<22} {'giống TB':>9} {'ngắn':>7} {'dài':>7}")
    print("  " + "-"*50)
    le = [await svc.synthesize(c, voice=ten, use_cache=False) for c in het]
    d = [diem(c, b) for c, b in zip(het, le)]
    print(f"  {'sinh lẻ':<22} {np.mean(d):>8.1f}% {np.mean(d[:4]):>6.1f}% {np.mean(d[4:]):>6.1f}%")
    a = await svc.synthesize_nhieu(NGAN, voice=ten)
    b = await svc.synthesize_nhieu(DAI, voice=ten)
    d2 = [diem(c, x) for c, x in zip(NGAN, a)] + [diem(c, x) for c, x in zip(DAI, b)]
    print(f"  {'lô ĐỒNG ĐỀU':<22} {np.mean(d2):>8.1f}% {np.mean(d2[:4]):>6.1f}% {np.mean(d2[4:]):>6.1f}%")
    tron = [NGAN[0], DAI[0], NGAN[1], DAI[1]]
    tron2 = [NGAN[2], DAI[2], NGAN[3], DAI[3]]
    c1 = await svc.synthesize_nhieu(tron, voice=ten)
    c2 = await svc.synthesize_nhieu(tron2, voice=ten)
    dn = [diem(tron[0],c1[0]), diem(tron[2],c1[2]), diem(tron2[0],c2[0]), diem(tron2[2],c2[2])]
    dd = [diem(tron[1],c1[1]), diem(tron[3],c1[3]), diem(tron2[1],c2[1]), diem(tron2[3],c2[3])]
    print(f"  {'lô TRỘN LỆCH':<22} {np.mean(dn+dd):>8.1f}% {np.mean(dn):>6.1f}% {np.mean(dd):>6.1f}%")
    print("  " + "-"*50)
asyncio.run(main())
