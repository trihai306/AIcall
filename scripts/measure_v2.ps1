# =====================================================
# Do tai nguyen v2 - he thong DA WARM
#   1. Lay mau GPU/RAM lien tuc bang vong lap PowerShell (khong dung nvidia-smi -l)
#   2. Benchmark tuan tu (so lieu on dinh, khong dinh warmup)
#   3. Test DONG THOI 1/2/4/6 cuoc -> tra loi "may nay kham may cuoc goi song song"
# =====================================================
$ErrorActionPreference = "Continue"
$PROJECT = "C:\duan\chat-ai"
$LOGS    = "$PROJECT\logs"
$SAMP    = "$LOGS\samples.csv"
$BASE    = "http://localhost:8100"
Remove-Item $SAMP -EA SilentlyContinue

function GpuNow {
    $g = (nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw,temperature.gpu --format=csv,noheader,nounits) -split ',' | ForEach-Object { $_.Trim() }
    return @{ util=[int]$g[0]; vram=[int]$g[1]; pw=[double]$g[2]; temp=[int]$g[3] }
}
function RamNow {
    $os = Get-CimInstance Win32_OperatingSystem
    return [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/1MB, 2)
}
function StartSampler {
    return Start-Job -ScriptBlock {
        param($out)
        "t,util,vram,pw,temp,ram_gb,py_mb,ollama_mb" | Out-File $out -Encoding ascii
        while ($true) {
            $g = (nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw,temperature.gpu --format=csv,noheader,nounits) -split ',' | ForEach-Object { $_.Trim() }
            $os = Get-CimInstance Win32_OperatingSystem
            $ram = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory)/1MB,2)
            $py = [math]::Round((((Get-Process python -EA SilentlyContinue) | Measure-Object WorkingSet64 -Sum).Sum)/1MB)
            $ol = [math]::Round((((Get-Process ollama -EA SilentlyContinue) | Measure-Object WorkingSet64 -Sum).Sum)/1MB)
            "$(Get-Date -Format 'HH:mm:ss'),$($g[0]),$($g[1]),$($g[2]),$($g[3]),$ram,$py,$ol" | Out-File $out -Append -Encoding ascii
            Start-Sleep -Milliseconds 700
        }
    } -ArgumentList $SAMP
}

Write-Output "############ DO TAI NGUYEN v2 (he thong da warm) ############"
Write-Output "[$(Get-Date -Format 'HH:mm:ss')]"

# --- warm-up de loai bien dinh lan dau ---
Write-Output ""
Write-Output "--- Warm-up (bo qua ket qua) ---"
foreach ($e in @("rag","stt","llm","tts")) {
    try { Invoke-RestMethod -Uri "$BASE/api/benchmark/$e" -Method Post -TimeoutSec 180 | Out-Null } catch {}
}
Write-Output "warm-up xong"

$job = StartSampler
Start-Sleep -Seconds 4

$g0 = GpuNow; $r0 = RamNow
Write-Output ""
Write-Output "=== A. IDLE (da warm, khong tai) ==="
"  VRAM {0} MB | GPU {1}% | {2} W | {3} C | RAM {4} GB" -f $g0.vram,$g0.util,$g0.pw,$g0.temp,$r0

# --- B. tuan tu ---
Write-Output ""
Write-Output "=== B. BENCHMARK TUAN TU ==="
foreach ($e in @("rag","stt","llm","tts","full")) {
    try {
        $t0 = Get-Date
        $r = Invoke-RestMethod -Uri "$BASE/api/benchmark/$e" -Method Post -TimeoutSec 300
        $w = [math]::Round(((Get-Date)-$t0).TotalMilliseconds)
        $g = GpuNow
        switch ($e) {
            "rag"  { "  RAG   : {0,6} ms                        | VRAM {1} MB  GPU {2}%" -f $r.latency_ms,$g.vram,$g.util }
            "stt"  { "  STT   : {0,6} ms                        | VRAM {1} MB  GPU {2}%" -f $r.latency_ms,$g.vram,$g.util }
            "llm"  { "  LLM   : ttft {0,4} ms | full {1,5} ms | {2} tok/s | VRAM {3} MB  GPU {4}%" -f $r.ttft_ms,$r.total_ms,$r.tokens_per_sec,$g.vram,$g.util }
            "tts"  { "  TTS   : {0,6} ms (tb 3 cau)              | VRAM {1} MB  GPU {2}%" -f $r.avg_latency_ms,$g.vram,$g.util }
            "full" { "  FULL  : total {0} ms | TTFA {1} ms | target {2} ms | {3}" -f $r.summary.avg_total_ms,$r.summary.avg_ttfa_ms,$r.summary.target_ms,$r.summary.status
                     "          VRAM {0} MB  GPU {1}%  {2} W" -f $g.vram,$g.util,$g.pw }
        }
    } catch { "  {0} : LOI {1}" -f $e,$_.Exception.Message }
    Start-Sleep -Seconds 2
}

