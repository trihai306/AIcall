import sys, wave, contextlib
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
D=Path(r"C:\Users\Admin\Desktop\Check giọng\Lan 5")
if not D.exists():
    for p in Path(r"C:\Users\Admin\Desktop\Check giọng").iterdir():
        print("có thư mục:", repr(p.name))
    sys.exit()
for p in sorted(D.iterdir()):
    t=""
    if p.suffix.lower()==".wav":
        with contextlib.suppress(Exception), wave.open(str(p)) as w:
            t=f"  {w.getnframes()/w.getframerate():.2f}s @ {w.getframerate()}Hz"
    print(f"{p.name!r}  {p.stat().st_size:>9} byte{t}")
