#!/usr/bin/env bash
# Dua 1 file audio vao thu muc nghe/ de nghe tren dien thoai.
#
#   scripts/gui_nghe.sh C:/duan/chat-ai/tmp_la.wav "giong A, nfe 12, toc 0.90"
#   scripts/gui_nghe.sh ./ket_qua.wav "ban goc chua nen"
#
# Duong dan bat dau bang C:/ hoac C:\ thi keo tu may Windows (ssh win) ve.
set -euo pipefail

GOC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NGHE="$GOC/nghe"
CONG="${CONG_NGHE:-8123}"

if [[ $# -lt 1 ]]; then
  echo "Dung: $0 <duong-dan-file> [nhan mo ta]" >&2
  exit 1
fi

NGUON="$1"
NHAN="${2:-}"
mkdir -p "$NGHE"

# Ten dat theo gio de trang xep dung thu tu va khong de len file cu.
DUOI="${NGUON##*.}"
[[ "$DUOI" == "$NGUON" || ${#DUOI} -gt 5 ]] && DUOI="wav"
if [[ -n "$NHAN" ]]; then
  # Bo dau tieng Viet va ky tu la, chi giu chu-so-gach de an toan trong URL.
  SLUG=$(printf '%s' "$NHAN" | iconv -f utf-8 -t ascii//TRANSLIT 2>/dev/null || printf '%s' "$NHAN")
  # sed -E chu khong phai sed thuong: ban BSD tren macOS khong hieu \+
  SLUG=$(printf '%s' "$SLUG" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' | cut -c1-40)
else
  SLUG=$(basename "$NGUON" | sed -E 's/\.[^.]*$//' | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' | cut -c1-40)
fi
SLUG=$(printf '%s' "$SLUG" | sed -E 's/-+$//')
TEN="$(date +%Y%m%d-%H%M%S)_${SLUG:-audio}.${DUOI}"
DICH="$NGHE/$TEN"

if [[ "$NGUON" =~ ^[A-Za-z]:[/\\] ]]; then
  # scp doi duong dan kieu Unix; doi \ thanh / roi boc nhay cho khoang trang.
  DUONG_WIN="${NGUON//\\//}"
  scp -q "win:${DUONG_WIN}" "$DICH"
else
  cp "$NGUON" "$DICH"
fi

[[ -s "$DICH" ]] || { echo "LOI: keo ve duoc file rong -> $DICH" >&2; rm -f "$DICH"; exit 1; }
[[ -n "$NHAN" ]] && printf '%s\n' "$NHAN" > "$DICH.txt"

TS=$(/Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4 2>/dev/null | head -1 || true)
echo "Da dua vao: nghe/$TEN  ($(du -h "$DICH" | cut -f1))"
[[ -n "$TS" ]] && echo "Mo tren dien thoai: http://$TS:$CONG"
exit 0
