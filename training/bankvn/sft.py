#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, deque
import json
import math
import sys
from pathlib import Path

import torch
from datasets import Dataset
from transformers import AutoModelForCausalLM, TokenizersBackend, Trainer, TrainingArguments

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.pipeline.cong_cu_llm import (  # noqa: E402
    DINH_NGHIA,
    PROMPT_QUYET_DINH,
    prompt_tool_bankvn,
)
try:
    from .common import (  # type: ignore
        ROLE_TOKEN,
        is_strict_vietnamese,
        redact_pii,
        render_messages,
        require_bankvn_tokenizer_files,
        save_bankvn_tokenizer,
    )
except ImportError:
    from common import (  # noqa: E402
        ROLE_TOKEN,
        is_strict_vietnamese,
        redact_pii,
        render_messages,
        require_bankvn_tokenizer_files,
        save_bankvn_tokenizer,
    )


TOOL_NAMES = {item["function"]["name"] for item in DINH_NGHIA}
ROUTER_FORMAT_TOKENS = [
    '{"name":"tra_ho_so_khach","arguments":{}}',
    '{"name":"',
    '","arguments":',
    'tra_ho_so_khach',
    'tra_thong_tin_san_pham',
    '{"san_pham":"',
    '","can_biet":"',
]


def balance_router_rows(router_rows_by_tool: dict[str, list[dict]]) -> tuple[list[dict], int]:
    """Oversample các tool router thiểu số bằng chính mẫu đã validate."""
    populated = {name: group for name, group in router_rows_by_tool.items() if group}
    if len(populated) < 2:
        return [], 0
    target = max(len(group) for group in populated.values())
    additions: list[dict] = []
    for name in sorted(populated):
        group = populated[name]
        missing = target - len(group)
        for idx in range(missing):
            additions.append(dict(group[idx % len(group)]))
    return additions, len(additions)


def balance_assistant_rows(
    assistant_rows: list[dict], router_rows: int, assistant_router_ratio: float
) -> tuple[list[dict], int]:
    """Bù assistant/no-tool để model không mặc định gọi tool cho mọi câu."""
    if not assistant_rows or assistant_router_ratio <= 0 or router_rows <= 0:
        return [], 0
    target = int(math.ceil(router_rows * assistant_router_ratio))
    missing = max(0, target - len(assistant_rows))
    additions = [dict(assistant_rows[idx % len(assistant_rows)]) for idx in range(missing)]
    return additions, len(additions)


def add_router_format_tokens(tokenizer, model) -> int:
    """Append vài token format, giữ nguyên ID của vocab cũ và khởi tạo từ decomposition cũ."""
    old_vocab_size = len(tokenizer)
    old_weight = model.get_input_embeddings().weight.detach().clone()
    decompositions = {
        token: [idx for idx in tokenizer.encode(token, add_special_tokens=False)
                if 0 <= idx < old_vocab_size]
        for token in ROUTER_FORMAT_TOKENS
    }
    added = tokenizer.add_tokens(ROUTER_FORMAT_TOKENS)
    if not added:
        return 0
    model.resize_token_embeddings(len(tokenizer), mean_resizing=True)
    new_weight = model.get_input_embeddings().weight
    with torch.no_grad():
        for token, old_ids in decompositions.items():
            token_id = tokenizer.convert_tokens_to_ids(token)
            if token_id < old_vocab_size or token_id >= len(tokenizer) or not old_ids:
                continue
            new_weight[token_id].copy_(old_weight[old_ids].mean(dim=0))
    model.tie_weights()
    for token in ROUTER_FORMAT_TOKENS:
        encoded = tokenizer.encode(token, add_special_tokens=False)
        if len(encoded) != 1:
            raise RuntimeError(f"Router format token không encode thành 1 token: {token!r} -> {encoded}")
    return added


def prepare_messages(obj: dict) -> list[dict]:
    """Đưa mẫu router về đúng prompt mà VoiceBank dùng lúc inference."""
    messages = [dict(msg) for msg in (obj.get("messages") or []) if isinstance(msg, dict)]
    has_tool_call = any(
        msg.get("role") == "assistant" and bool(msg.get("tool_calls"))
        for msg in messages
    )
    mode = str(obj.get("mode") or ("router" if has_tool_call else "assistant"))
    if mode != "router":
        return messages

    system_idx = next((i for i, msg in enumerate(messages) if msg.get("role") == "system"), None)
    rendered_system = prompt_tool_bankvn(PROMPT_QUYET_DINH, DINH_NGHIA)
    if system_idx is None:
        messages.insert(0, {"role": "system", "content": rendered_system})
    else:
        messages[system_idx] = {**messages[system_idx], "content": rendered_system}
    return messages


