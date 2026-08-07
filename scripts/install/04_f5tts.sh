#!/bin/bash
set -e

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
F5TTS_DIR="$PROJECT_DIR/tools/F5-TTS-Vietnamese"

echo "Installing F5-TTS Vietnamese..."

if [ -d "$F5TTS_DIR" ]; then
    echo "F5-TTS exists, updating..."
    cd "$F5TTS_DIR" && git pull
else
    mkdir -p "$PROJECT_DIR/tools"
    git clone https://github.com/nguyenthienhy/F5-TTS-Vietnamese "$F5TTS_DIR"
fi

# Will be installed into the project venv in step 05
echo "[OK] F5-TTS Vietnamese cloned to $F5TTS_DIR"
echo "     Will be pip-installed in the Python env step"
