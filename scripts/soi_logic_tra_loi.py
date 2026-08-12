"""Lỗi trả lời vớ vẩn nằm ở ĐÂU: đầu vào méo, RAG lấy sai, hay LLM kém?

Cách tách: chạy cùng một bộ câu ở HAI dạng
  a) SẠCH  - gõ đúng chính tả, đúng ý khách muốn hỏi
  b) MÉO   - đúng chuỗi STT trả về trong cuộc gọi thật
Nếu (a) trả lời tốt mà (b) vớ vẩn -> lỗi ở STT, không phải logic.
Nếu cả (a) cũng vớ vẩn -> lỗi ở prompt/RAG/model.

In ra cả tài liệu RAG lấy được, vì trả lời sai chủ đề thường là do RAG kéo nhầm.
"""
import asyncio
import sys

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

CAP = [
    ("cần giấy tờ gì để vay tín chấp",      "cho anh thông tin căn cước"),
    ("lãi suất vay tín chấp bao nhiêu",     "em đồng lâu"),
    ("gửi hồ sơ ở đâu",                     "ở đâu đấy"),
    ("vay được tối đa bao nhiêu tiền",      "vay được bao nhiêu"),
]


async def hoi(llm, rag, cau: str, product: str):
    ctx = ""
    try:
        ctx = await rag.retrieve(cau, top_k=2)
    except Exception as e:
        ctx = f"(RAG lỗi: {e})"
    sysp = llm.build_system_prompt(customer_name="Anh Nam", product=product,
                                   rag_context=ctx)
    out = ""
    async for tok in llm.stream_response([{"role": "user", "content": cau}], sysp):
        out += tok
    return ctx, out.strip()


async def main():
    from backend.config import settings
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService

    llm, rag = LLMService(), RAGService()
    rag.load()
    print(f"  model: {settings.ollama_model} | max_tokens: {settings.llm_max_tokens}"
          f" | temp: {settings.llm_temperature}")

    for sach, meo in CAP:
        print("\n" + "=" * 74)
        for nhan, cau in (("SẠCH", sach), ("MÉO (đúng chuỗi STT thật)", meo)):
            ctx, tl = await hoi(llm, rag, cau, "vay tín chấp")
            print(f"\n  [{nhan}] hỏi: {cau!r}")
            print(f"     RAG lấy: {ctx[:150]!r}")
            print(f"     trả lời: {tl!r}")


asyncio.run(main())
