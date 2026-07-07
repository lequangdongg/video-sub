#!/usr/bin/env bash
#
# tts_server.sh — chạy VietTTS server (OpenAI-compatible) để app gọi đọc text -> giọng nói.
#   App (webapp) và VietTTS chạy 2 venv Python khác nhau nên giao tiếp qua HTTP.
#
#   ./tts_server.sh                         # http://127.0.0.1:8298
#   VIETTTS_PORT=8300 ./tts_server.sh       # đổi cổng
#   VIETTTS_HOME=/path/viet-tts ./tts_server.sh   # nếu cài viet-tts ở nơi khác
#
# Bật cái này TRƯỚC, rồi mới dùng tab "Đọc văn bản" trong web.
set -euo pipefail

VIETTTS_HOME="${VIETTTS_HOME:-/Users/dongquang/Desktop/viet-tts}"
PORT="${VIETTTS_PORT:-8298}"

if [[ ! -x "$VIETTTS_HOME/.venvuv/bin/viettts" ]]; then
  echo "!! Không thấy VietTTS ở: $VIETTTS_HOME"
  echo "   Đặt biến VIETTTS_HOME trỏ đúng thư mục viet-tts, hoặc cài lại."
  exit 1
fi

cd "$VIETTTS_HOME"
# gunicorn nằm trong .venvuv/bin nên phải cho vào PATH (server shell ra lệnh gunicorn)
export PATH="$PWD/.venvuv/bin:$HOME/.local/bin:$PATH"
export PYTORCH_ENABLE_MPS_FALLBACK=1   # nhiều op chưa hỗ trợ MPS -> rớt về CPU
export HF_HUB_DISABLE_TELEMETRY=1

echo "==> VietTTS server:  http://127.0.0.1:$PORT   (nạp model ~10s lần đầu)"
echo "    Dừng: Ctrl+C"
exec .venvuv/bin/viettts server --host 127.0.0.1 --port "$PORT"
