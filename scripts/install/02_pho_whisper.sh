#!/bin/bash
set -e

# PhoWhisper (VinAI) STT via faster-whisper (CTranslate2)
# Replaces whisper.cpp multilingual Whisper with a Vietnamese-specific model.

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
GPU_BACKEND="${GPU_BACKEND:-cpu}"
MODELS_DIR="$PROJECT_DIR/models/phowhisper"
PHO_MODEL="${PHO_MODEL:-vinai/PhoWhisper-small}"
CT2_DIR="$MODELS_DIR/$(basename "$PHO_MODEL")-ct2"

echo "Installing PhoWhisper STT (faster-whisper)..."

cd "$PROJECT_DIR"
source .venv/bin/activate 2>/dev/null || {
    echo "[ERROR] .venv not found. Run 05_python_env.sh first."
    exit 1
}

pip install -q faster-whisper "ctranslate2>=4.5" transformers

# Convert HF model -> CTranslate2 format (once)
if [ -d "$CT2_DIR" ] && [ -f "$CT2_DIR/model.bin" ]; then
    echo "[SKIP] PhoWhisper CT2 model already exists: $CT2_DIR"
else
    echo "Converting $PHO_MODEL to CTranslate2 format..."
    mkdir -p "$MODELS_DIR"
    QUANT="int8_float16"
    if [ "$GPU_BACKEND" != "cuda" ]; then
        QUANT="int8"
    fi
    ct2-transformers-converter \
        --model "$PHO_MODEL" \
        --output_dir "$CT2_DIR" \
        --quantization "$QUANT" \
        --copy_files tokenizer.json preprocessor_config.json 2>/dev/null || \
    ct2-transformers-converter \
        --model "$PHO_MODEL" \
        --output_dir "$CT2_DIR" \
        --quantization "$QUANT"
fi

echo "[OK] PhoWhisper ready at $CT2_DIR"
echo "     Start server: bash whisper_server/start.sh"
