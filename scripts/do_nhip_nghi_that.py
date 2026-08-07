"""Một vòng ĐOÁN TRƯỚC tốn bao lâu thật, và nhịp 0.4s có với tới được không?

Nhịp đoán đặt 400ms, nhưng `speculate()` có chốt `spec_running`: lượt đoán trước
chưa xong thì mọi cơ hội sau bị bỏ qua. Nên nhịp THẬT = max(400ms, thời gian một
vòng đoán). Nếu một vòng tốn 1.5s thì đặt 400ms hay 800ms cũng như nhau - và
điều chỉnh nhịp là vô nghĩa cho tới khi biết con số này.

Mỗi vòng đoán gồm: STT cả đoạn tiếng từ đầu lượt -> RAG -> LLM sinh trọn câu.
Script đo từng chặng theo ĐỘ DÀI LƯỢT, vì STT phải đọc lại từ đầu mỗi lần nên
chi phí tăng theo độ dài.

Chạy TRÊN MÁY WIN (không qua đường hầm, không thì đo cả độ trễ mạng):

    python scripts\\do_nhip_nghi_that.py
"""

import asyncio
import sys
import time
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


async def main() -> int:
    import soundfile as sf

    from backend.pipeline.session_manager import CallSession
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService
    from backend.services.stt_service import STTService

    goc = PROJECT / "data" / "recordings"
    tep = sorted(goc.rglob("*.opus")) + sorted(goc.rglob("*.wav"))
    if not tep:
        print("  không thấy bản ghi nào")
        return 1
    f = max(tep, key=lambda p: p.stat().st_mtime)
    x, sr = sf.read(str(f), dtype="float32", always_2d=True)
    kh = x[:, 0]

    stt, rag, llm = STTService(), RAGService(), LLMService()
    ss = CallSession(product="vay tín chấp")
    ss.audio_rate = 8000

    print(f"\n  {f.name} | đo trên máy chạy backend\n")
    print(f"  {'lượt dài':>9} {'STT':>7} {'RAG':>7} {'LLM':>8} {'TỔNG':>8}   nhịp thật")
    for giay in (1.5, 3, 5, 8):
        seg = kh[:int(8000 * giay)]
        pcm = (np.clip(seg, -1, 1) * 32767).astype("<i2").tobytes()

        t = time.perf_counter()
        text = (await stt.transcribe(pcm, sample_rate=8000)).strip()
        t_stt = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        ctx = await rag.retrieve(f"vay tín chấp {text}", top_k=2, san_pham=ss.product)
        t_rag = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        sysp = llm.build_system_prompt(customer_name=ss.customer_name,
                                       product=ss.product, rag_context=ctx)
        msgs = [{"role": "user", "content": text or "xin chào"}]
        n = 0
        async for _tok in llm.stream_response(msgs, sysp):
            n += 1
        t_llm = (time.perf_counter() - t) * 1000

        tong = t_stt + t_rag + t_llm
        print(f"  {giay:>7.1f}s {t_stt:>6.0f}ms {t_rag:>6.0f}ms {t_llm:>7.0f}ms"
              f" {tong:>7.0f}ms   {max(400, tong):.0f}ms")

    print("\n  Nhịp thật = max(400ms, tổng một vòng). Lớn hơn 400 nghĩa là chốt")
    print("  `spec_running` đang quyết định nhịp, không phải `_SPEC_STEP_MS`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
