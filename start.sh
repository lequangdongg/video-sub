#!/usr/bin/env bash
# start.sh — chạy tất cả trong 1 lệnh:
#   1) chuẩn bị venv (nếu cần)
#   2) xử lý sẵn các video đang nằm trong input/ bằng run.sh (nếu có)
#   3) bật web server + mở trình duyệt
#
#   ./start.sh              # xử lý input/ rồi mở web
#   SKIP_BATCH=1 ./start.sh # bỏ qua bước xử lý input/, mở web luôn
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
PORT="${PORT:-5005}"

# 1) venv
if [[ ! -d .venv ]]; then
  echo "==> Tạo venv + cài Flask..."
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

# 2) xử lý sẵn video trong input/ (CLI) — chạy trước, tránh giành CPU với web
shopt -s nullglob nocaseglob
PENDING=(input/*.{mp4,mkv,mov,avi,webm,m4v,flv,wmv})
shopt -u nullglob nocaseglob
if [[ "${SKIP_BATCH:-0}" != "1" && ${#PENDING[@]} -gt 0 ]]; then
  echo "==> Có ${#PENDING[@]} video trong input/ — xử lý bằng run.sh trước..."
  bash run.sh || echo "   (run.sh gặp lỗi ở vài file, xem log phía trên)"
fi

# 3) web server + mở trình duyệt
echo "==> Mở http://localhost:$PORT"
( sleep 1; open "http://localhost:$PORT" ) >/dev/null 2>&1 &
PORT="$PORT" .venv/bin/python -m webapp.server
