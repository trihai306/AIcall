# Cho F5-TTS nap xong. KHONG duoc goi /api/tts truoc khi thay "loaded":
# model mat 2-3 phut moi nap, goi som thi luot do cam tieng va rat de tuong
# nham la giong moi hong.
param([int]$ToiDa = 300)
$het = (Get-Date).AddSeconds($ToiDa)
while ((Get-Date) -lt $het) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8100/health" -TimeoutSec 5
        $t = $r.tts
        if ($t -eq "loaded") {
            Write-Output "TTS: loaded  (sau $([math]::Round(($ToiDa - ($het - (Get-Date)).TotalSeconds)))s)"
            $r | ConvertTo-Json -Depth 3
            exit 0
        }
        Write-Output "  tts=$t ..."
    } catch {
        Write-Output "  backend chua tra loi ..."
    }
    Start-Sleep -Seconds 10
}
Write-Output "QUA GIO: TTS chua nap xong sau $ToiDa giay"
exit 1
