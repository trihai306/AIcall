import json, sys, time, urllib.request
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
L = Path(r"C:/duan/chat-ai/logs/backend.log")
t0 = time.time()
while time.time() - t0 < 900:
    try:
        d = json.loads(urllib.request.urlopen("http://127.0.0.1:8100/api/health", timeout=5).read())
        if d.get("services", {}).get("tts") == "loaded":
            tho = L.read_bytes().decode("utf-8", "replace")
            for k in ("đã hâm", "da ham", "hâm hình dạng", "hinh dang"):
                i = tho.rfind(k)
                if i > 0:
                    print(f"  sau {time.time()-t0:.0f}s: {tho[i-60:i+110].splitlines()[-1][:130]}")
                    sys.exit(0)
    except Exception:
        pass
    time.sleep(5)
print("  HET GIO - khong thay dong ham nong"); sys.exit(1)
