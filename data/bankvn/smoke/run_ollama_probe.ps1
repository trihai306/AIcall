$ErrorActionPreference = "Stop"
Set-Location C:\duan\chat-ai

& C:\duan\chat-ai\.venv\python.exe -X utf8 `
  C:\duan\chat-ai\data\bankvn\smoke\ollama_raw_probe.py

exit $LASTEXITCODE
