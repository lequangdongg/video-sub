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
MODEL="large-v3"         # large-v3 (chính xác nhất, mặc định) | large-v3-turbo (nhanh) | medium | small
MODE="burn"              # burn (cứng) | soft (mềm) | srt (chỉ .srt)
```

| MODE   | Ý nghĩa                                  | Yêu cầu             |
|--------|------------------------------------------|---------------------|
| `burn` | Phụ đề vẽ thẳng lên hình, không tắt được | ffmpeg **có libass**|
| `soft` | Phụ đề đính kèm, bật/tắt trong player     | ffmpeg thường       |
| `srt`  | Chỉ xuất file `.srt`                      | —                   |

## App desktop (macOS Apple Silicon) — Tauri

Ngoài bản web, có bản **app desktop** đóng gói bằng Tauri v2 (lõi Rust, nhẹ, kèm sẵn
`ffmpeg`+libass và `whisper-cli` — **không cần Homebrew/Python/cài gì**).

```bash
# lần đầu: cần Rust + tauri-cli + binary bundle
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
cargo install tauri-cli --version "^2.0.0"
./scripts/fetch-binaries.sh        # dựng ffmpeg/ffprobe/whisper-cli vào src-tauri/binaries

# chạy thử (dev)
cd src-tauri && cargo tauri dev

# đóng gói .dmg gửi cho người khác
cd src-tauri && cargo tauri build
./scripts/build-dmg.sh             # ký ad-hoc + tạo AutoSub_signed.dmg
```

- Mở lần đầu app tự hỏi tải model **large-v3** (~3GB); nếu máy đã có ở `~/whisper-models/` thì tự nhận.
- Người nhận `.dmg`: chuột phải → Open lần đầu (chưa notarize) — xem [`DIST-README.md`](DIST-README.md).
- Lõi xử lý (sinh SRT/ASS, sửa từ, align) được **port sang Rust và kiểm khớp bản Python bằng golden test**
  (`src-tauri/tests/golden`, chạy `cargo test`). Bản web Python (`webapp/`) vẫn giữ nguyên, chạy song song.

## Cài đặt — chạy 1 lệnh

Máy mới (macOS) — clone rồi cài:
```bash
git clone https://github.com/lequangdongg/video-sub.git
cd video-sub
./install.sh
```

Tự cài hết: Homebrew (nếu thiếu) → `whisper-cpp` → `ffmpeg` có libass → tải model whisper
→ tạo `.venv` + cài Flask → `chmod +x` mọi script → tạo `input/` `output/`.
Chạy lại nhiều lần vô tư (có gì rồi thì bỏ qua).

Sau khi cài xong, **chạy**:
```bash
./web.sh          # mở giao diện web ở http://localhost:5005
# hoặc xử lý hàng loạt: bỏ video vào input/ rồi  ./run.sh
```

> ⚠️ Luôn chạy qua `./web.sh` / `./run.sh` (chúng dùng đúng Python trong `.venv`).
> **Đừng** gõ `python3 -m webapp.server` trực tiếp — Python hệ thống của macOS (3.9)
> không có Flask nên sẽ lỗi `ModuleNotFoundError: No module named 'flask'`.

Tùy chọn:
```bash
MODEL="large-v3-turbo" ./install.sh            # tải model nhẹ/nhanh hơn (mặc định là large-v3)
MODEL="large-v3 large-v3-turbo" ./install.sh   # tải NHIỀU model (cách nhau bởi dấu cách)
SKIP_LIBASS=1 ./install.sh                     # KHÔNG build ffmpeg-libass: cài nhanh, chỉ sub mềm/srt
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
| **large-v3** ⭐  | Chậm      | **Cao nhất** | ~3GB       |

**`large-v3` là mặc định** (chính xác nhất, hợp tiếng Việt khó/nhiều thuật ngữ) — `./install.sh` tự tải.
Máy yếu / muốn nhanh hơn thì chọn **large-v3-turbo** ở ô Model trong web, hoặc:
```bash
MODEL="large-v3-turbo" ./install.sh
```

