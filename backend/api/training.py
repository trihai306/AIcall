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
import sys
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel

from backend.config import settings
from backend.core.device import get_system_info
from backend.core.jobs import JobRunner, Step
from backend.core.vram import giai_phong_vram, theo_doi_roi_don

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
VENV_TRAIN = PROJECT_DIR / ".venv-train"
MERGED = DATASET_DIR / "merged_dataset.jsonl"

# Fine-tune 234 mẫu x 3 epoch mất 30-60 phút; để rộng cho dataset lớn hơn.
JOB_TIMEOUT_S = 8 * 3600

# Dưới mức này thì fine-tune học không đủ pattern (theo training/llm/README.md).
MIN_SAMPLES = 200

runner = JobRunner(PROJECT_DIR, timeout_s=JOB_TIMEOUT_S)

# Tên model sinh ra trong Ollama. Phải khớp dòng FROM của Modelfile tương ứng.
MODEL_NAME = "tuvan-qwen"
MODELFILE = "Modelfile.tuvan-qwen"
GGUF_NAME = "tuvan-qwen-q4.gguf"


def venv_train_python() -> Path:
    return VENV_TRAIN / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


# ============================================================
# Dataset
# ============================================================

SAMPLE_SYSTEM = ("Bạn là nhân viên tư vấn ngân hàng ABC, tên Lan, đang gọi điện cho khách. "
                 "Trả lời tối đa 2 câu, xưng em, gọi khách là anh/chị.")

# Phải khớp ràng buộc của SYSTEM_PROMPT_TEMPLATE trong services/llm_service.py:
# tối đa 2 câu / 25 từ, viết số thành chữ, không liệt kê quá 2 thứ. Model học
# theo data, nên mẫu dài dòng hay dùng chữ số sẽ dạy ngược lại quy tắc đang ép
# ở system prompt.
#
# Câu hỏi ở đây cố ý KHÔNG trùng với dataset chính: make_dataset.py gộp mọi file
# .jsonl trong thư mục, trùng câu hỏi sẽ làm model thiên lệch về mẫu đó.
SAMPLE_PAIRS = [
    ("Tôi muốn vay để sửa nhà",
     "Dạ anh chị vay tín chấp là được ạ, không cần thế chấp. Anh chị cần khoảng bao nhiêu ạ?"),
    ("Lương 12 triệu vay được bao nhiêu?",
     "Dạ mức lương đó anh chị vay được khoảng hai trăm triệu ạ. Anh chị cần vay bao nhiêu ạ?"),
    ("Hồ sơ bị từ chối thì sao?",
     "Dạ anh chị đợi sáu tháng rồi nộp lại được ạ. Em xem giúp anh chị lý do bị từ chối nhé ạ?"),
    ("Tôi đang làm việc ở nước ngoài vay được không?",
     "Dạ em sẽ ghi nhận và có chuyên viên liên hệ lại ạ. Anh chị cho em xin số liên lạc nhé ạ?"),
    ("Vay tín chấp và mở thẻ cái nào lợi hơn?",
     "Dạ vay tín chấp hợp khi cần tiền mặt lớn ạ. Thẻ tín dụng tiện chi tiêu và miễn lãi năm mươi lăm ngày ạ."),
]


# Mọi định dạng make_dataset.py đọc được. .csv là mẫu cho người dùng tự điền
# bằng Excel, .txt là transcript cuộc gọi dạng "KH:/TV:".
DUOI_FILE = (".jsonl", ".json", ".csv", ".txt")


