import asyncio, sys
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
from backend.services.rag_service import RAGService
r = RAGService(); 
try: r.load()
except Exception as e: print("  load:", e)
for q in ["vay tín chấp hạn mức tối đa", "hạn mức vay tín chấp bao nhiêu"]:
    print(f"\n  === {q} ===")
    try:
        ra = r.search(q, top_k=3)
    except Exception as e:
        print("   loi:", e); continue
    if not ra: print("   KHONG co ket qua")
    for x in (ra if isinstance(ra, list) else [ra]):
        t = x if isinstance(x, str) else (x.get("text") or x.get("content") or str(x))
        print("   -", t[:220].replace("\n"," "))
