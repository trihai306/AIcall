# =====================================================
# AI Banking Call System - dung dich vu (Windows)
# Tuong duong scripts/stop_services.sh
#   .\scripts\stop_services.ps1            # dung backend + PhoWhisper
#   .\scripts\stop_services.ps1 -All       # dung ca Ollama
# =====================================================
param([switch]$All)

function Kill-ByCmdLine($pattern, $label) {
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue |
             Where-Object { $_.CommandLine -like $pattern }
    if ($procs) {
        foreach ($p in $procs) {
            Stop-Process -Id $p.ProcessId -Force -EA SilentlyContinue
            Write-Host "[STOP] $label (PID $($p.ProcessId))"
        }
    } else {
        Write-Host "[--] $label khong chay"
    }
}

Kill-ByCmdLine "*uvicorn*backend.main*" "FastAPI backend"
Kill-ByCmdLine "*pho_server.py*"        "PhoWhisper server"

if ($All) {
    $o = Get-Process ollama -EA SilentlyContinue
    if ($o) { $o | Stop-Process -Force; Write-Host "[STOP] Ollama" }
    else { Write-Host "[--] Ollama khong chay" }
} else {
    Write-Host "[--] Giu nguyen Ollama (dung -All de dung luon)"
}
