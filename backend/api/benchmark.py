import base64
import logging
import time
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings
from backend.core.logging_config import Timer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])

TEST_PHRASES = [
    "Lãi suất vay mua nhà hiện tại là bao nhiêu?",
    "Tôi muốn mở thẻ tín dụng, cần những gì?",
    "Cho tôi hỏi về chương trình vay tín chấp ưu đãi",
    "Thủ tục vay vốn kinh doanh như thế nào?",
    "Dạ anh ơi, hiện bên em đang có chương trình vay ưu đãi lãi suất chỉ từ bảy phẩy chín phần trăm một năm",
]


class BenchmarkResult(BaseModel):
    stt_ms: float = 0
    llm_ttft_ms: float = 0
    llm_full_ms: float = 0
    tts_ms: float = 0
    rag_ms: float = 0
    total_ms: float = 0
    text_input: str = ""
    llm_output: str = ""
    tts_audio_duration_ms: float = 0


@router.get("/info")
async def benchmark_info():
    """Tên MODEL ĐANG CHẠY THẬT cho từng khâu, để trang Benchmark hiện đúng.

    Trước đây nhãn ghi cứng trong HTML ("STT — Whisper", "LLM — Qwen2.5"). Đổi
    model xong thì nhãn vẫn nguyên, và người đọc số tin rằng mình đang đo cái
    khác với thứ thật sự chạy - kiểu sai nguy hiểm vì nó nhìn như đúng.
    """
    from pathlib import Path as _P

    from backend.main import app_state

    giong = ""
    try:
        giong = _P(settings.f5tts_ref_audio).stem
    except Exception:
        pass

    # HỎI THẲNG máy chủ STT xem nó nạp model nào. `settings.whisper_model` chỉ là
    # giá trị mặc định trong config, không phải thứ đang chạy - đổi model xong là
    # hai bên lệch nhau, mà kiểu sai đó nhìn như đúng.
    ten_stt = "STT — (không hỏi được máy chủ)"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as c:
            h = (await c.get(f"{settings.whisper_server_url}/health")).json()
        ten_stt = f"STT — {h.get('model') or settings.whisper_model}"
    except Exception:
        ten_stt = f"STT — {settings.whisper_model} (chưa xác nhận)"

    return {
        "stt": ten_stt,
        "llm": f"LLM — {app_state.llm.model}",
        "tts": f"TTS — F5-TTS · giọng {giong}" if giong else "TTS — F5-TTS",
        "rag": f"RAG — ChromaDB · {settings.embedding_model.split('/')[-1]}",
    }


@router.post("/stt")
async def benchmark_stt():
    """Benchmark STT with a test audio file."""
    from backend.main import app_state

    stt_ok = await app_state.stt.health_check()
    if not stt_ok:
        return {"error": "Whisper STT server chưa chạy. Chạy: bash whisper_server/start.sh"}

    # Lấy ĐÚNG giọng mẫu đang cấu hình, đừng trỏ cứng vào "default.wav" - file đó
    # không tồn tại nên trang Đo tốc độ luôn hiện lỗi ở ô STT.
    test_audio_path = Path(settings.f5tts_ref_audio)
    if not test_audio_path.exists():
        co = sorted(test_audio_path.parent.glob("*.wav"))
        if not co:
            return {"error": f"Không có file .wav nào trong {test_audio_path.parent}"}
        test_audio_path = co[0]

    audio_bytes = test_audio_path.read_bytes()

    try:
        with Timer("benchmark-stt") as t:
            text = await app_state.stt.transcribe(audio_bytes)
        return {"text": text, "latency_ms": round(t.elapsed_ms), "status": "ok"}
    except Exception as e:
        return {"error": f"STT lỗi: {e}"}


@router.post("/llm")
async def benchmark_llm():
    """Benchmark LLM TTFT and full generation."""
    from backend.main import app_state

    llm_ok = await app_state.llm.health_check()
    if not llm_ok:
        return {"error": "Ollama LLM chưa chạy. Chạy: ollama serve && ollama pull qwen2.5:3b"}

    prompt = "Lãi suất vay mua nhà bao nhiêu?"
    system = app_state.llm.build_system_prompt()
    messages = [{"role": "user", "content": prompt}]

    try:
        tokens = []
        t_start = time.perf_counter()
        ttft = 0

        async for token in app_state.llm.stream_response(messages, system):
            if not tokens:
                ttft = (time.perf_counter() - t_start) * 1000
            tokens.append(token)

        total = (time.perf_counter() - t_start) * 1000
        response = "".join(tokens)

        return {
            "prompt": prompt,
            "response": response,
            "ttft_ms": round(ttft),
            "total_ms": round(total),
            "tokens": len(tokens),
            "tokens_per_sec": round(len(tokens) / (total / 1000), 1) if total > 0 else 0,
        }
    except Exception as e:
        return {"error": f"LLM lỗi: {e}"}


