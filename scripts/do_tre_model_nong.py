"""Độ trễ THẬT của từng model, đo khi model ĐÃ NÓNG.

Số đo trong `so_model_tra_loi.py` không dùng được để so tốc độ: Ollama phải nạp
lại model mỗi lần đổi tên, nên lượt đầu của mỗi model gánh cả thời gian nạp
(đo được 32 giây). Script này làm nóng trước rồi mới bấm giờ.

Đo cả TTFT (chữ đầu tiên ra) vì đó mới là thứ khách cảm nhận - đường thoại phát
tiếng ngay khi có mảnh chữ đầu, không chờ hết câu.

Chạy TRÊN MÁY WIN:  python scripts\\do_tre_model_nong.py
"""

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CAU = ["lãi suất bao nhiêu", "anh cần vay năm mươi triệu",
       "vay bao lâu thì được", "cần giấy tờ gì", "phí trả trước hạn sao"]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", nargs="+",
                    default=["tuvan-qwen", "qwen2.5:3b", "vistral-7b-chat"])
    a = ap.parse_args()

    from backend.config import settings
    from backend.pipeline.session_manager import CallSession
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService

    rag = RAGService()
    ss = CallSession(customer_name="Anh", product="vay tín chấp")
    ctx = await rag.retrieve("vay tín chấp lãi suất", top_k=2, san_pham=ss.product)

    print(f"\n  {'model':<20} {'TTFT trung vị':>14} {'trọn câu':>10} {'chữ':>6}")
    for ten in a.model:
        settings.ollama_model = ten
        llm = LLMService()
        llm.model = ten
        sysp = llm.build_system_prompt(customer_name=ss.customer_name,
                                       product=ss.product, rag_context=ctx)

        # LÀM NÓNG - bỏ hẳn lượt này, nó gánh thời gian nạp model vào VRAM
        try:
            async for _ in llm.stream_response([{"role": "user", "content": "xin chào"}],
                                               sysp):
                pass
        except Exception as e:
            print(f"  {ten:<20} <không chạy được: {e}>")
            continue

        ttft, tron, chu = [], [], []
        for c in CAU:
            t0 = time.perf_counter()
            dau = None
            n = 0
            async for tok in llm.stream_response([{"role": "user", "content": c}], sysp):
                if dau is None:
                    dau = (time.perf_counter() - t0) * 1000
                n += len(tok)
            ttft.append(dau or 0)
            tron.append((time.perf_counter() - t0) * 1000)
            chu.append(n)
        print(f"  {ten:<20} {statistics.median(ttft):>11.0f}ms "
              f"{statistics.median(tron):>8.0f}ms {statistics.median(chu):>6.0f}")

    print("\n  Ngân sách của hệ thống: TTFA ~1000ms cho CẢ lượt (STT+RAG+LLM+TTS).")
    print("  LLM ăn hết bao nhiêu ở cột TTFT - phần còn lại chia cho STT và TTS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
