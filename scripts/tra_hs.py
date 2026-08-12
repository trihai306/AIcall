import asyncio, sys
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
from backend.services import data_source_service as D
try:
    ra = D.tra_ho_so("0912345678")
except AttributeError:
    fns = [x for x in dir(D) if "tra" in x.lower() or "look" in x.lower()]
    print("  ham co san:", fns)
    ra = None
if ra is not None:
    print("  ho so:", str(ra)[:600])
