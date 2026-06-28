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
#   MODEL=medium ./install.sh        # đổi model whisper tải về (mặc định large-v3-turbo)
#   SKIP_LIBASS=1 ./install.sh       # KHÔNG build ffmpeg-libass (chỉ dùng sub mềm/srt, cài nhanh)
#
set -euo pipefail

MODEL="${MODEL:-large-v3-turbo}"
MODELS_DIR="${WHISPER_MODELS_DIR:-$HOME/whisper-models}"
SKIP_LIBASS="${SKIP_LIBASS:-0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_BIN="$MODELS_DIR/ggml-$MODEL.bin"

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

# ---- 4. Model whisper ----
if [[ -f "$MODEL_BIN" ]]; then
  say "Model đã có: $MODEL_BIN"
else
  say "Tải model whisper ($MODEL)..."
  mkdir -p "$MODELS_DIR"
  URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$MODEL.bin"
  if curl -L --fail -o "$MODEL_BIN.part" "$URL"; then
    mv "$MODEL_BIN.part" "$MODEL_BIN"
  else
    rm -f "$MODEL_BIN.part"
    err "Tải model thất bại. Thử lại hoặc tải tay từ: $URL"
    exit 1
  fi
fi

# ---- 5. Quyền chạy + thư mục ----
chmod +x "$SCRIPT_DIR/run.sh" "$SCRIPT_DIR/sub.sh" 2>/dev/null || true
mkdir -p "$SCRIPT_DIR/input" "$SCRIPT_DIR/output"

# ---- 6. Kiểm tra cuối ----
say "Kiểm tra:"
ok=1
if command -v whisper-cli >/dev/null 2>&1; then echo "  ✓ whisper-cli"; else echo "  ✗ whisper-cli"; ok=0; fi
if has_libass; then echo "  ✓ ffmpeg (libass) — burn-in OK"
elif command -v ffmpeg >/dev/null 2>&1; then echo "  ⚠ ffmpeg KHÔNG libass — chỉ sub mềm/srt"
else echo "  ✗ ffmpeg"; ok=0; fi
if [[ -f "$MODEL_BIN" ]]; then echo "  ✓ model $MODEL"; else echo "  ✗ model"; ok=0; fi

if [[ $ok -eq 1 ]]; then
  say "Xong! Bỏ video vào thư mục input/ rồi chạy:   ./run.sh"
  echo "    Mở giao diện web:        ./web.sh"
  echo "    Chạy tất cả (web + xử lý input/): ./start.sh"
  echo "    Dọn input/ output/:      ./clean.sh"
else
  err "Còn thiếu thành phần ở trên — xem lại log phía trên."
  exit 1
fi
