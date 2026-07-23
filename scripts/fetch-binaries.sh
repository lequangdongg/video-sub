#!/usr/bin/env bash
# Dựng 3 binary bundle cho app Tauri (macOS arm64): whisper-cli (tĩnh), ffmpeg+ffprobe (static, có libass).
# Chạy: ./scripts/fetch-binaries.sh   (cần: git, cmake, clang, curl, unzip)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/src-tauri/binaries"
mkdir -p "$BIN"

echo "==> [1/2] Build whisper-cli tĩnh từ whisper.cpp"
WORK="$(mktemp -d)"
git clone --depth 1 https://github.com/ggerganov/whisper.cpp "$WORK/whisper.cpp"
cmake -S "$WORK/whisper.cpp" -B "$WORK/whisper.cpp/build" \
      -DBUILD_SHARED_LIBS=OFF -DCMAKE_BUILD_TYPE=Release -DWHISPER_METAL=ON
cmake --build "$WORK/whisper.cpp/build" -j --config Release
cp "$WORK/whisper.cpp/build/bin/whisper-cli" "$BIN/whisper-cli"

echo "==> [2/2] Tải ffmpeg + ffprobe static arm64 (có libass) từ osxexperts"
curl -sS -L -o "$WORK/ffmpeg.zip"  "https://www.osxexperts.net/ffmpeg711arm.zip"
curl -sS -L -o "$WORK/ffprobe.zip" "https://www.osxexperts.net/ffprobe711arm.zip"
unzip -o "$WORK/ffmpeg.zip"  -d "$WORK" >/dev/null
unzip -o "$WORK/ffprobe.zip" -d "$WORK" >/dev/null
cp "$WORK/ffmpeg"  "$BIN/ffmpeg"
cp "$WORK/ffprobe" "$BIN/ffprobe"

chmod +x "$BIN"/*
rm -rf "$WORK"

echo "==> Kiểm tra"
"$BIN/ffmpeg" -hide_banner -buildconf | grep -q enable-libass && echo "  ffmpeg: LIBASS OK" || { echo "  ffmpeg: LIBASS MISSING"; exit 1; }
for b in ffmpeg ffprobe whisper-cli; do
  n=$(otool -L "$BIN/$b" | grep -c /opt/homebrew || true)
  echo "  $b: homebrew deps=$n"
done
echo "==> Xong. Binary ở: $BIN"
