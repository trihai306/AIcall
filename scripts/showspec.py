import io, re, sys
sys.stdout.reconfigure(encoding="utf-8")
lines = io.open(r"C:\duan\chat-ai\logs\backend.log", encoding="utf-8", errors="replace").read().splitlines()
keys = ("Đoán trước", "đoán trước", "đoán trượt", "STT", "Turn complete", "TTFA=")
for l in lines[-40:]:
    if any(k in l for k in keys):
        print(re.sub(r'^\S+\s*\|\s*\w+\s*\|\s*[\w.]+\s*\|\s*', '', l))
