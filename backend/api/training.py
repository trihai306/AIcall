"""Fine-tune LLM từ giao diện web: quản lý dataset, dựng môi trường, train.

Trước đây endpoint /start chỉ trả về một khối text hướng dẫn để người dùng tự
copy vào terminal - không train gì cả. Giờ chạy thật qua JobRunner, cùng cơ chế
với trang Cài Model và Training giọng.

Train LLM cần 8-10GB VRAM mà máy chỉ có 12GB, F5-TTS và Ollama đang giữ một
phần. Nên trước khi train phải nhả VRAM ra, và nạp lại sau khi xong.
"""

import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel, Field

from backend.config import settings
from backend.core.device import get_system_info
from backend.core.jobs import JobRunner, Step
from backend.core.vram import giai_phong_vram, theo_doi_roi_don
from backend.core.training_guard import live_service_busy_reason

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/training", tags=["training"])

PROJECT_DIR = settings.project_dir
DATASET_DIR = PROJECT_DIR / "data" / "training"
DATASET_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_DIR = PROJECT_DIR / "training" / "llm"
SETUP_SCRIPT = TRAIN_DIR / "setup_env.py"
MAKE_DATASET = TRAIN_DIR / "make_dataset.py"
TRAIN_SCRIPT = TRAIN_DIR / "train_lora.py"
DEPLOY_SCRIPT = TRAIN_DIR / "deploy_ollama.py"
SINH_MAU_SCRIPT = TRAIN_DIR / "sinh_mau_tu_tri_thuc.py"
THU_MUC_TRI_THUC = PROJECT_DIR / "knowledge"
VENV_TRAIN = PROJECT_DIR / ".venv-train"
MERGED = DATASET_DIR / "merged_dataset.jsonl"
BANKVN_STATE_DIR = PROJECT_DIR / "data" / "bankvn" / "state"
BANKVN_CONTINUOUS = BANKVN_STATE_DIR / "continuous.json"
BANKVN_PROGRESS = BANKVN_STATE_DIR / "progress.json"
BANKVN_ROUTER_GATE = BANKVN_STATE_DIR / "router-classifier-gate.json"
BANKVN_HISTORY = BANKVN_STATE_DIR / "history.jsonl"
BANKVN_PAUSED = BANKVN_STATE_DIR / "paused.json"
BANKVN_ASSISTANT_GATE = BANKVN_STATE_DIR / "assistant-gate.json"
BANKVN_STALE_SECONDS = 30 * 60
BANKVN_TEST_OLLAMA_URL = os.getenv(
    "BANKVN_TEST_OLLAMA_URL", "http://127.0.0.1:11435"
).rstrip("/")
BANKVN_TEST_MODEL = os.getenv("BANKVN_TEST_MODEL", "bankvn-candidate-live")
BANKVN_TEST_GGUF = (
    PROJECT_DIR / "models" / "bankvn" / "gguf" /
    f"{BANKVN_TEST_MODEL}-f16.gguf"
)

# Fine-tune 234 mẫu x 3 epoch mất 30-60 phút; để rộng cho dataset lớn hơn.
JOB_TIMEOUT_S = 8 * 3600

# Dưới mức này thì fine-tune học không đủ pattern (theo training/llm/README.md).
MIN_SAMPLES = 200

runner = JobRunner(PROJECT_DIR, timeout_s=JOB_TIMEOUT_S)


@router.get("/availability")
async def training_availability():
    """Read-only GPU admission signal for schedulers and the training UI."""
    reason = live_service_busy_reason()
    return {"can_use_gpu": not reason and not runner.is_busy(),
            "reason": reason or ("Đang có job train chạy." if runner.is_busy() else ""),
            "job_id": runner.running_job_id}

# Tên model sinh ra trong Ollama. Phải khớp dòng FROM của Modelfile tương ứng.
MODEL_NAME = "tuvan-qwen"
MODELFILE = "Modelfile.tuvan-qwen"
GGUF_NAME = "tuvan-qwen-q4.gguf"


