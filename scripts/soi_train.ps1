$T = "C:\duan\chat-ai\tools\F5-TTS-Vietnamese\src\f5_tts\model\trainer.py"
$C = "C:\duan\chat-ai\tools\F5-TTS-Vietnamese\src\f5_tts\train\finetune_cli.py"

Write-Output "=== trainer.py: do chinh xac & don gradient ==="
Select-String -Path $T -Pattern 'precision|bf16|fp16|accumulation|autocast|compile' |
    ForEach-Object { Write-Output ("  {0}: {1}" -f $_.LineNumber, $_.Line.Trim()) }

Write-Output ""
Write-Output "=== finetune_cli.py: truyen gi vao Trainer ==="
Select-String -Path $C -Pattern 'precision|accumulation|batch_size_type|max_grad|compile' |
    ForEach-Object { Write-Output ("  {0}: {1}" -f $_.LineNumber, $_.Line.Trim()) }

Write-Output ""
Write-Output "=== cau hinh accelerate ==="
$p = "$env:USERPROFILE\.cache\huggingface\accelerate\default_config.yaml"
if (Test-Path $p) { Get-Content $p } else { Write-Output "  khong co $p (dung mac dinh = fp32)" }
