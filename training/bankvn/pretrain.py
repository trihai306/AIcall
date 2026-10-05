#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import torch
from torch.utils.data import IterableDataset
from transformers import (
    TokenizersBackend,
    LlamaConfig,
    LlamaForCausalLM,
    Trainer,
    TrainingArguments,
)
from transformers.trainer_utils import get_last_checkpoint

try:
    from .common import require_bankvn_tokenizer_files, save_bankvn_tokenizer
except ImportError:
    from common import require_bankvn_tokenizer_files, save_bankvn_tokenizer


class PackedCorpus(IterableDataset):
    def __init__(self, files: list[Path], tokenizer, block_size: int, seed: int = 42,
                 repeat: bool = True):
        self.files = files
        self.tokenizer = tokenizer
        self.block_size = block_size
        self.seed = seed
        self.repeat = repeat

    def _encode(self, text: str) -> list[int]:
        # PackedCorpus tự chia thành block_size trước khi đưa vào model. Dùng
        # backend tokenizer trực tiếp để không phát cảnh báo model_max_length
        # khi một document nguồn dài hơn context dù từng block train vẫn ngắn.
        backend = getattr(self.tokenizer, "backend_tokenizer", None)
        if backend is not None:
            return list(backend.encode(text, add_special_tokens=False).ids)
        return list(self.tokenizer.encode(text, add_special_tokens=False))

    def __iter__(self):
        rng = random.Random(self.seed)
        buf: list[int] = []
        while True:
            files = list(self.files)
            rng.shuffle(files)
            for path in files:
                with path.open(encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        text = obj.get("text") or ""
                        if not text:
                            continue
                        buf.extend(self._encode(text))
                        buf.append(self.tokenizer.eos_token_id)
                        while len(buf) >= self.block_size:
                            ids = buf[:self.block_size]
                            del buf[:self.block_size]
                            t = torch.tensor(ids, dtype=torch.long)
                            yield {"input_ids": t, "attention_mask": torch.ones_like(t),
                                   "labels": t.clone()}
            if not self.repeat:
                break


def load_profile(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    required = {"name", "hidden_size", "intermediate_size", "num_hidden_layers",
                "num_attention_heads", "block_size"}
    missing = required - cfg.keys()
    if missing:
        raise SystemExit(f"[ERROR] Profile thiếu: {sorted(missing)}")
    return cfg


def main() -> None:
    ap = argparse.ArgumentParser(description="Pretrain BankVN từ trọng số random")
    ap.add_argument("--profile", default="training/bankvn/configs/bankvn-350m.json")
    ap.add_argument("--tokenizer", default="models/bankvn/tokenizer")
    ap.add_argument("--corpus", nargs="+", default=["data/bankvn/clean/corpus.jsonl"])
    ap.add_argument("--output", default="")
    ap.add_argument("--max-steps", type=int, default=1000)
    ap.add_argument("--additional-steps", type=int, default=0,
                    help="Khi resume, train thêm N step so với checkpoint cuối")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--init-from", default="",
                    help="Nạp trọng số từ checkpoint/final nhưng tạo optimizer và scheduler mới")
    ap.add_argument("--allow-large", action="store_true",
                    help="Cho phép profile đánh dấu cần offload/multi-GPU")
    args = ap.parse_args()

    profile = load_profile(Path(args.profile))
    block_size = int(profile["block_size"])
    max_positions = int(profile.get("max_position_embeddings", 4096))
    if block_size > max_positions:
        raise SystemExit(
            f"[ERROR] block_size={block_size} vượt max_position_embeddings={max_positions}"
        )
    if args.resume and args.init_from:
        raise SystemExit("[ERROR] Không dùng đồng thời --resume và --init-from")
    if profile.get("requires_offload_or_multi_gpu") and not args.allow_large:
        raise SystemExit("[ERROR] Profile này không dành cho 12GB single-GPU. "
                         "Dùng --allow-large chỉ sau khi đã cấu hình offload/multi-GPU.")

    corpus = [Path(p) for p in args.corpus]
    missing = [str(p) for p in corpus if not p.exists()]
    if missing:
        raise SystemExit(f"[ERROR] Không thấy corpus: {missing}")

    # SentencePiece model là nguồn tokenizer chuẩn của BankVN và cũng là định
    # dạng llama.cpp/GGUF đọc trực tiếp.
    require_bankvn_tokenizer_files(args.tokenizer)
    tokenizer = TokenizersBackend.from_pretrained(args.tokenizer)
    out = Path(args.output or f"models/bankvn/pretrain/{profile['name']}")
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = get_last_checkpoint(str(out)) if args.resume else None
    init_from = Path(args.init_from) if args.init_from else None
    if init_from is not None and not init_from.exists():
        raise SystemExit(f"[ERROR] Không thấy checkpoint --init-from: {init_from}")
    completed_steps = 0
    if checkpoint:
        try:
            completed_steps = int(Path(checkpoint).name.rsplit("-", 1)[1])
        except (ValueError, IndexError):
            completed_steps = 0
    max_steps = args.max_steps
    if args.additional_steps:
        max_steps = completed_steps + args.additional_steps

    if checkpoint:
        model = LlamaForCausalLM.from_pretrained(checkpoint)
        print(f"Resume: {checkpoint}")
    elif init_from is not None:
        model = LlamaForCausalLM.from_pretrained(init_from)
        expected = {
            "hidden_size": int(profile["hidden_size"]),
            "intermediate_size": int(profile["intermediate_size"]),
            "num_hidden_layers": int(profile["num_hidden_layers"]),
            "num_attention_heads": int(profile["num_attention_heads"]),
        }
        mismatches = {
            key: {"expected": value, "actual": int(getattr(model.config, key))}
            for key, value in expected.items()
            if int(getattr(model.config, key)) != value
        }
        if mismatches:
            raise SystemExit(f"[ERROR] --init-from không khớp profile: {mismatches}")
        print(f"Init weights: {init_from}")
    else:
        config = LlamaConfig(
            vocab_size=len(tokenizer),
            hidden_size=profile["hidden_size"],
            intermediate_size=profile["intermediate_size"],
            num_hidden_layers=profile["num_hidden_layers"],
            num_attention_heads=profile["num_attention_heads"],
            num_key_value_heads=profile.get("num_key_value_heads",
                                            profile["num_attention_heads"]),
            max_position_embeddings=max_positions,
            rope_theta=profile.get("rope_theta", 10000.0),
            rms_norm_eps=1e-5,
            hidden_act="silu",
            attention_bias=False,
            tie_word_embeddings=True,
            bos_token_id=tokenizer.bos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id,
        )
        model = LlamaForCausalLM(config)

    model.config.use_cache = False
    gradient_checkpointing = bool(profile.get("gradient_checkpointing", True))
    if gradient_checkpointing:
        model.gradient_checkpointing_enable()
    else:
        model.gradient_checkpointing_disable()
    params = sum(p.numel() for p in model.parameters())
    print(json.dumps({"model": profile["name"], "parameters": params,
                      "parameters_m": round(params / 1e6, 1)}, ensure_ascii=False))

    dataset = PackedCorpus(corpus, tokenizer, block_size, repeat=True)
    ignore_data_skip = bool(
        checkpoint and profile.get("ignore_data_skip_on_resume", False)
    )
    train_args = TrainingArguments(
        output_dir=str(out),
        max_steps=max_steps,
        per_device_train_batch_size=profile.get("batch_size", 1),
        gradient_accumulation_steps=profile.get("gradient_accumulation_steps", 16),
        learning_rate=profile.get("learning_rate", 3e-4),
        warmup_steps=profile.get("warmup_steps", 200),
        weight_decay=profile.get("weight_decay", 0.1),
        lr_scheduler_type="cosine",
        bf16=True,
        fp16=False,
        gradient_checkpointing=gradient_checkpointing,
        logging_steps=profile.get("logging_steps", 10),
        save_steps=profile.get("save_steps", 500),
        save_total_limit=2,
        optim=profile.get("optim", "adamw_torch_fused"),
        dataloader_num_workers=0,
        remove_unused_columns=False,
        ignore_data_skip=ignore_data_skip,
        report_to="none",
        seed=42,
    )
    trainer = Trainer(model=model, args=train_args, train_dataset=dataset)
    mixed_precision = getattr(getattr(trainer, "accelerator", None), "mixed_precision", None)
    print(json.dumps({
        "device": str(trainer.args.device),
        "parameter_storage_dtype": str(next(model.parameters()).dtype),
        "mixed_precision": mixed_precision,
        "bf16_requested": bool(trainer.args.bf16),
        "gradient_checkpointing": gradient_checkpointing,
        "batch_size": trainer.args.per_device_train_batch_size,
        "gradient_accumulation_steps": trainer.args.gradient_accumulation_steps,
        "ignore_data_skip": bool(trainer.args.ignore_data_skip),
        "cuda_bf16_supported": bool(torch.cuda.is_available() and torch.cuda.is_bf16_supported()),
    }, ensure_ascii=False))
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    train_output = trainer.train(resume_from_checkpoint=checkpoint if checkpoint else None)
    runtime = float(train_output.metrics.get("train_runtime") or 0.0)
    trained_steps = max(0, int(trainer.state.global_step) - completed_steps)
    effective_steps_per_second = trained_steps / runtime if runtime > 0 else 0.0
    world_size = max(1, int(getattr(trainer.args, "world_size", 1) or 1))
    tokens_this_run = (
        trained_steps
        * block_size
        * int(trainer.args.per_device_train_batch_size)
        * int(trainer.args.gradient_accumulation_steps)
        * world_size
    )
    tokens_per_second = tokens_this_run / runtime if runtime > 0 else 0.0
    print(json.dumps({
        "train_runtime": round(runtime, 3),
        "trained_steps_this_run": trained_steps,
        "global_step": int(trainer.state.global_step),
        "train_steps_per_second": round(effective_steps_per_second, 3),
        "train_tokens_per_second": round(tokens_per_second, 1),
        "trained_tokens_this_run": tokens_this_run,
        "trainer_reported_steps_per_second": train_output.metrics.get("train_steps_per_second"),
    }, ensure_ascii=False))
    # Luôn để lại checkpoint có đủ optimizer/scheduler/RNG ở đúng global step
    # cuối. Smoke 100 bước dùng profile save_steps=500 nên nếu chỉ dựa vào
    # Trainer mặc định sẽ không có checkpoint-100 và lần --resume kế tiếp sẽ
    # vô tình train lại từ đầu.
    current_checkpoint = out / f"checkpoint-{trainer.state.global_step}"
    if not current_checkpoint.exists():
        trainer._save_checkpoint(model, trial=None)
        print(f"[OK] Resumable checkpoint: {current_checkpoint}")
    if torch.cuda.is_available():
        free, total = torch.cuda.mem_get_info()
        print(json.dumps({
            "cuda_peak_allocated_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 2),
            "cuda_peak_reserved_gb": round(torch.cuda.max_memory_reserved() / 1024**3, 2),
            "cuda_free_gb_after_train": round(free / 1024**3, 2),
            "cuda_total_gb": round(total / 1024**3, 2),
        }, ensure_ascii=False))

    final = out / "final"
    trainer.save_model(str(final))
    save_bankvn_tokenizer(tokenizer, final, args.tokenizer)
    print(f"[OK] BankVN checkpoint: {final}")


if __name__ == "__main__":
    main()
