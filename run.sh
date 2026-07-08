#!/usr/bin/env bash
#
# run.sh — Bỏ video vào thư mục input/ rồi chạy ./run.sh
#          Mọi video trong input/ sẽ được tạo phụ đề, kết quả ra output/
#
# Pipeline mỗi video: tách audio (FFmpeg) -> whisper.cpp -> .srt -> nhúng vào video
#
set -euo pipefail

# ===================== CẤU HÌNH (chỉnh ở đây) =====================
LANG_CODE="vi"                 # mã ngôn ngữ NÓI trong video: vi, en, ja, ko, zh, auto...
MODEL="large-v3"               # tiny | base | small | medium | large-v3 (chính xác nhất) | large-v3-turbo (nhanh)
MODE="burn"                    # burn (cứng) | soft (mềm) | srt (chỉ xuất .srt)

# --- Tăng tốc ---
THREADS=8                      # số luồng CPU cho whisper (M3 Pro: 8 lõi hiệu năng/hiệu quả)
ENCODER="hardware"             # burn: hardware (videotoolbox, NHANH) | software (libx264, nén nhỏ hơn)
VT_QUALITY=60                  # chất lượng videotoolbox 1-100 (cao = đẹp hơn, file to hơn)
X264_CRF=20                    # chất lượng libx264 (thấp = đẹp hơn); chỉ dùng khi ENCODER=software
# ==================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IN_DIR="$SCRIPT_DIR/input"
OUT_DIR="$SCRIPT_DIR/output"
MODELS_DIR="${WHISPER_MODELS_DIR:-$HOME/whisper-models}"
MODEL_BIN="$MODELS_DIR/ggml-$MODEL.bin"

mkdir -p "$IN_DIR" "$OUT_DIR"

# ---- Kiểm tra công cụ & model ----
for tool in ffmpeg whisper-cli; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Chưa cài '$tool'. Xem README.md." >&2; exit 1; }
done
if [[ ! -f "$MODEL_BIN" ]]; then
  echo "Không tìm thấy model: $MODEL_BIN (xem README.md để tải)." >&2; exit 1
fi

# ---- Tìm video trong input/ ----
shopt -s nullglob nocaseglob
VIDEOS=("$IN_DIR"/*.{mp4,mkv,mov,avi,webm,m4v,flv,wmv})
shopt -u nullglob nocaseglob

if [[ ${#VIDEOS[@]} -eq 0 ]]; then
  echo "Không có video nào trong: $IN_DIR"
  echo "Bỏ file video vào đó rồi chạy lại ./run.sh"
  exit 0
fi

# burn-in cần ffmpeg có libass; báo rõ nếu thiếu
if [[ "$MODE" == "burn" ]] && ! ffmpeg -hide_banner -buildconf 2>/dev/null | grep -qi enable-libass; then
  echo "ffmpeg hiện tại KHÔNG có libass -> không burn-in được." >&2
  echo "Cài bản có libass: brew uninstall --ignore-dependencies ffmpeg && brew install homebrew-ffmpeg/ffmpeg/ffmpeg" >&2
  echo "Hoặc tạm dùng sub mềm: đổi MODE=\"soft\" ở đầu run.sh" >&2
  exit 1
fi

echo "Tìm thấy ${#VIDEOS[@]} video. lang=$LANG_CODE model=$MODEL mode=$MODE"
echo "================================================================"

OK=0; FAIL=0
for INPUT in "${VIDEOS[@]}"; do
  BASE="$(basename "${INPUT%.*}")"
  EXT="${INPUT##*.}"
  AUDIO="$OUT_DIR/$BASE.wav"
  SRT="$OUT_DIR/$BASE.srt"
  OUT="$OUT_DIR/${BASE}_sub.${EXT}"

  echo ""
  echo ">>> Xử lý: $(basename "$INPUT")"

  if ! ffmpeg -y -loglevel error -i "$INPUT" -vn -ac 1 -ar 16000 "$AUDIO"; then
    echo "    [LỖI] tách audio thất bại"; FAIL=$((FAIL+1)); rm -f "$AUDIO"; continue
  fi
  echo "    [1/3] đã tách audio"

  if ! whisper-cli -m "$MODEL_BIN" -l "$LANG_CODE" -t "$THREADS" -fa -osrt -of "$OUT_DIR/$BASE" -f "$AUDIO" >/dev/null 2>&1; then
    echo "    [LỖI] whisper thất bại"; FAIL=$((FAIL+1)); rm -f "$AUDIO"; continue
  fi
  rm -f "$AUDIO"
  [[ -f "$SRT" ]] || { echo "    [LỖI] không tạo được .srt"; FAIL=$((FAIL+1)); continue; }
  echo "    [2/3] đã tạo phụ đề -> $(basename "$SRT")"

  case "$MODE" in
    srt)
      echo "    [3/3] xong (chỉ .srt)"; OK=$((OK+1)) ;;
    soft)
      if ffmpeg -y -loglevel error -i "$INPUT" -i "$SRT" -c copy -c:s mov_text "$OUT"; then
        echo "    [3/3] xong (sub mềm) -> $(basename "$OUT")"; OK=$((OK+1))
      else echo "    [LỖI] nhúng sub mềm thất bại"; FAIL=$((FAIL+1)); fi ;;
    burn)
      if [[ "$ENCODER" == "hardware" ]]; then
        VENC=(-c:v h264_videotoolbox -q:v "$VT_QUALITY")      # phần cứng: nhanh
      else
        VENC=(-c:v libx264 -crf "$X264_CRF" -preset medium)   # phần mềm: nén nhỏ hơn
      fi
      if ffmpeg -y -loglevel error -i "$INPUT" -vf "subtitles='${SRT//\'/\\\'}'" "${VENC[@]}" -c:a copy "$OUT"; then
        echo "    [3/3] xong (sub cứng, $ENCODER) -> $(basename "$OUT")"; OK=$((OK+1))
      else echo "    [LỖI] nhúng sub cứng thất bại"; FAIL=$((FAIL+1)); fi ;;
    *)
      echo "    [LỖI] MODE không hợp lệ: $MODE"; FAIL=$((FAIL+1)) ;;
  esac
done

echo ""
echo "================================================================"
echo "Hoàn tất. Thành công: $OK | Lỗi: $FAIL | Kết quả tại: $OUT_DIR"
