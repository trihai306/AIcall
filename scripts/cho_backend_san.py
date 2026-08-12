import json, sys, time, urllib.request
t0 = time.time()
while time.time() - t0 < 420:
    try:
        d = json.loads(urllib.request.urlopen("http://127.0.0.1:8100/api/health", timeout=5).read())
        if d.get("services", {}).get("tts") == "loaded":
            print(f"TTS da nap sau {time.time()-t0:.0f}s"); sys.exit(0)
    except Exception:
        pass
    time.sleep(5)
print("HET GIO CHO"); sys.exit(1)
