import re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
L=Path(r"C:\duan\chat-ai\logs")
KHOA=("phone","goi","dial","uplink","tiem","cau tieng","AudioTrack","adb","call",
      "duong_tieng","mixer","ABOX","SIFS")
for f in sorted(L.glob("*.log"), key=lambda p:p.stat().st_mtime, reverse=True)[:2]:
    t=f.read_text(encoding="utf-8",errors="replace").splitlines()
    d=[l for l in t if any(k.lower() in l.lower() for k in KHOA)]
    print(f"--- {f.name}: {len(t)} dòng, {len(d)} dòng liên quan")
    for l in d[-30:]: print("  ", l[-140:])
