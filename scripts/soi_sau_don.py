import sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
D=Path(r"C:\duan\chat-ai\data\fillers_wav")
tong=list(D.rglob("*.wav"))
print(f"tệp câu đệm trên đĩa: {len(tong)}")
for g in sorted({p.parts[len(D.parts)] for p in tong}):
    n=[p for p in tong if p.parts[len(D.parts)]==g]
    vt={p.stem.split('__')[-1] for p in n}
    print(f"   {g:<12} {len(n):>5} tệp, {len(vt):>5} vân tay")
L=Path(r"C:\duan\chat-ai\logs\backend.log")
if L.exists():
    for l in L.read_text(encoding="utf-8",errors="replace").splitlines():
        if "Câu đệm" in l and ("dọn" in l or "tổng" in l): print("   log:", l[-110:])
