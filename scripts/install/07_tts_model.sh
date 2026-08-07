#!/bin/bash
set -e

# F5-TTS Vietnamese ViVoice model only.
# Tách riêng khỏi 06_models_download.sh để không kéo theo Vistral GGUF (~4GB).

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
F5TTS_DIR="$PROJECT_DIR/tools/F5-TTS-Vietnamese"
MODEL_DIR="$PROJECT_DIR/models/tts/F5-TTS-Vietnamese-ViVoice"

cd "$PROJECT_DIR"
source .venv/bin/activate 2>/dev/null || {
    echo "[ERROR] .venv không tồn tại. Chạy: bash scripts/install/05_python_env.sh"
    exit 1
}

# --- 1. Source code F5-TTS ---
if python -c "import f5_tts" 2>/dev/null; then
    echo "[SKIP] Package f5_tts đã cài"
else
    echo "Cài source code F5-TTS..."
    bash "$PROJECT_DIR/scripts/install/04_f5tts.sh"
    pip install -e "$F5TTS_DIR"
fi

# --- 2. Checkpoint ViVoice (~1.3GB) ---
if [ -f "$MODEL_DIR/model_last.pt" ]; then
    echo "[SKIP] Checkpoint F5-TTS đã có: $MODEL_DIR/model_last.pt"
else
    echo "Tải F5-TTS Vietnamese ViVoice (model_last.pt ~5.4GB, mất 10-20 phút)..."
    mkdir -p "$MODEL_DIR"
    pip install -q huggingface_hub
    python - "$MODEL_DIR" <<'PY'
import sys
from huggingface_hub import snapshot_download

snapshot_download(repo_id="hynt/F5-TTS-Vietnamese-ViVoice", local_dir=sys.argv[1])
PY
fi

# --- 3. config.json -> vocab.txt ---
if [ -f "$MODEL_DIR/config.json" ] && [ ! -f "$MODEL_DIR/vocab.txt" ]; then
    mv "$MODEL_DIR/config.json" "$MODEL_DIR/vocab.txt"
    echo "[OK] Đã đổi tên config.json -> vocab.txt"
fi

if [ ! -f "$MODEL_DIR/vocab.txt" ]; then
    echo "[ERROR] Thiếu vocab.txt trong $MODEL_DIR"
    exit 1
fi

echo "[OK] F5-TTS sẵn sàng: $MODEL_DIR"
du -sh "$MODEL_DIR" 2>/dev/null || true
