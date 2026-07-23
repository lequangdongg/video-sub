# Auto Sub — cách cài & mở (macOS Apple Silicon)

1. Mở file **`AutoSub_signed.dmg`**, kéo **AutoSub** vào thư mục **Applications**.
2. Lần đầu mở: **chuột phải vào AutoSub → Open → Open**
   (app chưa notarize nên macOS hỏi một lần; các lần sau mở bình thường).
3. Nếu chưa có model: bấm **Tải model large-v3** (~3 GB, chỉ lần đầu).
   Nếu máy đã có model ở `~/whisper-models/ggml-large-v3.bin` thì app tự nhận, vào thẳng app.

## Nếu vẫn báo bị chặn

Mở **Terminal** dán lệnh:

```bash
xattr -dr com.apple.quarantine /Applications/AutoSub.app
```

rồi mở lại app.

## Yêu cầu

- macOS Apple Silicon (M1/M2/M3…).
- Không cần cài Homebrew, Python, ffmpeg — app đã kèm sẵn.
