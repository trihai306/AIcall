"""Ngu canh cho cau hoi tiet kiem thuc su chua gi?"""
import asyncio, json, sys, urllib.request
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
with urllib.request.urlopen("http://127.0.0.1:8100/api/health",timeout=30) as r: json.load(r)
from backend.pipeline.text_normalizer import chan_lai_suat_bia, _PHAN_TRAM_RE
from backend.services.rag_service import RAGService
print("1) ham chan chay tren may nay chua:")
print("  ", chan_lai_suat_bia("Dạ lãi suất tiết kiệm là 3,8% một năm ạ.", ""))
async def main():
    rag=RAGService(); rag.load()
    print("\n2) san pham co tai lieu:", sorted(rag._san_pham_co_tai_lieu() or []))
    for sp,q in (("tiết kiệm","lãi suất gửi tiết kiệm bao nhiêu"),
                 ("vay tín chấp","lãi suất vay tín chấp bao nhiêu")):
        nc, ct = await rag.retrieve_chi_tiet(q, san_pham=sp)
        m=_PHAN_TRAM_RE.search(nc or "")
        print(f"\n   [{sp}] ngữ cảnh dài {len(nc)} ký tự · có phần trăm: "
              f"{m.group(0) if m else 'KHÔNG'}")
        for c in ct: print(f"      {'BỎ ' if c['bi_loc'] else 'giữ'} {c['nguon']:<20} {c['doan'][:52]!r}")
        if nc: print(f"      nội dung giữ lại: {nc[:120]!r}")
asyncio.run(main())
