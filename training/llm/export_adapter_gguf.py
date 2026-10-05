"""Resume GGUF export from a saved LoRA adapter without repeating training."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", type=Path, required=True)
    ap.add_argument("--gguf-dir", type=Path, required=True)
    ap.add_argument("--max-seq-len", type=int, default=2048)
    args = ap.parse_args()
    if not (args.adapter / "adapter_model.safetensors").is_file():
        raise SystemExit(f"Adapter chưa được lưu: {args.adapter}")
    from unsloth import FastLanguageModel

    print(f"Loading saved adapter: {args.adapter}", flush=True)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(args.adapter),
        max_seq_length=args.max_seq_len,
        load_in_16bit=True,
        load_in_4bit=False,
    )
    print(f"Exporting q4_k_m: {args.gguf_dir}", flush=True)
    model.save_pretrained_gguf(str(args.gguf_dir), tokenizer,
                               quantization_method="q4_k_m")
    from deploy_ollama import tim_gguf
    if tim_gguf(Path(str(args.gguf_dir) + "_gguf")) is None:
        raise RuntimeError("GGUF không hợp lệ hoặc bị cụt; kiểm tra dung lượng ổ đĩa.")
    print(f"[OK] GGUF: {args.gguf_dir}_gguf", flush=True)


if __name__ == "__main__":
    main()
