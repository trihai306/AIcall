$ErrorActionPreference = "Stop"
Set-Location C:\duan\chat-ai

& C:\duan\chat-ai\.venv-train\Scripts\python.exe -X utf8 `
  C:\duan\chat-ai\training\bankvn\sft.py `
  --base C:\duan\chat-ai\models\bankvn\pretrain\sp-smoke6-final\final `
  --dataset C:\duan\chat-ai\data\bankvn\smoke\teacher.jsonl `
  --output C:\duan\chat-ai\models\bankvn\sft\bankvn-smoke6-router-overfit `
  --epochs 60 `
  --batch-size 1 `
  --grad-accum 1

exit $LASTEXITCODE
