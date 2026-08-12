"""TTS cham di bao nhieu khi Ollama dang sinh chu cung luc?

Log cho thay manh dau luot ton 700-1141ms trong khi manh giua luot chi 293ms.
Manh dau luot sinh DUNG LUC Ollama con dang chay. Do doi chung.
"""
import asyncio, io, json, sys, time, threading, urllib.request, statistics as st
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import soundfile as sf
from backend.config import settings
from backend.services.tts_service import F5TTSService

CAU = ["anh cần chuẩn bị chứng minh", "nhân dân sổ hộ khẩu và",
       "sao kê lương ba tháng", "gần nhất anh nhé ạ"]
LAP = 4

DEM = [0]
def dot_ollama(dung: threading.Event):
    """Bat Ollama sinh lien tuc cho toi khi bao dung."""
    while not dung.is_set():
        try:
            d = json.dumps({"model": settings.ollama_model,
                            "prompt": "Viết một đoạn tư vấn vay tín chấp dài 300 từ.",
                            "stream": False}).encode()
            r = urllib.request.Request(f"{settings.ollama_base_url}/api/generate", data=d,
                                       headers={"Content-Type": "application/json"})
            urllib.request.urlopen(r, timeout=120).read(); DEM[0] += 1
        except Exception as e:
            print(f"    [Ollama LOI] {str(e)[:70]}"); return

async def do(svc, ten):
    t = []
    for c in CAU * LAP:
        t0 = time.perf_counter()
        await svc.synthesize(c, voice=ten, use_cache=False)
        t.append((time.perf_counter() - t0) * 1000)
    return t

async def main():
    svc = F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    await svc.synthesize("hâm nóng", voice=ten, use_cache=False)
    ranh = await do(svc, ten)
    dung = threading.Event()
    th = threading.Thread(target=dot_ollama, args=(dung,), daemon=True); th.start()
    await asyncio.sleep(3)
    ban = await do(svc, ten)
    dung.set()
    print(f"\n  Ollama da sinh xong {DEM[0]} luot trong luc do")
    print(f"\n  {'':<22} {'trung vi':>10} {'to nhat':>9}")
    print("  " + "-"*44)
    print(f"  {'GPU ranh':<22} {st.median(ranh):>9.0f}ms {max(ranh):>8.0f}ms")
    print(f"  {'Ollama dang sinh':<22} {st.median(ban):>9.0f}ms {max(ban):>8.0f}ms")
    print("  " + "-"*44)
    print(f"\n  cham di {st.median(ban)/st.median(ranh):.2f} lan khi tranh GPU")
asyncio.run(main())
