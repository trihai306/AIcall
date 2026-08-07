"""Thu âm và fine-tune giọng nói từ giao diện web.

Thay cho quy trình CLI trong training/voice/README.md: thu 60 câu theo kịch bản
ngay trên trình duyệt, chuẩn hoá dataset, rồi chạy train.sh như một background
job có log trực tiếp.

Thu âm lưu ở data/voice_recordings/<voice_name>/NNN.wav - tách theo giọng để
train nhiều giọng mà không đè lên nhau.
"""

import base64
import logging
import os
import re
import sys
import unicodedata
import wave
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import settings
from backend.core.device import get_system_info
from backend.core.jobs import JobRunner, Step
from backend.core.vram import giai_phong_vram, theo_doi_roi_don
from backend.services.audio_utils import pcm_to_wav

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice-training", tags=["voice-training"])

PROJECT_DIR = settings.project_dir
RECORDINGS_ROOT = PROJECT_DIR / "data" / "voice_recordings"
SCRIPT_PATH = PROJECT_DIR / "training" / "voice" / "record_script.txt"
PREPARE_SCRIPT = PROJECT_DIR / "training" / "voice" / "prepare_dataset.py"
# Cắt một bản thu dài (30-60 phút) thành từng câu. Không có bước này thì người
# có sẵn file dài không dùng được giao diện: upload đòi tên file là số thứ tự
# câu, mà một file dài thì không đánh số được.
SPLIT_SCRIPT = PROJECT_DIR / "training" / "voice" / "split_long_audio.py"
TRAIN_SCRIPT = PROJECT_DIR / "training" / "voice" / "train.sh"
# Máy Windows không có bash. train.ps1 là bản tương đương, đã vá sẵn ba lỗi
# fine-tune F5-TTS (accelerate quá mới, start_update của checkpoint ViVoice,
# here-string PowerShell nuốt dấu xuống dòng).
TRAIN_SCRIPT_PS1 = PROJECT_DIR / "training" / "voice" / "train.ps1"
DATASET_DIR = PROJECT_DIR / "tools" / "F5-TTS-Vietnamese" / "data" / "your_dataset"
# Dataset đã chuẩn hoá nằm ở MỘT thư mục dùng chung cho mọi giọng - chuẩn hoá
# giọng mới là ghi đè lên giọng cũ, và không có gì báo. Ghi tên chủ sở hữu vào
# đây để bước train từ chối khi dataset không phải của giọng đang train: train
# giọng A trên tiếng của giọng B thì chỉ tới lúc nghe mới biết, sau nhiều giờ.
_TEP_CHU = "_giong.txt"


def _doc_dau(p: Path) -> str:
    """Đọc tệp dấu, bỏ BOM.

    Code ở đây ghi bằng `write_text(encoding="utf-8")` nên không có BOM, nhưng
    sửa tay bằng PowerShell (`Set-Content -Encoding utf8`) thì CÓ - và tên đọc
    ra thành "﻿giong_x", so với "giong_x" là trượt. Bắt được khi tự thử.
    """
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8-sig").strip()


def _dataset_cua_giong() -> str:
    return _doc_dau(DATASET_DIR / _TEP_CHU)


def _dat_chu_dataset(voice: str) -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    (DATASET_DIR / _TEP_CHU).write_text(voice, encoding="utf-8")

# Train một dataset 45-60 phút trên GPU yếu có thể mất nhiều giờ.
JOB_TIMEOUT_S = 8 * 3600

runner = JobRunner(PROJECT_DIR, timeout_s=JOB_TIMEOUT_S)

_NAME_RE = re.compile(r"[^a-z0-9_]+")
_SCRIPT_LINE_RE = re.compile(r"^(\d{3})\.\s*(.+)$")
_GROUP_RE = re.compile(r"^##\s*Nhóm\s*\d+:\s*(.+?)\s*(?:\([^)]*\))?\s*$")

# Mốc tối thiểu lấy từ training/voice/README.md: dưới 10 phút thì giọng nhận ra
# được nhưng chưa mượt.
MIN_MINUTES = 10