def validate_record(obj: dict, line_no: int) -> None:
    errors: list[str] = []
    mode = str(obj.get("mode") or "").strip()
    if mode and mode not in {"assistant", "router"}:
        errors.append(f"mode không hỗ trợ: {mode!r}")
    if not str(obj.get("source_id") or "").strip():
        errors.append("thiếu source_id")
    messages = obj.get("messages")
    if not isinstance(messages, list) or not messages:
        errors.append("messages không phải danh sách hợp lệ")
        messages = []

    roles = [str(msg.get("role") or "") for msg in messages if isinstance(msg, dict)]
    if "user" not in roles:
        errors.append("thiếu lượt user")
    if "assistant" not in roles:
        errors.append("thiếu lượt assistant")

    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            errors.append(f"messages[{idx}] không phải object")
            continue
        role = str(msg.get("role") or "")
        if role not in ROLE_TOKEN:
            errors.append(f"messages[{idx}] role không hỗ trợ: {role!r}")
        content = str(msg.get("content") or "")
        if content and redact_pii(content) != content:
            errors.append(f"messages[{idx}] còn PII thô")
        if role in {"user", "assistant"} and content and not is_strict_vietnamese(
                content, min_score=0.24, min_chars=8):
            errors.append(f"messages[{idx}] không đạt gate tiếng Việt")

        calls = msg.get("tool_calls")
        if not calls:
            continue
        if role != "assistant":
            errors.append(f"messages[{idx}] tool_calls chỉ được nằm ở assistant")
            continue
        if not isinstance(calls, list) or len(calls) != 1:
            errors.append(f"messages[{idx}] phải có đúng một tool_call")
            continue
        call = calls[0]
        function = call.get("function", call) if isinstance(call, dict) else {}
        name = str(function.get("name") or "") if isinstance(function, dict) else ""
        arguments = function.get("arguments") if isinstance(function, dict) else None
        if name not in TOOL_NAMES:
            errors.append(f"messages[{idx}] function không tồn tại: {name!r}")
        if not isinstance(arguments, dict):
            errors.append(f"messages[{idx}] arguments phải là object")
        elif redact_pii(json.dumps(arguments, ensure_ascii=False)) != json.dumps(
                arguments, ensure_ascii=False):
            errors.append(f"messages[{idx}] arguments còn PII thô")

    if mode == "assistant" and any(
            isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("tool_calls")
            for msg in messages):
        errors.append("mode assistant không được chứa tool_calls")

    if errors:
        raise SystemExit(f"[ERROR] SFT dòng {line_no}: " + "; ".join(errors))


