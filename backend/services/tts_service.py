import asyncio
import logging
import concurrent.futures
from collections import OrderedDict
from contextlib import nullcontext
from pathlib import Path
import numpy as np
import soundfile as sf

from backend.config import settings
from backend.pipeline.text_normalizer import normalize_for_tts
from backend.services.audio_utils import float32_to_int16, resample_audio, pcm_to_wav
from backend.core.logging_config import Timer
from backend.core.device import DEVICE
from backend.services.filler_store import CauDem, van_tay
from backend.services.filler_pick import chon as _chon_filler

logger = logging.getLogger(__name__)

# Below this peak amplitude a reference clip is treated as an empty recording.
SILENCE_PEAK = 1e-3

# Tiếng câu đệm cất ở đây để khởi động không phải gọi F5 lại. Tên file mang vân
# tay: đổi nfe/speed/giọng là vân tay lệch -> dựng lại đúng câu đó.
THU_MUC_FILLER = Path("data/fillers_wav")

def trim_silence(audio: np.ndarray, sr: int, thresh: float = 0.005,
                 keep_ms: int = 25) -> np.ndarray:
    """Cắt khoảng lặng đầu/cuối của một mảnh TTS.

    Ngưỡng để thấp (0.005) và chừa lại 25ms hai đầu: phụ âm bật hơi đầu câu
    ("kh", "th", "ph") vào rất nhẹ, cắt sát quá là mất luôn tiếng đầu.
    """
    if audio is None or len(audio) == 0:
        return audio
    amp = np.abs(audio)
    nz = np.nonzero(amp > thresh)[0]
    if len(nz) == 0:
        return audio            # cả mảnh im lặng - trả nguyên, đừng cắt thành rỗng
    keep = int(sr * keep_ms / 1000)
    start = max(0, int(nz[0]) - keep)
    end = min(len(audio), int(nz[-1]) + keep)
    return audio[start:end]


