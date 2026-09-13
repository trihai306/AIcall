#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Starting AI Banking Call System..."
echo "Project: $PROJECT_DIR"

# 1. Start Ollama
# NUM_PARALLEL: số cuộc gọi chạy đồng thời. Mỗi slot có KV cache riêng, nên giữ
# số slot thấp trên GPU 12GB để tránh đẩy model ra khỏi VRAM.
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-2}"
LLM_NUM_CTX_CFG=""
if [[ -f "$PROJECT_DIR/.env" ]]; then
    LLM_NUM_CTX_CFG="$(sed -n 's/^[[:space:]]*LLM_NUM_CTX[[:space:]]*=[[:space:]]*//p' "$PROJECT_DIR/.env" | tail -n 1 | tr -d '\r\"')"
fi
export OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-${LLM_NUM_CTX_CFG:-8192}}"
if ! pgrep -x "ollama" > /dev/null 2>&1; then
    echo "Starting Ollama (NUM_PARALLEL=$OLLAMA_NUM_PARALLEL, CONTEXT=$OLLAMA_CONTEXT_LENGTH)..."
    nohup ollama serve > /tmp/ollama.log 2>&1 &
    sleep 2
else
    echo "  (Ollama đã chạy sẵn - OLLAMA_NUM_PARALLEL chỉ có tác dụng khi khởi động lại nó)"
fi
echo "[OK] Ollama running"

# 2. Start STT. Gipformer runs inside FastAPI; only PhoWhisper needs :8178.
STT_ENGINE="${STT_ENGINE:-}"
if [[ -z "$STT_ENGINE" && -f "$PROJECT_DIR/.env" ]]; then
    STT_ENGINE="$(sed -n 's/^[[:space:]]*STT_ENGINE[[:space:]]*=[[:space:]]*//p' "$PROJECT_DIR/.env" | tail -n 1 | tr -d '\r\"' | tr '[:upper:]' '[:lower:]')"
fi
STT_ENGINE="${STT_ENGINE:-phowhisper}"
if [[ "$STT_ENGINE" == "gipformer" ]]; then
    echo "[OK] STT_ENGINE=gipformer — model sẽ nạp trong FastAPI, bỏ qua PhoWhisper :8178"
else
    if ! pgrep -f "pho_server.py" > /dev/null 2>&1; then
        echo "Starting PhoWhisper server..."
        nohup bash "$PROJECT_DIR/whisper_server/start.sh" > /tmp/pho-server.log 2>&1 &
        sleep 3
    fi
    echo "[OK] PhoWhisper server running on :8178"
fi

# 3. Start FastAPI backend
cd "$PROJECT_DIR"
source .venv/bin/activate 2>/dev/null || true

echo "Starting FastAPI backend on :8000..."
echo "  Open http://localhost:8000 in your browser"
echo ""
python -m uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info
