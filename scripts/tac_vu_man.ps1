# Bo dieu phoi cho tac vu dinh thoi: doc lenh tu TEP roi thuc hien.
#
# Vi sao qua tep chu khong qua tham so: `schtasks /tr` phai boc lenh trong dau
# nhay, ma lenh PowerShell ben trong lai can dau nhay cua no, roi ca chuoi con
# di qua SSH va qua bash tren Mac - bon tang trich dan long nhau. Da thu va no
# hong ngay lan dau. Dat lenh vao tep thi tac vu chi con MOT chuoi co dinh,
# khong con tang trich dan nao.
#
# Tep lenh: logs\_man_lenh.txt, mot dong duy nhat, cac truong cach nhau bang TAB
#   chup
#   bam<TAB>500<TAB>300
#   go<TAB>xin chao
#   phim<TAB>{ENTER}
#   chay                      <- chay logs\_man_ps.ps1 trong Session 1
#
# Vi sao can `chay`: nhieu viec doi DESKTOP chu khong chi doi quyen - liet ke cua
# so dang mo, dua mot cua so len truoc, hay quay man hinh bang ffmpeg gdigrab.
# Hoi tu Session 0 (SSH) thi Get-Process tra ve MainWindowTitle RONG het, con
# gdigrab bao khong co man hinh. Nen phai day ca doan script sang day chay.
$ErrorActionPreference = "Continue"
$goc = Split-Path -Parent $PSScriptRoot
$tep = Join-Path $goc "logs\_man_lenh.txt"
$ket = Join-Path $goc "logs\_man_ket.txt"

if (-not (Test-Path $tep)) {
    "khong co tep lenh" | Set-Content -Path $ket -Encoding utf8
    exit 1
}

$dong = (Get-Content $tep -Raw -Encoding utf8).Trim()
$p = $dong -split "`t"
$hanh = $p[0]

try {
    if ($hanh -eq "chup") {
        & (Join-Path $PSScriptRoot "chup_man_win.ps1") *>&1 | Out-String | Set-Content -Path $ket -Encoding utf8
    }
    elseif ($hanh -in @("bam", "bam2", "phai", "chuot")) {
        & (Join-Path $PSScriptRoot "dieu_khien_man_win.ps1") -Hanh $hanh `
            -X ([int]$p[1]) -Y ([int]$p[2]) *>&1 | Out-String | Set-Content -Path $ket -Encoding utf8
    }
    elseif ($hanh -in @("go", "phim")) {
        & (Join-Path $PSScriptRoot "dieu_khien_man_win.ps1") -Hanh $hanh `
            -Text $p[1] *>&1 | Out-String | Set-Content -Path $ket -Encoding utf8
    }
    elseif ($hanh -eq "chay") {
        # Script nam o tep rieng chu khong nhet vao dong lenh: noi dung co xuong
        # dong va dau nhay, ma tep lenh chi mot dong tach bang TAB.
        $ps = Join-Path $goc "logs\_man_ps.ps1"
        if (-not (Test-Path $ps)) { "khong co tep script" | Set-Content -Path $ket -Encoding utf8 }
        else { & powershell -ExecutionPolicy Bypass -File $ps *>&1 |
               Out-String | Set-Content -Path $ket -Encoding utf8 }
    }
    else {
        "khong hieu hanh dong: $hanh" | Set-Content -Path $ket -Encoding utf8
    }
} catch {
    ("LOI: " + $_.Exception.Message) | Set-Content -Path $ket -Encoding utf8
}
