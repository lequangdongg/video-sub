#!/usr/bin/env bash
#
# tunnel.sh — đưa web Auto Sub ra INTERNET qua Cloudflare Tunnel (HTTPS, miễn phí).
#
#   1) Mở 1 cửa sổ Terminal:  ./serve.sh        (hoặc ./web.sh) để chạy server
#   2) Mở cửa sổ khác:        ./tunnel.sh       -> hiện URL https://*.trycloudflare.com
#
#   PORT=8080 ./tunnel.sh    # nếu server chạy cổng khác (mặc định 5005)
#
# Máy bạn vẫn là nơi xử lý; tunnel chỉ dẫn Internet về http://localhost:$PORT.
set -euo pipefail
PORT="${PORT:-5005}"

# 1) cài cloudflared nếu thiếu
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "==> Cài cloudflared qua Homebrew..."
  brew install cloudflared
fi

# 2) kiểm tra server có đang chạy không
if ! curl -s -o /dev/null "http://localhost:$PORT/"; then
  echo "[CẢNH BÁO] Chưa thấy server ở http://localhost:$PORT"
  echo "           Hãy chạy ./serve.sh (hoặc ./web.sh) ở cửa sổ khác trước."
  echo
fi

cat <<'WARN'
============================================================
 ⚠️  BẢO MẬT: link này AI CÓ LINK ĐỀU VÀO ĐƯỢC, không đăng nhập.
     Họ có thể upload video, ngốn CPU máy bạn. Chỉ chia sẻ link
     cho người tin cậy, và TẮT (Ctrl+C) khi dùng xong.
     Muốn có đăng nhập -> dùng Cloudflare Access hoặc nhờ thêm
     Basic Auth vào app.
============================================================
WARN
echo "==> Mở tunnel Internet cho http://localhost:$PORT"
echo "    URL công khai (https://*.trycloudflare.com) sẽ hiện ngay bên dưới."
echo "    Dừng: Ctrl+C"
echo
exec cloudflared tunnel --url "http://localhost:$PORT"