def _dem_mau(path: Path) -> int:
    """Đếm số mẫu. CSV phải trừ dòng tiêu đề, đếm dòng thô là lệch một."""
    try:
        cap = _doc_cap_tu_file(path.read_text(encoding="utf-8-sig"), path.suffix.lower())
        if cap:
            return len(cap)
        return sum(1 for l in path.read_text(encoding="utf-8-sig").splitlines() if l.strip())
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
        datasets.append({
            "id": f.stem,
            "filename": f.name,
            "size_kb": round(stat.st_size / 1024, 1),
            "samples": _dem_mau(f),
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
     "Dạ vay tín chấp bên em lãi suất từ bảy phẩy chín phần trăm một năm ạ. Anh chị định vay khoảng bao nhiêu ạ?",
     "Viết số thành CHỮ, không viết 7.9%"),
    ("Vay 100 triệu trả hàng tháng bao nhiêu?",
     "Dạ vay một trăm triệu ba năm thì mỗi tháng khoảng ba phẩy bốn triệu ạ. Mức đó ổn không ạ?",
     "Trả lời xong hỏi lại để giữ mạch hội thoại"),
    ("Mở thẻ tín dụng cần giấy tờ gì?",
     "Dạ anh chị chuẩn bị căn cước và sao kê lương ba tháng ạ. Anh chị đang làm ở đâu ạ?",
     "Chỉ nói HAI thứ chính rồi hỏi lại, đừng liệt kê dài"),
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
            hoi = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")
            tl = next((m["content"] for m in reversed(msgs) if m.get("role") == "assistant"), "")
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
        "model_sau_train": MODEL_NAME,
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
    # Mặc định khớp model production đang chạy. Fine-tune lệch cỡ model là đổi
    # luôn hồ sơ độ trễ của cả hệ thống gọi điện.
    base_model: str = "Qwen/Qwen2.5-3B-Instruct"
    epochs: int = 3
    learning_rate: float = 2e-4
    lora_rank: int = 16
    batch_size: int = 2
    grad_accum: int = 8
    auto_deploy: bool = True


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

    py_train = venv_train_python()
    if not py_train.exists():
        return {"error": "Chưa có môi trường training. Bấm 'Cài môi trường training' trước."}

    device = str(get_system_info().get("device", "cpu"))
    if not device.startswith("cuda"):
        return {"error": f"Máy này chạy trên '{device}'. Fine-tune cần GPU NVIDIA (CUDA)."}

    for p in (MAKE_DATASET, TRAIN_SCRIPT, DEPLOY_SCRIPT):
        if not p.exists():
            return {"error": f"Thiếu script: {p.relative_to(PROJECT_DIR)}"}

    nguon = [f for f in DATASET_DIR.glob("*.jsonl") if f.name != MERGED.name]
    if not nguon:
        return {"error": "Chưa có dataset nào. Upload hoặc tạo dataset mẫu trước."}

    if not 1 <= config.epochs <= 50:
        return {"error": "epochs phải trong khoảng 1-50"}
    if not 1 <= config.lora_rank <= 256:
        return {"error": "lora_rank phải trong khoảng 1-256"}
    if not 1 <= config.batch_size <= 32:
        return {"error": "batch_size phải trong khoảng 1-32"}
    if not 1e-6 <= config.learning_rate <= 1e-2:
        return {"error": "learning_rate phải trong khoảng 1e-6 đến 1e-2"}

    steps = [
        Step(command=[sys.executable, str(MAKE_DATASET)],
             label="Gộp và kiểm tra dataset"),
        Step(command=[
            str(py_train), str(TRAIN_SCRIPT),
            "--base-model", config.base_model,
            "--epochs", str(config.epochs),
            "--lr", str(config.learning_rate),
            "--lora-rank", str(config.lora_rank),
            "--batch-size", str(config.batch_size),
            "--grad-accum", str(config.grad_accum),
        ], label=f"Fine-tune {config.base_model}"),
    ]
    if config.auto_deploy:
        steps.append(Step(
            command=[sys.executable, str(DEPLOY_SCRIPT),
                     "--name", MODEL_NAME, "--modelfile", MODELFILE,
                     "--gguf-name", GGUF_NAME, "--set-env"],
            label="Nạp vào Ollama và chuyển .env",
        ))

    job = runner.start("train-llm", steps,
                       f"Fine-tune {config.base_model} ({config.epochs} epochs)")

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
