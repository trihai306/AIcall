"""Sau khi qua hàng rào chặn số, khách nghe được con số nào?

Đo ĐÚNG thứ tới tai khách: đầu ra thô của LLM -> `chan_so_sai` -> so với tài liệu.
"""
import asyncio
import re
import sys

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")

HOI = "lãi suất vay tín chấp bao nhiêu"
RAG = ("# Vay Tín Chấp Cá Nhân\n- Lãi suất: từ 7.9%/năm\n"
       "- Hạn mức: lên đến 500 triệu đồng\n- Thời hạn: 12 - 60 tháng")
DUNG = re.compile(r"7[.,]9|bảy\s+phẩy\s+chín", re.I)
SO = re.compile(r"(\d+[.,]\d+)|((?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín)\s+phẩy\s+"
                r"(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín))", re.I)


async def main():
    from backend.config import settings
    from backend.pipeline.text_normalizer import chan_so_sai, normalize_for_tts
    from backend.services.llm_service import LLMService

    llm = LLMService()
    sysp = llm.build_system_prompt(customer_name="Anh Nam",
                                   product="vay tín chấp", rag_context=RAG)
    N = 8
    tho_dung = sau_dung = 0
    print(f"  hỏi {N} lần, temp {settings.llm_temperature}\n")
    print(f"  {'#':>3}  {'LLM nói thô':<26}{'sau hàng rào':<26}")
    print("  " + "-" * 60)
    for i in range(1, N + 1):
        out = ""
        async for t in llm.stream_response([{"role": "user", "content": HOI}], sysp):
            out += t
        sau, sua = chan_so_sai(out, RAG)
        m_tho = SO.search(out)
        m_sau = SO.search(sau)
        tho_dung += bool(DUNG.search(out))
        sau_dung += bool(DUNG.search(sau))
        print(f"  {i:>3}  {(m_tho.group(0) if m_tho else '—'):<26}"
              f"{(m_sau.group(0) if m_sau else '—'):<26}")

    print("  " + "-" * 60)
    print(f"  đúng 7.9%:   thô {tho_dung}/{N}   ->   sau hàng rào {sau_dung}/{N}")

    # nghe ra sao sau khi qua cả bộ đọc số
    vd = "Dạ lãi suất từ 6.9% một năm ạ."
    print(f"\n  ví dụ chuỗi cuối cùng đưa vào TTS:")
    print(f"    LLM   : {vd!r}")
    chan, _ = chan_so_sai(vd, RAG)
    print(f"    chặn  : {chan!r}")
    print(f"    TTS   : {normalize_for_tts(chan)!r}")


asyncio.run(main())
