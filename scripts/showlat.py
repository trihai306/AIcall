import io, re, sys
sys.stdout.reconfigure(encoding="utf-8")
lines = io.open(r"C:\duan\chat-ai\logs\backend.log", encoding="utf-8", errors="replace").read().splitlines()
keys = ("TTFA=", "Turn complete", "AI bắt đầu nói", "Đường text")
out = [l for l in lines if any(k in l for k in keys)]
for l in out[-9:]:
    print(re.sub(r'^\S+\s*\|\s*\w+\s*\|\s*[\w.]+\s*\|\s*', '', l))
