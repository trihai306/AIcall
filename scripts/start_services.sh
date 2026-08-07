#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Starting AI Banking Call System..."
echo "Project: $PROJECT_DIR"

# 1. Start Ollama
# NUM_PARALLEL: số cuộc gọi chạy đồng thời (mỗi slot tốn thêm ~250MB KV cache
# với num_ctx=2048). Để 1 thì cuộc gọi thứ hai phải xếp hàng chờ sinh token.
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-2}"
if ! pgrep -x "ollama" > /dev/null 2>&1; then
    echo "Starting Ollama (NUM_PARALLEL=$OLLAMA_NUM_PARALLEL)..."
    nohup ollama serve > /tmp/ollama.log 2>&1 &
    sleep 2
else
    echo "  (Ollama đã chạy sẵn - OLLAMA_NUM_PARALLEL chỉ có tác dụng khi khởi động lại nó)"
fi
echo "[OK] Ollama running"

# 2. Start PhoWhisper STT server
if ! pgrep -f "pho_server.py" > /dev/null 2>&1; then
    echo "Starting PhoWhisper server..."
    nohup bash "$PROJECT_DIR/whisper_server/start.sh" > /tmp/pho-server.log 2>&1 &
    sleep 3
fi
echo "[OK] PhoWhisper server running on :8178"

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
