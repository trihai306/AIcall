"""Chenh lech do dai bao nhieu lan trong mot lo thi bat dau hong?

Do bang cach ghep mot manh NGAN co dinh voi mot manh dai dan.
"""
import asyncio, difflib, io, json, re, sys, unicodedata, urllib.request
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.services.tts_service import F5TTSService, so_am_tiet
from backend.pipeline.text_normalizer import normalize_for_tts

NGAN = "dạ vâng ạ em nghe"
BAN = ["anh cần chuẩn bị giấy",                                        # ~5
       "anh cần chuẩn bị chứng minh nhân dân và sổ",                   # ~9
       "anh cần chuẩn bị chứng minh nhân dân sổ hộ khẩu cùng sao kê lương",   # ~14
       "anh cần chuẩn bị chứng minh nhân dân sổ hộ khẩu cùng sao kê lương ba tháng gần nhất của mình nhé"]  # ~20
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
    n_ngan = so_am_tiet(normalize_for_tts(NGAN))
    le = await svc.synthesize(NGAN, voice=ten, use_cache=False)
    print(f"\n  mảnh ngắn {n_ngan} âm tiết, sinh lẻ: {diem(NGAN, le):.0f}% giống\n")
    print(f"  {'âm tiết dài':>12} {'tỉ lệ':>7} {'ngắn':>7} {'dài':>7}")
    print("  " + "-"*38)
    for b in BAN:
        n = so_am_tiet(normalize_for_tts(b))
        ra = await svc.synthesize_nhieu([NGAN, b], voice=ten)
        print(f"  {n:>12} {n/n_ngan:>6.1f}x {diem(NGAN, ra[0]):>6.0f}% {diem(b, ra[1]):>6.0f}%")
    print("  " + "-"*38)
asyncio.run(main())
