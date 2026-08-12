$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$noi = @(
  "$env:USERPROFILE\Desktop", "$env:USERPROFILE\Downloads",
  "$env:USERPROFILE\Documents", "$env:USERPROFILE\Music",
  "$env:USERPROFILE\OneDrive\Desktop", "C:\duan"
)

Write-Output "=== file WAV o cac thu muc nguoi dung ==="
foreach ($d in $noi) {
  if (Test-Path $d) {
    Get-ChildItem -Path $d -Filter *.wav -Recurse -ErrorAction SilentlyContinue -Depth 3 |
      Select-Object -First 40 |
      ForEach-Object {
        "{0,10:N0} KB  {1:yyyy-MM-dd}  {2}" -f ($_.Length/1KB), $_.LastWriteTime, $_.FullName
      }
  }
}

Write-Output ""
Write-Output "=== file co ten chua 'gio' / 'Heu' / 'hếu' (moi dinh dang) ==="
foreach ($d in $noi) {
  if (Test-Path $d) {
    Get-ChildItem -Path $d -Recurse -ErrorAction SilentlyContinue -Depth 3 |
      Where-Object { $_.Name -match 'gi[oọ]ng|H[eếề]u|heu' } |
      Select-Object -First 20 |
      ForEach-Object {
        "{0,10:N0} KB  {1:yyyy-MM-dd}  {2}" -f ($_.Length/1KB), $_.LastWriteTime, $_.FullName
      }
  }
}