## Sửa từ bị nhận nhầm

Whisper đôi khi nghe sai (nhất là dấu thanh, vd *nôn mửa* → *nôn mưởng*). Có 2 cách:

1. **Từ điển sửa** — mở [`webapp/corrections.txt`](webapp/corrections.txt), thêm dòng `sai => đúng`:
   ```
   nôn mưởng => nôn mửa
   thành phố hồ chí mih => Thành phố Hồ Chí Minh
   ```
   Áp dụng tự động cho mọi sub tạo mới (không phân biệt hoa/thường, giữ hoa chữ đầu).
2. **Model `large-v3`** — chính xác hơn `turbo` cho câu khó.
3. **Gợi ý từ vựng** (tuỳ chọn): `WHISPER_PROMPT="tên riêng, thuật ngữ hay dùng" ./web.sh` để bias nhận diện.

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
./web.sh        # chỉ mở web (http://localhost:5005)
./start.sh      # CHẠY TẤT CẢ: xử lý video sẵn trong input/ (run.sh) rồi mở web
```

- **Tab "Tự động tạo sub":** upload video → whisper nhận diện → nhúng sub → tải về (video + .srt).
- **Tab "Ghép sub có sẵn":** upload video + file sub. Sub có timeline (`.srt`/`.vtt`/`.ass`) thì
  dời theo ô "Bắt đầu sub từ giây thứ"; sub là **văn bản thuần** (`.txt`/`.docx`, không timeline)
  thì whisper nghe video rồi **tự căn** văn bản vào timeline. Chọn kiểu sub cứng/mềm.
- Khi chọn **"Cháy vào hình"**, có panel **Kiểu chữ phụ đề**: font, cỡ chữ, đậm/nghiêng,
  màu chữ, màu + độ dày viền, vị trí (trên/giữa/dưới), lề, nền chữ + độ mờ — xem trước ngay
  trên khung preview. (Áp dụng cho burn-in; ánh xạ sang `force_style` của libass.)
- Font đi kèm sẵn trong repo tại `assets/fonts/` (ffmpeg dùng qua `fontsdir` — **không cài vào máy**):
  - **UTM Avo** (4 kiểu: Regular/Bold/Italic/BoldItalic) — mặc định.
  - **Be Vietnam Pro** (SIL OFL, 9 độ đậm: Thin → Black, kèm italic).
  Thả thêm `.ttf`/`.otf` vào `assets/fonts/` là libass tự nhận (chọn trong ô Font).
- Sau khi xong, nút **"🗑 Xoá & làm video khác"** xoá video đã upload + kết quả của job đó.
- Lần đầu `web.sh`/`start.sh` tự tạo venv và cài Flask (thuần Python, không đụng PyTorch).
- `web.sh`/`start.sh` tự giải phóng cổng nếu còn bản cũ đang chạy (tránh lỗi 404 do server cũ).

### Sửa giao diện (Tailwind qua npm)

CSS được **Tailwind quản lý** (không dùng CDN). Nguồn: `webapp/styles/input.css` →
build ra `webapp/static/app.css` (đã commit sẵn nên chạy app không cần Node).

```bash
npm install            # lần đầu
npm run build:css      # build lại sau khi sửa style
npm run watch:css      # tự build khi đang chỉnh
```

## Dọn dẹp

```bash
./clean.sh      # hỏi xác nhận rồi xoá sạch input/ output/ webapp/jobs/ (giữ .gitkeep)
./clean.sh -y   # xoá luôn không hỏi
```

## Ghi chú
- `sub.sh video.mp4` — bản chạy lẻ 1 file (tham số `-l`, `-m`, `--mode`), nếu không muốn dùng thư mục.
- File audio tạm được tự xoá sau khi xong.
