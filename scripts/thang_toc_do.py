"""Cung mot doan, cat may moc 5 tu, sinh o nhieu muc toc do de nguoi nghe chon.

Moi muc ra mot tep rieng. KHONG chen nghi gi giua cac manh - noi thang, dung
nhu che do dang chay.
"""
import asyncio, io, sys
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.pipeline.text_chunker import tach_manh
from backend.services.tts_service import F5TTSService

DOAN = ("Dạ anh muốn vay tín chấp thì lãi suất sẽ là từ 7.9%/năm nha anh. "
        "Hạn mức tối đa là năm trăm triệu đồng, còn giấy tờ thì anh chuẩn bị "
        "chứng minh nhân dân, sổ hộ khẩu và sao kê lương ba tháng gần nhất. "
        "Thời gian giải ngân trong vòng 24 giờ sau khi hồ sơ được phê duyệt, "
        "anh yên tâm nhé.")
RA = Path(r"C:/tmp/thangtoc"); RA.mkdir(parents=True, exist_ok=True)

def cat(van):
    ra, dem = [], ""
    for tu in van.split():
        dem = f"{dem} {tu}" if dem else tu
        while True:
            m, dem = tach_manh(dem)
            if m is None: break
            ra.append(m)
    if dem.strip(): ra.append(dem.strip())
    return ra

async def main():
    svc = F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    manh = cat(DOAN)
    print(f"\n  {len(manh)} manh, cat 5 tu, noi thang khong chen nghi")
    print(f"  vi du: {manh[0]!r} | {manh[1]!r} | {manh[2]!r}\n")
    print(f"  {'toc':>5} {'dai':>7} {'am tiet/phut':>13}")
    print("  " + "-"*30)
    for toc in (1.20, 1.30, 1.40, 1.50):
        khuc = []
        for m in manh:
            b = await svc.synthesize(m, voice=ten, speed=toc, use_cache=False)
            x, sr = sf.read(io.BytesIO(b), dtype="float32")
            khuc.append(x.mean(axis=1) if x.ndim > 1 else x)
        y = np.concatenate(khuc)
        sf.write(RA / f"toc_{int(toc*100)}.wav", y / max(1.0, float(np.abs(y).max())), sr)
        am = sum(len(m.split()) for m in manh)
        print(f"  {toc:>5.2f} {len(y)/sr:>6.2f}s {am/(len(y)/sr)*60:>12.0f}")
    print("  " + "-"*30)
    print(f"\n  {RA}")
asyncio.run(main())
