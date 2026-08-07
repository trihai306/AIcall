#!/bin/bash
set -e

# Fine-tune LLM (Vistral) theo dữ liệu tư vấn riêng — QLoRA/Unsloth.
# Chạy trên máy GPU NVIDIA. Unsloth cài vào venv RIÊNG (.venv-train)
# để không xung đột dependency với f5-tts trong .venv chính.
#
# Usage: bash training/llm/train.sh [tham số truyền cho train_lora.py]
# Ví dụ: bash training/llm/train.sh --epochs 4

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV="$PROJECT_DIR/.venv-train"

command -v nvidia-smi >/dev/null || { echo "[ERROR] Cần GPU NVIDIA (Unsloth không chạy trên Mac/CPU)"; exit 1; }

# Cảnh báo nếu Ollama/backend đang chiếm VRAM
if pgrep -x ollama >/dev/null || pgrep -f "uvicorn backend.main" >/dev/null; then
    echo "[WARN] Ollama/backend đang chạy - sẽ tranh VRAM với training."
    echo "       Nên tắt trước: pkill ollama; pkill -f uvicorn"
    read -p "Tiếp tục? [y/N] " yn
    [ "$yn" = "y" ] || exit 1
fi

if [ ! -d "$VENV" ]; then
    echo "Tạo venv training tại $VENV ..."
    python3 -m venv "$VENV"
    source "$VENV/bin/activate"
    pip install --upgrade pip
    pip install torch --index-url https://download.pytorch.org/whl/cu128
    pip install unsloth datasets trl transformers
else
    source "$VENV/bin/activate"
fi

# Dataset
if [ ! -f "$PROJECT_DIR/data/training/merged_dataset.jsonl" ]; then
    echo "Chưa có merged_dataset.jsonl - chạy make_dataset.py trước..."
    python "$SCRIPT_DIR/make_dataset.py"
fi

python "$SCRIPT_DIR/train_lora.py" "$@"
