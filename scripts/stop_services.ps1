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

# Chot chan theo CONG: ngay 06-09-2026, "[STOP] FastAPI backend (PID ...)" in ra
# mot PID khong phai tien trinh dang giu cong 8100 (PID 34268, chay tu 21:15),
# tien trinh do song sot, start_services thay cong con song nen bo qua, kiem tra
# suc khoe van OK vi tien trinh cu tra loi -> hai lan "khoi dong lai" khong he
# xay ra, code moi khong duoc nap, va cuoc goi thu ngay sau do chet ngay khung
# tieng dau tien vi phone_call_service moi (nap luoi) doc settings cu.
# Cong nao con LISTEN thi giet dung tien trinh dang giu no, khong tin danh sach.
function Kill-ByPort($port, $label) {
    $conn = Get-NetTCPConnection -State Listen -LocalPort $port -EA SilentlyContinue
    foreach ($c in $conn) {
        if ($c.OwningProcess -gt 0) {
            Stop-Process -Id $c.OwningProcess -Force -EA SilentlyContinue
            Write-Host "[STOP] $label van giu cong $port -> giet PID $($c.OwningProcess)"
        }
    }
}
Start-Sleep -Milliseconds 800
Kill-ByPort 8100 "FastAPI backend"
Kill-ByPort 8178 "PhoWhisper server"

if ($All) {
    $o = Get-Process ollama -EA SilentlyContinue
    if ($o) { $o | Stop-Process -Force; Write-Host "[STOP] Ollama" }
    else { Write-Host "[--] Ollama khong chay" }
} else {
    Write-Host "[--] Giu nguyen Ollama (dung -All de dung luon)"
}
