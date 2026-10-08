#!/usr/bin/env bash
# Nối PHIÊN ĐÁM MÂY (Claude Code trên web) tới máy Windows admin-pc, để chạy
# `ssh win ...` thẳng từ đám mây mà không phải đi vòng qua Mac.
#
# Cách hoạt động: container đám mây không nằm trong mạng Tailscale của bạn, nên
# script cài Tailscale ở chế độ userspace (không cần quyền tạo thiết bị mạng),
# vào tailnet bằng một khoá dùng một lần, rồi ghi sẵn `Host win` vào ~/.ssh.
# Đo thử: máy chủ điều khiển và DERP của Tailscale tới được từ container; UDP bị
# chặn nên mọi gói đi qua DERP (giống đường Mac -> Windows hiện tại, ~100-140ms).
#
# Script ĐỌC thông tin từ biến môi trường của môi trường đám mây (Edit môi
# trường -> Environment variables / Secrets). KHÔNG dán khoá vào chat, KHÔNG ghi
# khoá vào repo.
#   TS_AUTHKEY       khoá Tailscale: Ephemeral + Pre-approved + gắn tag riêng
#   WIN_SSH_USER     tên tài khoản Windows dùng để ssh (giống `User` của `Host win` trên Mac)
#   WIN_SSH_KEY_B64  khoá riêng ssh, mã hoá base64 một dòng
#   WIN_HOSTKEY      (tuỳ chọn) dòng known_hosts của admin-pc, để chốt đúng máy
#   WIN_HOST         (tuỳ chọn) mặc định 100.117.154.82
#
# Dùng:   scripts/cloud_noi_win.sh            # nối + kiểm `ssh win`
#         scripts/cloud_noi_win.sh tunnel     # nối + mở cổng 8100 về localhost
# Chạy lại bao nhiêu lần cũng được (không làm gì thừa nếu đã nối).
# Mã thoát: 0 nối được | 3 thiếu cấu hình | 4 không vào được tailnet | 5 ssh lỗi
set -uo pipefail

WIN_HOST="${WIN_HOST:-100.117.154.82}"
DIR="${HOME}/.cache/ccr-win"
SOCK="${DIR}/tailscaled.sock"
TS="${DIR}/bin/tailscale"
TSD="${DIR}/bin/tailscaled"
KEY="${HOME}/.ssh/id_ccr_win"
log() { echo "[noi-win] $*" >&2; }

thieu=()
for v in TS_AUTHKEY WIN_SSH_USER WIN_SSH_KEY_B64; do
  [ -n "${!v:-}" ] || thieu+=("$v")
done
if [ "${#thieu[@]}" -gt 0 ]; then
  log "chưa cấu hình, bỏ qua. Thiếu biến: ${thieu[*]}"
  exit 3
fi

mkdir -p "${DIR}/bin" "${HOME}/.ssh"; chmod 700 "${HOME}/.ssh"

# ---- 1. Cài Tailscale (bản tĩnh, một lần) và ssh client --------------------
if [ ! -x "$TS" ] || [ ! -x "$TSD" ]; then
  log "tải Tailscale ..."
  tarball=$(curl -fsS -m 30 "https://pkgs.tailscale.com/stable/?mode=json" |
    python3 -c "import sys,json; print(json.load(sys.stdin)['Tarballs']['amd64'])") || {
    log "không lấy được bản Tailscale mới nhất"; exit 4; }
  tmp=$(mktemp -d)
  curl -fsS -m 180 -o "$tmp/t.tgz" "https://pkgs.tailscale.com/stable/${tarball}" &&
    tar xzf "$tmp/t.tgz" -C "$tmp" &&
    cp "$tmp"/tailscale_*/tailscale "$tmp"/tailscale_*/tailscaled "${DIR}/bin/" || {
    log "tải/giải nén Tailscale lỗi"; rm -rf "$tmp"; exit 4; }
  rm -rf "$tmp"
fi
if ! command -v ssh >/dev/null 2>&1; then
  log "cài openssh-client ..."
  { apt-get update -qq && apt-get install -y -qq openssh-client; } >/dev/null 2>&1 ||
    { log "không cài được openssh-client"; exit 5; }
fi

