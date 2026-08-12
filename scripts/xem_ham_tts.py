import sys, time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
L = Path(r"C:/duan/chat-ai/logs/backend.log")
t0 = time.time()
while time.time() - t0 < 900:
    tho = L.read_bytes().decode("utf-8", "replace").splitlines()
    for l in reversed(tho[-400:]):
        if "hình dạng" in l or "hinh dang" in l or "TTS lô" in l:
            print(f"  sau {time.time()-t0:.0f}s: {l.strip()[:140]}")
            if "hình dạng" in l and ("đã hâm" in l or "hâm" in l):
                sys.exit(0)
            break
    time.sleep(10)
print("  chua thay dong ham hinh dang")
