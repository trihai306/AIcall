# Do toc do ZipVoice tieng Viet, tach chi phi nap model ra khoi chi phi moi cau.
# Chay 1 cau va 6 cau, hieu so chia 5 = chi phi thuc cua moi cau.
$ErrorActionPreference = "Continue"
$PY   = "C:\duan\chat-ai\.venv\python.exe"
$MDIR = "C:\duan\chat-ai\models\tts\ZipVoice-Vietnamese-2500h"
Set-Location "C:\duan\chat-ai\tools\ZipVoice"

function Chay($tsv, $out) {
    $t0 = Get-Date
    & $PY -m zipvoice.bin.infer_zipvoice `
        --model-name zipvoice --model-dir $MDIR `
        --checkpoint-name iter-525000-avg-2.pt `
        --tokenizer espeak --lang vi `
        --test-list "C:\duan\chat-ai\logs\$tsv" `
        --res-dir "C:\duan\chat-ai\logs\$out" *> $null
    return ((Get-Date) - $t0).TotalMilliseconds
}

Chay "zv_1.tsv" "zv_warm" | Out-Null        # lam am
$t1 = Chay "zv_1.tsv" "zv_out1"
$t6 = Chay "zv_6.tsv" "zv_out6"

$nap  = (6*$t1 - $t6) / 5
$moi  = ($t6 - $t1) / 5
"1 cau : {0:N0} ms" -f $t1
"6 cau : {0:N0} ms" -f $t6
""
"chi phi nap model : {0:N0} ms" -f $nap
"CHI PHI MOI CAU   : {0:N0} ms" -f $moi
""
"--- file da sinh ---"
Get-ChildItem "C:\duan\chat-ai\logs\zv_out6" -Filter *.wav | ForEach-Object { "  {0}  {1:N0} bytes" -f $_.Name, $_.Length }
