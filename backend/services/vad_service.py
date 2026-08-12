import logging
import numpy as np
import torch

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)  # 480 samples


class VADService:
    """Silero VAD wrapper for speech detection."""

    def __init__(self, threshold: float = 0.5, min_silence_ms: int = 300):
        self.threshold = threshold
        self.min_silence_ms = min_silence_ms
        self.model = None
        self._is_loaded = False

    def load(self):
        if self._is_loaded:
            return
        logger.info("Loading Silero VAD model...")
        # GHI RÕ NHÁNH ":master" - đây mới là thứ chặn được lần gọi mạng.
        #
        # `_parse_repo_info` trong torch/hub.py: chỉ khi KHÔNG ghi nhánh nó mới
        # mở https://github.com/<repo>/tree/main/ để đoán xem nhánh mặc định là
        # `main` hay `master`. Ghi sẵn `:master` (khớp thư mục cache
        # `snakers4_silero-vad_master`) thì `ref` khác None và nhánh gọi mạng
        # không bao giờ chạy.
        #
        # `skip_validation=True` KHÔNG cứu được: `_parse_repo_info` chạy vô điều
        # kiện ở đầu `_get_cache_or_reload`, trước cả chỗ xét cờ đó. Đã thử và
        # thất bại 12-08-2026.
        #
        # Torch CÓ đường lùi offline, nhưng nó chỉ bắt `URLError`. Sự cố thật
        # 12-08-2026 là `http.client.RemoteDisconnected` - kết nối được chấp
        # nhận rồi bị đóng giữa chừng - không phải `URLError`, nên đường lùi
        # không chạy và cả backend chết ở "[2/6] Loading VAD" dù cache còn
        # nguyên. Mạng HỎNG NỬA VỜI nguy hiểm hơn mất mạng hẳn.
        self.model, _ = torch.hub.load(
            "snakers4/silero-vad:master", "silero_vad",
            trust_repo=True, skip_validation=True,
        )
        self.model.eval()
        self._is_loaded = True
        logger.info("Silero VAD loaded (CPU)")

    def reset(self):
        """Reset VAD state for a new utterance."""
        if self.model is not None:
            self.model.reset_states()

    def is_speech(self, audio_chunk: np.ndarray) -> float:
        """Return speech probability for a 30ms chunk (480 samples at 16kHz)."""
        if not self._is_loaded:
            self.load()

        tensor = torch.from_numpy(audio_chunk).float()
        if tensor.dim() == 1:
            tensor = tensor.unsqueeze(0)

        with torch.no_grad():
            prob = self.model(tensor, SAMPLE_RATE).item()
        return prob

    def detect_speech_end(self, audio_frames: list[np.ndarray]) -> int | None:
        """
        Process a sequence of audio frames.
        Returns the index where speech ends (after min_silence_ms of silence),
        or None if speech is still ongoing.
        """
        silence_frames = 0
        min_silence_frames = int(self.min_silence_ms / FRAME_MS)

        for i, frame in enumerate(audio_frames):
            prob = self.is_speech(frame)
            if prob < self.threshold:
                silence_frames += 1
                if silence_frames >= min_silence_frames:
                    return i - min_silence_frames + 1
            else:
                silence_frames = 0

        return None
