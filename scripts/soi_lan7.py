import contextlib, re, sys, wave, zipfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
G=Path(r"C:\Users\Admin\Desktop\Check giọng")
print("các thư mục trong Check giọng:")
for p in sorted(G.iterdir()):
    print("  ", repr(p.name))
D=None
for p in G.iterdir():
    if re.search(r"\b7\b", p.name) and p.is_dir(): D=p
if D is None:
    print("\nKHÔNG thấy thư mục nào có số 7"); sys.exit()
print(f"\n=== {D.name}")
for sub in sorted(D.rglob("*")):
    if sub.is_dir():
        print(f"\n  [{sub.relative_to(D)}]"); continue
    t=""
    if sub.suffix.lower()==".wav":
        with contextlib.suppress(Exception), wave.open(str(sub)) as w:
            t=f"  {w.getnframes()/w.getframerate():.2f}s"
    print(f"   {str(sub.relative_to(D)):<64} {sub.stat().st_size:>8}B{t}")
    if sub.suffix.lower()==".docx" and not sub.name.startswith("~$"):
        try:
            with zipfile.ZipFile(sub) as z: x=z.read("word/document.xml").decode("utf-8")
            x=re.sub(r"</w:p>","\n",x); txt=re.sub(r"<[^>]+>","",x).strip()
            for l in [l for l in txt.splitlines() if l.strip()]:
                print(f"      | {l[:150]}")
        except Exception as e:
            print(f"      (không đọc được: {type(e).__name__})")
