param([int]$ToiDa = 280)
$het = (Get-Date).AddSeconds($ToiDa)
while ((Get-Date) -lt $het) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8100/api/health" -TimeoutSec 5
        if ($r.services.tts -eq "loaded") {
            Write-Output "SAN SANG - tts=loaded stt=$($r.services.stt) llm=$($r.services.llm)"
            exit 0
        }
        Write-Output "  tts=$($r.services.tts) ..."
    } catch { Write-Output "  dang khoi dong ..." }
    Start-Sleep -Seconds 8
}
Write-Output "QUA GIO"
exit 1
