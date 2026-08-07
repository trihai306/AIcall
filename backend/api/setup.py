"""
Cài đặt model từ giao diện web.

Kiểm tra model nào đã có, model nào thiếu, rồi chạy script cài đặt trong
scripts/install/ như một background job và stream log về frontend.
"""
import asyncio
import logging
import shlex
import shutil
import time
from pathlib import Path

import httpx
from fastapi import APIRouter

from backend.config import settings
from backend.core.jobs import JobRunner, Step, build_env

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/setup", tags=["setup"])

PROJECT_DIR = settings.project_dir
JOB_TIMEOUT_S = 3600  # 1 giờ - đủ cho model lớn trên mạng chậm

runner = JobRunner(PROJECT_DIR, timeout_s=JOB_TIMEOUT_S)


def _env() -> dict:
    return build_env(PROJECT_DIR)


def _which(name: str) -> str | None:
    return shutil.which(name, path=_env()["PATH"])


# ============================================================
# Kiểm tra trạng thái
# ============================================================

def _dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / 1024 / 1024, 1)


async def _ollama_models() -> list[str] | None:
    """Danh sách model trong Ollama. None nghĩa là server không chạy."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            if resp.status_code != 200:
                return None
            return [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception:
        return None


async def _http_ok(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            return (await client.get(url)).status_code == 200
    except Exception:
        return False


def _phowhisper_dir() -> Path | None:
    base = PROJECT_DIR / "models" / "phowhisper"
    if not base.exists():
        return None
    for d in sorted(base.iterdir()):
        if (d / "model.bin").exists():
            return d
    return None


def _f5tts_installed() -> bool:
    try:
        import f5_tts  # noqa: F401
        return True
    except Exception:
        return False


def _abs(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else PROJECT_DIR / p


async def _check_ollama() -> dict:
    binary = _which("ollama")
    return {
        "installed": binary is not None,
        "detail": binary or "Chưa cài Ollama",
        "size_mb": 0,
    }


async def _check_llm() -> dict:
    models = await _ollama_models()
    want = settings.ollama_model
    if models is None:
        return {"installed": False, "detail": "Ollama server chưa chạy", "size_mb": 0}
    base = want.split(":")[0]
    found = [m for m in models if m == want or m.split(":")[0] == base]
    return {
        "installed": bool(found),
        "detail": found[0] if found else f"Chưa có model '{want}'",
        "size_mb": 0,
    }


async def _check_stt() -> dict:
    d = _phowhisper_dir()
    return {
        "installed": d is not None,
        "detail": str(d.relative_to(PROJECT_DIR)) if d else "Chưa có model PhoWhisper CT2",
        "size_mb": _dir_size_mb(d) if d else 0,
    }


async def _check_tts() -> dict:
    ckpt = _abs(settings.f5tts_ckpt_path)
    vocab = _abs(settings.f5tts_vocab_path)
    pkg = _f5tts_installed()

    missing = []
    if not pkg:
        missing.append("package f5_tts")
    if not ckpt.exists():
        missing.append("model_last.pt")
    if not vocab.exists():
        missing.append("vocab.txt")

    return {
        "installed": not missing,
        "detail": "Sẵn sàng" if not missing else "Thiếu: " + ", ".join(missing),
        "size_mb": _dir_size_mb(ckpt.parent),
    }


_OLLAMA_PULL = f"""
set -e
if ! command -v ollama >/dev/null 2>&1; then
    echo "[ERROR] Chưa cài Ollama. Cài bước 'Ollama' trước."
    exit 1
fi
if ! curl -sf {shlex.quote(settings.ollama_base_url)}/api/tags >/dev/null 2>&1; then
    echo "Khởi động Ollama server..."
    nohup ollama serve > /tmp/ollama.log 2>&1 &
    sleep 4
