# Do chat luong ZipVoice theo tung bo tham so sinh.
# Lan chay dau dung mac dinh (guidance 1.0) cho ra tieng vo nghia -> nghi ngo
# mac dinh do danh cho ban distill chu khong phai ban thuong.
$PY   = "C:\duan\chat-ai\.venv\python.exe"
$MDIR = "C:\duan\chat-ai\models\tts\ZipVoice-Vietnamese-2500h"
Set-Location "C:\duan\chat-ai\tools\ZipVoice"

$bo = @(
    @{ step = 16; guid = 3.0 },
    @{ step = 8;  guid = 3.0 },
    @{ step = 16; guid = 1.0 }
)
foreach ($b in $bo) {
    $out = "C:\duan\chat-ai\logs\zv_s$($b.step)_g$($b.guid -replace '\.','')"
    $t0 = Get-Date
    & $PY -m zipvoice.bin.infer_zipvoice `
        --model-name zipvoice --model-dir $MDIR `
        --checkpoint-name iter-525000-avg-2.pt `
        --tokenizer espeak --lang vi `
        --num-step $b.step --guidance-scale $b.guid `
        --test-list "C:\duan\chat-ai\logs\zv_6.tsv" --res-dir $out *> $null
    $ms = ((Get-Date) - $t0).TotalMilliseconds
    "num-step={0,-3} guidance={1,-4} -> {2:N0} ms tong ({3:N0} ms/cau ke ca nap)  -> {4}" -f `
        $b.step, $b.guid, $ms, ($ms/6), (Split-Path $out -Leaf)
}