def venv_train_python() -> Path:
    return VENV_TRAIN / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _doc_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _utc_age_seconds(value) -> int | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(
            0,
            int((datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()),
        )
    except ValueError:
        return None


def _bankvn_recent_cycles(limit: int = 5) -> list[dict]:
    try:
        lines = BANKVN_HISTORY.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    recent: list[dict] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            recent.append(item)
        if len(recent) >= limit:
            break
    return list(reversed(recent))


def _bankvn_24x7_status() -> dict:
    state = _doc_json(BANKVN_CONTINUOUS)
    progress = _doc_json(BANKVN_PROGRESS)
    paused = _doc_json(BANKVN_PAUSED)
    assistant_gate = _doc_json(BANKVN_ASSISTANT_GATE)
    if not state and not progress:
        return {
            "available": False,
            "stale": True,
            "age_seconds": None,
            "message": "Chưa có trạng thái BankVN 24/7 trên máy này",
        }

    last_cycle_utc = state.get("last_cycle_utc") or progress.get("last_cycle_utc")
    age_seconds = _utc_age_seconds(last_cycle_utc)

    gate = _doc_json(BANKVN_ROUTER_GATE)
    quality = state.get("sft_quality") or {}
    router_state = state.get("router_classifier") or {}
    candidate_metrics = gate.get("metrics") or {}
    current_metrics = gate.get("current_metrics") or {}
    progress_updated = progress.get("updated_at_utc")
    progress_age_seconds = _utc_age_seconds(progress_updated)
    cycle_age_seconds = _utc_age_seconds(progress.get("cycle_started_utc"))
    freshness_age = progress_age_seconds if progress_age_seconds is not None else age_seconds
    stale = freshness_age is None or freshness_age > BANKVN_STALE_SECONDS

    return {
        "available": True,
        "paused": bool(paused),
        "pause_reason": paused.get("reason"),
        "paused_at_utc": paused.get("paused_at_utc"),
        "stale": stale,
        "age_seconds": freshness_age,
        "stale_after_seconds": BANKVN_STALE_SECONDS,
        "last_cycle_utc": last_cycle_utc,
        "progress": {
            "phase": progress.get("phase"),
            "updated_at_utc": progress_updated,
            "age_seconds": progress_age_seconds,
            "cycle_started_utc": progress.get("cycle_started_utc"),
            "cycle_age_seconds": cycle_age_seconds,
            "error": progress.get("error"),
            "next_cycle_in_seconds": progress.get("next_cycle_in_seconds"),
            "active_process": progress.get("active_process"),
            "active_process_pid": progress.get("active_process_pid"),
            "active_process_elapsed_seconds": progress.get("active_process_elapsed_seconds"),
        },
        "profile": state.get("profile"),
        "new_teacher_samples": state.get("new_teacher_samples", 0),
        "new_assistant_samples": state.get("new_assistant_samples", 0),
        "new_router_samples": state.get("new_router_samples", 0),
        "teacher_samples_total": state.get("teacher_samples_total", 0),
        "teacher_samples_per_minute": state.get("teacher_samples_per_minute"),
        "teacher_elapsed_seconds": state.get("teacher_elapsed_seconds"),
        "teacher_workers": state.get("teacher_workers"),
        "new_speech_profiles": state.get("new_speech_profiles") or {},
        "new_speech_regions": state.get("new_speech_regions") or {},
        "train_elapsed_seconds": state.get("train_elapsed_seconds"),
        "cycle_elapsed_seconds": state.get("cycle_elapsed_seconds"),
        "promotion": state.get("promotion"),
        "sft": {
            "train_loss": quality.get("sft_training_loss"),
            "eval_loss_before": quality.get("sft_eval_loss_before"),
            "eval_loss_after": quality.get("sft_eval_loss_after"),
            "eval_improvement_pct": quality.get("sft_eval_loss_improvement_pct"),
            "train_runtime": quality.get("train_runtime"),
            "samples_per_second": quality.get("train_samples_per_second"),
            "cuda_peak_allocated_gb": quality.get("cuda_peak_allocated_gb"),
            "cuda_peak_reserved_gb": quality.get("cuda_peak_reserved_gb"),
        },
        "router": {
            "status": router_state.get("status"),
            "eligible_manual_review": gate.get("eligible_manual_review"),
            "checks": gate.get("checks") or {},
            "candidate": candidate_metrics,
            "current": current_metrics,
        },
        "assistant_gate": {
            "passed": assistant_gate.get("passed"),
            "model": assistant_gate.get("model"),
            "usable_rate": assistant_gate.get("usable_rate"),
            "semantic_rate": assistant_gate.get("semantic_rate"),
            "safe_rate": assistant_gate.get("safe_rate"),
            "degenerate_rate": assistant_gate.get("degenerate_rate"),
            "stop_rate": assistant_gate.get("stop_rate"),
            "failures": assistant_gate.get("failures") or [],
        },
        "recent_cycles": _bankvn_recent_cycles(),
    }


class BankVNTestRequest(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)


def _bankvn_test_messages(req: BankVNTestRequest) -> list[dict]:
    messages = [{
        "role": "system",
        "content": (
            "Bạn là trợ lý ngân hàng Việt Nam đang được thử nghiệm. "
            "Trả lời ngắn gọn bằng tiếng Việt. Không tự bịa lãi suất, hạn mức, "
            "điều kiện, trạng thái hồ sơ hoặc thông tin không có trong câu hỏi. "
            "Nếu chưa có dữ liệu sản phẩm hoặc hồ sơ thì tuyệt đối không đưa con số; "
            "hãy hướng dẫn khách kiểm tra trên kênh chính thức. "
            "Không hỏi hoặc tiết lộ mật khẩu, mã OTP, mã CVV hay toàn bộ số thẻ. "
            "Vay tín chấp không yêu cầu tài sản bảo đảm. Trả lời tối đa 80 từ."
        ),
    }]
    for item in req.history[-8:]:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:4000]})
    messages.append({"role": "user", "content": req.message.strip()[:2000]})
    return messages


