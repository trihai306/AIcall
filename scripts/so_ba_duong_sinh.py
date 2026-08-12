"""Cung mot cau, ba duong sinh khac nhau. Do dai tieng ra."""
import asyncio, base64, io, json, sys, urllib.parse, urllib.request
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, soundfile as sf

CAU = ["Em cảm ơn anh và", "điều kiện sau:", "Anh cần vay tín",
       "chấp thì lãi suất khoảng"]

def qua_http(chu, fast=False):
    d = urllib.parse.urlencode({"text": chu, "voice_name": "default",
                                "fast": str(fast).lower()}).encode()
    r = urllib.request.Request("http://127.0.0.1:8100/api/voices/test-tts", data=d,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    g = json.loads(urllib.request.urlopen(r, timeout=180).read())
    if "error" in g: return None, g["error"]
    b = base64.b64decode(g.get("audio") or g.get("audio_base64"))
    x, sr = sf.read(io.BytesIO(b), dtype="float32")
    return len(x)/sr, None

async def main():
    from backend.services.tts_service import F5TTSService
    svc = F5TTSService(); svc.load()
    ten = svc.default_voice_name(); await svc.ensure_voice(ten)
    print(f"\n  {'instance moi':>13} {'backend dang chay':>19}  chu")
    print("  " + "-"*62)
    for c in CAU:
        b = await svc.synthesize(c, voice=ten, use_cache=False)
        x, sr = sf.read(io.BytesIO(b), dtype="float32")
        moi = len(x)/sr
        be, loi = qua_http(c)
        be_s = f"{be:.2f}s" if be else f"loi: {loi}"
        print(f"  {moi:>12.2f}s {be_s:>18}  {c}")
    print("  " + "-"*62)
asyncio.run(main())
