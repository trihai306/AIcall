$OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output "=== tien trinh python + dong lenh ==="
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Select-Object ProcessId,
    @{n="Bat_dau";e={$_.CreationDate}},
    @{n="Lenh";e={ if ($_.CommandLine) { $_.CommandLine.Substring(0, [Math]::Min(110, $_.CommandLine.Length)) } else { "(khong doc duoc)" } }} |
  Sort-Object Bat_dau |
  Format-Table -AutoSize -Wrap | Out-String -Width 200
