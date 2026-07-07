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

echo "==> Mở http://localhost:$PORT"
( sleep 1; open "http://localhost:$PORT" ) >/dev/null 2>&1 &
PORT="$PORT" .venv/bin/python -m webapp.server
