$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Output "=== CAC MODEL CO TRONG OLLAMA ==="
ollama list

Write-Output ""
Write-Output "=== MODELFILE cua tuvan-qwen ==="
ollama show tuvan-qwen --modelfile

Write-Output ""
Write-Output "=== THONG TIN MODEL ==="
ollama show tuvan-qwen
