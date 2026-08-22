#!/bin/bash
# Cài tính năng SỬA LỜI đoạn mẫu lên máy Windows admin-pc, rồi tự đo xem có ăn không.
#
#   bash cai_sua_loi_len_win.sh
#
# Chạy TRÊN MÁY MAC. Máy Windows không có git, nên đồng bộ là việc thủ công -
# xem `dong_bo_lai_win.sh` cùng thư mục, script này làm y hệt cho lần sửa này.
set -e
cd "$(dirname "$0")"

WIN_IP=100.117.154.82
GOC=http://127.0.0.1:8100

# Chỉ ba file. KHÔNG đẩy .env (Windows là PORT=8100, đè bằng bản Mac là mất web),
# .venv (torch CUDA riêng), models/ (5.3GB), data/ hay logs/ (dữ liệu chạy thật).
FILES=(
  backend/api/voices.py
  frontend/app.js
  scripts/kiem_sua_loi.py
)

echo "Chờ admin-pc lên mạng ..."
until ping -c 1 -W 4000 "$WIN_IP" >/dev/null 2>&1; do sleep 10; done
echo "  đã thấy máy"

# Tunnel để gọi HTTP như localhost. Báo "Address already in use" là đã có sẵn -
# tin tốt, đi tiếp.
ssh -f -N -o ExitOnForwardFailure=yes -L 8100:127.0.0.1:8100 win 2>/dev/null || true

echo
echo "Đẩy file:"
for f in "${FILES[@]}"; do
  scp -q "$f" "win:C:/duan/chat-ai/$f" && echo "  gửi $f"
done

# `start_services.ps1` BỎ QUA tiến trình đang chạy, nên gọi start không thôi là
# không nạp code mới - bắt buộc stop trước. Đây đúng là cách hỏng hay mắc nhất:
# sửa xong thấy hành vi y như cũ rồi đi tìm lỗi ở chỗ khác.
echo
echo "Khởi động lại dịch vụ (nạp backend mới, ~60-90 giây) ..."
ssh win 'cd C:\duan\chat-ai; .\scripts\stop_services.ps1; .\scripts\start_services.ps1 -Detached'

printf "Chờ backend sống lại "
for _ in $(seq 1 40); do
  if curl -s -m 5 "$GOC/api/health" >/dev/null 2>&1; then echo " xong"; break; fi
  printf "."; sleep 5
done
curl -s -m 10 "$GOC/api/health" || { echo; echo "Backend chưa lên. Xem log:"; \
  echo "  ssh win 'Get-Content C:\\duan\\chat-ai\\logs\\backend.log -Tail 40'"; exit 1; }

echo
echo "=== Đo xem sửa lời có ăn không ==="
python3 scripts/kiem_sua_loi.py --goc "$GOC"
