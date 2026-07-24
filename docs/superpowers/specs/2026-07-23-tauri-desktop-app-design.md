# Auto Sub — Tauri v2 Desktop App (Design)

Ngày: 2026-07-23
Trạng thái: đã duyệt thiết kế, chờ lập kế hoạch triển khai.

## Mục tiêu

Đóng gói web app tạo phụ đề hiện tại (Flask + whisper.cpp + ffmpeg) thành **app desktop
Tauri v2**, nhẹ, chạy **chỉ macOS (Apple Silicon)**. Xuất **file `.dmg` để gửi cho user tải về
và dùng**. Khi mở: có màn hình setup với nút bấm để tải model (như bản web) rồi dùng ngay.
Ưu tiên Rust cho phần lõi để nhẹ.

## Quyết định chốt

| Vấn đề | Quyết định |
|---|---|
| Kiến trúc | **Hybrid Tauri**: lõi Rust + giữ nguyên UI HTML/CSS/JS hiện tại (webview) |
| Backend xử lý | Port `pipeline.py` + `subtitles.py` sang Rust; spawn `whisper-cli`/`ffmpeg` như CLI |
| Nền tảng | Chỉ macOS Apple Silicon (arm64) |
| Cài đặt công cụ | **Bundle** `whisper-cli` + `ffmpeg`(libass) + `ffprobe` trong `.app` |
| Model | Setup **chỉ tải large-v3** (~3GB); không turbo. App dùng đúng large-v3 xuyên suốt |
| Nhớ trạng thái | Model đã tải → lần sau **bỏ qua** màn Setup, vào thẳng UI chính |

### Vì sao Hybrid thay vì "port hết qua Rust GUI thuần"

Trong Tauri, UI luôn là webview → "viết lại UI" vẫn ra HTML/JS, không lợi MB/perf. GUI Rust
thuần (egui/iced) mới khác, nhưng: kích thước gần như bằng nhau (thứ nặng là ffmpeg+whisper
~40MB và model ~3GB, giống nhau ở mọi phương án); tốc độ xử lý **bằng nhau tuyệt đối** (do
subprocess whisper/ffmpeg quyết định); Rust thuần chỉ hơn ở RAM idle / khởi động (vô nghĩa khi
whisper đã ngốn vài GB lúc chạy); và **mất khả năng xem trước video** (`<video>` dễ trong
webview, gần như bất khả trong egui/iced). → Hybrid thắng rõ, ít rủi ro "làm sai" hơn.

## 1. Kiến trúc

```
Webview (index.html + app.js)  --invoke()-->  Rust core (src-tauri)
        ^  listen('progress')  <--emit()--         |
                                                    v  spawn
                                        whisper-cli / ffmpeg / ffprobe (bundle)
```

Không Python, không Flask, không HTTP. Frontend gọi `invoke()`; tiến trình đẩy qua Tauri
event (`emit`/`listen`) thay cho SSE/polling.

## 2. Cấu trúc thư mục

```
audio_translate/
├─ src-tauri/
│  ├─ src/
│  │  ├─ main.rs          # đăng ký commands
│  │  ├─ commands.rs      # run_auto / run_merge / check_setup / download_model / save_output
│  │  ├─ pipeline.rs      # process_auto / process_merge (orchestrator)
│  │  ├─ whisper.rs       # spawn whisper-cli, parse progress=NN%, apply_corrections
│  │  ├─ ffmpeg.rs        # extract_audio / burn_or_mux / video_dimensions / video_duration / have_libass
│  │  ├─ ass.rs           # write_band_ass / build_force_style / hex_to_ass / char-width
│  │  ├─ srt.rs           # parse_srt / write_srt / shift / hide_before
│  │  ├─ align.rs         # word_timings + align văn bản thuần (subtitles.align, .docx)
│  │  └─ setup.rs         # check_setup / download_model / đường dẫn data dir
│  ├─ binaries/           # whisper-cli, ffmpeg, ffprobe (arm64) — bundle
│  ├─ resources/          # assets/fonts/*, corrections.txt mặc định
│  └─ tauri.conf.json
├─ webapp/static/         # index.html, app.js, app.css (giữ, chỉnh nhẹ app.js)
└─ webapp/ (Python cũ)    # GIỮ LẠI VĨNH VIỄN — vừa là golden reference để test, vừa để chạy bản web song song
```

## 3. Bản đồ port Python → Rust (giữ nguyên hành vi)

