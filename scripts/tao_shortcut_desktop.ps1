# =====================================================
# Tao loi tat VoiceBank AI ngoai Desktop.
#   .\scripts\tao_shortcut_desktop.ps1
#
# KHONG chep file exe ra Desktop. Ban portable nhan dien thu muc du an qua vi
# tri file exe goc (PORTABLE_EXECUTABLE_DIR), nen exe nam ngoai C:\duan\chat-ai
# la khong thay backend/ va .venv/ -> app vao thang trang loi. Loi tat thi tro
# nguoc ve exe goc nen van dung.
#
# Chay lai duoc nhieu lan (ghi de loi tat cu).
# =====================================================
param([string]$Ten = "VoiceBank AI")

$PROJECT = Split-Path -Parent $PSScriptRoot
$EXE     = "$PROJECT\VoiceBank-AI.exe"

if (-not (Test-Path $EXE)) {
    Write-Host "[LOI] Chua co $EXE - build truoc:"
    Write-Host "      cd $PROJECT\desktop ; npx electron-builder --win"
    Write-Host "      Copy-Item $PROJECT\dist\VoiceBank-AI.exe $EXE -Force"
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnk     = Join-Path $desktop "$Ten.lnk"

$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut($lnk)
$s.TargetPath       = $EXE
$s.WorkingDirectory = $PROJECT
$s.IconLocation     = $EXE
$s.Description      = "VoiceBank AI - he thong goi dien tu van (offline)"
$s.Save()

Write-Host "[OK] Da tao loi tat: $lnk"
Write-Host "     -> $EXE"
