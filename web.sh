#!/usr/bin/env bash
# web.sh — mở giao diện web Auto Sub (tạo venv + Flask nếu cần)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
PORT="${PORT:-5005}"

if [[ ! -d .venv ]]; then
  echo "==> Tạo venv + cài Flask..."
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

# giải phóng cổng nếu còn server cũ đang chạy (tránh lỗi 404 do bản cũ)
lsof -ti tcp:"$PORT" 2>/dev/null | xargs kill 2>/dev/null || true

# --- VietTTS server cho tab "Đọc văn bản" (chạy nền) ---
VIETTTS_PORT="${VIETTTS_PORT:-8298}"
TTS_PID=""
if lsof -ti tcp:"$VIETTTS_PORT" >/dev/null 2>&1; then
  echo "==> VietTTS đã chạy sẵn ở cổng $VIETTTS_PORT"
elif [[ -x ./tts_server.sh ]]; then
  echo "==> Bật VietTTS server (nền, nạp model ~10s, log: tts_server.log)..."
  VIETTTS_PORT="$VIETTTS_PORT" ./tts_server.sh > tts_server.log 2>&1 &
  TTS_PID=$!
else
  echo "==> Bỏ qua VietTTS (không thấy ./tts_server.sh) — tab 'Đọc văn bản' sẽ báo cần bật server."
fi
# tắt VietTTS khi thoát web
cleanup() {
  [[ -n "$TTS_PID" ]] && kill "$TTS_PID" 2>/dev/null || true
  pkill -f "viettts server" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> Mở http://localhost:$PORT"
( sleep 1; open "http://localhost:$PORT" ) >/dev/null 2>&1 &
PORT="$PORT" .venv/bin/python -m webapp.server
