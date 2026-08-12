$T = "C:\duan\chat-ai\tools\F5-TTS-Vietnamese\src\f5_tts\model\trainer.py"
Write-Output "=== log_samples chay khi nao ==="
Select-String -Path $T -Pattern 'log_samples|save_per_updates|last_per_updates|global_update %|sample_' |
    ForEach-Object { Write-Output ("  {0}: {1}" -f $_.LineNumber, $_.Line.Trim()) }

Write-Output ""
Write-Output "=== dia: tien trinh train doc/ghi bao nhieu ==="
$a = Get-CimInstance Win32_Process -Filter "ProcessId=17556"
Start-Sleep -Seconds 10
$b = Get-CimInstance Win32_Process -Filter "ProcessId=17556"
$rd = ($b.ReadTransferCount - $a.ReadTransferCount)/1MB
$wr = ($b.WriteTransferCount - $a.WriteTransferCount)/1MB
Write-Output ("  doc  {0,8:N1} MB / 10s" -f $rd)
Write-Output ("  ghi  {0,8:N1} MB / 10s" -f $wr)
