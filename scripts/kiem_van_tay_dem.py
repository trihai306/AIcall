"""Cau dem tren dia co dung van tay cua TOC HIEN TAI khong?"""
import sys
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import urllib.request, json
with urllib.request.urlopen("http://127.0.0.1:8100/api/health",timeout=30) as r: json.load(r)
from backend.services.filler_store import van_tay, PHIEN_BAN
from backend.config import settings
R=Path(r"C:\duan\chat-ai\models\tts\ref_voices")
toc=float((R/"giong_heu.speed").read_text().strip())
ref=(R/"giong_heu.txt").read_text(encoding="utf-8").strip() if (R/"giong_heu.txt").exists() else settings.f5tts_ref_text
print(f"tốc giọng hiện tại = {toc}   nfe = {settings.f5tts_nfe_step}   PHIEN_BAN = {PHIEN_BAN}")
# tim thu muc filler
c=[p for p in Path(r"C:\duan\chat-ai").rglob("*__*.wav") if "filler" in str(p).lower() or "dem" in str(p).lower()]
if not c:
    c=[p for p in Path(r"C:\duan\chat-ai\data").rglob("*__*.wav")] if Path(r"C:\duan\chat-ai\data").exists() else []
if not c:
    for d in Path(r"C:\duan\chat-ai").rglob("*"):
        if d.is_dir() and "filler" in d.name.lower(): print("thư mục:",d); c=list(d.rglob("*.wav")); break
print(f"tệp câu đệm trên đĩa: {len(c)}")
if c:
    print("thư mục:", c[0].parent.parent)
    vts={p.stem.split("__")[-1] for p in c}
    print(f"số vân tay khác nhau trên đĩa: {len(vts)}")
    # dung mot cau dem that de tinh van tay mong doi
    from backend.services import filler_store as FS
    print("ví dụ tên tệp:", c[0].name)
