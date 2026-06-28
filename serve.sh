#!/usr/bin/env bash
#
# serve.sh — chạy web Auto Sub ở CHẾ ĐỘ PRODUCTION (gunicorn) và CHIA SẺ TRONG MẠNG LAN
#            để máy tính khác cùng Wi-Fi/mạng truy cập qua http://<IP-máy-này>:<PORT>
#
#   ./serve.sh                       # production, mở cho cả LAN
#   PORT=8080 ./serve.sh             # đổi cổng (mặc định 5005)
#   THREADS=12 ./serve.sh            # số luồng phục vụ song song (mặc định 8)
#   HOST=127.0.0.1 ./serve.sh        # chỉ máy này (không chia sẻ LAN)
#
# Khác với web.sh (dev server, chỉ localhost): serve.sh dùng gunicorn,
# bind 0.0.0.0 nên các máy khác trong LAN vào được.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PORT="${PORT:-5005}"
THREADS="${THREADS:-8}"
HOST="${HOST:-0.0.0.0}"        # 0.0.0.0 = mở cho LAN; 127.0.0.1 = chỉ máy này

# 1) venv + thư viện (gồm gunicorn)
if [[ ! -d .venv ]]; then
  echo "==> Tạo venv..."
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

# 2) giải phóng cổng nếu còn server cũ đang chạy
lsof -ti tcp:"$PORT" 2>/dev/null | xargs kill 2>/dev/null || true

# 3) tìm IP LAN của máy này (để báo cho máy khác truy cập)
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
if [[ -z "${IP:-}" ]]; then
  IP="$(ifconfig 2>/dev/null | awk '/inet /{print $2}' | grep -v '^127\.' | head -1 || true)"
fi

echo "==> PRODUCTION server (gunicorn)"
echo "    Máy này:   http://localhost:$PORT"
if [[ "$HOST" == "0.0.0.0" && -n "${IP:-}" ]]; then
  echo "    Máy khác:  http://$IP:$PORT   (mở trên máy cùng mạng LAN/Wi-Fi)"
elif [[ "$HOST" == "0.0.0.0" ]]; then
  echo "    (Không dò được IP LAN — kiểm tra kết nối mạng)"
fi
echo "    Dừng:      Ctrl+C"
echo "    Lưu ý: macOS có thể hỏi 'cho phép Python nhận kết nối mạng' -> bấm Cho phép (Allow)."
echo

# 4) gunicorn:
#    - 1 worker: app giữ trạng thái job trong RAM + dùng SSE, nhiều worker sẽ vỡ state
#    - gthread + nhiều thread: phục vụ SSE/nhiều request song song
#    - timeout lớn: job xử lý video dài không bị cắt giữa chừng
exec .venv/bin/gunicorn "webapp.server:create_app()" \
  --bind "$HOST:$PORT" \
  --worker-class gthread \
  --workers 1 \
  --threads "$THREADS" \
  --timeout 3600 \
  --graceful-timeout 30 \
  --access-logfile -
