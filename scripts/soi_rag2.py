import asyncio, sys
sys.path.insert(0, r"C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")
from backend.services.rag_service import RAGService
r = RAGService(); r.load()
for q in ["vay tín chấp hạn mức tối đa bao nhiêu", "hạn mức vay tín chấp"]:
    print(f"\n  === {q} ===")
    ra = asyncio.run(r.retrieve(q, top_k=3, san_pham="vay tín chấp"))
    print("  " + (ra[:700].replace("\n", "\n  ") if ra else "KHONG CO KET QUA"))
