# Auto Sub — Tạo phụ đề tự động cho video

Bỏ video vào thư mục **`input/`**, chạy **`./run.sh`**, kết quả ra **`output/`**.

Pipeline mỗi video: `tách audio (FFmpeg) → whisper.cpp nhận diện giọng → .srt → nhúng vào video`

Dùng **whisper.cpp** (`whisper-cli`) thay `openai-whisper` để khỏi phụ thuộc PyTorch
(máy chạy Python 3.14). Nhanh, offline, không cần Python.

## Cách dùng

```bash
# 1. Bỏ video vào thư mục input/
cp ~/Downloads/video.mp4 input/

# 2. Chạy
./run.sh

# 3. Lấy kết quả ở output/  ->  video_sub.mp4 + video.srt
```

Chạy được nhiều video một lúc — cứ bỏ hết vào `input/`.

## Cấu hình (sửa ở đầu `run.sh`)

```bash
LANG_CODE="vi"            # mã ngôn ngữ NÓI: vi, en, ja, ko, zh, auto...
MODEL="large-v3-turbo"    # tiny|base|small|medium|large-v3|large-v3-turbo
MODE="burn"              # burn (cứng) | soft (mềm) | srt (chỉ .srt)
```

| MODE   | Ý nghĩa                                  | Yêu cầu             |
|--------|------------------------------------------|---------------------|
| `burn` | Phụ đề vẽ thẳng lên hình, không tắt được | ffmpeg **có libass**|
| `soft` | Phụ đề đính kèm, bật/tắt trong player     | ffmpeg thường       |
| `srt`  | Chỉ xuất file `.srt`                      | —                   |

## Cài đặt — chạy 1 lệnh

```bash
./install.sh
```

Tự cài hết: Homebrew (nếu thiếu) → `whisper-cpp` → `ffmpeg` có libass → tải model whisper
→ tạo thư mục `input/` `output/`. Chạy lại nhiều lần vô tư (có gì rồi thì bỏ qua).

Tùy chọn:
```bash
MODEL=medium ./install.sh      # đổi model tải về (mặc định large-v3-turbo)
SKIP_LIBASS=1 ./install.sh     # KHÔNG build ffmpeg-libass: cài nhanh, chỉ dùng sub mềm/srt
```

> ⚠️ Burn-in (sub cứng) cần `ffmpeg` **có libass**. Bản `brew install ffmpeg` (homebrew core)
> không kèm libass nên `install.sh` build bản từ tap `homebrew-ffmpeg/ffmpeg` (từ nguồn,
> 15–40 phút, **chỉ lần đầu**). Nếu chỉ cần sub mềm thì dùng `SKIP_LIBASS=1` cho nhanh.

**Cài thủ công** (nếu không dùng `install.sh`):
```bash
brew install whisper-cpp
brew install homebrew-ffmpeg/ffmpeg/ffmpeg
python3 -c "import urllib.request,os;d=os.path.expanduser('~/whisper-models');os.makedirs(d,exist_ok=True);urllib.request.urlretrieve('https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin',d+'/ggml-large-v3-turbo.bin')"
```

## Chọn model
| Model            | Tốc độ    | Độ chính xác | Kích thước |
|------------------|-----------|--------------|------------|
| tiny / base      | Rất nhanh | Thấp–TB      | ~75–140MB  |
| small            | Vừa       | Khá          | ~460MB     |
| medium           | Chậm      | Tốt          | ~1.5GB     |
| large-v3-turbo   | Nhanh     | Rất tốt      | ~1.6GB     |

## Tăng tốc cho video lớn (vài GB)

Hai phần tốn thời gian, tăng tốc khác nhau:

**1. Whisper (theo độ DÀI audio, không theo dung lượng)** — đã bật sẵn:
- `THREADS=8` + flash attention (`-fa`) trong `run.sh`.
- Còn chậm? Đổi model nhẹ hơn: `MODEL="medium"` hoặc `"small"` (nhanh hơn, độ chính xác giảm chút).
- Bản lượng tử hoá nhanh hơn + nhẹ RAM (gần như không giảm chất lượng):
  ```bash
  python3 -c "import urllib.request,os;d=os.path.expanduser('~/whisper-models');urllib.request.urlretrieve('https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin',d+'/ggml-large-v3-turbo-q5_0.bin')"
  ```
  rồi đặt `MODEL="large-v3-turbo-q5_0"`.

**2. Burn-in (mã hoá lại video — thường CHẬM NHẤT với video lớn/4K):**
- `ENCODER="hardware"` (mặc định) dùng **videotoolbox của Apple Silicon** — nhanh gấp nhiều lần libx264.
  Chỉnh chất lượng qua `VT_QUALITY` (1–100, cao = đẹp/to hơn).
- **Nhanh nhất tuyệt đối:** `MODE="soft"` → **không mã hoá lại** (chỉ ghép luồng, gần như tức thì
  kể cả video vài GB). Đánh đổi: phụ đề bật/tắt trong player chứ không cháy vào hình.
- `ENCODER="software"` (libx264) chỉ nên dùng khi cần file nén nhỏ nhất và không vội.

| Nhu cầu | Cấu hình |
|---|---|
| Nhanh nhất, vẫn sub cứng | `MODE="burn"` + `ENCODER="hardware"` (mặc định) |
| Nhanh nhất tuyệt đối | `MODE="soft"` (không re-encode) |
| File nhỏ nhất, chấp nhận chậm | `MODE="burn"` + `ENCODER="software"` |

## Giao diện web

```bash
./web.sh        # mở http://localhost:5005
```

- **Tab "Tự động tạo sub":** upload video → whisper nhận diện → nhúng sub → tải về (video + .srt).
- **Tab "Ghép sub có sẵn":** upload video + file sub. Sub có timeline (`.srt`/`.vtt`/`.ass`) thì
  dời theo ô "Bắt đầu sub từ giây thứ"; sub là **văn bản thuần** (`.txt`/`.docx`, không timeline)
  thì whisper nghe video rồi **tự căn** văn bản vào timeline. Chọn kiểu sub cứng/mềm.
- Lần đầu `web.sh` tự tạo venv và cài Flask (thuần Python, không đụng PyTorch).

## Ghi chú
- `sub.sh video.mp4` — bản chạy lẻ 1 file (tham số `-l`, `-m`, `--mode`), nếu không muốn dùng thư mục.
- File audio tạm được tự xoá sau khi xong.
