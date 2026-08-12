Write-Output "=== Su kien ung dung sap 30 phut qua ==="
$tu = (Get-Date).AddMinutes(-30)
Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$tu} -ErrorAction SilentlyContinue |
  Where-Object { $_.Id -in 1000,1001,1026 -or $_.Message -match 'python' } |
  Select-Object -First 5 |
  ForEach-Object {
      Write-Output "--- $($_.TimeCreated)  Id=$($_.Id)  $($_.ProviderName)"
      Write-Output ($_.Message -split "`n" | Select-Object -First 12 | Out-String)
  }
