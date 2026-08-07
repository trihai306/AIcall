#!/bin/bash
set -e

# STT server launcher.
# Default: PhoWhisper (faster-whisper) — Vietnamese-specific, fastest.
# Fallback: whisper.cpp — bash whisper_server/start.sh legacy [model]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

MODE="${1:-pho}"

if [ "$MODE" = "legacy" ]; then
    # --- whisper.cpp fallback ---
    WHISPER_DIR="$PROJECT_DIR/tools/whisper.cpp"
    WHISPER_MODEL="${2:-small}"
    MODEL_PATH="${3:-$PROJECT_DIR/models/whisper/ggml-${WHISPER_MODEL}.bin}"
    WHISPER_SERVER="$WHISPER_DIR/build/bin/whisper-server"

    if [ ! -f "$WHISPER_SERVER" ]; then
        echo "[ERROR] whisper-server not found: $WHISPER_SERVER"
        echo "  Run: bash scripts/install/02_whisper_cpp.sh"
        exit 1
    fi

    echo "Starting whisper.cpp server (legacy)..."
    exec "$WHISPER_SERVER" \
        --model "$MODEL_PATH" \
        --host 0.0.0.0 \
        --port 8178 \
        --language vi \
        --threads 4 \
        --no-timestamps
fi

# --- PhoWhisper (default) ---
PHO_CT2_DIR="${PHO_CT2_DIR:-$PROJECT_DIR/models/phowhisper/PhoWhisper-small-ct2}"

source "$PROJECT_DIR/.venv/bin/activate"

if [ ! -f "$PHO_CT2_DIR/model.bin" ]; then
    echo "[ERROR] PhoWhisper CT2 model not found: $PHO_CT2_DIR"
    echo "  Run: bash scripts/install/02_pho_whisper.sh"
    exit 1
fi

echo "Starting PhoWhisper server..."
echo "  Model: $PHO_CT2_DIR"
echo "  Port:  8178"

exec python "$SCRIPT_DIR/pho_server.py" --model "$PHO_CT2_DIR" --port 8178
