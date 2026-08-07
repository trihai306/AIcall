"""
PhoWhisper STT server (faster-whisper / CTranslate2).

Drop-in replacement for whisper.cpp's whisper-server:
exposes the same /inference and /health endpoints on port 8178,
so backend/services/stt_service.py works unchanged.

Usage:
    python whisper_server/pho_server.py --model models/phowhisper/PhoWhisper-small-ct2 --port 8178
"""
import argparse
import asyncio
import io
import os
import logging
import time

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("pho_server")

app = FastAPI(title="PhoWhisper STT Server")
model = None


# Đường dẫn model ĐANG NẠP, để `/health` báo ra ngoài. Không có nó thì phía
# backend chỉ đoán theo `settings.whisper_model` - mà giá trị đó là tên model
# MẶC ĐỊNH trong config, không phải thứ máy chủ thật sự nạp. Đổi model xong là
# hai bên lệch nhau ngay.
DUONG_MODEL = ""


def load_model(model_path: str):
    global model, DUONG_MODEL
    from faster_whisper import WhisperModel

    DUONG_MODEL = model_path

    device, compute_type = _pick_device()
    logger.info(f"Loading PhoWhisper: {model_path} (device={device}, compute={compute_type})")
    t0 = time.perf_counter()
    model = WhisperModel(model_path, device=device, compute_type=compute_type)
    logger.info(f"Model loaded in {time.perf_counter() - t0:.1f}s")


def _pick_device() -> tuple[str, str]:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "int8_float16"
    except Exception:
        pass
    return "cpu", "int8"


# Bật/tắt bằng biến môi trường để đo được tác dụng thật thay vì tin là nó giúp.
VAD_FILTER = os.environ.get("STT_VAD_FILTER", "1") not in ("0", "false", "False")
BEAM_SIZE = int(os.environ.get("STT_BEAM_SIZE", "5"))


@app.get("/health")
async def health():
    import os.path
    return {"status": "ok", "engine": "faster-whisper", "loaded": model is not None,
            "model": os.path.basename(DUONG_MODEL.rstrip("/\\")) or DUONG_MODEL,
            "model_path": DUONG_MODEL, "beam_size": BEAM_SIZE,
            "vad_filter": VAD_FILTER}


@app.post("/inference")
async def inference(
    file: UploadFile = File(...),
    language: str = Form("vi"),
    response_format: str = Form("json"),
    temperature: str = Form("0"),
):
    """whisper.cpp-compatible inference endpoint."""
    if model is None:
        return {"text": "", "error": "model not loaded"}

    audio_bytes = await file.read()
    t0 = time.perf_counter()

    # transcribe() is a blocking CTranslate2 call and segments is a lazy
    # generator - consuming it here would run the decode on the event loop and
    # stall every other in-flight request. Two concurrent phone lines would
    # then serialize on the socket, not just on the model.
    text, doan = await asyncio.to_thread(
        _transcribe_sync, audio_bytes, language, float(temperature or 0)
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(f"STT {elapsed_ms:.0f}ms: '{text[:60]}'")
    if response_format == "verbose_json":
        return {"text": text, "segments": doan}
    return {"text": text}


def _transcribe_sync(audio_bytes: bytes, language: str,
                     temperature: float) -> tuple[str, list[dict]]:
    """Trả (văn bản, danh sách đoạn kèm chỉ số tin cậy).

    Phải trả cả `no_speech_prob` và `avg_logprob`: Whisper BỊA CHỮ khi đầu vào
    chỉ có nhiễu - trên đường thoại EDGE nó sinh ra câu tiếng Việt trôi chảy từ
    tạp âm, lặp y hệt qua nhiều lượt. Không có hai số này thì phía gọi không
    phân biệt nổi "khách nói thật" với "mô hình đoán mò", và trước đây chúng bị
    vứt đi ngay tại đây.
    """
    segments, _info = model.transcribe(
        io.BytesIO(audio_bytes),
        language=language,
        temperature=temperature,
        beam_size=BEAM_SIZE,
        # BẬT VAD Silero của faster-whisper. Chú thích cũ nói "VAD đã làm ở phía
        # client" - đúng với đường TRÌNH DUYỆT (Silero chạy trong trang), nhưng
        # SAI với đường THOẠI: ở đó VAD chỉ là ngưỡng RMS thô. Không có VAD ở
        # đây thì Whisper nhận nguyên cả đoạn nhiễu và bịa ra câu tiếng Việt
        # trôi chảy - đã thấy một cuộc gọi thật cho 4 lượt toàn chữ bịa.
        vad_filter=VAD_FILTER,
        vad_parameters={"min_silence_duration_ms": 300} if VAD_FILTER else None,
        # Ba ngưỡng chống bịa chữ có sẵn trong faster-whisper, trước không dùng:
        #   no_speech_threshold      - đoạn nào mô hình cho là không có tiếng nói
        #   log_prob_threshold       - đoạn nào mô hình đoán mò
        #   compression_ratio_threshold - văn bản lặp đi lặp lại bất thường
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
        condition_on_previous_text=False,
        without_timestamps=True,
    )
    doan = [{"text": seg.text.strip(),
             "no_speech_prob": float(getattr(seg, "no_speech_prob", 0.0) or 0.0),
             "avg_logprob": float(getattr(seg, "avg_logprob", 0.0) or 0.0)}
            for seg in segments]
    return " ".join(d["text"] for d in doan).strip(), doan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/phowhisper/PhoWhisper-small-ct2",
                        help="Path to CT2 model dir, or HF repo id (e.g. vinai/PhoWhisper-small)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8178)
    args = parser.parse_args()

    load_model(args.model)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
