"""Con số 6.5% đến từ đâu: prompt, RAG, hay ĐÃ NUNG VÀO MÔ HÌNH?

Thử tách bằng cách bỏ dần: hỏi mô hình với prompt TỐI GIẢN, không ví dụ, không
gì ngoài một dòng RAG ghi rõ 7.9%. Nếu vẫn ra 6.5% thì số đó nằm trong trọng số
mô hình (bị fine-tune vào), không sửa được bằng prompt.
"""
import asyncio
import sys

sys.path.insert(0, "C:/duan/chat-ai")
sys.stdout.reconfigure(encoding="utf-8")


async def main():
    from backend.config import settings
    from backend.services.llm_service import LLMService, SYSTEM_PROMPT_TEMPLATE

    print(f"  model đang dùng: {settings.ollama_model}")
    print(f"  prompt có chứa 'sáu phẩy năm': "
          f"{'CÓ - chưa đổi!' if 'sáu phẩy năm' in SYSTEM_PROMPT_TEMPLATE else 'KHÔNG (đã sửa)'}")

    llm = LLMService()
    HOI = "lãi suất vay tín chấp bao nhiêu"

    thu = {
        "A. prompt TỐI GIẢN + RAG ghi rõ 7.9":
            "Bạn là nhân viên ngân hàng. Trả lời NGẮN, chỉ dùng số trong tài liệu.\n"
            "TÀI LIỆU: Vay tín chấp - Lãi suất: từ 7.9%/năm. Hạn mức 500 triệu.",
        "B. prompt TỐI GIẢN + CẤM số khác":
            "Bạn là nhân viên ngân hàng. Lãi suất vay tín chấp là 7.9%/năm. "
            "TUYỆT ĐỐI không nói con số nào khác.",
        "C. hỏi thẳng, không tài liệu":
            "Bạn là nhân viên ngân hàng ABC.",
        "D. prompt THẬT của hệ thống":
            llm.build_system_prompt(
                customer_name="Anh Nam", product="vay tín chấp",
                rag_context="# Vay Tín Chấp Cá Nhân\n- Lãi suất: từ 7.9%/năm\n"
                            "- Hạn mức: lên đến 500 triệu đồng"),
    }

    for ten, sysp in thu.items():
        out = ""
        async for t in llm.stream_response([{"role": "user", "content": HOI}], sysp):
            out += t
        co65 = "sáu phẩy năm" in out or "6.5" in out or "6,5" in out
        co79 = "bảy phẩy chín" in out or "7.9" in out or "7,9" in out
        dau = "!! vẫn 6.5" if co65 else ("OK 7.9" if co79 else "không nêu số")
        print(f"\n  [{ten}]")
        print(f"     -> {out.strip()[:110]!r}")
        print(f"     {dau}")


asyncio.run(main())
