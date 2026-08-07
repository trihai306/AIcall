#!/bin/bash
set -e

PLATFORM="${PLATFORM:-$(uname -s)}"

echo "Installing system dependencies..."

case "$PLATFORM" in
    macos|Darwin)
        if ! command -v brew &>/dev/null; then
            echo "Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        brew install cmake git wget ffmpeg portaudio libsndfile sox python@3.11 2>/dev/null || true
        echo "[OK] macOS dependencies installed via Homebrew"
        ;;
    linux|Linux)
        sudo apt update
        sudo apt install -y \
            build-essential cmake git wget curl \
            python3.11 python3.11-venv python3.11-dev python3-pip \
            ffmpeg portaudio19-dev libsndfile1-dev \
            libssl-dev libffi-dev pkg-config \
            sox libsox-fmt-all
        echo "[OK] Linux dependencies installed via apt"
        ;;
esac
