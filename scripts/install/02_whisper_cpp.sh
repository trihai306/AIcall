#!/bin/bash
set -e

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WHISPER_DIR="$PROJECT_DIR/tools/whisper.cpp"
GPU_BACKEND="${GPU_BACKEND:-cpu}"

echo "Building whisper.cpp..."

if [ -d "$WHISPER_DIR" ]; then
    echo "whisper.cpp exists, updating..."
    cd "$WHISPER_DIR" && git pull
else
    mkdir -p "$PROJECT_DIR/tools"
    git clone https://github.com/ggerganov/whisper.cpp "$WHISPER_DIR"
fi

cd "$WHISPER_DIR"

# Platform-specific CMake flags
case "$GPU_BACKEND" in
    cuda)
        echo "Building with CUDA support..."
        cmake -B build \
            -DGGML_CUDA=1 \
            -DCMAKE_CUDA_ARCHITECTURES="75;80;86;89;90" \
            -DWHISPER_BUILD_SERVER=ON
        ;;
    metal)
        echo "Building with Metal (Apple Silicon) support..."
        cmake -B build \
            -DGGML_METAL=1 \
            -DWHISPER_BUILD_SERVER=ON
        ;;
    *)
        echo "Building CPU-only..."
        cmake -B build \
            -DWHISPER_BUILD_SERVER=ON
        ;;
esac

# Cross-platform core count
if command -v nproc &>/dev/null; then
    CORES=$(nproc)
else
    CORES=$(sysctl -n hw.logicalcpu 2>/dev/null || echo 4)
fi

cmake --build build --config Release -j"$CORES"

if [ -f build/bin/whisper-server ]; then
    echo "[OK] whisper.cpp built at $WHISPER_DIR/build/bin/whisper-server"
else
    echo "[ERROR] whisper-server binary not found"
    exit 1
fi
