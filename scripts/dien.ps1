# Tim nguon doc dien nang thuc te. Windows KHONG co san API doc W cua CPU
# (khac Linux co RAPL qua powercap), nen phai muon phan mem cam bien.
foreach ($ns in "root\LibreHardwareMonitor","root\OpenHardwareMonitor") {
    try {
        $s = Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction Stop |
             Where-Object { $_.SensorType -eq "Power" }
        if ($s) {
            Write-Output "--- $ns ---"
            $s | ForEach-Object { Write-Output ("  {0,-28} {1} W" -f $_.Name, [math]::Round($_.Value,1)) }
        }
    } catch { Write-Output "khong co: $ns" }
}

Write-Output "--- phan mem cam bien dang chay ---"
Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match "HWiNFO|LibreHardware|OpenHardware|HWMonitor|JONSBO|Jungle|Armoury|Ryzen" } |
    Select-Object -ExpandProperty ProcessName -Unique |
    ForEach-Object { Write-Output "  $_" }

Write-Output "--- pin / UPS (neu co, doc duoc W thuc) ---"
$b = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
if ($b) { $b | Format-List Name,EstimatedChargeRemaining } else { Write-Output "  khong co (may ban)" }
