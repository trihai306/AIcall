# In DUY NHAT mot tu: XONG | DANGCHAY | DUNG
# Viet thanh file rieng thay vi nhet vao -Command qua ssh: ngoac long ba lop
# (bash -> ssh -> powershell) tung nuot mat dau thoat, tra ve chuoi rong, va
# ben goi tuong nham la job da gay.
$ck = "C:\duan\chat-ai\models\tts\finetuned\giong_nam\model_last.pt"
if (Test-Path $ck) { Write-Output "XONG"; exit 0 }

$q = & schtasks /query /tn chatai_train_giong_nam /fo list 2>&1
if (($q -join " ") -match "Running") { Write-Output "DANGCHAY" } else { Write-Output "DUNG" }
