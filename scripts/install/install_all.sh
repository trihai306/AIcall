#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "============================================"
echo "  AI Banking Call System - Full Installer"
echo "============================================"
echo "Project: $PROJECT_DIR"

# --- Detect platform ---
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Darwin)
        PLATFORM="macos"
        echo "[OS] macOS ($ARCH)"
        if [[ "$ARCH" == "arm64" ]]; then
            GPU_BACKEND="metal"
            echo "[GPU] Apple Silicon - Metal/MPS"
        else
            GPU_BACKEND="cpu"
            echo "[GPU] Intel Mac - CPU only"
        fi
        ;;
    Linux)
        PLATFORM="linux"
        if grep -qi microsoft /proc/version 2>/dev/null; then
            echo "[OS] Windows WSL2 (Linux)"
        else
            echo "[OS] Linux ($ARCH)"
        fi
        if command -v nvidia-smi &>/dev/null; then
            GPU_BACKEND="cuda"
            echo "[GPU] NVIDIA CUDA:"
            nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true
        else
            GPU_BACKEND="cpu"
            echo "[GPU] No NVIDIA GPU detected - will use CPU"
        fi
        ;;
    *)
        echo "[ERROR] Unsupported OS: $OS"
        exit 1
        ;;
esac

export PLATFORM GPU_BACKEND PROJECT_DIR

echo ""
echo "=== Step 1/6: System Dependencies ==="
bash "$SCRIPT_DIR/01_system_deps.sh"

echo ""
echo "=== Step 2/6: Ollama (LLM) ==="
bash "$SCRIPT_DIR/03_ollama.sh"

echo ""
echo "=== Step 3/6: F5-TTS Vietnamese (TTS) ==="
bash "$SCRIPT_DIR/04_f5tts.sh"

echo ""
echo "=== Step 4/6: Python Environment ==="
bash "$SCRIPT_DIR/05_python_env.sh"

echo ""
echo "=== Step 5/6: PhoWhisper (STT tiếng Việt) ==="
bash "$SCRIPT_DIR/02_pho_whisper.sh"
# Fallback whisper.cpp (không bắt buộc): bash scripts/install/02_whisper_cpp.sh

echo ""
echo "=== Step 6/6: Download Models ==="
bash "$SCRIPT_DIR/06_models_download.sh"

echo ""
echo "============================================"
echo "  Installation Complete!"
echo "  Platform: $PLATFORM / GPU: $GPU_BACKEND"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. cp .env.example .env"
echo "  2. Add reference voice: models/tts/ref_voices/default.wav"
echo "  3. bash scripts/start_services.sh"
echo "  4. Open http://localhost:8000 in browser"
echo ""
