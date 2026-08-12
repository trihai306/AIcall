import re, sys, statistics as st
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
tho = Path(r"C:/duan/chat-ai/logs/backend.log").read_bytes().decode("utf-8","replace").splitlines()
RE = re.compile(r"TTS \[([^\]]+)\]: '.*?\.\.\.' -> \d+ms audio \((\d+)ms\)")
moc = [i for i, l in enumerate(tho) if "[6/6]" in l or "Loading F5-TTS" in l]
print(f"  tim thay {len(moc)} lan khoi dong")
khoi = list(zip(moc, moc[1:] + [len(tho)]))
for k, (a, b) in enumerate(khoi[-3:], start=len(khoi)-2):
    t = [int(m.group(2)) for l in tho[a:b] if (m := RE.search(l))]
    ham = any("đã hâm" in l and "hình dạng" in l for l in tho[a:b])
    if not t: 
        print(f"  khoi {k}: khong co lan sinh nao"); continue
    print(f"\n  khối {k} ({'CÓ hâm' if ham else 'không hâm'}): {len(t)} lần sinh")
    print(f"    tổng {sum(t)/1000:.2f}s | trung vị {st.median(t):.0f}ms | >450ms: "
          f"{sum(1 for x in t if x>450)} ({sum(1 for x in t if x>450)/len(t)*100:.0f}%)")
