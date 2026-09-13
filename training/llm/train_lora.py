"""
QLoRA fine-tune model Qwen theo dataset tư vấn riêng (Unsloth).

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
import random
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

# Base mặc định là bản nhỏ, ổn để fine-tune phong cách trên GPU 12GB. Production
# có thể đang chạy model khác; vì vậy sau train PHẢI A/B bằng danh_gia.py và
# danh_gia_hoi_thoai.py trước khi đổi OLLAMA_MODEL. Đừng coi LoRA nhỏ là nâng
# cấp tự động chỉ vì loss giảm.
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
    parser.add_argument("--eval-ratio", type=float, default=0.1,
                        help="Tỷ lệ holdout để đo eval_loss (mặc định 0.1; 0 = tắt)")
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
        # Unsloth tối ưu fast-path cho dropout=0 và khuyến nghị chỉ tăng
        # regularization khi có bằng chứng overfit. weight_decay + holdout bên
        # dưới đã cho tín hiệu rõ hơn so với thêm dropout mặc định.
        lora_dropout=0.0,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # TRL hỗ trợ trực tiếp conversational prompt-completion. Dùng đúng cấu trúc
    # này thay vì render toàn bộ hội thoại thành một chuỗi `text`: khi đặt
    # completion_only_loss=True, loss chỉ tính trên câu assistant CUỐI CÙNG.
    #
    # Đây là khác biệt rất quan trọng với transcript nhiều lượt. make_dataset.py
    # tạo một mẫu cho mỗi lượt TV và giữ lịch sử trước đó làm ngữ cảnh. Nếu train
    # full sequence thì câu chào/lượt đầu bị học lặp lại ở mọi prefix, còn system
    # và lời khách cũng tiêu tốn gradient. Prompt-completion vẫn cho model nhìn
    # toàn bộ lịch sử nhưng chỉ dạy đúng câu cần trả lời ở lượt hiện tại.
    rows = []
    groups: dict[str, list[dict]] = {}
    with open(dataset_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            messages = obj.get("messages") or []
            if not messages or messages[-1].get("role") != "assistant":
                raise SystemExit(
                    "[ERROR] Mỗi mẫu phải kết thúc bằng role=assistant để tách "
                    "prompt/completion chính xác. Chạy lại make_dataset.py để kiểm tra."
                )
            row = {
                "prompt": messages[:-1],
                "completion": [messages[-1]],
            }
            rows.append(row)

            # Các prefix của CÙNG một transcript chia sẻ system + lượt user và
            # assistant đầu tiên. Gom chúng thành một group để holdout không bị
            # rò rỉ: nếu lượt 1 của cuộc gọi nằm ở train còn lượt 2-8 nằm ở eval
            # thì eval_loss đẹp giả vì model đã thấy gần như cùng ngữ cảnh.
            dau = messages[:3] if len(messages) >= 3 else messages
            group_key = json.dumps(dau, ensure_ascii=False, sort_keys=True)
            groups.setdefault(group_key, []).append(row)
            if args.max_samples and len(rows) >= args.max_samples:
                break

    print(f"Dataset: {len(rows)} mẫu từ {dataset_path.name}")

    # Không đánh giá trên chính dữ liệu train: loss train thấp chỉ chứng minh mô
    # hình nhớ được data, không chứng minh nó trả lời tốt câu chưa thấy. Giữ lại
    # khoảng 10% làm holdout THEO CUỘC HỘI THOẠI, không chia ngẫu nhiên từng
    # prefix. Với smoke test quá nhỏ thì bỏ eval để tránh tập train chỉ còn vài
    # mẫu.
    eval_dataset = None
    if args.eval_ratio and len(rows) >= 20 and len(groups) >= 2:
        ratio = min(max(args.eval_ratio, 0.01), 0.5)
        muc_tieu = max(1, round(len(rows) * ratio))
        cac_nhom = list(groups.values())
        random.Random(42).shuffle(cac_nhom)
        eval_rows: list[dict] = []
        train_rows: list[dict] = []
        for nhom in cac_nhom:
            if len(eval_rows) < muc_tieu and len(cac_nhom) > 1:
                eval_rows.extend(nhom)
            else:
                train_rows.extend(nhom)
        # Trường hợp group đầu quá lớn vẫn phải chừa ít nhất một group để train.
        if not train_rows:
            train_rows = eval_rows[-len(cac_nhom[-1]):]
            del eval_rows[-len(cac_nhom[-1]):]
        dataset = Dataset.from_list(train_rows)
        eval_dataset = Dataset.from_list(eval_rows)
        print(f"Split: train={len(dataset)}, eval={len(eval_dataset)} ({ratio:.0%} holdout)")
    else:
        dataset = Dataset.from_list(rows)
        print("Split: không tạo holdout (dataset <20 mẫu, chỉ 1 hội thoại, hoặc --eval-ratio=0)")

    # trl hiện tại hỗ trợ conversational prompt-completion và
    # `completion_only_loss=True`: chỉ tối ưu phần completion thay vì system /
    # user / lịch sử. Cách này không phụ thuộc template phải có `{% generation %}`
    # như assistant_only_loss, nên an toàn hơn với các Qwen đời khác nhau.
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        eval_dataset=eval_dataset,
        args=SFTConfig(
            output_dir=str(OUTPUT_DIR / "checkpoints"),
            max_length=MAX_SEQ_LEN,
            completion_only_loss=True,
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            warmup_ratio=0.05,
            weight_decay=0.01,
            logging_steps=5,
            save_strategy="epoch",
            save_total_limit=2,
            eval_strategy="epoch" if eval_dataset is not None else "no",
            load_best_model_at_end=eval_dataset is not None,
            metric_for_best_model="eval_loss" if eval_dataset is not None else None,
            greater_is_better=False if eval_dataset is not None else None,
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