# --- C. dong thoi ---
Write-Output ""
Write-Output "=== C. TEST DONG THOI (/api/benchmark/full song song) ==="
Write-Output "  N = so cuoc chay cung luc | wall = thoi gian den khi ca N xong"
foreach ($N in @(1,2,4,6)) {
    $jobs = @()
    $t0 = Get-Date
    for ($i=0; $i -lt $N; $i++) {
        $jobs += Start-Job -ScriptBlock {
            param($u)
            try {
                $s = Get-Date
                $r = Invoke-RestMethod -Uri $u -Method Post -TimeoutSec 600
                return @{ ok=$true; ms=[math]::Round(((Get-Date)-$s).TotalMilliseconds); total=$r.summary.avg_total_ms; ttfa=$r.summary.avg_ttfa_ms }
            } catch { return @{ ok=$false; err=$_.Exception.Message } }
        } -ArgumentList "$BASE/api/benchmark/full"
    }
    # theo doi dinh trong luc chay
    $peakV = 0; $peakU = 0
    while ($jobs | Where-Object { $_.State -eq 'Running' }) {
        $g = GpuNow
        if ($g.vram -gt $peakV) { $peakV = $g.vram }
        if ($g.util -gt $peakU) { $peakU = $g.util }
        Start-Sleep -Milliseconds 400
    }
    $wall = [math]::Round(((Get-Date)-$t0).TotalMilliseconds)
    $res = $jobs | ForEach-Object { Receive-Job $_ }
    $jobs | Remove-Job -Force -EA SilentlyContinue
    $okr = @($res | Where-Object { $_.ok })
    if ($okr.Count -gt 0) {
        $avgT = [math]::Round((($okr | ForEach-Object { [double]$_.total }) | Measure-Object -Average).Average)
        $avgF = [math]::Round((($okr | ForEach-Object { [double]$_.ttfa }) | Measure-Object -Average).Average)
        "  N={0} : wall {1,6} ms | total/cuoc {2,5} ms | TTFA {3,4} ms | dinh VRAM {4} MB | dinh GPU {5}% | ok {6}/{7}" -f $N,$wall,$avgT,$avgF,$peakV,$peakU,$okr.Count,$N
    } else {
        "  N={0} : THAT BAI het - {1}" -f $N, ($res | Select-Object -First 1).err
    }
    Start-Sleep -Seconds 3
}

# --- D. tong ket ---
Stop-Job $job -EA SilentlyContinue; Receive-Job $job -EA SilentlyContinue | Out-Null; Remove-Job $job -Force -EA SilentlyContinue
Write-Output ""
Write-Output "=== D. TONG KET TU MAU LIEN TUC ==="
if (Test-Path $SAMP) {
    $s = Import-Csv $SAMP
    "  So mau      : {0}" -f $s.Count
    "  VRAM  idle/dinh : {0} / {1} MB  (tren tong 12227 MB)" -f (($s | ForEach-Object {[int]$_.vram}) | Measure-Object -Minimum).Minimum, (($s | ForEach-Object {[int]$_.vram}) | Measure-Object -Maximum).Maximum
    "  GPU%  tb/dinh   : {0} / {1} %" -f [math]::Round((($s | ForEach-Object {[int]$_.util}) | Measure-Object -Average).Average), (($s | ForEach-Object {[int]$_.util}) | Measure-Object -Maximum).Maximum
    "  Dien  tb/dinh   : {0} / {1} W" -f [math]::Round((($s | ForEach-Object {[double]$_.pw}) | Measure-Object -Average).Average,1), (($s | ForEach-Object {[double]$_.pw}) | Measure-Object -Maximum).Maximum
    "  Nhiet dinh      : {0} C" -f (($s | ForEach-Object {[int]$_.temp}) | Measure-Object -Maximum).Maximum
    "  RAM   idle/dinh : {0} / {1} GB  (tren tong 61.65 GB)" -f (($s | ForEach-Object {[double]$_.ram_gb}) | Measure-Object -Minimum).Minimum, (($s | ForEach-Object {[double]$_.ram_gb}) | Measure-Object -Maximum).Maximum
    "  RAM python dinh : {0} MB" -f (($s | ForEach-Object {[int]$_.py_mb}) | Measure-Object -Maximum).Maximum
    "  RAM ollama dinh : {0} MB" -f (($s | ForEach-Object {[int]$_.ollama_mb}) | Measure-Object -Maximum).Maximum
}
Write-Output ""
Write-Output "MARKER_V2_DONE"
