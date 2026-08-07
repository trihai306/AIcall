import io, re, sys
sys.stdout.reconfigure(encoding="utf-8")
lines = io.open(r"C:\duan\chat-ai\logs\backend.log", encoding="utf-8", errors="replace").read().splitlines()
keys = ("Đã nghĩ sẵn", "dùng bản đã nghĩ", "KHÔNG dùng được", "TTFA=", "AI bắt đầu nói",
        "STT result", "RAG: dùng lại", "RAG: đoán trượt", "Turn complete")
out = []
for l in lines:
    if any(k in l for k in keys):
        t = l.split("|")[0].strip()
        body = re.sub(r'^\S+\s*\|\s*\w+\s*\|\s*[\w.]+\s*\|\s*', '', l).strip()
        out.append((t, body))
for t, b in out[-26:]:
    print("%s  %s" % (t, b[:150]))