@router.get("/bankvn-test/status")
async def bankvn_test_status():
    """Trạng thái Ollama CPU riêng dùng thử candidate, không chiếm GPU train."""
    model_details: dict = {}
    model_record: dict = {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{BANKVN_TEST_OLLAMA_URL}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            names = [str(item.get("name") or "") for item in models]
            normalized = {name.removesuffix(":latest") for name in names}
            ready = BANKVN_TEST_MODEL.removesuffix(":latest") in normalized
            if ready:
                model_record = next(
                    (
                        item for item in models
                        if str(item.get("name") or "").removesuffix(":latest")
                        == BANKVN_TEST_MODEL.removesuffix(":latest")
                    ),
                    {},
                )
                show_response = await client.post(
                    f"{BANKVN_TEST_OLLAMA_URL}/api/show",
                    json={"model": BANKVN_TEST_MODEL},
                )
                show_response.raise_for_status()
                model_details = show_response.json().get("details") or {}
    except Exception as exc:
        return {
            "ready": False,
            "model": BANKVN_TEST_MODEL,
            "message": f"Máy thử BankVN chưa sẵn sàng: {exc}",
        }

    snapshot = model_record.get("modified_at")
    if not snapshot:
        try:
            snapshot = datetime.fromtimestamp(
                BANKVN_TEST_GGUF.stat().st_mtime, tz=timezone.utc
            ).isoformat()
        except OSError:
            pass
    return {
        "ready": ready,
        "model": BANKVN_TEST_MODEL,
        "parameter_size": model_details.get("parameter_size"),
        "quantization_level": model_details.get("quantization_level"),
        "family": model_details.get("family"),
        "runtime": "CPU riêng — không chiếm GPU training",
        "snapshot_utc": snapshot,
        "message": "Sẵn sàng" if ready else "Chưa nạp snapshot candidate vào máy thử",
    }


@router.post("/bankvn-test/chat")
async def bankvn_test_chat(req: BankVNTestRequest):
    question = req.message.strip()
    if not question:
        return {"error": "Nhập câu muốn thử."}
    if len(question) > 2000:
        return {"error": "Câu thử dài quá 2.000 ký tự."}

    payload = {
        "model": BANKVN_TEST_MODEL,
        "messages": _bankvn_test_messages(req),
        "stream": False,
        "keep_alive": "10m",
        # Ollama Windows không luôn tôn trọng CUDA_VISIBLE_DEVICES của process
        # serve phụ. num_gpu=0 đặt ngay trên từng request mới là chốt chắc chắn
        # candidate không tranh VRAM với Qwen teacher/SFT 24/7.
        "options": {"temperature": 0.0, "num_predict": 160, "num_gpu": 0},
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{BANKVN_TEST_OLLAMA_URL}/api/chat", json=payload
            )
            response.raise_for_status()
        data = response.json()
        answer = str((data.get("message") or {}).get("content") or "").strip()
        if not answer:
            return {"error": "Candidate không sinh được câu trả lời."}
        return {
            "answer": answer,
            "model": BANKVN_TEST_MODEL,
            "eval_count": data.get("eval_count"),
            "eval_duration": data.get("eval_duration"),
        }
    except httpx.TimeoutException:
        return {"error": "Candidate phản hồi quá 120 giây."}
    except Exception as exc:
        logger.warning("Thử BankVN candidate lỗi: %s", exc)
        return {"error": f"Không gọi được candidate: {exc}"}


# ============================================================
# Dataset
# ============================================================

SAMPLE_SYSTEM = (
    "Bạn là nhân viên tư vấn ngân hàng ABC, tên Lan, đang gọi điện cho khách. "
    "Trả lời tối đa 35 từ trong 1-2 câu, xưng em, gọi khách là anh/chị. "
    "Chỉ dùng dữ kiện có trong ngữ cảnh hoặc do khách vừa nói; không tự thêm con số."
)

# Phải khớp ràng buộc của CORE_RULES trong services/llm_service.py: tối đa 35
# từ / 2 câu, giữ nguyên con số khách nói và không tự thêm dữ kiện. Model học
# theo data, nên mẫu có facts sản phẩm cố định sẽ biến LoRA thành một bản RAG
# cũ không thể cập nhật khi tài liệu đổi.
#
# Câu hỏi ở đây cố ý KHÔNG trùng với dataset chính: make_dataset.py gộp mọi file
# .jsonl trong thư mục, trùng câu hỏi sẽ làm model thiên lệch về mẫu đó.
SAMPLE_PAIRS = [
    ("Tôi muốn vay để sửa nhà",
     "Dạ em ghi nhận nhu cầu vay để sửa nhà ạ. Anh chị muốn tìm hiểu điều kiện hay hồ sơ trước để em tư vấn đúng phần đó ạ?"),
    ("Lương 12 triệu vay được bao nhiêu?",
     "Dạ hạn mức cụ thể cần dựa trên hồ sơ và thông tin sản phẩm ạ. Em sẽ dùng đúng dữ liệu hệ thống, không tự đoán số tiền cho anh chị."),
    ("Hồ sơ bị từ chối thì sao?",
     "Dạ em cần xem đúng lý do và trạng thái hồ sơ mới tư vấn chính xác ạ. Em không đoán khi hệ thống chưa có dữ liệu đó."),
    ("Tôi đang làm việc ở nước ngoài vay được không?",
     "Dạ em sẽ ghi nhận và có chuyên viên liên hệ lại ạ. Anh chị cho em xin số liên lạc nhé ạ?"),
    ("Vay tín chấp và mở thẻ cái nào lợi hơn?",
     "Dạ hai sản phẩm phục vụ nhu cầu khác nhau ạ. Anh chị cần tiền mặt hay chủ yếu muốn chi tiêu bằng thẻ để em tư vấn đúng hơn ạ?"),
]


# Mọi định dạng make_dataset.py đọc được. .csv là mẫu cho người dùng tự điền
# bằng Excel, .txt là transcript cuộc gọi dạng "KH:/TV:".
DUOI_FILE = (".jsonl", ".json", ".csv", ".txt")


def _co_the_train(path: Path) -> bool:
    """Do not offer evaluation logs or generated train outputs as a source."""
    name = path.stem.lower()
    blocked = ("challenge", "stress", "audit", "recheck", "_eval", "_raw", "_teacher_")
    return not any(marker in name for marker in blocked) and not name.startswith("banking-qwen")


def _dem_mau(path: Path) -> int:
    """Đếm đúng số cặp train đọc được, không đếm dòng thô của transcript."""
    try:
        cap = _doc_cap_tu_file(path.read_text(encoding="utf-8-sig"), path.suffix.lower())
        return len(cap)
    except Exception:
        return 0


@router.get("/datasets")
async def list_datasets():
    """Liệt kê dataset đã có. Bỏ qua file gộp - nó là kết quả, không phải nguồn."""
    datasets = []
    files = sorted(f for d in DUOI_FILE for f in DATASET_DIR.glob(f"*{d}"))
    for f in files:
        if f.name == MERGED.name:
            continue
        stat = f.stat()
        try:
            lines = f.read_text(encoding="utf-8-sig").splitlines()
            preview = next((l.strip()[:200] for l in lines if l.strip()), "")
        except Exception:
            preview = ""
        count = _dem_mau(f)
        datasets.append({
            "id": f.stem,
            "filename": f.name,
            "size_kb": round(stat.st_size / 1024, 1),
            "samples": count,
            "trainable": _co_the_train(f) and count >= 30,
            "preview": preview,
            "created": stat.st_mtime,
        })
    return {
        "datasets": datasets,
        "tong_mau": sum(d["samples"] for d in datasets),
        "min_samples": MIN_SAMPLES,
    }


# Cột của file mẫu. Giữ tên không dấu để Excel ở mọi máy đều mở đúng, và khớp
# với danh sách _COT_HOI/_COT_TRA_LOI trong training/llm/make_dataset.py.
COT_MAU = ["khach_hoi", "tu_van_tra_loi", "ghi_chu"]

# Mẫu điền sẵn: mỗi dòng minh hoạ một tình huống khác nhau và đều ĐẠT luật
# phong cách, để người dùng nhìn là biết viết thế nào cho đúng.
DONG_MAU = [
    ("Lãi suất vay tín chấp bao nhiêu?",
     "Dạ em sẽ trả đúng mức đang có trong thông tin sản phẩm của hệ thống ạ. Em không tự đoán lãi suất khi chưa có nguồn.",
     "Facts thay đổi như lãi suất phải lấy từ tài liệu/RAG, không train cứng vào LoRA"),
    ("Tôi muốn vay 100 triệu",
     "Dạ em ghi nhận anh chị muốn vay 100 triệu ạ. Anh chị đang quan tâm thời hạn khoảng bao lâu để em tư vấn theo đúng thông tin sản phẩm ạ?",
     "Giữ nguyên con số khách nói; không tự đổi thành số khác"),
    ("Mở thẻ tín dụng cần giấy tờ gì?",
     "Dạ em sẽ dựa đúng mục điều kiện mở thẻ trong tài liệu để trả lời anh chị ạ. Em không tự thêm giấy tờ ngoài nguồn.",
     "Dữ kiện sản phẩm nằm trong tài liệu, dataset chỉ dạy hành vi"),
    ("Tôi không quan tâm",
     "Dạ em xin lỗi đã làm phiền anh chị ạ. Em cảm ơn anh chị đã nghe máy ạ.",
     "Khách từ chối thì cảm ơn rồi dừng, đừng nài"),
    ("Tôi bận lắm",
     "Dạ em xin lỗi đã làm phiền ạ. Em xin phép gọi lại lúc khác ạ.",
     ""),
    ("Gửi tiết kiệm lãi bao nhiêu?",
     "Dạ em sẽ ghi nhận và có chuyên viên liên hệ lại ạ. Anh chị quan tâm vay hay thẻ không ạ?",
     "Câu ngoài phạm vi thì dùng đúng câu này, đừng bịa"),
    ("", "", "Xoá các dòng mẫu phía trên rồi điền của anh chị vào đây"),
]


def _tao_csv_mau() -> str:
    import csv as _csv
    import io
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(COT_MAU)
    for r in DONG_MAU:
        w.writerow(r)
    return buf.getvalue()


@router.get("/datasets/template")
async def tai_mau_csv():
    """Tải file CSV mẫu để điền bằng Excel.

    Ghi kèm BOM (utf-8-sig): Excel trên Windows mặc định đọc CSV theo bảng mã
    hệ thống, không có BOM là toàn bộ tiếng Việt hiện thành ký tự lạ và người
    dùng tưởng file hỏng.
    """
    from fastapi.responses import Response
    noi_dung = _tao_csv_mau().encode("utf-8-sig")
    return Response(
        content=noi_dung,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="mau_dataset_tu_van.csv"'},
    )


def _doc_cap_tu_file(text: str, ext: str) -> list[tuple[str, str]]:
    """Rút (câu hỏi, câu trả lời) từ nội dung file để đem đi kiểm tra."""
    cap: list[tuple[str, str]] = []
    if ext == ".csv":
        import csv as _csv
        import io
        rows = [r for r in _csv.reader(io.StringIO(text)) if any((c or "").strip() for c in r)]
        if not rows:
            return []
        # Bỏ dòng tiêu đề nếu nhận ra được
        dau = 1 if rows and any("khach" in (c or "").lower() or "hoi" in (c or "").lower()
                                for c in rows[0]) else 0
        for r in rows[dau:]:
            if len(r) >= 2:
                cap.append((r[0].strip(), r[1].strip()))
    elif ext == ".txt":
        pending_user = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            upper = line[:3].upper()
            if upper.startswith("KH:"):
                pending_user = line[3:].strip()
            elif upper.startswith("TV:"):
                reply = line[3:].strip()
                if pending_user and reply:
                    cap.append((pending_user, reply))
                    pending_user = None
    elif ext == ".json":
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return []
        objs = raw if isinstance(raw, list) else [raw]
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            msgs = obj.get("messages") or []
            hoi = next((m.get("content", "") for m in reversed(msgs)
                        if isinstance(m, dict) and m.get("role") == "user"), "")
            tl = next((m.get("content", "") for m in reversed(msgs)
                       if isinstance(m, dict) and m.get("role") == "assistant"), "")
            if hoi and tl:
                cap.append((hoi, tl))
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msgs = obj.get("messages") or []
            hoi = next((m.get("content", "") for m in reversed(msgs)
                        if isinstance(m, dict) and m.get("role") == "user"), "")
            tl = next((m.get("content", "") for m in reversed(msgs)
                       if isinstance(m, dict) and m.get("role") == "assistant"), "")
            if hoi and tl:
                cap.append((hoi, tl))
    return cap


@router.post("/datasets/upload")
async def upload_dataset(file: UploadFile = File(...), name: str = Form("")):
    content = await file.read()
    # utf-8-sig: file lưu từ Excel có BOM, đọc bằng utf-8 thường thì BOM dính
    # vào ô đầu tiên và cột đó không bao giờ khớp tên.
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {"error": "File phải lưu ở bảng mã UTF-8. Trong Excel chọn "
                         "'CSV UTF-8 (Comma delimited)' khi lưu."}

    dataset_name = name.strip() or Path(file.filename or "dataset").stem
    safe_name = "".join(c for c in dataset_name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        return {"error": "Tên dataset không hợp lệ"}
    if safe_name == MERGED.stem:
        return {"error": f"'{safe_name}' là tên file gộp do hệ thống sinh, chọn tên khác"}

    ext = (Path(file.filename or "").suffix or ".jsonl").lower()
    if ext not in (".jsonl", ".json", ".csv", ".txt"):
        return {"error": f"Không hỗ trợ định dạng {ext}. Dùng .csv, .jsonl hoặc .txt"}

    save_path = DATASET_DIR / f"{safe_name}{ext}"
    save_path.write_text(text, encoding="utf-8")

    cap = _doc_cap_tu_file(text, ext)
    from backend.core.dataset_rules import kiem_tra_cap
    kiem_tra = kiem_tra_cap(cap) if cap else None

    logger.info(f"Dataset uploaded: {safe_name}{ext} ({len(cap)} mẫu)")
    return {
        "id": safe_name,
        "filename": save_path.name,
        "samples": len(cap),
        "size_kb": round(len(content) / 1024, 1),
        "kiem_tra": kiem_tra,
    }


@router.get("/datasets/{dataset_id}/check")
async def kiem_tra_dataset(dataset_id: str):
    """Soi một dataset đã có theo luật phong cách."""
    for ext in (".csv", ".jsonl", ".json", ".txt"):
        p = DATASET_DIR / f"{dataset_id}{ext}"
        if p.exists():
            cap = _doc_cap_tu_file(p.read_text(encoding="utf-8-sig"), ext)
            if not cap:
                return {"error": "Không đọc được mẫu nào trong file"}
            from backend.core.dataset_rules import kiem_tra_cap
            return {"id": dataset_id, "filename": p.name, "kiem_tra": kiem_tra_cap(cap)}
    return {"error": "Không thấy dataset"}


@router.post("/datasets/generate-sample")
async def generate_sample_dataset():
    samples = [
        {"messages": [
            {"role": "system", "content": SAMPLE_SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]}
        for user, assistant in SAMPLE_PAIRS
    ]
    save_path = DATASET_DIR / "banking_sample.jsonl"
    with open(save_path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    return {"id": "banking_sample", "filename": "banking_sample.jsonl",
            "samples": len(samples),
            "message": "Dataset mẫu đã được tạo với 5 mẫu hội thoại ngân hàng"}


# Xin bao nhiêu cặp một mảnh. Trên 40 thì model bắt đầu bịa ra hàng loạt câu
# hỏi na ná nhau cho cùng một đoạn ngắn, và bộ lọc trùng bỏ gần hết - tốn thời
# gian gọi model mà không thêm được mẫu nào.
SO_CAP_TOI_DA = 40


@router.post("/datasets/sinh-tu-tri-thuc")
async def sinh_tu_tri_thuc(nhom: str = "", so_cap: int = 20):
    """Sinh dataset từ chính tài liệu tri thức đang dùng để tư vấn.

    Chạy qua JobRunner như mọi job khác: sinh vài trăm mẫu bằng model 7B mất
    nhiều phút, chạy thẳng trong request là treo trình duyệt rồi đứt giữa chừng.
    """
    if runner.is_busy():
        return {"error": "Đang có tiến trình khác chạy.", "job_id": runner.running_job_id}
    if not SINH_MAU_SCRIPT.exists():
        return {"error": f"Thiếu script: {SINH_MAU_SCRIPT.relative_to(PROJECT_DIR)}"}

    co_tai_lieu = any(THU_MUC_TRI_THUC.rglob("*.md")) or any(THU_MUC_TRI_THUC.rglob("*.txt"))
    if not co_tai_lieu:
        return {"error": "Chưa có tài liệu nào trong Tri thức AI. "
                         "Thêm tài liệu trước rồi sinh mẫu từ đó."}

    so_cap = max(1, min(int(so_cap or 20), SO_CAP_TOI_DA))
    lenh = [sys.executable, str(SINH_MAU_SCRIPT), "--so-cap", str(so_cap)]
    if nhom:
        lenh += ["--nhom", nhom]

    job = runner.start("sinh-mau", [Step(command=lenh, label="Sinh mẫu từ tài liệu")],
                       f"Sinh mẫu train từ tài liệu tri thức ({so_cap} cặp/mảnh)")
    return job.to_dict()


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str):
    for ext in DUOI_FILE:
        p = DATASET_DIR / f"{dataset_id}{ext}"
        if p.exists():
            p.unlink()
            return {"deleted": dataset_id}
    return {"error": "Dataset not found"}


# ============================================================
# Trạng thái
# ============================================================

@router.get("/status")
async def get_status():
    """Mọi thứ UI cần để biết bấm Train được chưa."""
    sys_info = get_system_info()
    device = str(sys_info.get("device", "cpu"))
    py = venv_train_python()

    vram_free = vram_total = None
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            vram_free = round(free / 1024**3, 1)
            vram_total = round(total / 1024**3, 1)
    except Exception:
        pass

    # Phải quét đủ DUOI_FILE, không riêng .jsonl: dataset dạng .csv người dùng
    # tự điền cũng được gộp vào lúc train, đếm thiếu thì thẻ trạng thái báo sai
    # và cờ "đủ mẫu" cũng sai theo.
    tong_mau = sum(
        _dem_mau(f)
        for d in DUOI_FILE for f in DATASET_DIR.glob(f"*{d}")
        if f.name != MERGED.name
    )

    return {
        "env_ready": py.exists(),
        "venv_path": str(VENV_TRAIN),
        "gpu_ok": device.startswith("cuda"),
        "device": device,
        "gpu_name": sys_info.get("gpu_name", ""),
        "vram_free_gb": vram_free,
        "vram_total_gb": vram_total,
        "tong_mau": tong_mau,
        "min_samples": MIN_SAMPLES,
        "du_mau": tong_mau >= MIN_SAMPLES,
        "running_job": runner.running_job_id,
        "model_dang_dung": settings.ollama_model,
        "model_sau_train": "candidate riêng để A/B",
        "bankvn_24x7": _bankvn_24x7_status(),
    }


# ============================================================
# Dựng môi trường (.venv-train)
# ============================================================

@router.post("/env/setup")
async def setup_env(force: bool = False):
    """Dựng .venv-train. Tách khỏi /start vì nó tải vài GB và chỉ cần làm một lần.

    Gộp vào mỗi lần train thì lỗi cài và lỗi train trộn vào nhau, rất khó gỡ.
    """
    if runner.is_busy():
        return {"error": "Đang có tiến trình khác chạy.", "job_id": runner.running_job_id}
    if not SETUP_SCRIPT.exists():
        return {"error": f"Thiếu script: {SETUP_SCRIPT.relative_to(PROJECT_DIR)}"}

    cmd = [sys.executable, str(SETUP_SCRIPT)]
    if force:
        cmd.append("--force")
    job = runner.start("env-setup", [Step(command=cmd, label="Dựng môi trường training")],
                       "Cài môi trường training (tải vài GB, mất một lúc)")
    return job.to_dict()


# ============================================================
# Train
# ============================================================

class TrainingConfig(BaseModel):
    # Base 3B này vừa RTX 5070 12GB, nhưng KHÔNG mặc định coi là tương đương
    # model production. Nếu production đang là Qwen3.5-9B thì chuyển thẳng sang
    # bản 3B sau train là hạ model, phải A/B trước.
    base_model: str = "Qwen/Qwen2.5-3B-Instruct"
    dataset_id: str = ""
    epochs: int = 3
    learning_rate: float = 2e-4
    lora_rank: int = 16
    batch_size: int = 2
    grad_accum: int = 8
    auto_deploy: bool = False


def _chuyen_model_khi_xong(auto_deploy: bool):
    """Trả về bước dọn riêng của train LLM: chuyển settings sang model mới."""
    async def _xong(job):
        if auto_deploy and job.status == "done":
            # deploy_ollama.py đã sửa .env, nhưng settings đã nạp từ lúc khởi
            # động. Sửa luôn trong bộ nhớ để model mới ăn ngay, khỏi restart.
            settings.ollama_model = MODEL_NAME
            job.log(f"Đã chuyển sang model '{MODEL_NAME}'")
    return _xong


@router.post("/start")
async def start_training(config: TrainingConfig):
    if runner.is_busy():
        return {"error": "Đang có tiến trình khác chạy.", "job_id": runner.running_job_id}
    from backend.api.voice_training import runner as voice_runner
    if voice_runner.is_busy():
        return {"error": "Đang train giọng trên cùng GPU.",
                "job_id": voice_runner.running_job_id}

    busy_reason = live_service_busy_reason()
    if busy_reason:
        return {"error": busy_reason + " Tiếp tục tạo/rà dữ liệu, train GPU khi dịch vụ rảnh."}

    py_train = venv_train_python()
    if not py_train.exists():
        return {"error": "Chưa có môi trường training. Bấm 'Cài môi trường training' trước."}

    device = str(get_system_info().get("device", "cpu"))
    if not device.startswith("cuda"):
        return {"error": f"Máy này chạy trên '{device}'. Fine-tune cần GPU NVIDIA (CUDA)."}

    for p in (MAKE_DATASET, TRAIN_SCRIPT, DEPLOY_SCRIPT):
        if not p.exists():
            return {"error": f"Thiếu script: {p.relative_to(PROJECT_DIR)}"}

    supported_models = {
        "Qwen/Qwen2.5-3B-Instruct": (False, "Modelfile.tuvan-qwen"),
        "Qwen/Qwen3.5-2B": (True, "auto-qwen35"),
    }
    if config.base_model not in supported_models:
        return {"error": "Base model chưa được kiểm chứng trên máy GPU này."}
    if not config.dataset_id or not config.dataset_id.replace("-", "").replace("_", "").isalnum():
        return {"error": "Hãy chọn một dataset cụ thể để train."}
    nguon = [DATASET_DIR / f"{config.dataset_id}{ext}" for ext in DUOI_FILE
             if (DATASET_DIR / f"{config.dataset_id}{ext}").is_file()]
    if len(nguon) != 1 or nguon[0].name == MERGED.name:
        return {"error": "Dataset không tồn tại hoặc tên bị trùng định dạng."}
    if not _co_the_train(nguon[0]):
        return {"error": "Đây là file kiểm thử/nháp, không được dùng làm nguồn train."}

    tong_mau = sum(_dem_mau(f) for f in nguon)
    if tong_mau < 30:
        return {
            "error": (
                f"Mới có {tong_mau} mẫu, dưới mức thử nghiệm 30. "
                "Train lúc này rất dễ học thuộc và trả lời lệch khi gặp câu mới. "
                "Bổ sung dữ liệu sạch rồi train lại."
            )
        }

    free_gb = shutil.disk_usage(PROJECT_DIR).free / (1024 ** 3)
    if free_gb < 11:
        return {"error": (f"Ổ chứa dự án chỉ còn {free_gb:.1f} GB trống; "
                          "cần ít nhất 11 GB để xuất GGUF an toàn. "
                          "Dọn file export trung gian cũ rồi train lại; giữ adapter LoRA.")}

    if not 1 <= config.epochs <= 50:
        return {"error": "epochs phải trong khoảng 1-50"}
    if not 1 <= config.lora_rank <= 256:
        return {"error": "lora_rank phải trong khoảng 1-256"}
    if not 1 <= config.batch_size <= 32:
        return {"error": "batch_size phải trong khoảng 1-32"}
    if not 1e-6 <= config.learning_rate <= 1e-2:
        return {"error": "learning_rate phải trong khoảng 1e-6 đến 1e-2"}

    if config.auto_deploy:
        return {"error": "Cần kiểm tra hội thoại và nghiệp vụ sau train trước khi chuyển model đang phục vụ."}

    run_name = f"banking-{('qwen35-2b' if '3.5' in config.base_model else 'qwen25-3b')}-style-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    prepared = DATASET_DIR / f"{run_name}-train.jsonl"
    adapter_dir = PROJECT_DIR / "models" / "llm" / f"{run_name}-lora"
    gguf_dir = PROJECT_DIR / "models" / "llm" / f"{run_name}-gguf"
    gguf_name = f"{run_name}.gguf"
    load_16bit, modelfile = supported_models[config.base_model]
    train_cmd = [
        str(py_train), str(TRAIN_SCRIPT),
        "--dataset", str(prepared),
        "--output-dir", str(adapter_dir),
        "--gguf-dir", str(gguf_dir),
        "--base-model", config.base_model,
        "--epochs", str(config.epochs),
        "--lr", str(config.learning_rate),
        "--lora-rank", str(config.lora_rank),
        "--batch-size", str(config.batch_size),
        "--grad-accum", str(config.grad_accum),
    ]
    if load_16bit:
        train_cmd.append("--load-in-16bit")
    steps = [
        Step(command=[sys.executable, str(MAKE_DATASET), "--sources", nguon[0].name,
                      "--output", str(prepared), "--conversation-style"],
             label="Gộp và kiểm tra dataset"),
        Step(command=train_cmd, label=f"Fine-tune {config.base_model}"),
    ]
    # Luôn nạp model mới vào Ollama để có thể A/B với production. Chỉ sửa .env
    # và chuyển model đang phục vụ khi người dùng bật auto_deploy rõ ràng.
    deploy_cmd = [sys.executable, str(DEPLOY_SCRIPT),
                  "--name", run_name, "--modelfile", modelfile,
                  "--gguf-name", gguf_name, "--gguf-dir", str(gguf_dir),
                  "--cleanup-export"]
    steps.append(Step(
        command=deploy_cmd,
        label=("Nạp vào Ollama và chuyển .env" if config.auto_deploy
               else "Nạp model vào Ollama để A/B (chưa chuyển production)"),
    ))

    job = runner.start("train-llm", steps,
                       f"Fine-tune {config.base_model} ({config.epochs} epochs)")

    # Cảnh báo rất dễ bỏ sót trên UI: hiện production có thể là Qwen3.5-9B,
    # trong khi cấu hình mặc định fine-tune Qwen2.5-3B để vừa VRAM 12GB. Loss
    # giảm không có nghĩa model nhỏ hơn sẽ tốt hơn model production lớn hơn.
    job.log(f"Dataset đã chọn: {nguon[0].name} ({tong_mau} mẫu); candidate: {run_name}")
    if tong_mau < MIN_SAMPLES:
        job.log(f"CẢNH BÁO: {tong_mau} mẫu < {MIN_SAMPLES} khuyến nghị; chỉ coi đây là bản thử nghiệm.")
    if settings.ollama_model not in (MODEL_NAME, "qwen2.5:3b") \
            and config.base_model == "Qwen/Qwen2.5-3B-Instruct":
        job.log(
            f"CẢNH BÁO: production đang dùng '{settings.ollama_model}', còn base train là "
            "Qwen2.5-3B. Hãy A/B trước khi chuyển production."
        )

    # Nhả VRAM SAU khi job đã tạo để dòng log đi vào đúng job, nhưng trước khi
    # bước train thật sự chạy - bước đầu (gộp dataset) không đụng GPU nên vẫn kịp.
    giai_phong_vram(job, {settings.ollama_model, MODEL_NAME})
    theo_doi_roi_don(job, _chuyen_model_khi_xong(config.auto_deploy))
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


@router.get("/jobs")
async def list_jobs():
    return {"jobs": [j.to_dict() for j in runner._jobs.values()]}