@router.post("/tts")
async def benchmark_tts():
    """Benchmark TTS for multiple phrases."""
    from backend.main import app_state

    if not app_state.tts._is_loaded:
        return {"error": "F5-TTS chưa được cài. Chạy: bash scripts/install/04_f5tts.sh && pip install -e tools/F5-TTS-Vietnamese"}

    try:
        results = []
        for phrase in TEST_PHRASES[:3]:
            # use_cache=False BẮT BUỘC. Để mặc định thì lần bấm thứ hai trở đi
            # lấy lại bản đã lưu và báo ~0ms - trang Đo tốc độ hiện một con số
            # đẹp mà vô nghĩa, và đã có người tin theo nó.
            with Timer("benchmark-tts") as t:
                wav_bytes = await app_state.tts.synthesize(phrase, use_cache=False)

            results.append({
                "text": phrase,
                "latency_ms": round(t.elapsed_ms),
                "audio_size_kb": round(len(wav_bytes) / 1024, 1),
            })

        avg_ms = sum(r["latency_ms"] for r in results) / len(results)
        return {"results": results, "avg_latency_ms": round(avg_ms)}
    except Exception as e:
        return {"error": f"TTS lỗi: {e}"}


@router.post("/rag")
async def benchmark_rag():
    """Benchmark RAG retrieval."""
    from backend.main import app_state

    try:
        query = "lãi suất vay mua nhà"
        with Timer("benchmark-rag") as t:
            context = await app_state.rag.retrieve(query, top_k=3)

        return {
            "query": query,
            "context_length": len(context),
            "context_preview": context[:200] if context else "(trống)",
            "latency_ms": round(t.elapsed_ms),
        }
    except Exception as e:
        return {"error": f"RAG lỗi: {e}"}


@router.post("/full")
async def benchmark_full_pipeline():
    """Benchmark full pipeline: RAG -> LLM -> TTS (skip unavailable)."""
    from backend.main import app_state

    llm_ok = await app_state.llm.health_check()
    if not llm_ok:
        return {"error": "Ollama LLM chưa chạy. Cần LLM để chạy full pipeline."}

    try:
        results = []

        for phrase in TEST_PHRASES[:3]:
            result = BenchmarkResult(text_input=phrase)
            t_total_start = time.perf_counter()

            # RAG
            with Timer("rag") as t_rag:
                rag_context = await app_state.rag.retrieve(phrase, top_k=3)
            result.rag_ms = round(t_rag.elapsed_ms)

            # LLM
            system = app_state.llm.build_system_prompt(rag_context=rag_context)
            messages = [{"role": "user", "content": phrase}]
            tokens = []
            t_llm_start = time.perf_counter()

            async for token in app_state.llm.stream_response(messages, system):
                if not tokens:
                    result.llm_ttft_ms = round((time.perf_counter() - t_llm_start) * 1000)
                tokens.append(token)

            result.llm_full_ms = round((time.perf_counter() - t_llm_start) * 1000)
            result.llm_output = "".join(tokens)

            # TTS (skip if not loaded)
            if app_state.tts._is_loaded and result.llm_output:
                first_chunk = result.llm_output[:80]
                with Timer("tts") as t_tts:
                    await app_state.tts.synthesize(first_chunk, use_cache=False)
                result.tts_ms = round(t_tts.elapsed_ms)

            result.total_ms = round((time.perf_counter() - t_total_start) * 1000)
            results.append(result.model_dump())

        avg_total = sum(r["total_ms"] for r in results) / len(results) if results else 0
        avg_ttfa = sum(r["llm_ttft_ms"] + r["tts_ms"] for r in results) / len(results) if results else 0

        return {
            "results": results,
            "summary": {
                "avg_total_ms": round(avg_total),
                "avg_ttfa_ms": round(avg_ttfa),
                "target_ms": 1000,
                "status": "PASS" if avg_ttfa < 1000 else "FAIL",
                "tts_available": app_state.tts._is_loaded,
            },
        }
    except Exception as e:
        return {"error": f"Full pipeline lỗi: {e}"}
