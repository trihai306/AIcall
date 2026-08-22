import contextlib, sys, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
D=Path(r"C:\Users\Admin\Desktop\Check giọng\Lan 6")
if not D.exists():
    print("không thấy:", D)
    for p in sorted(Path(r"C:\Users\Admin\Desktop\Check giọng").iterdir()):
        print("  có:", repr(p.name))
    sys.exit()
for sub in sorted(D.iterdir(), key=lambda p:p.name):
    print(f"\n=== {sub.name}")
    if not sub.is_dir():
        print("   (tệp)", sub.stat().st_size, "byte"); continue
    for p in sorted(sub.rglob("*")):
        if p.is_dir(): continue
        t=""
        if p.suffix.lower()==".wav":
            with contextlib.suppress(Exception), wave.open(str(p)) as w:
                t=f"  {w.getnframes()/w.getframerate():.2f}s @ {w.getframerate()}Hz"
        print(f"   {p.relative_to(sub)!s:<58} {p.stat().st_size:>8}B{t}")
