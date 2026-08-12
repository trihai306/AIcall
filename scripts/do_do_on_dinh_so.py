"""Mô hình có nói ĐÚNG lãi suất một cách ỔN ĐỊNH không, và temperature ảnh hưởng sao?

Hỏi cùng một câu N lần ở vài mức temperature, đếm số lần ra đúng 7.9%.
Con số duy nhất đúng nằm trong tài liệu; mọi con số khác đều là bịa.
"""
import asyncio
import re
import sys

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

HOI = "lãi suất vay tín chấp bao nhiêu"
RAG = ("# Vay Tín Chấp Cá Nhân\n- Lãi suất: từ 7.9%/năm\n"
       "- Hạn mức: lên đến 500 triệu đồng\n- Thời hạn: 12 - 60 tháng")

# nhận cả dạng chữ số lẫn chữ viết
DUNG = re.compile(r"7[.,]9|bảy\s+phẩy\s+chín", re.I)
SO_KHAC = re.compile(r"(\d+[.,]\d+)\s*%|"
                     r"((?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\s+phẩy\s+"
                     r"(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín))", re.I)


async def main():
    from backend.config import settings
    from backend.services.llm_service import LLMService

    llm = LLMService()
    sysp = llm.build_system_prompt(customer_name="Anh Nam",
                                   product="vay tín chấp", rag_context=RAG)
    N = 6
    print(f"  model {settings.ollama_model} | hỏi {N} lần mỗi mức\n")
    print(f"  {'temp':>6}{'đúng 7.9':>10}{'sai':>6}  các số nó nói ra")
    print("  " + "-" * 62)

    for temp in (0.7, 0.4, 0.2, 0.0):
        settings.llm_temperature = temp
        llm2 = LLMService()
        dung = 0
        thay = []
        for _ in range(N):
            out = ""
            async for t in llm2.stream_response([{"role": "user", "content": HOI}], sysp):
                out += t
            if DUNG.search(out):
                dung += 1
            else:
                m = SO_KHAC.search(out)
                thay.append((m.group(0) if m else "(không nêu số)").strip())
        print(f"  {temp:>6.1f}{dung:>10}/{N}{N-dung:>6}  {', '.join(thay[:4]) or '—'}")

    settings.llm_temperature = 0.7


asyncio.run(main())
