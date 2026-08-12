import asyncio, io, sys, time
from pathlib import Path
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf
from backend.services.tts_service import F5TTSService
VAN = ("Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức "
       "lên đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến sáu mươi "
       "tháng, và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm tính trên dư nợ "
       "giảm dần ạ. Anh chị chuẩn bị giúp em chứng minh nhân dân, sổ hộ khẩu và sao kê "
       "lương ba tháng gần nhất thì bên em xử lý rất nhanh ạ.")
RA = Path(r"C:/tmp/ab58"); RA.mkdir(parents=True, exist_ok=True)
svc = F5TTSService(); svc.load()
ten = svc.default_voice_name(); asyncio.run(svc.ensure_voice(ten))
tu = VAN.split()
for n in (5, 8):
    manh, t0 = [], time.perf_counter()
    for i in range(0, len(tu), n):
        c = " ".join(tu[i:i+n])
        b = asyncio.run(svc.synthesize(c, voice=ten))
        x, sr = sf.read(io.BytesIO(b), dtype="float32")
        if x.ndim > 1: x = x.mean(axis=1)
        manh.append(x)
    y = np.concatenate(manh)
    d = float(np.abs(y).max())
    if d > 1.0: y /= d
    p = RA / f"cat_{n}_tu.wav"
    sf.write(p, y, sr)
    print(f"  {n} tu: {len(manh):>2} manh, {len(y)/sr:5.2f}s tieng, sinh {time.perf_counter()-t0:5.2f}s -> {p.name}")
