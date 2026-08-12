"""Bao lau de sinh moi manh, va sinh nhanh gap may lan thoi gian phat.

Doc log backend. Dong dang:
    TTS [giong_heu]: 'chu...' -> NNNNms audio (MMMms)
    NNNN = do dai TIENG ra, MMM = thoi gian SINH.
He so realtime = tieng ra / thoi gian sinh. Duoi 1 la sinh khong kip phat.
"""
import re, sys, statistics as st
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
L = Path(r"C:/duan/chat-ai/logs/backend.log")
tho = L.read_bytes().decode("utf-8", "replace").splitlines()
RE = re.compile(r"TTS \[([^\]]+)\]: '(.*?)\.\.\.' -> (\d+)ms audio \((\d+)ms\)")
hang = []
for l in tho[-4000:]:
    m = RE.search(l)
    if m:
        hang.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4))))
if not hang:
    print("  khong thay dong TTS nao"); sys.exit()
hang = hang[-60:]
print(f"\n  {len(hang)} manh gan nhat\n")
print(f"  {'sinh':>7} {'tieng ra':>9} {'nhanh gap':>10}  chu")
print("  " + "-"*66)
he = []
for giong, chu, tieng, sinh in hang:
    r = tieng/max(sinh,1); he.append(r)
    co = "  <== KHONG KIP" if r < 1.0 else ""
    print(f"  {sinh:>6}ms {tieng:>8}ms {r:>9.1f}x  {chu[:26]}{co}")
print("  " + "-"*66)
print(f"\n  thoi gian sinh : trung vi {st.median([h[3] for h in hang]):.0f}ms"
      f"  to nhat {max(h[3] for h in hang)}ms")
print(f"  nhanh gap      : trung vi {st.median(he):.1f}x  cham nhat {min(he):.1f}x")
print(f"  so manh sinh khong kip phat: {sum(1 for r in he if r < 1.0)}")