fi
echo "Tải model {settings.ollama_model} ..."
ollama pull {shlex.quote(settings.ollama_model)}
"""

COMPONENTS: dict[str, dict] = {
    "ollama": {
        "name": "Ollama",
        "desc": "Runtime chạy LLM cục bộ",
        "size_hint": "~50 MB",
        "check": _check_ollama,
        "command": ["bash", "scripts/install/03_ollama.sh"],
        "requires": [],
    },
    "llm": {
        "name": f"LLM — {settings.ollama_model}",
        "desc": "Model sinh câu trả lời",
        "size_hint": "~2 GB",
        "check": _check_llm,
        "command": ["bash", "-c", _OLLAMA_PULL],
        "requires": ["ollama"],
    },
    "stt": {
        "name": "STT — PhoWhisper",
        "desc": "Nhận dạng giọng nói tiếng Việt",
        "size_hint": "~500 MB",
        "check": _check_stt,
        "command": ["bash", "scripts/install/02_pho_whisper.sh"],
        "requires": [],
    },
    "tts": {
        "name": "TTS — F5-TTS ViVoice",
        "desc": "Tổng hợp giọng nói tiếng Việt",
        "size_hint": "~5.4 GB",
        "check": _check_tts,
        "command": ["bash", "scripts/install/07_tts_model.sh"],
        "requires": [],
    },
}

INSTALL_ORDER = ["ollama", "llm", "stt", "tts"]


@router.get("/status")
async def get_status():
    """Trạng thái cài đặt của từng model + dịch vụ đang chạy."""
    components = []
    for cid in INSTALL_ORDER:
        spec = COMPONENTS[cid]
        try:
            state = await spec["check"]()
        except Exception as e:
            logger.exception("check %s failed", cid)
            state = {"installed": False, "detail": f"Lỗi kiểm tra: {e}", "size_mb": 0}

        components.append({
            "id": cid,
            "name": spec["name"],
            "desc": spec["desc"],
            "size_hint": spec["size_hint"],
            "requires": spec["requires"],
            **state,
        })

    ollama_up, whisper_up = await asyncio.gather(
        _http_ok(f"{settings.ollama_base_url}/api/tags"),
        _http_ok(f"{settings.whisper_server_url}/health"),
    )

    from backend.main import app_state

    return {
        "components": components,
        "services": {
            "ollama": ollama_up,
            "whisper": whisper_up,
            "tts_loaded": bool(getattr(app_state.tts, "_is_loaded", False)),
        },
        "running_job": runner.running_job_id,
    }


@router.post("/install/{component}")
async def install(component: str):
    """Cài một model. component='all' để cài tất cả những gì còn thiếu."""
    if runner.is_busy():
        return {"error": "Đang có tiến trình cài đặt khác chạy.", "job_id": runner.running_job_id}

    if component == "all":
        steps = []
        for cid in INSTALL_ORDER:
            state = await COMPONENTS[cid]["check"]()
            if not state["installed"]:
                steps.append(Step(command=COMPONENTS[cid]["command"], label=COMPONENTS[cid]["name"]))
        if not steps:
            return {"error": "Tất cả model đã được cài."}
        label = "Cài tất cả (" + ", ".join(s.label for s in steps) + ")"
        return runner.start("all", steps, label).to_dict()

    spec = COMPONENTS.get(component)
    if not spec:
        return {"error": f"Không có component '{component}'"}

    for dep in spec["requires"]:
        if not (await COMPONENTS[dep]["check"]())["installed"]:
            return {"error": f"Cần cài '{COMPONENTS[dep]['name']}' trước."}

    step = Step(command=spec["command"], label=spec["name"])
    return runner.start(component, [step], spec["name"]).to_dict()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = runner.get(job_id)
    if not job:
        return {"error": "Job không tồn tại"}
    return job.to_dict()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    return runner.cancel(job_id)


# ============================================================
# Dịch vụ: bật server, nạp model vào RAM
# ============================================================

@router.post("/service/{name}/start")
async def start_service(name: str):
    """Bật Ollama server hoặc PhoWhisper server (chạy nền, không chặn)."""
    commands = {
        "ollama": ["ollama", "serve"],
        "whisper": ["bash", "whisper_server/start.sh"],
    }
    if name not in commands:
        return {"error": f"Không có dịch vụ '{name}'"}

    urls = {
        "ollama": f"{settings.ollama_base_url}/api/tags",
        "whisper": f"{settings.whisper_server_url}/health",
    }
    if await _http_ok(urls[name]):
        return {"status": "already_running"}

    if name == "ollama" and not _which("ollama"):
        return {"error": "Chưa cài Ollama."}
    if name == "whisper" and _phowhisper_dir() is None:
        return {"error": "Chưa có model PhoWhisper. Cài STT trước."}

    log_path = PROJECT_DIR / "data" / f"{name}_server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "ab")

    await asyncio.create_subprocess_exec(
        *commands[name],
        cwd=str(PROJECT_DIR),
        env=_env(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=log_file,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )

    # PhoWhisper mất ~20s nạp model; chờ tới khi /health trả lời
    deadline = time.time() + (60 if name == "whisper" else 20)
    while time.time() < deadline:
        await asyncio.sleep(2)
        if await _http_ok(urls[name]):
            return {"status": "started", "log": str(log_path.relative_to(PROJECT_DIR))}

    return {
        "status": "starting",
        "message": f"Đang khởi động, xem log: {log_path.relative_to(PROJECT_DIR)}",
    }


@router.post("/reload-tts")
async def reload_tts():
    """Nạp F5-TTS vào RAM mà không cần restart backend (mất ~30-60s)."""
    from backend.main import app_state

    if getattr(app_state.tts, "_is_loaded", False):
        return {"status": "already_loaded"}

    state = await _check_tts()
    if not state["installed"]:
        return {"error": state["detail"]}

    try:
        t0 = time.time()
        await asyncio.to_thread(app_state.tts.load)
        return {"status": "loaded", "elapsed_s": round(time.time() - t0, 1)}
    except Exception as e:
        logger.exception("reload tts failed")
        return {"error": str(e)}
