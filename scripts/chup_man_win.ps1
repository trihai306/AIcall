# Chup man hinh may Windows ra PNG, de xem tu xa qua SSH.
#
# Vi sao can: khong MCP nao trong phien nay nhin duoc man hinh may khac.
#   - computer-use  -> dieu khien man hinh MAC, khong phai Windows
#   - electron      -> chi do localhost:9222, ma app tren Win khong bat cong do
#   - browser tools -> chi thay trang web, khong thay desktop
# AnyDesk thi xem duoc nhung phai qua cua so tren Mac, cham va phu thuoc nguoi
# dung dang mo san.
#
# Cach nay chup thang tren may Windows roi keo file ve - nhanh, khong can ai bam
# gi, va thay duoc CA desktop chu khong rieng app.
#
# LUU Y: phai co phien desktop dang dang nhap. Chay qua SSH khi may dang khoa
# man hinh se ra anh den - do la gioi han cua Windows, khong phai loi script.
param(
    [string]$Out = "C:\duan\chat-ai\logs\man_hinh.png",
    # 0 = KHONG thu nho. Mac dinh phai la 0: thu nho lam toa do tren anh khac
    # toa do that, va moi lenh bam sau do deu lech ma khong co gi bao. Man
    # 1600x900 chup ra ~570KB - keo qua Tailscale trong 1-2 giay, khong dang
    # doi lay rui ro bam nham.
    # Doc kich thuoc that bang VirtualScreen QUA SSH la SAI: Session 0 bao
    # 1024x768 trong khi man that 1600x900. Chi doc duoc trong phien dang nhap.
    [int]$MaxWidth = 0
)
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$g.Dispose()

# Thu nho neu qua rong: anh 4K day du ~8MB, keo qua Tailscale lau ma khong them
# thong tin gi cho viec xem giao dien.
if ($MaxWidth -gt 0 -and $bmp.Width -gt $MaxWidth) {
    $ty = $MaxWidth / $bmp.Width
    $w = [int]$MaxWidth
    $h = [int]($bmp.Height * $ty)
    $nho = New-Object System.Drawing.Bitmap $w, $h
    $g2 = [System.Drawing.Graphics]::FromImage($nho)
    $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g2.DrawImage($bmp, 0, 0, $w, $h)
    $g2.Dispose()
    $bmp.Dispose()
    $bmp = $nho
}

New-Item -ItemType Directory -Force -Path (Split-Path $Out) | Out-Null
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$kt = $bmp.Size
$bmp.Dispose()

$f = Get-Item $Out
Write-Host ("  da chup {0}x{1} -> {2} ({3} KB)" -f $kt.Width, $kt.Height, $Out, [math]::Round($f.Length/1KB))
