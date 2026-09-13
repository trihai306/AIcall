"""Local Gipformer FP32 decoding with an acoustic, not textual, silence gate.

No model downloads at call time. Whisper-specific prompts, substitutions and
log-probability thresholds must not be applied to this transducer. Silero only
checks whether speech is present; the recognizer still receives the WHOLE clip
so quiet word endings and short replies are not cut out of a valid utterance.
"""
from __future__ import annotations

import io
import logging
import math
import threading
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)
MODEL_NAME = "Gipformer-1.5-65M-FP32"
MODEL_FILES = {"encoder": "encoder.onnx", "decoder": "decoder.onnx",
               "joiner": "joiner.onnx", "tokens": "tokens.txt"}


class GipformerSTT:
    def __init__(self, model_dir: str | Path, num_threads: int = 4):
        self.model_dir = Path(model_dir).resolve()
        self.num_threads = num_threads
        self.recognizer = None
        self._lock = threading.Lock()

    def _load_locked(self) -> None:
        if self.recognizer is not None:
            return
        paths = {key: str(self.model_dir / name) for key, name in MODEL_FILES.items()}
        missing = [name for name in paths.values() if not Path(name).is_file()]
        if missing:
            raise FileNotFoundError("Gipformer model files missing: " + ", ".join(missing))
        import sherpa_onnx
        from faster_whisper.vad import get_vad_model

        # Load the bundled, offline Silero model before reporting readiness.
        get_vad_model()
        recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            **paths, num_threads=self.num_threads, sample_rate=16000,
            feature_dim=80, decoding_method="modified_beam_search", provider="cpu",
        )
        self.recognizer = recognizer
        logger.info("Loaded %s (CPU, %d threads): %s", MODEL_NAME,
                    self.num_threads, self.model_dir)

    def load(self) -> None:
        with self._lock:
            self._load_locked()

    def info(self) -> dict:
        return {"engine": "gipformer", "model": MODEL_NAME,
                "model_path": str(self.model_dir), "loaded": self.recognizer is not None,
                "precision": "fp32", "provider": "cpu", "threads": self.num_threads,
                "decoding": "modified_beam_search", "vad_filter": "presence_only"}

    @staticmethod
    def _has_speech(audio: np.ndarray) -> bool:
        if audio.size == 0 or not np.isfinite(audio).all():
            return False
        # Only reject near-digital-silence here. Normal telephone VAD opens at
        # much higher levels; this is NOT a replacement for speech detection.
        frames = np.pad(audio, (0, (-len(audio)) % 320)).reshape(-1, 320)
        if float(np.sqrt(np.mean(frames * frames, axis=1)).max()) < 16 / 32768:
            return False
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        spans = get_speech_timestamps(audio, VadOptions(
            threshold=0.20, min_speech_duration_ms=64,
            min_silence_duration_ms=100, speech_pad_ms=80,
        ))
        return bool(spans)

    def transcribe(self, wav: bytes) -> str:
        import soundfile as sf
        from scipy.signal import resample_poly

        audio, sr = sf.read(io.BytesIO(wav), dtype="float32")
        if audio.ndim != 1:
            raise ValueError("Live STT requires mono audio; select the customer channel first")
        if sr != 16000:
            divisor = math.gcd(sr, 16000)
            # Same full-utterance resampler used by the real-call A/B test.
            audio = resample_poly(audio, 16000 // divisor, sr // divisor).astype(np.float32)
        with self._lock:
            self._load_locked()
            if not self._has_speech(audio):
                logger.info("Gipformer: no acoustic speech; skipping decoder")
                return ""
            stream = self.recognizer.create_stream()
            stream.accept_waveform(16000, audio)
            self.recognizer.decode_streams([stream])
            # Preserve words, numbers and diacritics. Do not manufacture a
            # loan unit or repair text using the old PhoWhisper error list.
            return " ".join(stream.result.text.lower().split())
