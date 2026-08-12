# Ai dang ngon CPU: tien trinh chinh hay cac worker nap du lieu?
# Doc CPU tich luy hai lan cach nhau N giay roi lay hieu - con so .CPU mot lan
# la vo nghia vi worker bi sinh lai moi epoch nen bo dem tu reset.
param([int]$Giay = 30)

$truoc = @{}
Get-Process python -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "C:\duan\chat-ai*" } |
    ForEach-Object { $truoc[$_.Id] = $_.CPU }

$t = Get-Date
Start-Sleep -Seconds $Giay
$w = ((Get-Date) - $t).TotalSeconds

Get-Process python -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "C:\duan\chat-ai*" } |
    ForEach-Object {
        $cu = if ($truoc.ContainsKey($_.Id)) { $truoc[$_.Id] } else { 0 }
        $pct = [math]::Round(($_.CPU - $cu) / $w * 100, 1)
        $ram = [math]::Round($_.WorkingSet64 / 1MB)
        Write-Output ("pid {0,-7} CPU {1,6}% mot loi   RAM {2,6} MB" -f $_.Id, $pct, $ram)
    }
Write-Output ("So loi CPU may nay: {0}" -f [Environment]::ProcessorCount)
