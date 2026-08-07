#!/bin/bash
# Chạy nốt các phép đo còn dở khi máy Windows lên lại.
set -e
cd "$(dirname "$0")"

echo "Chờ admin-pc lên mạng ..."
until ping -c 1 -W 4000 100.117.154.82 >/dev/null 2>&1; do sleep 10; done
echo "  đã thấy máy"

for f in backend/config.py backend/services/phone_call_service.py \
         scripts/kiem_volte.py scripts/cham_lam_sach.py \
         scripts/do_kim_loai.py scripts/so_giong_thoai.py scripts/nguoi_that_vs_tts.py; do
  scp -q "$f" "win:C:/duan/chat-ai/$f" && echo "  gửi $f"
done

echo
echo "1) Máy phone farm có gọi được VoLTE (AMR-WB 16kHz) không:"
ssh win 'chcp 65001 > $null; $env:PYTHONUTF8="1"; C:\duan\chat-ai\.venv\python.exe C:\duan\chat-ai\scripts\kiem_volte.py'

echo
echo "2) Bộ làm sạch có nâng được HNR không:"
ssh win 'chcp 65001 > $null; $env:PYTHONUTF8="1"; $env:PATH="C:\ffmpeg-shared\bin;$env:PATH"; cd C:\duan\chat-ai; C:\duan\chat-ai\.venv\python.exe scripts\cham_lam_sach.py'
