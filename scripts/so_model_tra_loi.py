"""So các model LLM trên ĐÚNG những lượt đã hỏng trong cuộc gọi thật.

Người dùng báo "AI trả lời không thật, chưa thông minh". Trước khi đổi model hay
train lại, phải biết lỗi nằm ở ĐÂU:

  - Model gốc đã kém sẵn?          -> đổi model
  - Bản LoRA làm tệ đi?             -> bỏ LoRA hoặc dựng lại dữ liệu
  - Model chuyên tiếng Việt hơn?    -> đổi sang nó

Bộ câu thử lấy nguyên văn từ bản ghi các cuộc gọi hôm nay, kèm câu trả lời SAI
mà hệ thống đã đưa ra, để chấm được là đã sửa hay chưa.

Chạy TRÊN MÁY WIN:  python scripts\\so_model_tra_loi.py
                    python scripts\\so_model_tra_loi.py --model tuvan-qwen vistral-7b-chat
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# (lời khách, câu SAI đã gặp, điều PHẢI có trong câu đúng)
CA_THU = [
    ("cho anh hỏi khoản vay năm mươi triệu",
     "em xin phép ghi nhận và báo cho chuyên viên khác tư vấn",
     "phải TRẢ LỜI về khoản vay 50 triệu, không đá sang người khác"),
    ("anh cần vay năm mươi triệu",
     "Em đoán có lẽ là hai trăm triệu chứ không phải năm mươi",
     "phải GIỮ đúng con số khách nói, không tự sửa thành số khác"),
    ("tôi muốn vay hai trăm triệu",
     "Dạ được ạ, với khoản vay 200 triệu trong 36 tháng thì anh sẽ trả góp khoảng 6.8 triệu mỗi tháng ạ.",
     "phải GIỮ 200 triệu nhưng KHÔNG tự gán 36 tháng hay 6.8 triệu khi khách chưa nói thời hạn"),
    ("ừ em ở đâu vậy",
     "Dạ em ở TP.HCM ạ (lần trước lại nói Hà Nội)",
     "không được BỊA địa điểm; nói không rõ hoặc hỏi lại thì tốt hơn"),
    ("nghe rõ những gì anh nói không",
     "Dạ em xin lỗi đã làm phiền ạ",
     "đây là câu HỎI, không phải lời từ chối"),
    ("đúng rồi",
     "Anh chị đang gặp khó khăn để trả nợ bên ngoài à ạ?",
     "không được BỊA hoàn cảnh khách chưa hề nói"),
    ("lãi suất bao nhiêu",
     "",
     "phải nói 7.9%/năm theo tài liệu, không bịa số khác"),
]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", nargs="+",
                    default=["tuvan-qwen", "qwen2.5:3b", "vistral-7b-chat"])
    a = ap.parse_args()

    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService

    ss = CallSession(customer_name="Anh", product="vay tín chấp")

    # Khớp đường production: ưu tiên trọn tài liệu sản phẩm để giữ prefix cache;
    # chỉ dùng RAG top-k khi chế độ đó tắt hoặc chưa có tài liệu chuẩn.
    tron = ""
    if settings.ngu_canh_tron_tai_lieu:
        from backend.pipeline.ngu_canh_tai_lieu import toan_van
        tron = toan_van(ss.product)
    rag = None if tron else RAGService()

    # Dựng ngữ cảnh MỘT LẦN, dùng chung cho mọi model - khác ngữ cảnh thì phép
    # so model vô nghĩa.
    ctx = {}
    for khach, _, _ in CA_THU:
        ctx[khach] = (tron if tron else
                      await rag.retrieve(f"vay tín chấp {khach}", top_k=2,
                                         san_pham=ss.product))

    for ten in a.model:
        print(f"\n{'='*78}\n  MODEL: {ten}\n{'='*78}")
        settings.ollama_model = ten
        llm = LLMService()
        llm.model = ten
        for khach, sai, yeu_cau in CA_THU:
            sysp = llm.build_system_prompt(customer_name=ss.customer_name,
                                           product=ss.product,
                                           rag_context=ctx[khach])
            t = time.perf_counter()
            ra = ""
            try:
                async for tok in llm.stream_response(
                        [{"role": "user", "content": khach}], sysp):
                    ra += tok
            except Exception as e:
                ra = f"<lỗi: {e}>"
            ms = (time.perf_counter() - t) * 1000
            # Chạy qua ĐÚNG bộ dọn của đường thật, nếu không thì chấm bản thô
            # rồi kết luận sai về thứ khách thực sự nghe.
            from backend.pipeline.text_normalizer import sua_xung_ho
            don = sua_xung_ho(ra.strip())
            print(f"\n  KHÁCH  {khach!r}")
            print(f"  cần    {yeu_cau}")
            if sai:
                print(f"  đã sai {sai!r}")
            print(f"  thô  {ra.strip()[:170]!r}   ({ms:.0f}ms)")
            if don != ra.strip():
                print(f"  DỌN  {don[:170]!r}")

    print(f"\n{'='*78}")
    print("  Chấm bằng MẮT theo cột 'cần'. Ba lỗi cần soi kỹ nhất:")
    print("    1. có tự đổi con số khách vừa nói không")
    print("    2. có bịa thông tin (địa điểm, hoàn cảnh, lãi suất) không")
    print("    3. có trả lời đúng câu hỏi, hay đá sang chuyện khác")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
