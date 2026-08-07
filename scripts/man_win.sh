#!/bin/bash
# Xem va thao tac man hinh may Windows tu Mac.
#
# Vi sao can: khong MCP nao trong phien nay nhin duoc man hinh may KHAC.
#   computer-use  -> dieu khien man hinh MAC
#   electron      -> chi do localhost:9222, app tren Win khong bat cong do
#   browser tools -> chi thay trang web, khong thay desktop / app native
#   AnyDesk       -> xem duoc, nhung qua cua so tren Mac, cham, va phu thuoc
#                    nguoi dung dang mo san phien ket noi
#
# HAI BAY DA MAC:
#  1. Chay thang qua SSH la Session 0 - phien dich vu, KHONG CO DESKTOP - nen
#     CopyFromScreen va SendInput deu bao "The handle is invalid". Phai day sang
#     phien dang nhap bang `schtasks /it`.
#  2. Truyen lenh qua `schtasks /tr` la bon tang trich dan long nhau (bash -> ssh
#     -> schtasks -> powershell) va hong ngay. Nen tac vu chi co MOT lenh co
#     dinh, con tham so ghi vao tep logs\_man_lenh.txt.
#
#   scripts/man_win.sh chup            -> chup man, keo ve Mac, in duong dan
#   scripts/man_win.sh bam 500 300
#   scripts/man_win.sh go "xin chao"
#   scripts/man_win.sh phim "{ENTER}"
set -e

TASK="VoiceBankMan"
LENH_WIN='C:\duan\chat-ai\logs\_man_lenh.txt'
RA="${TMPDIR:-/tmp}/man_hinh_win.png"

# Tao tac vu neu chua co. Lenh co dinh, khong tham so -> khong trich dan long.
ssh -o ConnectTimeout=25 win "
if (-not (schtasks /query /tn '$TASK' 2>\$null)) {
  schtasks /create /tn '$TASK' /tr 'powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\duan\chat-ai\scripts\tac_vu_man.ps1' /sc once /st 00:00 /ru Admin /it /f | Out-Null
}" >/dev/null 2>&1 || true

hanh="${1:-chup}"
case "$hanh" in
  chup)                 dong="chup" ;;
  bam|bam2|phai|chuot)  dong=$(printf '%s\t%s\t%s' "$hanh" "${2:-0}" "${3:-0}") ;;
  go|phim)              dong=$(printf '%s\t%s' "$hanh" "${2:-}") ;;
  # chay <tep.ps1 tren Mac> -> day script sang Session 1 roi chay o do.
  # Can cho nhung viec doi DESKTOP: liet ke cua so, dua cua so len truoc, quay
  # man hinh bang ffmpeg. Hoi tu Session 0 thi MainWindowTitle rong het.
  chay)
    [ -f "${2:-}" ] || { echo "  thieu tep script: man_win.sh chay duong/dan.ps1"; exit 1; }
    ps64=$(base64 < "$2" | tr -d '\n')
    ssh -o ConnectTimeout=25 win "[IO.File]::WriteAllBytes('C:\duan\chat-ai\logs\_man_ps.ps1', [Convert]::FromBase64String('$ps64'))" >/dev/null
    dong="chay" ;;
  *) echo "  dung: man_win.sh {chup|bam X Y|bam2 X Y|phai X Y|chuot X Y|go 'chu'|phim '{ENTER}'|chay tep.ps1}"; exit 1 ;;
esac

# Ghi tep lenh bang base64: chuoi tieng Viet di qua SSH roi PowerShell bi hong
# dau o nhieu tang, con base64 thi chi co ky tu ASCII an toan.
b64=$(printf '%s' "$dong" | base64 | tr -d '\n')
# PHAI CHO TEP KET QUA MOI, khong ngu co dinh roi doc: chup man mat lau hon 1.5s
# nen doc som ra ket qua cua LAN CHAY TRUOC. Da mac - no in "1600x900" trong khi
# anh vua chup la 1920x1080, va toa do bam theo do lech het.
ssh -o ConnectTimeout=30 win "
\$ket = 'C:\duan\chat-ai\logs\_man_ket.txt'
\$truoc = if (Test-Path \$ket) { (Get-Item \$ket).LastWriteTimeUtc } else { [datetime]::MinValue }
[IO.File]::WriteAllBytes('$LENH_WIN', [Convert]::FromBase64String('$b64'))
schtasks /run /tn '$TASK' | Out-Null
foreach (\$i in 1..60) {
  Start-Sleep -Milliseconds 250
  if ((Test-Path \$ket) -and (Get-Item \$ket).LastWriteTimeUtc -gt \$truoc) { break }
}
Get-Content \$ket -Raw -EA SilentlyContinue
" 2>/dev/null | sed 's/^/  /' | grep -v '^\s*$' || true

if [ "$hanh" = "chup" ]; then
  scp -q "win:C:/duan/chat-ai/logs/man_hinh.png" "$RA"
  echo "  $RA"
fi
