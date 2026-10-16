#!/bin/bash
# Phiên đám mây: tự nối tới máy Windows admin-pc nếu môi trường có đủ biến
# (TS_AUTHKEY, WIN_SSH_USER, WIN_SSH_KEY_B64). Thiếu thì lặng lẽ bỏ qua; có lỗi
# cũng không làm hỏng phiên. Chi tiết: scripts/cloud_noi_win.sh
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
"${CLAUDE_PROJECT_DIR:-.}/scripts/cloud_noi_win.sh" || true
exit 0
