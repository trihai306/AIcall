$f = Get-Item C:\duan\chat-ai\logs\backend.log
Write-Output ("log backend: {0:N0} KB, sua luc {1}" -f ($f.Length/1KB), $f.LastWriteTime)
Write-Output ""
Write-Output "=== VRAM ==="
nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv,noheader
Write-Output ""
Write-Output "=== cua so lenh backend con khong ==="
Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
  Where-Object { $_.CommandLine -match "backend|uvicorn|main" } |
  ForEach-Object { "PID $($_.ProcessId): $($_.CommandLine.Substring(0,[Math]::Min(120,$_.CommandLine.Length)))" }
Write-Output ""
Write-Output "=== .bat khoi chay backend ==="
if (Test-Path C:\duan\chat-ai\logs\_run\backend.bat) {
  Get-Content C:\duan\chat-ai\logs\_run\backend.bat -Encoding UTF8
}
Write-Output ""
Write-Output "=== 25 dong cuoi backend.log ==="
Get-Content C:\duan\chat-ai\logs\backend.log -Tail 25 -Encoding UTF8
