# =====================================================
# Do tai nguyen tieu ton khi chay AI Banking Call System
#   - Lay mau GPU (util / VRAM / power / temp) moi 1s bang nvidia-smi -l
#   - Lay mau RAM tung tien trinh (ollama, python) + RAM/CPU he thong
#   - Chay benchmark that (STT / LLM / TTS / RAG / full pipeline)
#   - Tong ket: idle vs tai, dinh VRAM, dinh RAM
# =====================================================
$ErrorActionPreference = "Continue"
$PROJECT = "C:\duan\chat-ai"
$LOGS    = "$PROJECT\logs"
$GPUCSV  = "$LOGS\gpu_samples.csv"
$PROCCSV = "$LOGS\proc_samples.csv"
$BASE    = "http://localhost:8100"
New-Item -ItemType Directory -Force -Path $LOGS | Out-Null
Remove-Item $GPUCSV,$PROCCSV -EA SilentlyContinue

function Snapshot($label) {
    $g = (nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,power.draw,temperature.gpu --format=csv,noheader,nounits) -split ',' | ForEach-Object { $_.Trim() }
    $os = Get-CimInstance Win32_OperatingSystem
    $ramUsedGB = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/1MB, 2)
    $ramTotGB  = [math]::Round($os.TotalVisibleMemorySize/1MB, 2)
    [PSCustomObject]@{
        Moc          = $label
        GPU_util_pct = [int]$g[0]
        VRAM_MB      = [int]$g[1]
        VRAM_tot_MB  = [int]$g[2]
        Power_W      = $g[3]
        Temp_C       = [int]$g[4]
        RAM_used_GB  = $ramUsedGB
        RAM_tot_GB   = $ramTotGB
    }
}

function ProcTable($label) {
    Get-Process ollama,python,"ollama app" -EA SilentlyContinue |
      Group-Object ProcessName | ForEach-Object {
        [PSCustomObject]@{
            Moc     = $label
            Process = $_.Name
            Count   = $_.Count
            RAM_MB  = [math]::Round((($_.Group | Measure-Object WorkingSet64 -Sum).Sum)/1MB)
        }
      }
}

function CallApi($path, $timeoutSec = 300) {
    $t0 = Get-Date
    try {
        $r = Invoke-RestMethod -Uri "$BASE$path" -Method Post -TimeoutSec $timeoutSec
        $ms = [math]::Round(((Get-Date) - $t0).TotalMilliseconds)
        return @{ ok = $true; data = $r; wall_ms = $ms }
    } catch {
        $ms = [math]::Round(((Get-Date) - $t0).TotalMilliseconds)
        return @{ ok = $false; err = $_.Exception.Message; wall_ms = $ms }
    }
}

Write-Output "################ DO TAI NGUYEN ################"
Write-Output "[$(Get-Date -Format 'HH:mm:ss')]"
Write-Output ""
Write-Output "=== GPU ==="
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

# ---------- A. IDLE (dich vu da chay, chua co request) ----------
Write-Output ""
Write-Output "=== A. IDLE (sau khi dich vu khoi dong, chua co tai) ==="
$idle = Snapshot "idle"
$idle | Format-List | Out-String
ProcTable "idle" | Format-Table -Auto | Out-String

