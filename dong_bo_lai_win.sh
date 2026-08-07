#!/bin/bash
# Đẩy lại các file đã sửa lên máy Windows sau khi nó rớt mạng giữa chừng.
# Máy Windows offline lúc sửa xong nên chưa chắc bản trên đó là mới nhất.
#
#   bash dong_bo_lai_win.sh
set -e
cd "$(dirname "$0")"

FILES=(
  scripts/check_vocab.py
  scripts/pick_ref.py
  scripts/reset_update.py
  scripts/test_voice.py
  scripts/stoptrain.py
  training/voice/train.ps1
  training/voice/train.sh
  backend/pipeline/text_normalizer.py
)

echo "Chờ admin-pc lên mạng ..."
until ping -c 1 -W 4000 100.117.154.82 >/dev/null 2>&1; do sleep 10; done
echo "  đã thấy máy"

for f in "${FILES[@]}"; do
  scp -q "$f" "win:C:/duan/chat-ai/$f" && echo "  gửi $f"
done

echo
echo "Khởi động lại backend để nạp text_normalizer mới:"
echo "  ssh win 'powershell -ExecutionPolicy Bypass -File C:\\duan\\chat-ai\\scripts\\start_services.ps1'"
echo "Rồi đo lại:"
echo "  ssh win 'C:\\duan\\chat-ai\\.venv\\python.exe C:\\duan\\chat-ai\\scripts\\test_voice.py --runs 4 --fast'"
