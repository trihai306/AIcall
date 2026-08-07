"""Máy này gánh được mấy cuộc gọi CÙNG LÚC?

Câu hỏi thật là "chạy 2 máy điện thoại song song có kịp không", và nó KHÔNG phải
câu hỏi về VRAM: hai cuộc gọi dùng chung một bản model, bộ nhớ gần như không tăng.
Cái tăng là THỜI GIAN CHỜ, vì các khâu nặng đều nối đuôi nhau.

Chỗ nghẽn đã biết trước khi đo:
  - F5-TTS chạy trong ThreadPoolExecutor `max_workers=1` -> mọi mảnh tiếng của
    MỌI cuộc gọi xếp một hàng.
  - PhoWhisper một bản duy nhất trên GPU.
  - Ollama đặt `OLLAMA_NUM_PARALLEL=2` nên riêng LLM chịu được 2.

Đo: cho N phiên cùng chạy một lượt hội thoại đầy đủ (RAG -> LLM -> cắt mảnh ->
TTS từng mảnh) và chấm TTFA - thời gian từ lúc "khách dứt lời" tới lúc có mảnh
tiếng ĐẦU TIÊN. Đó là con số khách cảm nhận được, và trần của dự án là 1000ms.

    python scripts/do_hai_cuoc_cung_luc.py
    python scripts/do_hai_cuoc_cung_luc.py --muc 1 2 3
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

TRAN_MS = 1000.0
CAU = [
    "lãi suất bao nhiêu",
    "vay được tối đa bao nhiêu",
    "cần giấy tờ gì không",
    "bao lâu thì có tiền",
]
SAN_PHAM = "vay tín chấp"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--muc", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--lap", type=int, default=2, help="mỗi mức chạy mấy vòng")
    # Nới số luồng TTS để xem chỗ nghẽn có thật nằm ở đó không. Thử ở đây
    # TRƯỚC, đừng sửa thẳng production: hai suy luận F5 cùng lúc trên một
    # GPU có thể tranh nhau mà chậm hơn, hoặc tràn VRAM.
    ap.add_argument("--luong-tts", type=int, default=0,
                    help="0 = giữ nguyên, >0 = đặt lại số worker của TTS")
    a = ap.parse_args()

    from backend.config import settings
    from backend.pipeline.text_chunker import should_flush
    from backend.pipeline.text_normalizer import BotLichSu, chan_so_sai
    from backend.services.llm_service import LLMService
    from backend.services.rag_service import RAGService
    from backend.services.tts_service import F5TTSService

    tts = F5TTSService(); tts.load()
    llm, rag = LLMService(), RAGService()
    rag.load()
    if a.luong_tts:
        import concurrent.futures
        tts._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=a.luong_tts)
    giong = await tts.ensure_voice(Path(settings.f5tts_ref_audio).stem)
    await tts.synthesize("khởi động", voice=giong, use_cache=False)   # nạp nóng

    print(f"\n  model {settings.ollama_model} | giọng {giong}")
    print(f"  TTS worker: {tts._executor._max_workers} | trần TTFA {TRAN_MS:.0f}ms\n")

    async def mot_luot(cau: str) -> tuple[float, float, int]:
        """Một lượt đầy đủ. Trả (TTFA ms, tổng ms, số mảnh)."""
        t0 = time.perf_counter()
        ctx = await rag.retrieve(f"{SAN_PHAM} {cau}", top_k=2, san_pham=SAN_PHAM)
        sysp = llm.build_system_prompt(product=SAN_PHAM, rag_context=ctx)
        bot = BotLichSu(bo_da=False)
        buf, manh, ttfa = "", 0, None

        async def phat(doan: str):
            nonlocal ttfa, manh
            sach = bot(chan_so_sai(doan, ctx)[0])
            if not sach:
                return
            await tts.synthesize(sach, fast=(manh == 0), voice=giong,
                                 use_cache=False)
            manh += 1
            if ttfa is None:
                ttfa = (time.perf_counter() - t0) * 1000

        async for tk in llm.stream_response([{"role": "user", "content": cau}], sysp):
            buf += tk
            if should_flush(buf, first_chunk=(manh == 0)):
                doan, buf = buf.strip(), ""
                if doan:
                    await phat(doan)
        if buf.strip():
            await phat(buf.strip())
        return ttfa or -1.0, (time.perf_counter() - t0) * 1000, manh

    print(f"  {'cuộc song song':>16}{'TTFA trung vị':>16}{'TTFA xấu nhất':>16}"
          f"{'tổng lượt':>12}  đánh giá")
    print("  " + "-" * 86)
    for n in a.muc:
        ttfa, tong = [], []
        for _ in range(a.lap):
            ket = await asyncio.gather(*[mot_luot(CAU[i % len(CAU)])
                                         for i in range(n)])
            ttfa += [k[0] for k in ket if k[0] > 0]
            tong += [k[1] for k in ket]
        tv, xau = statistics.median(ttfa), max(ttfa)
        danh_gia = ("ĐẠT" if xau < TRAN_MS else
                    "trung vị đạt, có lượt vượt trần" if tv < TRAN_MS else "KHÔNG ĐẠT")
        print(f"  {n:>16}{tv:>14.0f}ms{xau:>14.0f}ms"
              f"{statistics.median(tong):>10.0f}ms  {danh_gia}")

    print(f"\n  TTFA = từ lúc khách dứt lời tới mảnh tiếng ĐẦU TIÊN. Vượt {TRAN_MS:.0f}ms")
    print("  thì khách nghe một quãng im trước khi AI nói - đó là lúc người ta")
    print("  tưởng cuộc gọi bị rớt và cúp máy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
