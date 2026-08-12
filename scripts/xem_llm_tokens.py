import re, sys, statistics as st
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:/duan/chat-ai")
from backend.config import settings
print(f"  llm_max_tokens cau hinh: {getattr(settings, 'llm_max_tokens', '(khong co)')}")
L = Path(r"C:/duan/chat-ai/logs/backend.log")
tho = L.read_bytes().decode("utf-8", "replace").splitlines()
tok = [int(m.group(1)) for l in tho[-3000:] if (m := re.search(r"(\d+)\s*tokens?\b", l))]
ttfa = [int(m.group(1)) for l in tho[-3000:] if (m := re.search(r"TTFA[= ]+(\d+)", l))]
if tok: print(f"  token moi luot   : trung vi {st.median(tok):.0f}, to nhat {max(tok)}  (n={len(tok)})")
if ttfa: print(f"  TTFA trong log   : trung vi {st.median(ttfa):.0f}ms, to nhat {max(ttfa)}ms")
for l in tho[-3000:]:
    if "tokens" in l and "chunks" in l:
        print(f"  vi du: {l[-110:]}"); break
