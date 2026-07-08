#!/usr/bin/env bash
#
# install.sh — Cài tự động mọi thứ cần cho Auto Sub (macOS).
#
#   ./install.sh
#
# Sẽ cài: Homebrew (nếu thiếu) -> whisper-cpp -> ffmpeg CÓ libass -> tải model whisper
#         -> chmod script -> tạo thư mục input/ output/
#
# Tùy chọn (biến môi trường):
#   MODEL="large-v3-turbo" ./install.sh          # tải model nhẹ/nhanh hơn
#   MODEL="large-v3 large-v3-turbo" ./install.sh  # tải NHIỀU model (cách nhau bởi dấu cách)
#   SKIP_LIBASS=1 ./install.sh                    # KHÔNG build ffmpeg-libass (chỉ sub mềm/srt)
#
set -euo pipefail

# Mặc định large-v3: chậm nhưng chính xác nhất. Máy yếu thì dùng MODEL="large-v3-turbo".
MODEL="${MODEL:-large-v3}"
MODELS_DIR="${WHISPER_MODELS_DIR:-$HOME/whisper-models}"
SKIP_LIBASS="${SKIP_LIBASS:-0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say(){ printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
err(){ printf "\033[1;31m[LỖI] %s\033[0m\n" "$1" >&2; }

# ---- 0. Kiểm tra hệ điều hành ----
if [[ "$(uname)" != "Darwin" ]]; then
  err "Script này dành cho macOS."
  echo "Trên Linux: cài 'ffmpeg' (thường đã kèm libass) qua apt/dnf, và build whisper.cpp thủ công" >&2
  echo "(https://github.com/ggml-org/whisper.cpp), rồi tải model về \$HOME/whisper-models/." >&2
  exit 1
fi

# ---- 1. Homebrew ----
if ! command -v brew >/dev/null 2>&1; then
  say "Cài Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  [[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
  [[ -x /usr/local/bin/brew  ]] && eval "$(/usr/local/bin/brew shellenv)"
else
  say "Homebrew đã có."
fi

# ---- 2. whisper-cpp (cho lệnh whisper-cli) ----
if command -v whisper-cli >/dev/null 2>&1; then
  say "whisper-cpp đã có."
else
  say "Cài whisper-cpp..."
  brew install whisper-cpp
fi

# ---- 3. ffmpeg ----
has_libass(){ command -v ffmpeg >/dev/null 2>&1 && ffmpeg -hide_banner -buildconf 2>/dev/null | grep -qi enable-libass; }

if has_libass; then
  say "ffmpeg (có libass) đã có."
elif [[ "$SKIP_LIBASS" == "1" ]]; then
  say "SKIP_LIBASS=1 -> cài ffmpeg thường (chỉ dùng được sub MỀM/srt, không burn-in)."
  command -v ffmpeg >/dev/null 2>&1 || brew install ffmpeg
else
  say "Cài ffmpeg KÈM libass (cần cho burn-in)."
  echo "    Lưu ý: build từ nguồn, có thể mất 15-40 phút. (Bỏ qua: SKIP_LIBASS=1)"
  # gỡ ffmpeg core nếu có nhưng thiếu libass, tránh xung đột tên 'ffmpeg'
  if brew list ffmpeg >/dev/null 2>&1; then
    brew uninstall --ignore-dependencies ffmpeg || true
  fi
  brew tap homebrew-ffmpeg/ffmpeg
  brew install homebrew-ffmpeg/ffmpeg/ffmpeg
fi

# ---- 4. Model whisper (tải 1 hoặc nhiều model, cách nhau bởi dấu cách/phẩy) ----
mkdir -p "$MODELS_DIR"
for m in ${MODEL//,/ }; do
  bin="$MODELS_DIR/ggml-$m.bin"
  if [[ -f "$bin" ]]; then
    say "Model đã có: $bin"
  else
    say "Tải model whisper ($m)... (large-v3 ~3GB, lâu)"
    URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$m.bin"
    if curl -L --fail -o "$bin.part" "$URL"; then
      mv "$bin.part" "$bin"
    else
      rm -f "$bin.part"
      err "Tải model '$m' thất bại. Thử lại hoặc tải tay từ: $URL"
      exit 1
    fi
  fi
done

# ---- 5. Quyền chạy + thư mục ----
chmod +x "$SCRIPT_DIR"/*.sh 2>/dev/null || true   # tất cả script (run/web/serve/start/clean/sub/tunnel)
mkdir -p "$SCRIPT_DIR/input" "$SCRIPT_DIR/output"

# ---- 5b. Python venv + thư viện chạy web (Flask...) ----
say "Cài Python venv + thư viện web (Flask)..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "    python3 chưa có -> cài qua Homebrew..."
  brew install python
fi
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
  python3 -m venv "$SCRIPT_DIR/.venv"
fi
"$SCRIPT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$SCRIPT_DIR/.venv/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"

# ---- 6. Kiểm tra cuối ----
say "Kiểm tra:"
ok=1
if command -v whisper-cli >/dev/null 2>&1; then echo "  ✓ whisper-cli"; else echo "  ✗ whisper-cli"; ok=0; fi
if has_libass; then echo "  ✓ ffmpeg (libass) — burn-in OK"
elif command -v ffmpeg >/dev/null 2>&1; then echo "  ⚠ ffmpeg KHÔNG libass — chỉ sub mềm/srt"
else echo "  ✗ ffmpeg"; ok=0; fi
for m in ${MODEL//,/ }; do
  if [[ -f "$MODELS_DIR/ggml-$m.bin" ]]; then echo "  ✓ model $m"; else echo "  ✗ model $m"; ok=0; fi
done
if "$SCRIPT_DIR/.venv/bin/python" -c "import flask" >/dev/null 2>&1; then echo "  ✓ venv + Flask (web sẵn sàng)"; else echo "  ✗ venv/Flask"; ok=0; fi

if [[ $ok -eq 1 ]]; then
  say "Xong! Bỏ video vào thư mục input/ rồi chạy:   ./run.sh"
  echo "    Mở giao diện web:        ./web.sh"
  echo "    Chạy tất cả (web + xử lý input/): ./start.sh"
  echo "    Dọn input/ output/:      ./clean.sh"
else
  err "Còn thiếu thành phần ở trên — xem lại log phía trên."
  exit 1
fi
