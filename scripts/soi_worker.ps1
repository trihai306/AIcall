Write-Output "=== TAT CA tien trinh python (ke ca ngoai thu muc du an) ==="
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  ForEach-Object {
      Write-Output ("  pid {0,-7} cha {1,-7} RAM {2,6} MB" -f $_.ProcessId, $_.ParentProcessId, [math]::Round($_.WorkingSetSize/1MB))
  }

Write-Output ""
Write-Output "=== trainer.train() nhan nhung tham so gi ==="
$T = "C:\duan\chat-ai\tools\F5-TTS-Vietnamese\src\f5_tts\model\trainer.py"
$n = (Select-String -Path $T -Pattern 'def train\(').LineNumber
if ($n) { Get-Content $T | Select-Object -Skip ($n-1) -First 12 | ForEach-Object { Write-Output "  $_" } }

Write-Output ""
Write-Output "=== DataLoader duoc dung the nao ==="
Select-String -Path $T -Pattern 'DataLoader\(|num_workers|persistent_workers|pin_memory|preprocessed_mel|mel_spectrogram' |
    ForEach-Object { Write-Output ("  {0}: {1}" -f $_.LineNumber, $_.Line.Trim()) }
