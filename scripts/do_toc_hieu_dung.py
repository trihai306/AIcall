"""Toc nao cho ra dung do dai ma backend dang tra ve?"""
import asyncio, io, sys
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import soundfile as sf
from backend.config import settings
from backend.services import tts_service as T

MUC = {"Anh cần vay tín": 1.22, "Em cảm ơn anh và": 1.53,
       "chấp thì lãi suất khoảng": 1.47}

async def main():
    svc = T.F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    rw, rs, rt = svc._voices[ten]
    print(f"\n  doan mau : {rw.shape[-1]/rs:.3f}s, {rs} Hz")
    print(f"  ref_text : {rt[:60]!r}")
    print(f"  toc file : {svc.toc_do_cua(ten)}   settings.f5tts_speed = {settings.f5tts_speed}")
    print(f"  HE_SO_BU_LANG = {T.HE_SO_BU_LANG}  NHIP_CHUAN = {T.NHIP_CHUAN_AM_TIET_PHUT}")
    print(f"\n  {'toc':>5} " + " ".join(f"{c[:14]:>15}" for c in MUC))
    print("  " + "-"*56)
    for toc in (0.80, 0.90, 1.00, 1.10, 1.20):
        ra = []
        for c in MUC:
            b = await svc.synthesize(c, voice=ten, speed=toc, use_cache=False)
            x, sr = sf.read(io.BytesIO(b), dtype="float32")
            ra.append(len(x)/sr)
        print(f"  {toc:>5.2f} " + " ".join(f"{d:>14.2f}s" for d in ra))
    print("  " + "-"*56)
    print("  backend  " + " ".join(f"{v:>14.2f}s" for v in MUC.values()))
asyncio.run(main())
