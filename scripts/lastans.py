import io, re, sys
sys.stdout.reconfigure(encoding="utf-8")
lines = io.open(r"C:\duan\chat-ai\logs\backend.log", encoding="utf-8", errors="replace").read().splitlines()
# gom cac dong TTS de dung lai cau tra loi
cur, outs = [], []
for l in lines:
    m = re.search(r"TTS \[[^\]]+\]: '(.+?)\.\.\.' ->", l)
    if "Turn complete" in l:
        if cur: outs.append(" | ".join(cur)); cur = []
    elif m and "filler" not in l:
        cur.append(m.group(1))
for o in outs[-3:]:
    print("  ->", o[:220]); print()
