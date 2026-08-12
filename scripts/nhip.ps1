# Do nhip train THAT SU: dem so update tang trong N giay.
# Khong dung con so s/update cua tqdm - do la trung binh truot, khong phai nhip that.
param([int]$Giay = 120)
$LOG = "C:\duan\chat-ai\logs\train_giong_giong_nam.log"

function Lay-Update {
    $m = Select-String -Path $LOG -Pattern "update=(\d+)" -AllMatches | Select-Object -Last 1
    if ($null -eq $m) { return -1 }
    return [int]$m.Matches[-1].Groups[1].Value
}

$a = Lay-Update
$t = Get-Date
$v0 = (nvidia-smi --query-gpu=power.draw,memory.free --format=csv,noheader)
Start-Sleep -Seconds $Giay
$b = Lay-Update
$w = ((Get-Date) - $t).TotalSeconds
$v1 = (nvidia-smi --query-gpu=power.draw,memory.free --format=csv,noheader)

$d = $b - $a
if ($d -le 0) {
    Write-Output "KHONG TIEN: van o update=$b sau $([math]::Round($w))s"
} else {
    $sPerUpd = [math]::Round($w / $d, 2)
    Write-Output "update $a -> $b  ($d buoc / $([math]::Round($w))s)  =  $sPerUpd s/update"
}
Write-Output "GPU truoc: $v0"
Write-Output "GPU sau  : $v1"