class PadCollator:
    def __init__(self, pad_id: int):
        self.pad_id = pad_id

    def __call__(self, rows: list[dict]) -> dict:
        max_len = max(len(r["input_ids"]) for r in rows)
        out = {"input_ids": [], "attention_mask": [], "labels": []}
        for row in rows:
            n = max_len - len(row["input_ids"])
            out["input_ids"].append(row["input_ids"] + [self.pad_id] * n)
            out["attention_mask"].append(row["attention_mask"] + [0] * n)
            out["labels"].append(row["labels"] + [-100] * n)
        return {k: torch.tensor(v, dtype=torch.long) for k, v in out.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description="SFT BankVN trên hội thoại + function calling")
    ap.add_argument("--base", required=True, help="Checkpoint BankVN pretrain")
    ap.add_argument("--dataset", default="data/bankvn/sft/teacher.jsonl")
    ap.add_argument(
        "--replay-dataset", action="append", default=[],
        help="Dataset neo kỹ năng cũ; có thể truyền nhiều lần.",
    )
    ap.add_argument(
        "--replay-repeat", type=int, default=1,
        help="Số lần lặp mỗi mẫu replay trong train để chống quên router.",
    )
    ap.add_argument("--max-source-records", type=int, default=0,
                    help="0 = toàn bộ; >0 = chỉ dùng N record mới nhất của dataset chính")
    ap.add_argument("--max-replay-records", type=int, default=0,
                    help="0 = toàn bộ; >0 = chỉ dùng N record mới nhất mỗi replay dataset")
    ap.add_argument(
        "--balance-router-tools", action=argparse.BooleanOptionalAction, default=True,
        help="Cân bằng số mẫu giữa các tool router bằng oversampling mẫu đã validate.",
    )
    ap.add_argument("--assistant-router-ratio", type=float, default=0.0,
                    help="Tỷ lệ assistant/no-tool tối thiểu so với số router row sau cân tool")
    ap.add_argument("--router-format-tokens", action="store_true",
                    help="Append token JSON/tool chuyên dụng nhưng giữ nguyên ID vocab cũ")
    ap.add_argument("--output", default="models/bankvn/sft/bankvn")
    ap.add_argument("--max-length", type=int, default=2048)
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument(
        "--min-updates", type=int, default=0,
        help="Số optimizer update tối thiểu; 0 = không ép. Hữu ích khi dataset teacher còn nhỏ.",
    )
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--no-gradient-checkpointing", action="store_true",
                    help="Tắt checkpointing để tăng tốc khi VRAM đủ")
    ap.add_argument("--validate-only", action="store_true",
                    help="Chỉ kiểm tra dataset/gate tiếng Việt và thống kê độ dài, không train")
    ap.add_argument("--lora-rank", type=int, default=0,
                    help="0 = full SFT; >0 = LoRA cho model lớn")
    args = ap.parse_args()

    require_bankvn_tokenizer_files(args.base)
    tokenizer = TokenizersBackend.from_pretrained(args.base)
    model = AutoModelForCausalLM.from_pretrained(args.base)
    router_format_tokens_added = (
        add_router_format_tokens(tokenizer, model) if args.router_format_tokens else 0
    )
    model.config.use_cache = False
    gradient_checkpointing = not args.no_gradient_checkpointing
    if gradient_checkpointing:
        model.gradient_checkpointing_enable()
    else:
        model.gradient_checkpointing_disable()

    if args.lora_rank > 0:
        from peft import LoraConfig, get_peft_model
        model = get_peft_model(model, LoraConfig(
            r=args.lora_rank,
            lora_alpha=args.lora_rank * 2,
            lora_dropout=0.0,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
        ))

    rows = []
    source_records = 0
    replay_records = 0
    mode_counts: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    router_rows_by_tool: dict[str, list[dict]] = {}
    assistant_rows: list[dict] = []

    def add_dataset(path: Path, repeat: int, replay: bool) -> None:
        nonlocal source_records, replay_records
        if not path.exists():
            raise SystemExit(f"[ERROR] Không thấy dataset SFT: {path}")
        with path.open(encoding="utf-8") as f:
            record_limit = args.max_replay_records if replay else args.max_source_records
            source_lines = deque(f, maxlen=record_limit) if record_limit > 0 else f
            for line_no, line in enumerate(source_lines, start=1):
                if not line.strip():
                    continue
                obj = json.loads(line)
                validate_record(obj, line_no)
                mode = str(obj.get("mode") or "assistant")
                mode_counts[mode] += 1
                record_tool_name: str | None = None
                for msg in obj.get("messages") or []:
                    for call in msg.get("tool_calls") or []:
                        function = call.get("function", call) if isinstance(call, dict) else {}
                        if isinstance(function, dict) and function.get("name"):
                            record_tool_name = str(function["name"])
                            tool_counts[record_tool_name] += 1
                rendered = render_messages(tokenizer, prepare_messages(obj), args.max_length)
                if not any(x != -100 for x in rendered["labels"]):
                    continue
                if replay:
                    replay_records += 1
                else:
                    source_records += 1
                rendered_copies = [dict(rendered) for _ in range(max(1, repeat))]
                rows.extend(rendered_copies)
                if mode == "assistant":
                    assistant_rows.extend(rendered_copies)
                if mode == "router" and record_tool_name:
                    router_rows_by_tool.setdefault(record_tool_name, []).extend(rendered_copies)

    add_dataset(Path(args.dataset), 1, replay=False)
    replay_repeat = max(1, int(args.replay_repeat))
    for replay_path in args.replay_dataset:
        add_dataset(Path(replay_path), replay_repeat, replay=True)
    router_balance_added = 0
    if args.balance_router_tools:
        balanced_rows, router_balance_added = balance_router_rows(router_rows_by_tool)
        rows.extend(balanced_rows)
    router_training_rows = sum(len(group) for group in router_rows_by_tool.values()) + router_balance_added
    assistant_balanced_rows, assistant_balance_added = balance_assistant_rows(
        assistant_rows,
        router_training_rows,
        args.assistant_router_ratio,
    )
    rows.extend(assistant_balanced_rows)
    if not rows:
        raise SystemExit("[ERROR] Dataset SFT không có mẫu hợp lệ")
    lengths = sorted(len(row["input_ids"]) for row in rows)
    p95_index = min(len(lengths) - 1, max(0, int(len(lengths) * 0.95) - 1))
    dataset_metrics = {
        "sft_samples": len(rows),
        "sft_min_tokens": lengths[0],
        "sft_p95_tokens": lengths[p95_index],
        "sft_max_tokens": lengths[-1],
        "sft_max_length": args.max_length,
        "sft_source_records": source_records,
        "sft_replay_records": replay_records,
        "sft_replay_repeat": replay_repeat if args.replay_dataset else 0,
        "sft_max_source_records": args.max_source_records,
        "sft_max_replay_records": args.max_replay_records,
        "sft_training_rows": len(rows),
        "sft_mode_counts": dict(mode_counts),
        "sft_tool_counts": dict(tool_counts),
        "sft_balance_router_tools": bool(args.balance_router_tools),
        "sft_router_balance_added": router_balance_added,
        "sft_assistant_router_ratio": args.assistant_router_ratio,
        "sft_assistant_balance_added": assistant_balance_added,
        "sft_router_format_tokens_added": router_format_tokens_added,
        "sft_tokenizer_size": len(tokenizer),
    }
    print(json.dumps(dataset_metrics, ensure_ascii=False))
    if args.validate_only:
        return

    ds = Dataset.from_list(rows)
    split = ds.train_test_split(test_size=0.1, seed=42) if len(ds) >= 50 else None
    train_ds = split["train"] if split else ds
    eval_ds = split["test"] if split else None
    effective_batch = max(1, args.batch_size * args.grad_accum)
    estimated_updates_per_epoch = max(1, math.ceil(len(train_ds) / effective_batch))
    effective_epochs = float(args.epochs)
    if args.min_updates > 0:
        effective_epochs = max(
            effective_epochs,
            float(math.ceil(args.min_updates / estimated_updates_per_epoch)),
        )

    ta = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=effective_epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        weight_decay=0.01,
        bf16=True,
        gradient_checkpointing=gradient_checkpointing,
        logging_steps=5,
        save_strategy="epoch" if eval_ds is not None else "no",
        eval_strategy="epoch" if eval_ds is not None else "no",
        save_total_limit=1,
        load_best_model_at_end=eval_ds is not None,
        report_to="none",
        remove_unused_columns=False,
    )
    trainer = Trainer(model=model, args=ta, train_dataset=train_ds, eval_dataset=eval_ds,
                      data_collator=PadCollator(tokenizer.pad_token_id))
    eval_loss_before = None
    if eval_ds is not None:
        before_metrics = trainer.evaluate()
        raw_before = before_metrics.get("eval_loss")
        if raw_before is not None and math.isfinite(float(raw_before)):
            eval_loss_before = float(raw_before)
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    result = trainer.train()
    if not math.isfinite(float(result.training_loss)):
        raise SystemExit(f"[ERROR] SFT loss không hữu hạn: {result.training_loss}")
    metrics = dict(result.metrics)
    metrics["sft_training_loss"] = float(result.training_loss)
    metrics["sft_requested_epochs"] = float(args.epochs)
    metrics["sft_effective_epochs"] = effective_epochs
    metrics["sft_min_updates"] = int(args.min_updates)
    metrics["sft_estimated_updates_per_epoch"] = estimated_updates_per_epoch
    metrics["gradient_checkpointing"] = gradient_checkpointing
    metrics["batch_size"] = args.batch_size
    metrics["grad_accum"] = args.grad_accum
    metrics.update(dataset_metrics)
    eval_loss_after = None
    if eval_ds is not None:
        after_metrics = trainer.evaluate()
        raw_after = after_metrics.get("eval_loss")
        if raw_after is not None and math.isfinite(float(raw_after)):
            eval_loss_after = float(raw_after)
    metrics["sft_eval_loss_before"] = eval_loss_before
    metrics["sft_eval_loss_after"] = eval_loss_after
    if eval_loss_before is not None and eval_loss_after is not None and eval_loss_before > 0:
        metrics["sft_eval_loss_improvement_pct"] = (
            (eval_loss_before - eval_loss_after) / eval_loss_before * 100.0
        )
    else:
        metrics["sft_eval_loss_improvement_pct"] = None
    if torch.cuda.is_available():
        gib = 1024 ** 3
        metrics["cuda_peak_allocated_gb"] = torch.cuda.max_memory_allocated() / gib
        metrics["cuda_peak_reserved_gb"] = torch.cuda.max_memory_reserved() / gib
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, ensure_ascii=False))

    final = output_root / "final"
    if args.lora_rank > 0:
        merged = model.merge_and_unload()
        merged.save_pretrained(final, safe_serialization=True)
    else:
        trainer.save_model(final)
    save_bankvn_tokenizer(tokenizer, final, args.base)
    print(f"[OK] SFT final: {final}")


if __name__ == "__main__":
    main()
