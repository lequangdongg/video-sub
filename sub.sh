#!/usr/bin/env bash
#
# sub.sh — Tự động tạo phụ đề cho video bằng whisper.cpp + FFmpeg
#
# Pipeline: video --(ffmpeg)--> audio.wav 16kHz --(whisper-cli)--> .srt --(ffmpeg)--> video có sub
#
# Cách dùng:
#   ./sub.sh video.mp4                       # mặc định: tiếng Việt (vi), model large-v3-turbo, burn-in
#   ./sub.sh video.mp4 -l en -m medium       # đổi ngôn ngữ / model
#   ./sub.sh video.mp4 --mode soft           # sub mềm (bật/tắt được)
#   ./sub.sh video.mp4 --mode srt            # chỉ xuất file .srt, không nhúng
#
# Ngôn ngữ dùng MÃ ISO: vi, en, ja, ko, zh, fr... hoặc 'auto' để tự nhận diện.
# Model nằm ở: ~/whisper-models/ggml-<model>.bin (đổi qua biến môi trường WHISPER_MODELS_DIR).
#
set -euo pipefail

# ---- Mặc định ----
LANG_CODE="vi"                 # mã ngôn ngữ NÓI trong video (vi, en, auto, ...)
MODEL="large-v3"               # tiny | base | small | medium | large-v3 (chính xác nhất) | large-v3-turbo (nhanh)
MODE="burn"                    # burn (cứng) | soft (mềm) | srt (chỉ xuất .srt)
MODELS_DIR="${WHISPER_MODELS_DIR:-$HOME/whisper-models}"

# ---- Parse tham số ----
INPUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -l|--language) LANG_CODE="$2"; shift 2 ;;
    -m|--model)    MODEL="$2";     shift 2 ;;
    --mode)        MODE="$2";      shift 2 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)
      echo "Tham số không hợp lệ: $1" >&2; exit 1 ;;
    *)
      INPUT="$1"; shift ;;
  esac
done

if [[ -z "$INPUT" ]]; then
  echo "Thiếu file video. Dùng: ./sub.sh video.mp4 [-l vi] [-m large-v3-turbo] [--mode burn|soft|srt]" >&2
  exit 1
fi
if [[ ! -f "$INPUT" ]]; then
  echo "Không tìm thấy file: $INPUT" >&2; exit 1
fi

# ---- Kiểm tra công cụ ----
for tool in ffmpeg whisper-cli; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Chưa cài '$tool'. Xem README.md để biết cách cài." >&2
    exit 1
  fi
done

MODEL_BIN="$MODELS_DIR/ggml-$MODEL.bin"
if [[ ! -f "$MODEL_BIN" ]]; then
  echo "Không tìm thấy model: $MODEL_BIN" >&2
  echo "Tải bằng: python3 -c \"import urllib.request,os;os.makedirs('$MODELS_DIR',exist_ok=True);urllib.request.urlretrieve('https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$MODEL.bin','$MODEL_BIN')\"" >&2
  exit 1
fi

# ---- Đường dẫn ----
DIR="$(cd "$(dirname "$INPUT")" && pwd)"
BASE="$(basename "${INPUT%.*}")"
EXT="${INPUT##*.}"
AUDIO="$DIR/$BASE.wav"
SRT="$DIR/$BASE.srt"
OUT="$DIR/${BASE}_sub.${EXT}"

echo "==> [1/3] Tách audio (16kHz mono)..."
ffmpeg -y -i "$INPUT" -vn -ac 1 -ar 16000 "$AUDIO"

echo "==> [2/3] whisper.cpp nhận diện giọng nói (lang=$LANG_CODE, model=$MODEL)..."
# -osrt: xuất .srt ; -of: tên file ra (không đuôi) -> tạo $SRT
whisper-cli -m "$MODEL_BIN" -l "$LANG_CODE" -osrt -of "$DIR/$BASE" -f "$AUDIO"

if [[ ! -f "$SRT" ]]; then
  echo "Không tạo được file .srt." >&2; exit 1
fi

case "$MODE" in
  srt)
    echo "==> Xong. File phụ đề: $SRT"
    ;;
  soft)
    echo "==> [3/3] Nhúng sub MỀM (bật/tắt được)..."
    ffmpeg -y -i "$INPUT" -i "$SRT" -c copy -c:s mov_text "$OUT"
    echo "==> Xong: $OUT"
    ;;
  burn)
    echo "==> [3/3] Nhúng sub CỨNG (burn-in)..."
    ffmpeg -y -i "$INPUT" -vf "subtitles='${SRT//\'/\\\'}'" -c:a copy "$OUT"
    echo "==> Xong: $OUT"
    ;;
  *)
    echo "--mode không hợp lệ: $MODE (chọn burn|soft|srt)" >&2; exit 1 ;;
esac

# Dọn file audio tạm
rm -f "$AUDIO"
