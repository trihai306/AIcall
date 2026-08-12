import asyncio, io, sys
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import soundfile as sf
from backend.config import settings
from backend.services.tts_service import F5TTSService

MUC = {"Anh cần vay tín": 1.22, "Em cảm ơn anh và": 1.53, "chấp thì lãi suất khoảng": 1.47}

async def main():
    svc = F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    print(f"\n  toc_do_cua('giong_heu') = {svc.toc_do_cua('giong_heu')}")
    print(f"  toc_do_cua('default')   = {svc.toc_do_cua('default')}   <== duong THAT tra bang ten nay")
    print(f"  settings.f5tts_speed    = {settings.f5tts_speed}\n")
    print(f"  {'toc':>6} " + " ".join(f"{c[:13]:>14}" for c in MUC))
    print("  " + "-"*54)
    for toc in (0.64, 1.20):
        ra = []
        for c in MUC:
            b = await svc.synthesize(c, voice=ten, speed=toc, use_cache=False)
            x, sr = sf.read(io.BytesIO(b), dtype="float32"); ra.append(len(x)/sr)
        print(f"  {toc:>6.2f} " + " ".join(f"{d:>13.2f}s" for d in ra))
    print("  " + "-"*54)
    print("  backend " + " ".join(f"{v:>13.2f}s" for v in MUC.values()))
asyncio.run(main())