class F5TTSService:
    """F5-TTS Vietnamese ViVoice wrapper for text-to-speech.

    Reference voices are held in a registry keyed by name, never as a single
    "current voice" on the instance: concurrent calls can be running on
    different phone lines with different voices, and a shared mutable ref would
    make one call switch voice mid-sentence. Every cache is keyed by voice for
    the same reason.
    """

    def __init__(self):
        self._model = None
        self._vocoder = None
        self._is_loaded = False
        # One worker: F5-TTS inference is GPU-bound, parallel CUDA calls just
        # interleave. Voice registration runs on the same thread, so _voices is
        # only ever mutated there.
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._default_voice = Path(settings.f5tts_ref_audio).stem
        self._voices: dict[str, tuple] = {}          # name -> (wave, sr, ref_text)
        self._filler_cache: dict[tuple[str, str], bytes] = {}   # (voice, cau_id) -> wav
        self._filler_ms: dict[tuple[str, str], float] = {}      # (voice, cau_id) -> ms
        self._synth_cache: "OrderedDict[tuple, bytes]" = OrderedDict()  # (voice, text, fast, sr)
        self._synth_cache_max = 256

    def load(self):
        """Load F5-TTS model and vocoder. Call once at startup."""
        if self._is_loaded:
            return

        logger.info("Loading F5-TTS Vietnamese ViVoice model...")

        try:
            import torch

            if str(DEVICE).startswith("cuda"):
                # TF32 for fp32 matmuls that fall outside the autocast region
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.set_float32_matmul_precision("high")
                torch.backends.cudnn.allow_tf32 = True
                # KHÔNG bật torch.backends.cudnn.benchmark: đã thử và nó làm CHẬM
                # HẲN. Độ dài câu TTS thay đổi liên tục nên mỗi kích thước mới lại
                # kích hoạt một lượt dò thuật toán. Đo thực tế trên 8 câu dài ngắn
                # khác nhau: 6/8 câu mất ~1420ms thay vì ~500ms.
                # cudnn.benchmark chỉ đáng bật khi kích thước đầu vào cố định.

            from f5_tts.infer.utils_infer import load_model, load_vocoder
            from f5_tts.model import DiT

            ckpt_path = settings.f5tts_ckpt_path
            vocab_path = settings.f5tts_vocab_path

            if not Path(ckpt_path).exists():
                raise FileNotFoundError(f"F5-TTS checkpoint not found: {ckpt_path}")
            if not Path(vocab_path).exists():
                raise FileNotFoundError(
                    f"F5-TTS vocab not found: {vocab_path}. "
                    "Did you rename config.json to vocab.txt?"
                )

            self._vocoder = load_vocoder(vocoder_name="vocos", device=DEVICE)
            # Arch phải khớp configs/F5TTS_Base.yaml - checkpoint ViVoice fine-tune
            # từ F5TTS_Base (bản cũ), KHÔNG phải F5TTS_v1_Base.
            # text_mask_padding và pe_attn_head chỉ đổi cách tính, không đổi shape
            # tensor, nên load_state_dict vẫn pass sạch nếu để sai - model clone
            # đúng giọng nhưng đọc ra tiếng Việt vô nghĩa, không có lỗi nào báo ra.
            # Mặc định của DiT là (True, None) = arch v1 => bắt buộc truyền tay.
            self._model = load_model(
                model_cls=DiT,
                model_cfg=dict(
                    dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512,
                    text_mask_padding=False, conv_layers=4, pe_attn_head=1,
                ),
                ckpt_path=ckpt_path,
                vocab_file=vocab_path,
                device=DEVICE,
            )

            # torch.compile gộp kernel, cắt chi phí phóng kernel. Đây đúng là nút
            # thắt của F5-TTS: 16 bước khuếch tán nối tiếp, mỗi bước một kernel nhỏ
            # -> đo được GPU chỉ đạt 73% và CPU 5%, không bên nào đầy.
            #
            # dynamic=True là BẮT BUỘC: độ dài câu thay đổi liên tục, để mặc định
            # thì mỗi shape mới lại biên dịch lại (đúng cái bẫy đã dính với
            # cudnn.benchmark: 6/8 câu chậm gấp 3).
            #
            # Tắt bằng F5TTS_COMPILE=false trong .env nếu gặp trục trặc.
            # PHẢI biên dịch self._model.transformer, KHÔNG phải self._model.
            # infer_batch_process gọi model.sample(), mà torch.compile chỉ chặn
            # forward/__call__ - bọc lớp ngoài thì .sample() đi thẳng vào bản gốc
            # chưa biên dịch, tức là không có tác dụng gì (đã thử và đo ra).
            # Bên trong sample(): odeint chạy 16 bước, mỗi bước gọi transformer 2
            # lần (classifier-free guidance) => 32 lượt. Đó mới là chỗ nóng.
            if settings.f5tts_compile and str(DEVICE).startswith("cuda"):
                try:
                    che_do = (settings.f5tts_compile_mode or "").strip()
                    self._model.transformer = torch.compile(
                        self._model.transformer, dynamic=True,
                        **({"mode": che_do} if che_do else {})
                    )
                    logger.info("F5-TTS: đã bật torch.compile cho DiT "
                                "(dynamic=True, mode=%s)", che_do or "mặc định")
                except Exception as e:
                    logger.warning(f"F5-TTS: torch.compile hỏng, chạy bản thường: {e}")

            ref_audio_path = settings.f5tts_ref_audio
            if Path(ref_audio_path).exists():
                self._register_voice_sync(
                    self._default_voice, ref_audio_path, settings.f5tts_ref_text
                )
                logger.info(f"Reference voice loaded: {ref_audio_path}")
            else:
                # Giọng mặc định có thể đã bị xoá qua UI. Nhận giọng đầu tiên còn
                # trên đĩa làm mặc định: ensure_voice() fallback về _default_voice
                # mỗi khi gặp tên lạ, trỏ nó vào một giọng không tồn tại thì cả
                # cuộc gọi chết chứ không chỉ riêng giọng đó.
                fallback = next(
                    (v for v in self.list_voices() if v["ref_text"] and not v["silent"]),
                    None,
                )
                if fallback:
                    self._default_voice = fallback["name"]
                    self._register_voice_sync(
                        fallback["name"], fallback["wav_path"], fallback["ref_text"]
                    )
                    logger.warning(
                        f"Không thấy {ref_audio_path}, dùng giọng '{fallback['name']}' "
                        "làm giọng mặc định."
                    )
                else:
                    logger.warning(
                        f"Reference audio not found: {ref_audio_path}, và không có "
                        "giọng mẫu nào khác. TTS sẽ không đọc được cho tới khi "
                        "upload một giọng."
                    )

            # Warmup chỉ chạy được khi đã có giọng. Trước đây gọi vô điều kiện nên
            # xoá giọng default là load() ném RuntimeError -> chết luôn cả TTS.
            if self._voices:
                logger.info(f"Warming up F5-TTS on {DEVICE} (first inference)...")
                # Chạy warmup QUA executor chứ đừng gọi thẳng. Với torch.compile,
                # lần suy luận đầu mới là lúc thật sự biên dịch (Triton sinh
                # kernel), và biên dịch ở luồng NÀY rồi chạy ở luồng KHÁC là chỗ
                # backend chết câm: không traceback, không log, tiến trình biến
                # mất - vì `load()` chạy ở luồng khởi động còn mọi lượt tổng hợp
                # sau đó chạy trong `self._executor`.
                #
                # Executor chỉ có ĐÚNG MỘT worker (bắt buộc, F5-TTS không an toàn
                # đa luồng), nên biên dịch ở đây thì mọi lượt sau dùng lại đúng
                # kernel đã biên dịch trên đúng luồng đó.
                self._executor.submit(
                    self._synthesize_sync, "xin chào", self._default_voice
                ).result()
            else:
                logger.warning("Bỏ qua warmup: chưa có giọng mẫu nào được nạp.")

            self._is_loaded = True
            logger.info("F5-TTS Vietnamese loaded successfully")

        except ImportError:
            logger.error(
                "F5-TTS not installed. "
                "Run: git clone https://github.com/nguyenthienhy/F5-TTS-Vietnamese && "
                "pip install -e F5-TTS-Vietnamese"
            )
            raise

    def unload(self) -> dict:
        """Nhả trọng số model khỏi VRAM để nhường GPU cho việc fine-tune.

        Fine-tune LLM cần 8-10GB, mà F5-TTS đang giữ một phần đáng kể. Không
        nhả ra thì train OOM.

        CHỈ bỏ model và vocoder. Giữ nguyên _voices và các cache: chúng nằm ở
        RAM thường, xoá đi không nhả thêm được VRAM nào mà lần dùng lại phải
        giải mã âm thanh từ đầu.

        Gọi load() sau đó là dùng lại được (_is_loaded về False nên load()
        không early-return).

        Người gọi phải đảm bảo không còn lượt tổng hợp nào đang chạy - executor
        chỉ có một luồng, nhưng unload() không chờ luồng đó.

        Trả về mức VRAM trước/sau (MiB) để bên gọi ghi log và quyết định có đủ
        chỗ train hay chưa.
        """
        do = {"vram_free_truoc_mib": None, "vram_free_sau_mib": None, "da_nha": False}
        if not self._is_loaded:
            do["ghi_chu"] = "F5-TTS chưa nạp, không có gì để nhả"
            return do

        try:
            import torch
            co_cuda = torch.cuda.is_available()
        except Exception:
            torch, co_cuda = None, False

        if co_cuda:
            do["vram_free_truoc_mib"] = round(torch.cuda.mem_get_info()[0] / 1024**2)

        logger.info("Nhả F5-TTS khỏi VRAM để nhường chỗ train...")
        self._model = None
        self._vocoder = None
        self._is_loaded = False

        import gc
        gc.collect()
        if co_cuda:
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            do["vram_free_sau_mib"] = round(torch.cuda.mem_get_info()[0] / 1024**2)

        do["da_nha"] = True
        if do["vram_free_truoc_mib"] is not None:
            logger.info(
                "VRAM trống: %s -> %s MiB (nhả thêm %s MiB)",
                do["vram_free_truoc_mib"], do["vram_free_sau_mib"],
                do["vram_free_sau_mib"] - do["vram_free_truoc_mib"],
            )
        return do

    # --- voice registry ------------------------------------------------------

    @staticmethod
    def probe_ref(wav_path: str | Path) -> dict:
        """Duration and peak level of a reference clip.

        F5-TTS clones the reference audio, so a silent file (peak ~0) yields
        silent speech - it synthesizes "successfully" and plays back as nothing,
        which is impossible to diagnose from the UI. Callers use this to refuse
        such a file up front.
        """
        try:
            data, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
        except Exception:
            return {"readable": False, "duration": 0.0, "peak": 0.0, "silent": False}

        mono = data.mean(axis=1)
        peak = float(np.abs(mono).max()) if len(mono) else 0.0
        return {
            "readable": True,
            "duration": round(len(mono) / sr, 2) if sr else 0.0,
            "peak": round(peak, 4),
            "silent": peak < SILENCE_PEAK,
        }

    def _register_voice_sync(self, name: str, wav_path: str, ref_text: str):
        """Preprocess a reference voice ONCE and keep it on the device.

        Disk read, mono mix, resample to 24kHz and device transfer would
        otherwise be redone by infer_process on every single synthesize call.
        Runs on the executor thread, which is the only writer of _voices.
        """
        import torch
        import torchaudio
        from f5_tts.infer.utils_infer import preprocess_ref_audio_text

        probe = self.probe_ref(wav_path)
        if probe["silent"]:
            logger.warning(
                f"Giọng mẫu '{name}' ({wav_path}) không có tiếng - mọi câu đọc bằng "
                "giọng này sẽ im lặng. Thu lại file 5-10 giây rồi upload đè."
            )

        ref_audio, processed_text = preprocess_ref_audio_text(wav_path, ref_text)

        audio, sr = torchaudio.load(ref_audio)
        if audio.shape[0] > 1:
            audio = torch.mean(audio, dim=0, keepdim=True)
        target_sr = 24000
        if sr != target_sr:
            audio = torchaudio.transforms.Resample(sr, target_sr)(audio)
            sr = target_sr
        audio = audio.to(DEVICE)

        self._voices[name] = (audio, sr, processed_text)

        duration = audio.shape[-1] / sr
        logger.info(f"Voice '{name}' cached in memory: {duration:.1f}s on {DEVICE}")
        if duration > 8:
            logger.warning(
                f"Ref audio giọng '{name}' dài {duration:.1f}s - ref càng dài mỗi lần "
                "synth càng chậm (ODE chạy trên cả ref). Khuyến nghị dùng clip 3-6s."
            )
        elif duration < 3:
            # ĐO THẬT 08-08, cùng câu, lặp 3 lần mỗi giọng, cho STT nghe lại:
            #   giong_heu (ref 2.21s): âm rác 2/3 lượt, biên độ vượt trần 3/3
            #   fosd_1    (ref 4.95s): âm rác 0/3,      vượt trần 0/3
            # Ref ngắn thì F5 thiếu ngữ cảnh, nó BỊA ra một cụm 2-5 âm tiết ở
            # ĐẦU mỗi lần sinh - khách nghe "hiếu... nhìn..." trước mỗi câu.
            # `trim_silence` không cắt được vì cụm đó rất TO (biên độ ~0.5).
            #
            # Cảnh báo chứ không chặn: giọng vẫn dùng được, chỉ là bẩn.
            logger.warning(
                "Ref audio giọng '%s' CHỈ %.1fs - NGẮN QUÁ. Đo được ref dưới 3s "
                "làm F5 bịa âm rác ở đầu ~2/3 số lượt và biên độ vượt trần. "
                "Thu lại clip 4-6s của cùng người rồi thay file, sẽ sạch.",
                name, duration,
            )

    async def ensure_voice(self, name: str) -> str:
        """Register a voice if it isn't loaded yet. Returns the usable voice name.

        Falls back to the default voice when `name` is unknown, so a bad
        voice_name degrades to the wrong-but-working voice instead of killing
        the call.
        """
        # "default" là TÊN QUY ƯỚC nghĩa là "giọng mặc định", không phải tên một
        # file giọng. Phiên mới và ô chọn giọng lúc chưa nạp xong đều gửi chuỗi
        # này. Không chặn ở đây thì mỗi mảnh audio lại đi tra danh sách giọng,
        # trượt, rồi ghi một dòng cảnh báo - log đầy rác mà chẳng có gì sai.
        if not name or name == "default" or name in self._voices:
            return self._default_voice if (not name or name == "default") else name

        voice = next((v for v in self.list_voices() if v["name"] == name), None)
        if not voice or not voice["ref_text"]:
            logger.warning(f"Voice '{name}' not found (or has no transcript), using default")
            return self._default_voice

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                self._executor, self._register_voice_sync,
                name, voice["wav_path"], voice["ref_text"],
            )
        except Exception as e:
            logger.warning(f"Failed to load voice '{name}': {e}. Using default.")
            return self._default_voice
        return name

    def drop_voice(self, name: str):
        """Forget a voice and everything synthesized with it (used after delete/retrain)."""
        self._voices.pop(name, None)
        for key in [k for k in self._synth_cache if k[0] == name]:
            del self._synth_cache[key]
        for key in [k for k in self._filler_cache if k[0] == name]:
            del self._filler_cache[key]

    # --- synthesis -----------------------------------------------------------

    def _autocast_ctx(self):
        """fp16 autocast on CUDA (~1.5-2x faster on RTX). Full precision elsewhere."""
        import torch

        if str(DEVICE).startswith("cuda"):
            return torch.autocast("cuda", dtype=torch.float16)
        return nullcontext()

    def _synthesize_sync(
        self, text: str, voice: str, nfe_step: int | None = None,
        speed: float | None = None,
    ) -> tuple[np.ndarray, int]:
        """Synchronous TTS synthesis (runs in thread executor).

        Calls infer_batch_process directly with the registered ref tensor —
        skips infer_process's per-call disk load/resample of the ref audio.
        Text is passed as a single batch (pipeline already chunks upstream).
        """
        from f5_tts.infer.utils_infer import infer_batch_process

        entry = self._voices.get(voice)
        if entry is None:
            raise RuntimeError(f"No reference audio loaded for voice '{voice}'")
        ref_wave, ref_sr, ref_text = entry

        # inference_mode mạnh hơn no_grad: bỏ luôn version-counter và view-tracking
        # của autograd. Suy luận thuần nên không mất gì.
        import torch as _t
        with _t.inference_mode(), self._autocast_ctx():
            audio, sr, _ = next(
                infer_batch_process(
                    (ref_wave, ref_sr),
                    ref_text,
                    [text],
                    self._model,
                    self._vocoder,
                    mel_spec_type="vocos",
                    progress=None,
                    nfe_step=nfe_step or settings.f5tts_nfe_step,
                    speed=speed if speed is not None else self.toc_do_cua(voice),
                    device=DEVICE,
                )
            )
        return audio, sr

    async def synthesize(
        self,
        text: str,
        target_sr: int = 24000,
        fast: bool = False,
        voice: str | None = None,
        use_cache: bool = True,
        nfe_step: int | None = None,
        speed: float | None = None,
    ) -> bytes:
        """
        Synthesize text to WAV bytes (async).
        fast=True uses f5tts_nfe_step_first (fewer diffusion steps) —
        slightly lower quality, ~2x faster; used for the first chunk to cut TTFA.
        voice selects a registered reference voice; None uses the default.
        use_cache=False forces a real synthesis and skips storing the result —
        the voice-test page needs true timings, and its throwaway phrases must
        not evict the ones live calls depend on.
        """
        if not self._is_loaded:
            self.load()

        voice = await self.ensure_voice(voice or self._default_voice)

        # Chuẩn hoá ở đây, không ở từng caller: pipeline gọi, trang test gọi,
        # benchmark gọi, filler gọi - đặt một chỗ thì cả bốn cùng đi qua.
        # Đặt trước cache_key luôn để "ABC" và "abc" dùng chung một bản ghi.
        text = normalize_for_tts(text)

        # Sentence cache: repeated phrases served instantly. Keyed by voice -
        # two lines saying the same sentence in different voices must not share.
        # `speed` PHẢI nằm trong khoá: thiếu nó thì đổi tốc xong đọc lại cùng
        # câu vẫn trả bản cũ, người dùng kéo thanh trượt mà không nghe khác gì.
        cache_key = (voice, text, fast, target_sr, nfe_step,
                     speed if speed is not None else self.toc_do_cua(voice))
        if use_cache:
            cached = self._synth_cache.get(cache_key)
            if cached is not None:
                self._synth_cache.move_to_end(cache_key)
                logger.info(f"TTS cache hit [{voice}]: '{text[:30]}...'")
                return cached

        loop = asyncio.get_event_loop()
        # nfe_step truyền tay chỉ dùng để ĐO (so các mức nfe với nhau).
        # Đường chạy thật luôn để None và lấy theo cấu hình.
        nfe = nfe_step or (settings.f5tts_nfe_step_first if fast
                           else settings.f5tts_nfe_step)

        with Timer("TTS", logger) as t:
            audio, sr = await loop.run_in_executor(
                self._executor, self._synthesize_sync, text, voice, nfe, speed
            )

        # F5-TTS trả về mỗi mảnh kèm khoảng lặng riêng: đo được 224-607ms ở ĐẦU
        # (trung bình 376ms) và ~38ms ở cuối. Ghép các mảnh lại thì mỗi ranh giới
        # câu có ~414ms chết -> nghe như bị vấp giữa các câu.
        # Lặng đầu của mảnh ĐẦU TIÊN còn cộng thẳng vào thời gian khách chờ:
        # TTFA 816ms nhưng phải 1150ms mới thực sự nghe thấy tiếng.
        audio = trim_silence(audio, sr)

        # Resample if needed
        if sr != target_sr:
            audio = resample_audio(audio, sr, target_sr)

        pcm_bytes = float32_to_int16(audio)
        wav_bytes = pcm_to_wav(pcm_bytes, sample_rate=target_sr)

        # Store in LRU cache
        if use_cache:
            self._synth_cache[cache_key] = wav_bytes
            if len(self._synth_cache) > self._synth_cache_max:
                self._synth_cache.popitem(last=False)

        duration_ms = len(audio) / target_sr * 1000
        logger.info(f"TTS [{voice}]: '{text[:30]}...' -> {duration_ms:.0f}ms audio ({t.elapsed_ms:.0f}ms)")
        return wav_bytes

    # --- fillers -------------------------------------------------------------

    def default_voice_name(self) -> str:
        """Tên giọng mặc định THẬT SỰ đang dùng.

        Không đọc thẳng `settings.f5tts_ref_audio` ở nơi khác: khi file đó thiếu,
        `load()` rơi về giọng đầu tiên tìm được trên đĩa và ghi đè `_default_voice`
        - lấy từ cấu hình sẽ ra một cái tên không tồn tại.
        """
        return self._default_voice

    def _giong_thuc(self, voice: str | None) -> str:
        """Quy tên giọng lạ về giọng mặc định.

        Phiên mới mặc định voice_name="default" trong khi giọng thật tên theo
        file (vd "giong_ngan") - không quy về thì mọi tra cứu cache đều trượt và
        câu đệm chưa bao giờ phát.
        """
        name = voice or self._default_voice
        return name if name in self._voices else self._default_voice

    def co_filler(self, voice: str | None = None) -> bool:
        """Giọng này đã có câu đệm dựng sẵn chưa."""
        name = self._giong_thuc(voice)
        return any(k[0] == name for k in self._filler_cache)

    def _duong_dan_filler(self, voice: str, cau_id: str, vt: str) -> Path:
        return THU_MUC_FILLER / voice / f"{cau_id}__{vt}.wav"

    def _van_tay_filler(self, text: str, voice: str) -> str:
        # Tốc và câu mẫu phải lấy từ bản riêng của giọng, không phải giá trị chung
        # trong .env. Nếu dùng settings.f5tts_speed: người dùng đặt tốc riêng giọng
        # đó -> tiếng WAV đã dựng theo tốc mới, nhưng vân tay tính từ tốc chung nên
        # không đổi -> hệ thống tưởng file còn tốt và phát câu đệm tốc cũ.
        speed = self.toc_do_cua(voice)
        entry = self._voices.get(voice)
        ref_text = entry[2] if entry is not None else settings.f5tts_ref_text
        return van_tay(text, voice, settings.f5tts_nfe_step, speed, ref_text)

    async def dung_fillers(self, cau: list[CauDem], voice: str | None = None):
        """Bảo đảm mọi câu đệm đều có tiếng sẵn sàng cho giọng này.

        Đọc từ đĩa trước, chỉ gọi F5 cho những câu còn thiếu hoặc lệch vân tay.
        Nhờ vậy khởi động lần hai trở đi KHÔNG chạm GPU - quan trọng vì
        `_warm_fillers` chạy đúng lúc cuộc gọi bắt đầu (api/websocket.py:286),
        và 28 câu gọi F5 nền sẽ giành GPU với chính cuộc gọi đang sống.
        """
        voice = await self.ensure_voice(voice or self._default_voice)
        thu_muc = THU_MUC_FILLER / voice
        thu_muc.mkdir(parents=True, exist_ok=True)

        doc_dia = dung_moi = 0
        for c in cau:
            khoa = (voice, c.id)
            if khoa in self._filler_cache:
                continue
            vt = self._van_tay_filler(c.text, voice)
            p = self._duong_dan_filler(voice, c.id, vt)
            if p.exists():
                try:
                    wav = p.read_bytes()
                    self._filler_cache[khoa] = wav
                    self._filler_ms[khoa] = self._wav_duration_ms(wav)
                    doc_dia += 1
                    continue
                except OSError as e:
                    logger.warning("Đọc %s hỏng, dựng lại: %s", p, e)
            try:
                wav = await self.synthesize(c.text, voice=voice)
            except Exception as e:
                logger.warning("Không dựng được câu đệm %r: %s", c.id, e)
                continue
            # Xoá bản vân tay cũ của cùng câu, nếu không đĩa phình mãi mỗi lần
            # đổi nfe.
            for cu in thu_muc.glob(f"{c.id}__*.wav"):
                cu.unlink(missing_ok=True)
            try:
                p.write_bytes(wav)
            except OSError as e:
                logger.warning(
                    "Ghi câu đệm %r ra %s thất bại (%s) — giữ trong bộ nhớ, "
                    "lần khởi động sau sẽ dựng lại.",
                    c.id, p, e,
                )
            self._filler_cache[khoa] = wav
            self._filler_ms[khoa] = self._wav_duration_ms(wav)
            dung_moi += 1

        logger.info("Câu đệm [%s]: %d đọc từ đĩa, %d dựng mới, tổng %d",
                    voice, doc_dia, dung_moi,
                    sum(1 for k in self._filler_cache if k[0] == voice))

    @staticmethod
    def _wav_duration_ms(wav_bytes: bytes) -> float:
        """Độ dài tiếng của một WAV PCM 16-bit mono (bỏ 44 byte header)."""
        try:
            import struct
            sr = struct.unpack_from("<I", wav_bytes, 24)[0]
            return max(0.0, (len(wav_bytes) - 44) / 2 / sr * 1000)
        except Exception:
            return 0.0

    def do_dai_filler(self, cau_id: str, voice: str | None = None) -> float:
        """Độ dài tiếng (ms) của một câu đệm, 0 nếu chưa dựng."""
        return self._filler_ms.get((self._giong_thuc(voice), cau_id), 0.0)

    def pick_filler(self, cau: list[CauDem], voice: str | None = None,
                    min_ms: float = 0.0,
                    dem: dict[str, int] | None = None
                    ) -> tuple[bytes | None, CauDem | None]:
        """Chọn câu đệm đã có tiếng cho giọng này. Trả (wav, CauDem).

        Lớp mỏng: luật chọn nằm ở services/filler_pick.py để test được mà không
        cần GPU. Ở đây chỉ lo tra cache và quy giọng lạ về giọng mặc định.
        """
        name = self._giong_thuc(voice)
        theo_id = {c.id: c for c in cau}
        ung_vien = [(c.id, self._filler_ms[(name, c.id)])
                    for c in cau if (name, c.id) in self._filler_cache]
        chon_id = _chon_filler(ung_vien, min_ms=min_ms, dem=dem or {})
        if chon_id is None:
            # Về tay không là khách nghe im lặng trọn TTFA, nên phải nói RÕ vì
            # sao: xin giọng nào, quy về giọng nào, cache còn gì. Bản trước chỉ
            # trả None và nơi gọi in "KHÔNG có filler cho giọng X" - mà X là tên
            # XIN chứ không phải tên đã quy, nên đọc log không biết trượt ở đâu.
            logger.warning(
                "pick_filler về tay không: xin='%s' -> quy về '%s'; kho đưa %d câu, "
                "trong đó %d câu đã có tiếng; cache giọng này %d mục / tổng %d; "
                "giọng đã nạp: %s",
                voice, name, len(cau), len(ung_vien),
                sum(1 for k in self._filler_cache if k[0] == name),
                len(self._filler_cache), sorted(self._voices),
            )
            return None, None
        return self._filler_cache[(name, chon_id)], theo_id[chon_id]

    # --- discovery -----------------------------------------------------------


    # --- Tốc độ riêng cho từng giọng -----------------------------------------
    #
    # `settings.f5tts_speed` là MỘT số cho mọi giọng, mà F5 sao chép cả nhịp nói
    # của đoạn mẫu - nên một số chung không thể vừa cho mọi giọng. Đo trên chính
    # các đoạn mẫu đang có:
    #     giong_heu  3.44 âm tiết/giây      nam_moi1  3.01
    #     giong_nam  2.95                   nam_moi2  2.30
    # Chênh 1.5 lần giữa nhanh nhất và chậm nhất. Đặt tốc chung 0.64 cho vừa
    # giọng nữ thì giọng nam thành lê thê - đúng thứ người dùng kêu "đọc chậm".
    #
    # Lưu vào tệp `<giọng>.speed` nằm cạnh `<giọng>.wav`: giọng là một bộ ba
    # (wav + txt + speed) đi liền nhau, chép sang máy khác là còn nguyên. Nhét
    # vào .env thì mỗi lần thêm giọng phải sửa cấu hình rồi khởi động lại.

    _TRAN_SPEED = (0.3, 2.5)

    def _tep_speed(self, voice: str | None) -> Path:
        goc = Path(settings.f5tts_ref_audio)
        ten = voice or goc.stem
        return goc.parent / f"{ten}.speed"

    def toc_do_cua(self, voice: str | None = None) -> float:
        """Tốc của giọng này; chưa đặt riêng thì lấy tốc chung trong .env."""
        p = self._tep_speed(voice)
        if p.exists():
            try:
                v = float(p.read_text(encoding="utf-8").strip())
                lo, hi = self._TRAN_SPEED
                return min(max(v, lo), hi)
            except ValueError:
                logger.warning("Tốc giọng hỏng ở %s, dùng tốc chung", p)
        return settings.f5tts_speed

    def dat_toc_do(self, voice: str, toc: float) -> float:
        lo, hi = self._TRAN_SPEED
        toc = min(max(float(toc), lo), hi)
        self._tep_speed(voice).write_text(f"{toc:.3f}", encoding="utf-8")
        # Bộ nhớ đệm giữ tiếng đã dựng theo tốc CŨ - không dọn thì đổi tốc xong
        # vẫn nghe y như trước và tưởng nút không ăn.
        self._xoa_cache_giong(voice)
        logger.info("Đặt tốc giọng %s = %.2f", voice, toc)
        return toc

    def _xoa_cache_giong(self, voice: str):
        """Dọn tiếng đã dựng của một giọng.

        Tên biến là `_synth_cache`, KHÔNG phải `_cache` - viết nhầm thì hàm này
        chạy êm mà không dọn gì, và người dùng kéo thanh tốc xong nghe y như cũ
        rồi tưởng nút hỏng.

        Phải dọn cả `_filler_cache`/`_filler_ms`: chúng dùng khoá `(voice, cau_id)`,
        kiểm tra bằng `k[0] == voice`. KHÔNG dùng `voice in k` cho filler vì có thể
        trùng tên với cau_id và xoá nhầm khoá của giọng khác.
        """
        try:
            for k in [k for k in self._synth_cache if isinstance(k, tuple) and voice in k]:
                self._synth_cache.pop(k, None)
        except Exception as e:
            logger.debug("Không dọn được synth_cache giọng %s: %s", voice, e)
        try:
            for k in [k for k in self._filler_cache if k[0] == voice]:
                self._filler_cache.pop(k, None)
                self._filler_ms.pop(k, None)
        except Exception as e:
            logger.debug("Không dọn được filler_cache giọng %s: %s", voice, e)


    # --- Hệ số tốc riêng cho ĐƯỜNG THOẠI -------------------------------------
    #
    # Kênh GSM là 8kHz, nén mạnh, và mất gần hết dải cao - chính dải mang phụ âm
    # (s, x, ch, tr). Cùng một tốc, nghe trên trình duyệt thì rõ mà qua điện
    # thoại thì dính chữ. Nên tốc thoại phải chỉnh RIÊNG, không dùng chung với
    # tốc nghe trên web.
    #
    # Là HỆ SỐ NHÂN chứ không phải một số tuyệt đối: mỗi giọng đã có tốc riêng
    # (xem `toc_do_cua`), đặt số tuyệt đối cho đường thoại sẽ xoá sạch phần
    # chỉnh theo giọng và mọi giọng lại nói cùng một nhịp.
    _TEP_HE_SO_THOAI = "_he_so_thoai.txt"
    _TRAN_HE_SO = (0.6, 1.4)

    def _tep_he_so(self) -> Path:
        return Path(settings.f5tts_ref_audio).parent / self._TEP_HE_SO_THOAI

    def he_so_thoai(self) -> float:
        p = self._tep_he_so()
        if p.exists():
            try:
                v = float(p.read_text(encoding="utf-8").strip())
                lo, hi = self._TRAN_HE_SO
                return min(max(v, lo), hi)
            except ValueError:
                pass
        return 1.0

    def dat_he_so_thoai(self, he_so: float) -> float:
        lo, hi = self._TRAN_HE_SO
        he_so = min(max(float(he_so), lo), hi)
        self._tep_he_so().write_text(f"{he_so:.3f}", encoding="utf-8")
        # Dọn sạch cache: tiếng đã dựng theo hệ số cũ còn nằm đó thì đổi xong
        # vẫn nghe y như trước.
        try:
            self._synth_cache.clear()
        except Exception:
            pass
        logger.info("Đặt hệ số tốc đường thoại = %.2f", he_so)
        return he_so

    def list_voices(self) -> list[dict]:
        """List available reference voices."""
        voices_dir = Path(settings.f5tts_ref_audio).parent
        voices = []
        for wav_file in sorted(voices_dir.glob("*.wav")):
            txt_file = wav_file.with_suffix(".txt")
            # encoding="utf-8" BẮT BUỘC: mặc định của Windows là cp1252, gặp chữ
            # có dấu là ném UnicodeDecodeError và kéo sập cả danh sách giọng -
            # tức là hỏng luôn ô chọn giọng và `ensure_voice` cho mọi giọng
            # không phải giọng mặc định (giọng mặc định lấy lời từ .env nên
            # không đi qua đây, vì thế lỗi náu được rất lâu).
            ref_text = (txt_file.read_text(encoding="utf-8", errors="replace").strip()
                        if txt_file.exists() else "")
            voices.append({
                "name": wav_file.stem,
                "wav_path": str(wav_file),
                "ref_text": ref_text,
                "speed": self.toc_do_cua(wav_file.stem),
                "speed_rieng": (wav_file.parent / f"{wav_file.stem}.speed").exists(),
                **self.probe_ref(wav_file),
            })
        return voices