| Python | Rust | Ghi chú |
|---|---|---|
| `extract_audio` | `ffmpeg.rs` | `ffmpeg -y -vn -ac 1 -ar 16000` |
| `transcribe` | `whisper.rs` | y hệt cờ `-bs 5 -bo 5 -fa -pp -osrt`; parse `progress=NN%`; `--prompt` nếu có |
| `apply_corrections` / `_load_corrections` | `whisper.rs` | regex case-insensitive, giữ hoa chữ đầu; format `sai => đúng` |
| `word_timings` / `parse_word_timings` | `align.rs` | `-ojf` JSON, gộp subword token thành từ |
| `write_band_ass` | `ass.rs` | **rủi ro cao nhất**: `_char_frac`, `_line_width`, `_wrap_width`, phân trang 2 dòng, hộp ôm sát, `\p1` drawing, PlayResY=288 |
| `build_force_style` / `hex_to_ass` / `_ass_bgr` / `_ass_alpha` / `_ass_time` | `ass.rs` | BorderStyle=3 tô hộp bằng OutlineColour; Outline>0 |
| `burn_or_mux` | `ffmpeg.rs` | burn: `h264_videotoolbox -q:v 60` + subtitles filter; soft: `mov_text`; srt: copy; escape filter path |
| `have_libass` / `video_dimensions` / `video_duration` | `ffmpeg.rs` | ffprobe/`-buildconf` |
| `subtitles.parse_srt/write_srt/shift/hide_before` | `srt.rs` | |
| `subtitles.align/extract_text/split_into_cue_texts` | `align.rs` | .docx: đọc bằng crate zip + xml |
| `process_auto` / `process_merge` | `pipeline.rs` | offset 5.5 mặc định; xoá wav tạm |

Config: model = large-v3, THREADS=8, ENCODER=hardware, VT_QUALITY=60 (mặc định, đọc từ env/config).

## 4. Màn hình Setup (first-run) + tải model

Luồng khởi động:

```
check_setup():
  ├─ binary (bundle) luôn có → OK
  └─ ~/Library/Application Support/AutoSub/models/ggml-large-v3.bin tồn tại?
        ├─ CHƯA → hiện màn Setup
        └─ RỒI  → vào thẳng UI chính (bỏ qua Setup)
```

- Màn Setup: **1 nút "Tải model large-v3 (~3GB)"** + thanh tiến trình %. Không có lựa chọn model khác.
- Tải bằng Rust (`reqwest` stream) từ HuggingFace (`ggml-large-v3.bin`), ghi ra data dir, emit `%`.
- Tải xong → chuyển UI chính. **Lần sau mở lại bỏ qua Setup hoàn toàn.**
- UI chính: dropdown Model chỉ liệt kê model đã tải (thực tế chỉ large-v3).

Vị trí lưu:

| Thứ | Chỗ |
|---|---|
| whisper-cli, ffmpeg, ffprobe | `.app/Contents/Resources` (read-only) |
| fonts, corrections.txt mặc định | bundle → seed sang data dir lần đầu |
| model `.bin`, corrections.txt (sửa được) | `~/Library/Application Support/AutoSub/` |

## 5. Chỉnh Frontend (tối thiểu)

Giữ nguyên `index.html` / `app.css`. Sửa `app.js` ở lớp giao tiếp:

| Web hiện tại | Tauri |
|---|---|
| `fetch('/api/auto', FormData)` | `invoke('run_auto', {path, opts})` |
| Poll `/status` / SSE `/events` | `listen('progress', …)` cập nhật `%` |
| `<input type=file>` + `createObjectURL` | drag-drop lấy path / dialog; preview bằng `convertFileSrc(path)` |
| Link `/download/*` | `dialog.save()` → Rust copy ra chỗ chọn, tên `<tên gốc>_sub.<ext>` |

Logic còn lại (panel kiểu chữ, preset, offset 5.5, xoá dropzone) giữ nguyên.

## 6. Đảm bảo KHÔNG SAI — golden test

1. Chuẩn bị input mẫu: câu ngắn, câu dài >2 dòng, có dấu thanh, tiếng Anh xen, nhiều màu/opacity/align.
2. Chạy hàm Python → lưu output làm "vàng" (`.srt`, `.ass`, chuỗi `force_style`).
3. Test Rust cùng input → **so khớp từng byte** với file vàng.
4. Phủ các hàm dễ lệch: `write_band_ass`, `hex_to_ass`, `apply_corrections`, `_char_frac`/wrap,
   `shift`, `hide_before`, `parse_srt`, `build_force_style`.