def safe_voice_name(name: str) -> str:
    """'Giọng Lan' -> 'giong_lan'.

    Bỏ dấu trước khi lọc, nếu không "giọng" thành "gi_ng". Phải khớp đúng với
    hàm cùng tên bên frontend/app.js vì client gửi tên đã chuẩn hoá sẵn.
    """
    s = unicodedata.normalize("NFD", (name or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("đ", "d")   # đ không tách dấu được bằng NFD
    return _NAME_RE.sub("_", s).strip("_")


def _voice_dir(voice_name: str) -> Path:
    return RECORDINGS_ROOT / voice_name


# Dấu nguồn của bản thu. Đặt ngay lúc tạo ra chúng, để các bước SAU tự biết phải
# lấy transcript từ đâu thay vì bắt người dùng nhớ tích một ô.
#
#   kich_ban  - thu trong app hoặc upload file đánh số -> transcript lấy theo
#               kịch bản 60 câu, chính xác tuyệt đối, KHÔNG cần nhận dạng.
#   cat_dai   - cắt ra từ một bản thu dài -> nội dung không khớp kịch bản, BẮT
#               BUỘC phải nhận dạng, không thì mọi mẫu bị gán nhầm lời và giọng
#               train ra đọc sai.
_TEP_NGUON = "_nguon.txt"


def _dat_nguon(voice: str, nguon: str) -> None:
    d = _voice_dir(voice)
    d.mkdir(parents=True, exist_ok=True)
    (d / _TEP_NGUON).write_text(nguon, encoding="utf-8")


def _doc_nguon(voice: str) -> str:
    return _doc_dau(_voice_dir(voice) / _TEP_NGUON) or "kich_ban"


def _can_nhan_dang(voice: str) -> bool:
    """Có phải phiên âm bằng máy không? Đây là chỗ hệ thống TỰ QUYẾT."""
    return _doc_nguon(voice) == "cat_dai"


def _wav_info(path: Path) -> tuple[float, int]:
    """(thời lượng giây, sample rate). (0, 0) nếu file hỏng.

    KHÔNG tin thẳng `getnframes()`. WAV ghi theo kiểu luồng (ffmpeg ghi ra
    stdout, máy ghi âm dừng đột ngột) để trường kích thước RIFF là 0xFFFFFFFF,
    và `wave` quy nó thành 2147483647 khung -> báo 89478 GIÂY cho một file 5,9
    giây. Đã gặp thật với `models/tts/ref_voices/fosd_1.wav`.

    Ở đây hậu quả nặng hơn chỗ khác: đây là đường upload giọng để train, độ dài
    sai làm bộ cắt tự động chia nhầm và cả buổi train hỏng theo.
    """
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            rong = w.getsampwidth() * w.getnchannels()
        # Đối chiếu với kích thước file thật; lệch quá thì tin file.
        theo_byte = max(0, path.stat().st_size - 44) // max(rong, 1)
        if frames <= 0 or (theo_byte and frames > theo_byte * 1.5):
            frames = theo_byte
        return (frames / rate if rate else 0.0), rate
    except Exception:
        return 0.0, 0


# ============================================================
# Kịch bản thu âm
# ============================================================

def load_script() -> list[dict]:
    """Đọc record_script.txt -> [{no, text, group}].

    Cùng cách parse với load_script() trong training/voice/prepare_dataset.py:
    dòng bắt đầu bằng '#' là chú thích, câu có dạng 'NNN. nội dung'.
    """
    if not SCRIPT_PATH.exists():
        return []

    items: list[dict] = []
    group = ""
    for line in SCRIPT_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("##"):
            m = _GROUP_RE.match(line)
            group = m.group(1) if m else line.lstrip("#").strip()
            continue
        if line.startswith("#"):
            continue
        m = _SCRIPT_LINE_RE.match(line)
        if m:
            items.append({"no": m.group(1), "text": m.group(2).strip(), "group": group})
    return items


@router.get("/script")
async def get_script():
    items = load_script()
    if not items:
        return {"error": f"Không đọc được kịch bản: {SCRIPT_PATH}", "sentences": []}
    return {"sentences": items, "total": len(items)}


# ============================================================
# Trạng thái
# ============================================================

@router.get("/status")
async def get_status(voice_name: str = ""):
    voice = safe_voice_name(voice_name)
    recordings = _list_recordings(voice) if voice else []
    total_s = sum(r["duration_s"] for r in recordings)

    sys_info = get_system_info()
    device = sys_info.get("device", "cpu")
    gpu_ok = str(device).startswith("cuda")

    pretrain = PROJECT_DIR / "models" / "tts" / "F5-TTS-Vietnamese-ViVoice" / "model_last.pt"
    dataset_files = list(DATASET_DIR.glob("*.wav")) if DATASET_DIR.exists() else []

    return {
        "voice_name": voice,
        "recorded": len(recordings),
        "total_sentences": len(load_script()),
        "total_seconds": round(total_s, 1),
        "min_minutes": MIN_MINUTES,
        "enough_audio": total_s >= MIN_MINUTES * 60,
        "dataset_ready": len(dataset_files) > 0,
        "dataset_files": len(dataset_files),
        "f5tts_repo": (PROJECT_DIR / "tools" / "F5-TTS-Vietnamese").exists(),
        "pretrain_ready": pretrain.exists(),
        "gpu_ok": gpu_ok,
        "device": device,
        "gpu_name": sys_info.get("gpu_name", ""),
        "running_job": runner.running_job_id,
        # Giao diện đọc hai trường này để tự tích và khoá ô "dùng nhận dạng",
        # thay vì để người dùng đoán.
        "nguon_ban_thu": _doc_nguon(voice) if voice else "kich_ban",
        "can_nhan_dang": _can_nhan_dang(voice) if voice else False,
        # Dataset đã chuẩn hoá đang thuộc về giọng nào (thư mục dùng chung).
        "dataset_cua_giong": _dataset_cua_giong(),
        "voices": sorted(p.name for p in RECORDINGS_ROOT.iterdir() if p.is_dir())
                  if RECORDINGS_ROOT.exists() else [],
    }


# ============================================================
# Thu âm
# ============================================================

def _list_recordings(voice_name: str) -> list[dict]:
    d = _voice_dir(voice_name)
    if not d.exists():
        return []
    out = []
    for wav in sorted(d.glob("[0-9][0-9][0-9].wav")):
        duration, rate = _wav_info(wav)
        out.append({
            "no": wav.stem,
            "duration_s": round(duration, 2),
            "sample_rate": rate,
            "size_kb": round(wav.stat().st_size / 1024, 1),
        })
    return out


@router.get("/recordings")
async def list_recordings(voice_name: str):
    voice = safe_voice_name(voice_name)
    if not voice:
        return {"error": "Thiếu tên giọng", "recordings": []}
    return {"voice_name": voice, "recordings": _list_recordings(voice)}


@router.post("/recordings/upload")
async def upload_recordings(
    voice_name: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Nhận thư mục đã thu sẵn. Tên file phải là số thứ tự câu: 001.wav...

    Phải khai báo TRƯỚC /recordings/{no}: FastAPI khớp route theo thứ tự, để
    sau thì "upload" bị nuốt làm giá trị của {no}.
    """
    voice = safe_voice_name(voice_name)
    if not voice:
        return {"error": "Thiếu tên giọng"}

    d = _voice_dir(voice)
    d.mkdir(parents=True, exist_ok=True)

    saved, skipped = [], []
    for f in files:
        stem = Path(f.filename or "").stem
        digits = re.sub(r"\D", "", stem)
        if not digits or len(digits) > 3:
            skipped.append({"file": f.filename, "reason": "tên file không phải số thứ tự câu"})
            continue
        no = digits.zfill(3)
        suffix = Path(f.filename).suffix.lower()
        if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}:
            skipped.append({"file": f.filename, "reason": f"định dạng {suffix} không hỗ trợ"})
            continue

        # Giữ nguyên định dạng gốc: prepare_dataset.py đọc được cả 5 loại và sẽ
        # chuẩn hoá về 24kHz mono.
        (d / f"{no}{suffix}").write_bytes(await f.read())
        saved.append(no)

    return {"saved": sorted(saved), "skipped": skipped, "recordings": _list_recordings(voice)}


class SaveRecording(BaseModel):
    voice_name: str
    sample_rate: int
    pcm_b64: str          # PCM 16-bit little-endian, 1 kênh


@router.post("/recordings/upload-long")
async def upload_long_recording(
    voice_name: str = Form(...),
    file: UploadFile = File(...),
):
    """Nhận MỘT bản thu dài rồi tự cắt thành từng câu đánh số.

    Vì sao tách khỏi /recordings/upload: đường kia đòi tên file là số thứ tự câu
    để gán transcript theo kịch bản 60 câu. Một bản thu 30 phút không có số nào
    để gán - phải cắt trước, và nội dung sau khi cắt gần như chắc chắn không
    khớp kịch bản, nên BẮT BUỘC phiên âm bằng PhoWhisper ở bước chuẩn hoá.
    """
    voice = safe_voice_name(voice_name)
    if not voice:
        return {"error": "Thiếu tên giọng"}
    if runner.is_busy():
        return {"error": "Đang có tiến trình khác chạy.", "job_id": runner.running_job_id}
    if not SPLIT_SCRIPT.exists():
        return {"error": f"Thiếu script: {SPLIT_SCRIPT.relative_to(PROJECT_DIR)}"}

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}:
        return {"error": f"Định dạng {suffix or '?'} không hỗ trợ"}

    d = _voice_dir(voice)
    # Script cắt ghi ra 001.wav, 002.wav... nên nếu thư mục đã có bản thu thì nó
    # ĐÈ MẤT. Chặn thay vì đè - mất bản thu của người dùng là hỏng không cứu được.
    da_co = sorted(p.name for p in d.glob("*") if p.is_file()) if d.exists() else []
    if da_co:
        return {"error": f"Giọng '{voice}' đã có {len(da_co)} bản thu. "
                         "Cắt file dài sẽ ghi đè lên chúng. Dùng tên giọng mới, "
                         "hoặc xoá các bản thu cũ trước."}
    d.mkdir(parents=True, exist_ok=True)
    # Đặt NGOÀI thư mục bản thu: để bên trong thì chính file dài cũng bị coi là
    # một câu, và bước chuẩn hoá sẽ nuốt nguyên 30 phút vào một mẫu.
    tam = d.parent / f"_dai_{voice}{suffix}"
    tam.write_bytes(await file.read())

    cmd = [
        sys.executable, str(SPLIT_SCRIPT),
        "--input", str(tam),
        "--out", str(d),
    ]
    # Đánh dấu NGAY, trước khi job chạy: từ đây trở đi mọi bước tự biết các bản
    # thu này không khớp kịch bản và phải phiên âm bằng máy.
    _dat_nguon(voice, "cat_dai")

    job = runner.start("split", [Step(command=cmd, label="Cắt bản thu dài -> câu")],
                       f"Cắt bản thu dài cho giọng '{voice}'")
    return job.to_dict()


@router.post("/recordings/{no}")
async def save_recording(no: str, body: SaveRecording):
    """Ghi một câu. PCM giữ nguyên sample rate của trình duyệt.

    prepare_dataset.py hạ về 24kHz mono ở bước sau, nên không cần resample ở
    client - bớt một chỗ có thể sai.
    """
    voice = safe_voice_name(body.voice_name)
    if not voice:
        return {"error": "Thiếu tên giọng"}
    if not re.fullmatch(r"\d{3}", no):
        return {"error": "Số câu phải có dạng 001-999"}
    if not 8000 <= body.sample_rate <= 192000:
        return {"error": f"Sample rate không hợp lệ: {body.sample_rate}"}

    try:
        pcm = base64.b64decode(body.pcm_b64)
    except Exception:
        return {"error": "Dữ liệu audio hỏng"}
    if len(pcm) < 2:
        return {"error": "Bản thu rỗng"}

    duration = len(pcm) / 2 / body.sample_rate
    if duration < 0.4:
        return {"error": f"Bản thu quá ngắn ({duration:.1f}s) - thu lại"}
    if duration > 30:
        return {"error": f"Bản thu quá dài ({duration:.0f}s) - tối đa 30s mỗi câu"}

    d = _voice_dir(voice)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{no}.wav").write_bytes(pcm_to_wav(pcm, sample_rate=body.sample_rate))

    logger.info(f"Voice recording saved: {voice}/{no}.wav ({duration:.1f}s)")
    return {"no": no, "duration_s": round(duration, 2), "sample_rate": body.sample_rate}


@router.get("/recordings/{no}/audio")
async def get_recording_audio(no: str, voice_name: str):
    voice = safe_voice_name(voice_name)
    wav = _voice_dir(voice) / f"{no}.wav"
    if not voice or not re.fullmatch(r"\d{3}", no) or not wav.exists():
        return {"error": "Không có bản thu"}
    return FileResponse(wav, media_type="audio/wav")


@router.delete("/recordings/{no}")
async def delete_recording(no: str, voice_name: str):
    voice = safe_voice_name(voice_name)
    wav = _voice_dir(voice) / f"{no}.wav"
    if wav.exists():
        wav.unlink()
        return {"deleted": no}
    return {"error": "Không có bản thu"}


# ============================================================
# Chuẩn hoá dataset + train
# ============================================================

class PrepareRequest(BaseModel):
    voice_name: str
    use_asr: bool = True


@router.post("/prepare")
async def prepare(body: PrepareRequest):
    voice = safe_voice_name(body.voice_name)
    if not voice:
        return {"error": "Thiếu tên giọng"}
    if runner.is_busy():
        return {"error": "Đang có tiến trình khác chạy.", "job_id": runner.running_job_id}

    d = _voice_dir(voice)
    if not d.exists() or not any(d.iterdir()):
        return {"error": "Chưa có bản thu nào. Thu âm hoặc upload trước."}
    if not PREPARE_SCRIPT.exists():
        return {"error": f"Thiếu script: {PREPARE_SCRIPT.relative_to(PROJECT_DIR)}"}
    if not (PROJECT_DIR / "tools" / "F5-TTS-Vietnamese").exists():
        return {"error": "Chưa có tools/F5-TTS-Vietnamese. Cài F5-TTS ở tab Cài Model trước."}

    # sys.executable, không phải "python": pyenv/asdf hay chắn lệnh trần, và
    # script cần đúng venv có soundfile/librosa của backend.
    cmd = [
        sys.executable, str(PREPARE_SCRIPT),
        "--input", str(d),
        "--stt-server", settings.whisper_server_url,
    ]
    # HỆ THỐNG TỰ QUYẾT, không tin hoàn toàn vào ô tích của giao diện.
    #
    # Bản thu cắt từ file dài mà tắt nhận dạng thì mọi mẫu bị gán nhầm lời theo
    # kịch bản 60 câu - giọng train ra sẽ đọc sai, và lỗi đó chỉ lộ ra sau vài
    # giờ train. Một ô tích quên bấm không đáng để mất chừng đó thời gian.
    dung_asr = body.use_asr or _can_nhan_dang(voice)
    if not dung_asr:
        cmd.append("--no-asr")
    ep_asr = _can_nhan_dang(voice) and not body.use_asr

    # Ghi chủ sở hữu NGAY lúc bắt đầu: prepare xoá/ghi đè thư mục dùng chung, nên
    # từ giây này dataset đã thuộc về giọng đang chuẩn hoá, bất kể job có xong hay
    # không. Ghi ở cuối thì job hỏng giữa chừng sẽ để lại dataset lẫn lộn mà vẫn
    # mang tên chủ cũ.
    _dat_chu_dataset(voice)

    job = runner.start("prepare", [Step(command=cmd, label="Chuẩn hoá dataset")],
                       f"Chuẩn hoá dataset giọng '{voice}'")
    ra = job.to_dict()
    if ep_asr:
        # Nói ra chuyện đã tự bật, không im lặng sửa lựa chọn của người dùng.
        ra["ghi_chu"] = ("Đã TỰ BẬT nhận dạng giọng nói: bản thu của giọng này "
                        "cắt ra từ file dài nên không khớp kịch bản 60 câu.")
    return ra


class TrainRequest(BaseModel):
    voice_name: str
    epochs: int = 100
    batch_size: int = 3200


@router.post("/train")
async def train(body: TrainRequest):
    voice = safe_voice_name(body.voice_name)
    if not voice:
        return {"error": "Thiếu tên giọng"}
    if runner.is_busy():
        return {"error": "Đang có tiến trình khác chạy.", "job_id": runner.running_job_id}

    device = get_system_info().get("device", "cpu")
    if not str(device).startswith("cuda"):
        # train.sh hard-code CUDA_VISIBLE_DEVICES, chạy ở đây chắc chắn hỏng.
        # Chặn ngay thay vì để người dùng chờ rồi mới thấy lỗi.
        return {"error": f"Máy này chạy trên '{device}', train giọng cần GPU NVIDIA (CUDA). "
                         "Mở giao diện trên máy có RTX rồi train ở đó."}

    # Dataset đã chuẩn hoá là của giọng NÀO? Thư mục dùng chung nên rất dễ train
    # giọng A trên tiếng của giọng B: chuẩn hoá giọng A, rồi đổi tên ở ô trên và
    # bấm train. Không chặn thì mất vài giờ train mới nghe ra là sai giọng.
    chu = _dataset_cua_giong()
    if chu and chu != voice:
        return {"error": f"Dataset đã chuẩn hoá đang là của giọng '{chu}', "
                         f"không phải '{voice}'. Chạy lại bước 'Chuẩn hoá dataset' "
                         f"cho giọng '{voice}' trước khi train."}

    script = TRAIN_SCRIPT_PS1 if os.name == "nt" else TRAIN_SCRIPT
    if not script.exists():
        return {"error": f"Thiếu script: {script.relative_to(PROJECT_DIR)}"}
    if not DATASET_DIR.exists() or not any(DATASET_DIR.glob("*.wav")):
        return {"error": "Chưa có dataset đã chuẩn hoá. Chạy bước 'Chuẩn hoá dataset' trước."}

    pretrain = PROJECT_DIR / "models" / "tts" / "F5-TTS-Vietnamese-ViVoice" / "model_last.pt"
    if not pretrain.exists():
        return {"error": "Thiếu model gốc ViVoice. Cài TTS ở tab Cài Model trước."}

    if not 1 <= body.epochs <= 1000:
        return {"error": "epochs phải trong khoảng 1-1000"}
    if not 400 <= body.batch_size <= 20000:
        return {"error": "batch_size phải trong khoảng 400-20000"}

    if os.name == "nt":
        # KHÔNG truyền -StopServices: cờ đó gọi stop_services.ps1 -All, tức là
        # giết luôn backend - chính tiến trình đang chạy job này. VRAM được nhả
        # bằng _giai_phong_vram() bên dưới, backend vẫn sống để stream log.
        step = Step(
            command=["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script),
                     "-VoiceName", voice,
                     "-Epochs", str(body.epochs),
                     "-BatchSize", str(body.batch_size)],
            label=f"Fine-tune giọng '{voice}'",
        )
    else:
        step = Step(
            command=["bash", str(script), voice],
            label=f"Fine-tune giọng '{voice}'",
            env={"EPOCHS": body.epochs, "BATCH_SIZE": body.batch_size},
        )

    job = runner.start("train", [step], f"Train giọng '{voice}' ({body.epochs} epochs)")

    # F5-TTS đang nạp trong chính tiến trình này và giữ VRAM - phải nhả ra,
    # nếu không train chính nó sẽ tranh bộ nhớ với bản đang chạy.
    giai_phong_vram(job, {settings.ollama_model})
    theo_doi_roi_don(job)
    return job.to_dict()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = runner.get(job_id)
    if not job:
        return {"error": "Job không tồn tại"}
    return job.to_dict()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    return runner.cancel(job_id)