# ---------- B. Bat dau lay mau lien tuc ----------
$smi = Start-Process -FilePath "nvidia-smi" -PassThru -WindowStyle Hidden `
        -ArgumentList "--query-gpu=timestamp,utilization.gpu,memory.used,power.draw,temperature.gpu","--format=csv,nounits","-l","1","-f",$GPUCSV

# sampler RAM tien trinh (chay nen bang job)
$job = Start-Job -ScriptBlock {
    param($out)
    "time,process,ram_mb" | Out-File -FilePath $out -Encoding utf8
    while ($true) {
        $t = (Get-Date -Format "HH:mm:ss")
        Get-Process ollama,python -EA SilentlyContinue | Group-Object ProcessName | ForEach-Object {
            $mb = [math]::Round((($_.Group | Measure-Object WorkingSet64 -Sum).Sum)/1MB)
            "$t,$($_.Name),$mb" | Out-File -FilePath $out -Append -Encoding utf8
        }
        Start-Sleep -Milliseconds 1000
    }
} -ArgumentList $PROCCSV

Start-Sleep -Seconds 3

# ---------- C. Chay benchmark ----------
Write-Output ""
Write-Output "=== C. CHAY BENCHMARK ==="
$results = @{}
foreach ($ep in @("rag","stt","llm","tts","full")) {
    Write-Output ""
    Write-Output "--- /api/benchmark/$ep ---"
    $r = CallApi "/api/benchmark/$ep"
    $results[$ep] = $r
    if ($r.ok) {
        $r.data | ConvertTo-Json -Depth 4 -Compress | Out-String
        Write-Output "wall_ms=$($r.wall_ms)"
    } else {
        Write-Output "LOI: $($r.err)  (wall_ms=$($r.wall_ms))"
    }
    $s = Snapshot "sau-$ep"
    "  GPU {0}%  VRAM {1}/{2} MB  {3}W  {4}C  RAM {5}/{6} GB" -f $s.GPU_util_pct,$s.VRAM_MB,$s.VRAM_tot_MB,$s.Power_W,$s.Temp_C,$s.RAM_used_GB,$s.RAM_tot_GB | Write-Output
    Start-Sleep -Seconds 2
}

# ---------- D. Dung lay mau + tong ket ----------
Start-Sleep -Seconds 2
Stop-Process -Id $smi.Id -Force -EA SilentlyContinue
Stop-Job $job -EA SilentlyContinue; Remove-Job $job -Force -EA SilentlyContinue

Write-Output ""
Write-Output "=== D. TONG KET TAI NGUYEN ==="
if (Test-Path $GPUCSV) {
    $g = Import-Csv $GPUCSV
    $vram = $g | ForEach-Object { [int]($_.' memory.used [MiB]' -replace '[^\d]','') } | Where-Object { $_ -gt 0 }
    $util = $g | ForEach-Object { [int]($_.' utilization.gpu [%]' -replace '[^\d]','') }
    $pw   = $g | ForEach-Object { [double]($_.' power.draw [W]' -replace '[^\d.]','') } | Where-Object { $_ -gt 0 }
    if ($vram) {
      "  So mau        : {0}" -f $g.Count
      "  VRAM  min/tb/dinh : {0} / {1} / {2} MB" -f ($vram|Measure-Object -Minimum).Minimum, [math]::Round(($vram|Measure-Object -Average).Average), ($vram|Measure-Object -Maximum).Maximum
      "  GPU%  tb/dinh     : {0} / {1} %" -f [math]::Round(($util|Measure-Object -Average).Average), ($util|Measure-Object -Maximum).Maximum
      if ($pw) { "  Dien  tb/dinh     : {0} / {1} W" -f [math]::Round(($pw|Measure-Object -Average).Average,1), ($pw|Measure-Object -Maximum).Maximum }
    }
}
if (Test-Path $PROCCSV) {
    $p = Import-Csv $PROCCSV
    Write-Output "  --- RAM tien trinh (dinh) ---"
    $p | Group-Object process | ForEach-Object {
        $mx = ($_.Group | ForEach-Object { [int]$_.ram_mb } | Measure-Object -Maximum).Maximum
        "  {0,-10} dinh {1,7} MB" -f $_.Name, $mx
    }
}
$fin = Snapshot "cuoi"
Write-Output ""
"  Trang thai cuoi: GPU {0}%  VRAM {1}/{2} MB  RAM {3}/{4} GB" -f $fin.GPU_util_pct,$fin.VRAM_MB,$fin.VRAM_tot_MB,$fin.RAM_used_GB,$fin.RAM_tot_GB
Write-Output ""
Write-Output "MARKER_MEASURE_DONE"
