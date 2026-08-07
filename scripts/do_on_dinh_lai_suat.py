"""Model đọc ĐÚNG lãi suất được bao nhiêu phần trăm số lần?

Con số quan trọng nhất trong nghiệp vụ. Đo được Vistral lúc nói "7.9%/năm", lúc
nói "9%/năm" trên cùng câu hỏi, cùng ngữ cảnh RAG - tức là KHÔNG ỔN ĐỊNH. Một
lần đo không kết luận được, phải hỏi nhiều lần.

Đồng thời kiểm luôn lưới `chan_so_sai` có bắt được số bịa không: đó là chốt chặn
cuối, nếu nó bắt được thì lỗi model bớt nguy hiểm.

Chạy TRÊN MÁY WIN:  python scripts\\do_on_dinh_lai_suat.py
                    python scripts\\do_on_dinh_lai_suat.py --lan 10 --model qwen2.5:3b
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOI = ["lãi suất bao nhiêu", "lãi suất thế nào ạ", "cho anh hỏi lãi suất",
       "vay thì lãi bao nhiêu", "lãi suất một năm là bao nhiêu"]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", nargs="+", default=["vistral-7b-chat"])
    ap.add_argument("--lan", type=int, default=2, help="số vòng lặp qua bộ câu hỏi")
    a = ap.parse_args()

    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.pipeline.text_normalizer import chan_so_sai, sua_xung_ho
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService

    rag = RAGService()
    ss = CallSession(customer_name="Anh", product="vay tín chấp")
    ctx = await rag.retrieve("vay tín chấp lãi suất", top_k=2, san_pham=ss.product)
    print(f"\n  Tài liệu RAG có nhắc tới: "
          f"{'7.9' if '7.9' in ctx else '<KHÔNG THẤY 7.9 — kiểm lại RAG>'}")

    for ten in a.model:
        settings.ollama_model = ten
        llm = LLMService()
        llm.model = ten
        sysp = llm.build_system_prompt(customer_name=ss.customer_name,
                                       product=ss.product, rag_context=ctx)
        dung = chan = sai_lot = 0
        print(f"\n  === {ten} ===")
        for vong in range(a.lan):
            for h in HOI:
                ra = ""
                async for tok in llm.stream_response([{"role": "user", "content": h}],
                                                     sysp):
                    ra += tok
                ra = sua_xung_ho(ra.strip())
                sau, ly_do = chan_so_sai(ra, ctx)
                # PHẢI chặn chữ số phía sau. Bản đầu dùng `"7.9" in ra` nên
                # "7.95%" và "7.92%" - hai con số SAI - bị đếm là đúng, và báo
                # cáo đội lên. Đo sai thì mọi kết luận sau đó vô nghĩa.
                co_79 = bool(re.search(r"7[.,]9(?!\d)", ra)) or \
                    "bảy phẩy chín" in ra.lower()
                if co_79:
                    dung += 1
                    dau = "ĐÚNG"
                elif ly_do:
                    chan += 1
                    dau = "chặn"
                else:
                    sai_lot += 1
                    dau = "SAI LỌT"
                print(f"    {dau:<8} {h:<28} {ra[:70]!r}")
                if ly_do:
                    print(f"             ^ lưới chặn: {ly_do}")
        tong = dung + chan + sai_lot
        print(f"\n    đúng {dung}/{tong} | bị lưới chặn {chan}/{tong} | "
              f"SAI MÀ LỌT {sai_lot}/{tong}")

    print("\n  'SAI MÀ LỌT' là con số đáng sợ duy nhất: số bịa đi thẳng tới khách.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
