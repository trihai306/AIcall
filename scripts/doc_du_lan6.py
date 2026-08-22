import re, sys, zipfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
D=Path(r"C:\Users\Admin\Desktop\Check giọng\Lan 6")
for sub in sorted(D.iterdir(), key=lambda p:p.name):
    if not sub.is_dir(): continue
    for p in sorted(sub.rglob("*.docx")):
        if p.name.startswith("~$"): continue
        try:
            with zipfile.ZipFile(p) as z: x=z.read("word/document.xml").decode("utf-8")
        except Exception: continue
        x=re.sub(r"</w:p>","\n",x); t=re.sub(r"<[^>]+>","",x).strip()
        print(f"\n### THƯ MỤC {sub.name}")
        for l in [l for l in t.splitlines() if l.strip()]:
            print(f"   {l}")
