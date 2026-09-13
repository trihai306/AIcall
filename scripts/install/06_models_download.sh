#!/bin/bash
set -e

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MODELS_DIR="$PROJECT_DIR/models"

echo "Downloading AI models..."

source "$PROJECT_DIR/.venv/bin/activate" 2>/dev/null || true
pip install -q huggingface_hub 2>/dev/null || true

# 1. LLM -> Ollama. Dùng đúng model mà app sẽ chạy thay vì tải Vistral cố định.
# Installer thường chạy trước khi người dùng copy .env, nên fallback phải khớp
# backend/config.py và .env.example.
LLM_MODEL="${OLLAMA_MODEL:-}"
if [ -z "$LLM_MODEL" ] && [ -f "$PROJECT_DIR/.env" ]; then
    LLM_MODEL="$(sed -n 's/^OLLAMA_MODEL[[:space:]]*=[[:space:]]*//p' "$PROJECT_DIR/.env" | tail -n 1 | tr -d '\r')"
fi
LLM_MODEL="${LLM_MODEL:-qwen3.5:9b}"

if command -v ollama &>/dev/null; then
    if ollama list 2>/dev/null | awk 'NR > 1 {print $1}' | grep -Fxq "$LLM_MODEL"; then
        echo "[SKIP] Ollama model $LLM_MODEL already exists"
    else
        echo "Pulling Ollama model $LLM_MODEL..."
        ollama pull "$LLM_MODEL"
    fi
else
    echo "[WARN] ollama not found - run 03_ollama.sh first, then:"
    echo "       ollama pull $LLM_MODEL"
fi

# 2. PhoWhisper CT2 (STT) - handled by 02_pho_whisper.sh, verify only
if [ -d "$MODELS_DIR/phowhisper" ] && ls "$MODELS_DIR/phowhisper"/*/model.bin &>/dev/null; then
    echo "[OK] PhoWhisper CT2 model present"
else
    echo "[WARN] PhoWhisper model missing - run scripts/install/02_pho_whisper.sh"
fi

# 3. F5-TTS Vietnamese model
F5TTS_MODEL_DIR="$MODELS_DIR/tts/F5-TTS-Vietnamese-ViVoice"

if [ -f "$F5TTS_MODEL_DIR/model_last.pt" ]; then
    echo "[SKIP] F5-TTS model already exists"
else
    echo "Downloading F5-TTS Vietnamese ViVoice model..."
    mkdir -p "$F5TTS_MODEL_DIR"

    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='hynt/F5-TTS-Vietnamese-ViVoice',
    local_dir='$F5TTS_MODEL_DIR'
)
"
    # Rename config.json to vocab.txt
    if [ -f "$F5TTS_MODEL_DIR/config.json" ] && [ ! -f "$F5TTS_MODEL_DIR/vocab.txt" ]; then
        mv "$F5TTS_MODEL_DIR/config.json" "$F5TTS_MODEL_DIR/vocab.txt"
        echo "[OK] Renamed config.json -> vocab.txt"
    fi
fi

# 4. Reference voice placeholder
REF_VOICES_DIR="$MODELS_DIR/tts/ref_voices"
mkdir -p "$REF_VOICES_DIR"
if [ ! -f "$REF_VOICES_DIR/default.wav" ]; then
    echo ""
    echo "[INFO] No reference voice found."
    echo "  Record 5-10 seconds of your preferred voice"
    echo "  Save as: $REF_VOICES_DIR/default.wav"
    echo "  Create:  $REF_VOICES_DIR/default.txt (transcript)"
    echo "  Để train giọng riêng: xem training/voice/README.md"
fi

echo ""
echo "[OK] Models downloaded to $MODELS_DIR"
du -sh "$MODELS_DIR"/* 2>/dev/null || true
