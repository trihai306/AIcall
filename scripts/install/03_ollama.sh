#!/bin/bash
set -e

PLATFORM="${PLATFORM:-$(uname -s)}"

echo "Installing Ollama..."

if command -v ollama &>/dev/null; then
    echo "Ollama already installed:"
    ollama --version
else
    case "$PLATFORM" in
        macos|Darwin)
            if command -v brew &>/dev/null; then
                brew install ollama 2>/dev/null || true
            else
                curl -fsSL https://ollama.com/install.sh | sh
            fi
            ;;
        linux|Linux)
            curl -fsSL https://ollama.com/install.sh | sh
            ;;
    esac
fi

# Start Ollama
case "$PLATFORM" in
    macos|Darwin)
        # macOS: ollama runs as an app or via brew services
        if ! pgrep -x "ollama" > /dev/null 2>&1; then
            echo "Starting Ollama..."
            nohup ollama serve > /tmp/ollama.log 2>&1 &
            sleep 3
        fi
        ;;
    linux|Linux)
        if command -v systemctl &>/dev/null && systemctl is-system-running &>/dev/null 2>&1; then
            sudo systemctl enable ollama --now 2>/dev/null || true
        else
            if ! pgrep -x "ollama" > /dev/null 2>&1; then
                nohup ollama serve > /tmp/ollama.log 2>&1 &
                sleep 3
            fi
        fi
        ;;
esac

echo "[OK] Ollama installed (model Vistral sẽ được tạo ở bước 06_models_download.sh)"
