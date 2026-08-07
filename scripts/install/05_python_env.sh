#!/bin/bash
set -e

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
GPU_BACKEND="${GPU_BACKEND:-cpu}"

echo "Setting up Python virtual environment..."

cd "$PROJECT_DIR"

# Create venv
if [ ! -d .venv ]; then
    python3.11 -m venv .venv 2>/dev/null || python3 -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip

# Install PyTorch with correct backend
case "$GPU_BACKEND" in
    cuda)
        # RTX 50xx (Blackwell, sm_120) requires CUDA 12.8+ builds.
        # cu121/cu124 wheels fail with "no kernel image available".
        echo "Installing PyTorch with CUDA 12.8 support (Blackwell/RTX 50xx compatible)..."
        DRIVER_VER="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 | cut -d. -f1)"
        if [ -n "$DRIVER_VER" ] && [ "$DRIVER_VER" -lt 570 ]; then
            echo "[WARN] NVIDIA driver $DRIVER_VER < 570. RTX 50xx cần driver >= 570 (cài trên Windows host nếu dùng WSL2)."
        fi
        pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
        ;;
    metal|mps)
        echo "Installing PyTorch with MPS (Metal) support..."
        # macOS PyPI torch includes MPS by default
        pip install torch torchaudio
        ;;
    *)
        echo "Installing PyTorch (CPU only)..."
        pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
        ;;
esac

# Install project dependencies
pip install -r backend/requirements.txt

# Install F5-TTS if cloned
F5TTS_DIR="$PROJECT_DIR/tools/F5-TTS-Vietnamese"
if [ -d "$F5TTS_DIR" ]; then
    echo "Installing F5-TTS Vietnamese into venv..."
    pip install -e "$F5TTS_DIR"
fi

# Copy .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[INFO] Created .env from .env.example"
fi

echo "[OK] Python environment ready at $PROJECT_DIR/.venv"
