"""Tong thoi gian sinh TTS cua tung cuoc goi, tach theo lan khoi dong backend."""
import re, sys, statistics as st
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
tho = Path(r"C:/duan/chat-ai/logs/backend.log").read_bytes().decode("utf-8","replace").splitlines()
RE = re.compile(r"TTS \[([^\]]+)\]: '.*?\.\.\.' -> \d+ms audio \((\d+)ms\)")
# moc phan cach: moi lan khoi dong backend
moc = [i for i, l in enumerate(tho) if "Loading F5-TTS" in l]
if len(moc) < 2:
    print("  can it nhat 2 lan khoi dong trong log"); sys.exit()
for nhan, a, b in (("A: KHONG ham", moc[-2], moc[-1]), ("B: CO ham", moc[-1], len(tho))):
    t = [int(m.group(2)) for l in tho[a:b] if (m := RE.search(l))]
    if not t: continue
    # bo phan ham nong (no chay ngay sau khoi dong, truoc cuoc goi)
    print(f"\n  {nhan}: {len(t)} lan sinh")
    print(f"    tong {sum(t)/1000:.2f}s | trung vi {st.median(t):.0f}ms | to nhat {max(t)}ms")
    print(f"    so lan > 450ms: {sum(1 for x in t if x > 450)} ({sum(1 for x in t if x>450)/len(t)*100:.0f}%)")
