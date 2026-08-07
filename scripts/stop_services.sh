#!/bin/bash

echo "Stopping AI Banking Call System..."

pkill -f "whisper-server" 2>/dev/null && echo "[OK] Whisper server stopped" || echo "[SKIP] Whisper not running"
pkill -f "uvicorn" 2>/dev/null && echo "[OK] FastAPI stopped" || echo "[SKIP] FastAPI not running"

echo ""
echo "Note: Ollama keeps running (shared service)"
echo "To stop Ollama: pkill ollama"
