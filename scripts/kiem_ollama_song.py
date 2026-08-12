import json, sys, time, urllib.request
sys.path.insert(0, r"C:/duan/chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.config import settings
try:
    d = json.dumps({"model": settings.ollama_model, "prompt": "đếm từ 1 đến 5",
                    "stream": False}).encode()
    r = urllib.request.Request(f"{settings.ollama_host}/api/generate", data=d,
                               headers={"Content-Type": "application/json"})
    t0 = time.perf_counter(); g = json.loads(urllib.request.urlopen(r, timeout=120).read())
    print(f"  Ollama OK: {(time.perf_counter()-t0)*1000:.0f}ms, "
          f"{len(g.get('response',''))} ky tu -> phep do tranh GPU HOP LE")
except Exception as e:
    print(f"  Ollama LOI: {str(e)[:80]} -> phep do tranh GPU KHONG hop le")
