#!/usr/bin/env bash
# Ký ad-hoc AutoSub.app (cả binary con) rồi đóng gói .dmg gửi cho user.
# Chạy SAU `cargo tauri build`. Không cần tài khoản Apple Developer.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE="$ROOT/src-tauri/target/release/bundle"
APP="$BUNDLE/macos/AutoSub.app"
DMG="$BUNDLE/dmg/AutoSub_signed.dmg"

[ -d "$APP" ] || { echo "Chưa có $APP — chạy 'cargo tauri build' trước."; exit 1; }

echo "==> Ký binary con trong Resources (ad-hoc)"
find "$APP/Contents/Resources/binaries" -type f -perm +111 -exec codesign --force -s - {} \;

echo "==> Ký toàn bộ app (deep, ad-hoc)"
codesign --deep --force -s - "$APP"

echo "==> Verify chữ ký"
codesign --verify --deep --verbose=2 "$APP"

echo "==> Đóng gói .dmg từ app đã ký"
rm -f "$DMG"
TMP="$(mktemp -d)"
cp -R "$APP" "$TMP/"
ln -s /Applications "$TMP/Applications"
hdiutil create -volname "AutoSub" -srcfolder "$TMP" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$TMP"

echo "==> Xong: $DMG"
