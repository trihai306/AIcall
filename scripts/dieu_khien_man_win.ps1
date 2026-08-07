# Thao tac tren man hinh may Windows tu xa: bam chuot, go phim.
#
# Di kem chup_man_win.ps1 (xem man hinh). Hai script nay bu cho khoang trong ma
# khong MCP nao trong phien lap dat lap duoc:
#   - computer-use  -> dieu khien man hinh MAC, khong phai may Windows nay
#   - electron      -> chi do localhost:9222; app tren Win khong bat cong do
#   - browser tools -> chi thay trang web, khong thay desktop hay app native
#
# PHAI CHAY TRONG PHIEN DANG NHAP (Session 1). Chay thang qua SSH la Session 0 -
# phien dich vu, khong co desktop nao - va SendInput/CopyFromScreen deu bao
# "The handle is invalid". Dung schtasks /it de day sang phien nguoi dung.
#
#   .\dieu_khien_man_win.ps1 -Hanh bam  -X 500 -Y 300
#   .\dieu_khien_man_win.ps1 -Hanh go   -Text "xin chao"
#   .\dieu_khien_man_win.ps1 -Hanh phim -Text "{ENTER}"
param(
    [ValidateSet("bam", "bam2", "phai", "go", "phim", "chuot")]
    [string]$Hanh = "bam",
    [int]$X = 0,
    [int]$Y = 0,
    [string]$Text = ""
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms

# SendInput qua P/Invoke: [Forms.Cursor]::Position dat duoc con tro nhung KHONG
# sinh su kien bam. Nhieu app native bo qua ca WM_LBUTTONDOWN gui truc tiep, nen
# phai di duong SendInput cho giong chuot that.
if (-not ([System.Management.Automation.PSTypeName]'Chuot').Type) {
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class Chuot {
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
    public const uint TRAI_XUONG = 0x0002, TRAI_LEN = 0x0004;
    public const uint PHAI_XUONG = 0x0008, PHAI_LEN = 0x0010;
}
'@
}

switch ($Hanh) {
    "chuot" { [Chuot]::SetCursorPos($X, $Y) | Out-Null }
    "bam" {
        [Chuot]::SetCursorPos($X, $Y) | Out-Null
        Start-Sleep -Milliseconds 60
        [Chuot]::mouse_event([Chuot]::TRAI_XUONG, 0, 0, 0, [IntPtr]::Zero)
        [Chuot]::mouse_event([Chuot]::TRAI_LEN,   0, 0, 0, [IntPtr]::Zero)
    }
    "bam2" {
        [Chuot]::SetCursorPos($X, $Y) | Out-Null
        Start-Sleep -Milliseconds 60
        foreach ($i in 1..2) {
            [Chuot]::mouse_event([Chuot]::TRAI_XUONG, 0, 0, 0, [IntPtr]::Zero)
            [Chuot]::mouse_event([Chuot]::TRAI_LEN,   0, 0, 0, [IntPtr]::Zero)
            Start-Sleep -Milliseconds 50
        }
    }
    "phai" {
        [Chuot]::SetCursorPos($X, $Y) | Out-Null
        Start-Sleep -Milliseconds 60
        [Chuot]::mouse_event([Chuot]::PHAI_XUONG, 0, 0, 0, [IntPtr]::Zero)
        [Chuot]::mouse_event([Chuot]::PHAI_LEN,   0, 0, 0, [IntPtr]::Zero)
    }
    # SendKeys can THOAT cac ky tu dieu khien: + ^ % ~ ( ) { } [ ]
    # Khong thoat thi "100%" thanh phim tat Alt, va "a+b" thanh Shift.
    "go"   { [System.Windows.Forms.SendKeys]::SendWait(($Text -replace '([+^%~(){}\[\]])', '{$1}')) }
    "phim" { [System.Windows.Forms.SendKeys]::SendWait($Text) }
}
Write-Host ("  da lam: {0} {1}" -f $Hanh, $(if ($Text) { $Text } else { "$X,$Y" }))
