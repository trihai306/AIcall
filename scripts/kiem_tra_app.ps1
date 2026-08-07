# =====================================================
# Kiem tra app desktop + dich vu nen dang o trang thai nao.
#   .\scripts\kiem_tra_app.ps1
#
# In ra tien trinh Electron, backend, PhoWhisper, Ollama, /api/health va xung
# GPU. Dung sau khi bam VoiceBank-AI.exe de xac minh app that su khoi dong du
# dich vu, thay vi chi nhin thay cua so mo len.
# =====================================================
param([int]$Port = 8100)

$PROJECT = Split-Path -Parent $PSScriptRoot

function Show-Proc($name, $pattern, $label) {
    $p = Get-CimInstance Win32_Process -Filter "Name='$name'" -EA SilentlyContinue |
         Where-Object { $pattern -eq '' -or $_.CommandLine -like $pattern }
    if ($p) { foreach ($x in $p) { Write-Host "[OK] $label (PID $($x.ProcessId))" } }
    else    { Write-Host "[--] $label KHONG chay" }
}

Write-Host "=== Tien trinh ==="
Show-Proc "VoiceBank AI.exe" ""                      "App Electron"
Show-Proc "python.exe" "*uvicorn*backend.main*"      "FastAPI backend"
Show-Proc "python.exe" "*pho_server.py*"             "PhoWhisper server"
Show-Proc "ollama.exe" ""                            "Ollama"

Write-Host ""
Write-Host "=== Health (cong $Port) ==="
try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 8
    Write-Host "status : $($h.status)"
    Write-Host "stt    : $($h.services.stt)"
    Write-Host "llm    : $($h.services.llm)"
    Write-Host "tts    : $($h.services.tts)"
    Write-Host "rag    : $($h.services.rag)"
} catch {
    Write-Host "[--] Backend chua tra loi: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "=== PhoWhisper (:8178) ==="
try {
    $w = Invoke-RestMethod -Uri "http://127.0.0.1:8178/health" -TimeoutSec 8
    Write-Host ($w | ConvertTo-Json -Compress)
} catch {
    Write-Host "[--] PhoWhisper chua tra loi: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "=== GPU ==="
try {
    # Xung san phai la 1500MHz neu start_services.ps1 da chay (khong khoa thi
    # GPU tut ve 277-600MHz luc ranh -> TTS 687ms thay vi 513ms).
    nvidia-smi --query-gpu=clocks.applications.graphics,clocks.max.sm,memory.used --format=csv
} catch {
    Write-Host "[--] Khong goi duoc nvidia-smi"
}
