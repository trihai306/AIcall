"""
QLoRA fine-tune Vistral-7B-Chat trên dataset tư vấn riêng (Unsloth).

Chạy trên máy GPU NVIDIA (RTX 5070 12GB: vừa với cấu hình mặc định).
KHÔNG chạy được trên macOS (Unsloth cần CUDA).

Trước khi train: TẮT Ollama và backend (nhường VRAM):
    pkill ollama; pkill -f uvicorn

Usage:
    python training/llm/train_lora.py
    python training/llm/train_lora.py --epochs 4 --lora-rank 32
"""
import argparse
import json
import sys
import time
from pathlib import Path

# Console Windows là cp1252: in tiếng Việt giữa lúc train là chết cả job.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_PATH = PROJECT_DIR / "data" / "training" / "merged_dataset.jsonl"
OUTPUT_DIR = PROJECT_DIR / "models" / "llm" / "tuvan-lora"
GGUF_DIR = PROJECT_DIR / "models" / "llm"

# Mặc định khớp model production đang chạy (.env: OLLAMA_MODEL=qwen2.5:3b).
# Fine-tune lệch cỡ model là đổi luôn hồ sơ độ trễ của cả hệ thống - 7B sinh
# token đầu chậm hơn 3B rõ rệt, mà đây là hệ thống gọi điện thời gian thực.
#
# Vistral-7B-Chat (base cũ) là repo gated: phải đăng nhập HuggingFace và xin
# quyền mới tải được, không có token là hỏng ngay ở bước nạp model.
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
MAX_SEQ_LEN = 2048

# Tiền tố để backend nhặt tiến độ ra khỏi log. Đọc thanh tqdm thay cho cái này
# thì rất dễ vỡ: tqdm in ra stderr, kèm mã ANSI, và bị JobRunner gộp dòng.
PROGRESS_PREFIX = "[PROGRESS] "


def make_progress_callback():
    """Callback in tiến độ dạng JSON mỗi lần Trainer log.

    Trả về class chứ không phải instance vì transformers chỉ được import sau khi
    unsloth đã import xong (unsloth vá transformers lúc nạp).
    """
    from transformers import TrainerCallback

    class TienDoCallback(TrainerCallback):
        def __init__(self):
            self.bat_dau = None

        def on_train_begin(self, args, state, control, **kw):
            self.bat_dau = time.time()

        def on_log(self, args, state, control, logs=None, **kw):
            if not logs or not state.max_steps:
                return
            troi_qua = time.time() - (self.bat_dau or time.time())
            buoc = state.global_step or 0
            con_lai = max(state.max_steps - buoc, 0)
            # ETA suy từ tốc độ trung bình thực tế, không phải ước lượng cố định.
            eta = (troi_qua / buoc * con_lai) if buoc else None

            data = {
                "step": buoc,
                "total": state.max_steps,
                "percent": round(buoc / state.max_steps * 100, 1),
                "epoch": round(state.epoch, 2) if state.epoch is not None else None,
                "elapsed_s": round(troi_qua),
                "eta_s": round(eta) if eta is not None else None,
            }
            if "loss" in logs:
                data["loss"] = round(logs["loss"], 4)
            if "learning_rate" in logs:
                data["lr"] = logs["learning_rate"]
            # Xuống dòng TRƯỚC: tqdm vẽ thanh tiến trình ra stderr bằng \r và
            # không kết thúc dòng, nên in thẳng là dòng này dính vào đuôi thanh
            # đó. Bên đọc đã dùng find() nên vẫn bắt được, nhưng tách dòng ra
            # cho log dễ đọc và bớt phụ thuộc lẫn nhau.
            print("\n" + PROGRESS_PREFIX + json.dumps(data), flush=True)

    return TienDoCallback()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--skip-gguf", action="store_true", help="Chỉ train LoRA, không xuất GGUF")
    parser.add_argument("--dataset", default=str(DATASET_PATH),
                        help="File .jsonl để train (mặc định merged_dataset.jsonl)")
    parser.add_argument("--max-samples", type=int, default=0,
                        help="Chỉ lấy N mẫu đầu - dùng để chạy thử nhanh, 0 = lấy hết")
    parser.add_argument("--base-model", default=BASE_MODEL,
                        help=f"Repo HuggingFace của model gốc (mặc định {BASE_MODEL})")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        raise SystemExit(f"[ERROR] Chưa có {dataset_path}. Chạy: python training/llm/make_dataset.py")

    from unsloth import FastLanguageModel
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer

    print(f"Loading base model: {args.base_model} (4-bit)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=MAX_SEQ_LEN,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_rank,
        lora_alpha=args.lora_rank * 2,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # Dataset: apply chat template của chính Vistral
    rows = []
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            text = tokenizer.apply_chat_template(
                obj["messages"], tokenize=False, add_generation_prompt=False
            )
            rows.append({"text": text})
            if args.max_samples and len(rows) >= args.max_samples:
                break

    print(f"Dataset: {len(rows)} mẫu từ {dataset_path.name}")
    dataset = Dataset.from_list(rows)

    # trl >= 0.20 đổi API: tokenizer -> processing_class, còn dataset_text_field
    # và max_seq_length chuyển từ tham số của SFTTrainer sang SFTConfig. Giữ
    # cách gọi cũ là ném TypeError ngay khi khởi tạo trainer.
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            output_dir=str(OUTPUT_DIR / "checkpoints"),
            dataset_text_field="text",
            max_length=MAX_SEQ_LEN,
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            warmup_ratio=0.05,
            logging_steps=5,
            save_strategy="epoch",
            bf16=True,
            optim="adamw_8bit",
            seed=42,
            report_to="none",
        ),
    )

    trainer.add_callback(make_progress_callback())

    print("Training...")
    trainer.train()

    print(f"Saving LoRA adapter -> {OUTPUT_DIR}")
    model.save_pretrained(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    if not args.skip_gguf:
        print("Exporting merged GGUF q4_k_m (mất vài phút)...")
        model.save_pretrained_gguf(
            str(GGUF_DIR / "tuvan-gguf"),
            tokenizer,
            quantization_method="q4_k_m",
        )
        # Unsloth thêm hậu tố "_gguf" vào thư mục đích, nên file thật nằm ở
        # tuvan-gguf_gguf/ chứ không phải tuvan-gguf/. Nói đúng chỗ để người
        # đọc log khỏi đi tìm nhầm.
        thuc_te = GGUF_DIR / "tuvan-gguf_gguf"
        print(f"""
============================================
 Train xong.

 File GGUF nằm ở: {thuc_te}
 (thư mục {GGUF_DIR / 'tuvan-gguf'} chỉ chứa bản 16-bit trung gian,
  xoá được để lấy lại ~5.8GB)

 Nạp vào Ollama và chuyển .env sang model mới:
   python training/llm/deploy_ollama.py --set-env

 Rồi khởi động lại dịch vụ.
============================================
""")
    else:
        print(f"[OK] LoRA adapter tại {OUTPUT_DIR} (chưa xuất GGUF, dùng --skip-gguf)")


if __name__ == "__main__":
    main()