# ---- 2. Chạy tailscaled (userspace) và vào tailnet -------------------------
if ! "$TS" --socket="$SOCK" version >/dev/null 2>&1 || [ ! -S "$SOCK" ]; then
  log "khởi động tailscaled (userspace) ..."
  # state=mem: nút này là tạm thời, mỗi phiên vào lại bằng khoá; không giữ danh tính cũ.
  nohup setsid "$TSD" --tun=userspace-networking --state=mem: \
    --socket="$SOCK" >"${DIR}/tailscaled.log" 2>&1 < /dev/null &
  for _ in $(seq 1 30); do [ -S "$SOCK" ] && break; sleep 0.5; done
  [ -S "$SOCK" ] || { log "tailscaled không lên, xem ${DIR}/tailscaled.log"; exit 4; }
fi

if ! "$TS" --socket="$SOCK" ip -4 >/dev/null 2>&1; then
  log "vào tailnet ..."
  # Khoá đưa qua tệp (quyền 600) để không lộ trong danh sách tiến trình.
  umask 077; printf '%s' "$TS_AUTHKEY" > "${DIR}/authkey"
  "$TS" --socket="$SOCK" up --auth-key="file:${DIR}/authkey" \
    --hostname="ccr-$(hostname | tr -cd 'a-z0-9-' | cut -c1-20)" \
    --accept-dns=false --accept-routes=false --shields-up --timeout=45s \
    >"${DIR}/up.log" 2>&1
  rc=$?; rm -f "${DIR}/authkey"
  if [ $rc -ne 0 ]; then
    log "không vào được tailnet (mã $rc): $(tail -n 3 "${DIR}/up.log" | tr '\n' ' ')"
    exit 4
  fi
fi

# ---- 3. Ghi cấu hình ssh ---------------------------------------------------
umask 077
printf '%s' "$WIN_SSH_KEY_B64" | base64 -d > "$KEY" 2>/dev/null || {
  log "WIN_SSH_KEY_B64 không giải mã được base64"; exit 3; }
[ -n "$(tail -c1 "$KEY")" ] && echo >> "$KEY"
chmod 600 "$KEY"

kh="${HOME}/.ssh/known_hosts_ccr_win"; strict="accept-new"
if [ -n "${WIN_HOSTKEY:-}" ]; then printf '%s\n' "$WIN_HOSTKEY" > "$kh"; strict="yes"; fi
cat > "${HOME}/.ssh/ccr_win_config" <<CFG
Host win
  HostName ${WIN_HOST}
  User ${WIN_SSH_USER}
  IdentityFile ${KEY}
  IdentitiesOnly yes
  ProxyCommand ${TS} --socket=${SOCK} nc %h %p
  UserKnownHostsFile ${kh}
  StrictHostKeyChecking ${strict}
  BatchMode yes
  ConnectTimeout 25
  ServerAliveInterval 30
CFG
if ! grep -qs 'ccr_win_config' "${HOME}/.ssh/config"; then
  { printf 'Include %s/.ssh/ccr_win_config\n' "$HOME"
    cat "${HOME}/.ssh/config" 2>/dev/null || true; } > "${HOME}/.ssh/config.new"
  mv "${HOME}/.ssh/config.new" "${HOME}/.ssh/config"
fi
chmod 600 "${HOME}/.ssh/config"

# ---- 4. Kiểm ---------------------------------------------------------------
if out=$(timeout 40 ssh win 'echo noi-win-ok' 2>&1) && printf '%s' "$out" | grep -q noi-win-ok; then
  log "ĐÃ NỐI: ssh win chạy được (${WIN_SSH_USER}@${WIN_HOST})"
else
  log "ssh win LỖI: $(printf '%s' "$out" | tail -n 3 | tr '\n' ' ')"
  log "gợi ý: máy Windows đang ngủ/tắt? khoá công khai đã có trong authorized_keys chưa?"
  exit 5
fi

if [ "${1:-}" = "tunnel" ]; then
  ssh -f -N -o ExitOnForwardFailure=yes -L 8100:127.0.0.1:8100 win 2>&1 |
    grep -v 'already in use' >&2
  log "cổng 8100: http://127.0.0.1:8100 (kiểm bằng /api/health)"
fi
exit 0