whisper/ffmpeg là CLI cùng cờ → không thể lệch. Rủi ro chỉ ở logic tính ASS/SRT — golden test khoá lại.

## 7. Đóng gói

- `cargo tauri build` → `AutoSub.app` + `.dmg` (arm64) — **để gửi cho user tải về**.
- Bundle: 3 binary + fonts + corrections mặc định.
- **Ký ad-hoc (miễn phí)**: `codesign --deep --force -s - AutoSub.app` ký cả app + binary con
  (ffmpeg/whisper-cli) → macOS **không giết binary con** khi user tải qua mạng. User chỉ cần
  **chuột phải → Open 1 lần** (Gatekeeper vẫn hỏi vì chưa notarize). Kèm README ngắn hướng dẫn.
  Không cần tài khoản Apple Developer. (Notarize $99/năm để hết cảnh báo — để dành bước sau.)
- Rủi ro xử lý sớm (bước đầu của plan):
  - Nguồn **ffmpeg-arm64 có libass** để bundle (verify `-buildconf` có `enable-libass`).
  - **whisper-cli self-contained** (build tĩnh từ whisper.cpp, không phụ thuộc dylib Homebrew).

## 8. Đánh giá rủi ro

Xếp theo mức nguy hiểm (khả năng × tác động).

| # | Rủi ro | Khả năng | Tác động | Giảm thiểu |
|---|---|---|---|---|
| **R1** | Bundle ffmpeg-arm64 **có libass** (Homebrew link cả cây dylib tuyệt đối, không copy-paste được) | Trung-cao | **Chí mạng** — hỏng "download & use" | **Spike bước 0**: build tĩnh *hoặc* copy dylib + `install_name_tool`; verify `-buildconf` có `enable-libass` + burn thử trong .app sạch |
| **R2** | Gatekeeper chặn binary con khi user tải .dmg qua mạng | Cao (phát cho user) | Cao | **Ký ad-hoc** cả app + binary con → binary không bị giết; user chuột phải → Open 1 lần. Kèm README |
| **R3** | Lệch logic ASS khi port: `round()` (Python banker's vs Rust away-from-zero), `{:g}`, `isupper/isdigit` trên ký tự tiếng Việt | Cao | Trung | **Golden test so từng byte**; tái hiện đúng banker's rounding + emulate `{:g}` |
| **R4** | Regex sửa từ + Unicode tiếng Việt (case-fold khác, NFC vs NFD) | Trung | Trung | Chuẩn hoá **NFC** cả hai đầu trước khi match |
| **R5** | Lấy path file trong Tauri v2 (`<input file>` không cho path; drag-drop API v2 dễ xung đột dropzone HTML5) | Trung | Trung | Dùng `dialog.open()` / sự kiện native drag-drop; test kỹ kéo-thả |
| **R6** | whisper-cli tĩnh + Metal shader trên Apple Silicon | Thấp-trung | Trung (mất tăng tốc GPU) | Verify Metal nhúng sẵn trong whisper.cpp mới |
| **R7** | Video preview cần bật `assetProtocol` + nới CSP cho `asset:` | Thấp | Thấp | Cấu hình `tauri.conf.json` |
| **R8** | Port `.docx` (merge văn bản thuần): zip+xml trong Rust | Thấp | Thấp | Làm sau cùng |
| **R9** | Kích thước .app phình ~70–90MB nếu bundle cả cây dylib | Thấp | Thấp | Chấp nhận |
| **R10** | Progress events / parse `progress=NN%` | Thấp | Thấp | `emit`/`listen` ổn định |

**Nguyên tắc giảm rủi ro:** làm **spike R1 làm bước 0** trước khi cam kết phần còn lại — nếu bundle
ffmpeg+libass không đạt thì biết sớm để tính lại (fallback: chỉ bundle whisper, ffmpeg vẫn qua `brew`).

## Ngoài phạm vi (YAGNI)

- Windows/Linux.
- Tải nhiều model / turbo (chỉ large-v3).
- **Notarization** (Apple Dev $99/năm) — chỉ ký **ad-hoc** miễn phí; notarize để dành bước sau.
- Tính năng TTS (đã gỡ trước đó).
- **Không** xoá `webapp/` Python — giữ lại chạy song song + làm golden reference.
