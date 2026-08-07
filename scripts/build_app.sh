#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

OS="$(uname -s)"

echo "============================================"
echo "  VoiceBank AI — Build Desktop App"
echo "============================================"

source .venv/bin/activate 2>/dev/null || true
pip install pyinstaller -q 2>/dev/null

case "$OS" in
  Darwin)
    echo "Building macOS .app bundle..."
    pyinstaller \
      --name "VoiceBank AI" \
      --windowed \
      --onedir \
      --add-data "frontend:frontend" \
      --add-data "knowledge:knowledge" \
      --add-data "backend:backend" \
      --add-data ".env:.env" \
      --hidden-import uvicorn \
      --hidden-import backend.main \
      --icon desktop/assets/icon.icns \
      --noconfirm \
      app.py

    echo ""
    echo "[OK] App built: dist/VoiceBank AI.app"
    echo "     Drag to /Applications to install"
    ;;

  Linux|MINGW*|MSYS*)
    echo "Building Windows/Linux executable..."
    pyinstaller \
      --name "VoiceBank-AI" \
      --windowed \
      --onedir \
      --add-data "frontend:frontend" \
      --add-data "knowledge:knowledge" \
      --add-data "backend:backend" \
      --hidden-import uvicorn \
      --hidden-import backend.main \
      --icon desktop/assets/icon.ico \
      --noconfirm \
      app.py

    echo ""
    echo "[OK] App built: dist/VoiceBank-AI/"
    ;;
esac

echo ""
echo "Note: models/ cần copy thủ công vào thư mục dist"
echo "      vì quá lớn để đóng gói (~5GB)"
