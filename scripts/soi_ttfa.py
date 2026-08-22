import re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
t=Path(r"C:\duan\chat-ai\logs\backend.log").read_text(encoding="utf-8",errors="replace")
for l in t.splitlines():
    if "TTFA=" in l and "=" in l:
        print(l[-200:])
print("\n--- các lượt trong cuộc gọi vừa rồi:")
for l in t.splitlines():
    if "Turn complete" in l or "câu trả lời thật sau" in l:
        print("  ", l[-150:])
