"""Tieng sinh THEO LO co giong tieng sinh LE khong? STT lam trong tai.

Nhanh ma sai thi vo nghia. Kiem ba thu:
  1. do dai tung manh co khop nhau khong
  2. STT nghe lai co ra dung chu khong
  3. co manh nao cut/rong khong
"""
import asyncio, difflib, io, json, re, sys, unicodedata, urllib.request
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.services.tts_service import F5TTSService

MANH = ["dạ vâng ạ em nghe", "anh cần chuẩn bị chứng minh", "nhân dân và sổ hộ",
        "khẩu bản sao công chứng", "sao kê lương ba tháng", "gần nhất của anh ạ",
        "em sẽ hỗ trợ anh", "làm hồ sơ ngay nhé"]
STT = "http://127.0.0.1:8178/inference"
def nghe(b):
    bd = b"----x"
    body = (b"--"+bd+b"\r\nContent-Disposition: form-data; name=\"file\"; "
            b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"+b+b"\r\n--"+bd+b"--\r\n")
    r = urllib.request.Request(STT, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r, timeout=300).read()).get("text","").strip()
def chuan(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",re.sub(r"[^\w\s]"," ",s)).strip()
def dai(b):
    x, sr = sf.read(io.BytesIO(b), dtype="float32"); return len(x)/sr

async def main():
    svc = F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    le = [await svc.synthesize(m, voice=ten, use_cache=False) for m in MANH]
    lo = await svc.synthesize_nhieu(MANH, voice=ten)
    print(f"\n  {'lẻ':>8} {'lô':>8} {'lệch':>7} {'STT lẻ':>8} {'STT lô':>8}  chữ")
    print("  " + "-"*72)
    ok = True
    for m, a, b in zip(MANH, le, lo):
        da, db = dai(a), dai(b)
        ta, tb = nghe(a), nghe(b)
        ga = difflib.SequenceMatcher(None, chuan(m).split(), chuan(ta).split()).ratio()*100
        gb = difflib.SequenceMatcher(None, chuan(m).split(), chuan(tb).split()).ratio()*100
        xau = abs(da-db)/max(da,db) > 0.25 or gb < 70
        if xau: ok = False
        print(f"  {da:>7.2f}s {db:>7.2f}s {abs(da-db)/max(da,db)*100:>6.0f}% "
              f"{ga:>7.0f}% {gb:>7.0f}%  {m[:22]}{'  <== NGO' if xau else ''}")
    print("  " + "-"*72)
    print(f"\n  tong le {sum(dai(x) for x in le):.2f}s | tong lo {sum(dai(x) for x in lo):.2f}s")
    print(f"  ket luan: {'GIONG NHAU, dung duoc' if ok else 'CO VAN DE'}")
asyncio.run(main())
