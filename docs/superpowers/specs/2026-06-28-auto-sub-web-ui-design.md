# Spec: Web UI cho Auto Sub

**Ngày:** 2026-06-28
**Trạng thái:** Đã duyệt thiết kế, chuẩn bị lập plan

## 1. Mục tiêu

Thêm giao diện web local cho công cụ tạo phụ đề hiện có (whisper.cpp + ffmpeg), cho phép
upload video và tải về kết quả qua trình duyệt, thay cho việc chạy script thủ công.

Hai chức năng (2 tab):
1. **Tự động tạo sub** — upload video, whisper nhận diện giọng nói, nhúng sub, tải về.
2. **Ghép sub có sẵn** — upload video + file sub của người dùng, ghép vào video. File sub có
   thể có timeline (.srt/.vtt/.ass) hoặc chỉ là văn bản thuần không timeline (.txt/.docx) —
   trường hợp sau hệ thống tự "nghe" video và căn chỉnh (forced alignment).

## 2. Quyết định đã chốt (từ brainstorming)

| Vấn đề | Quyết định |
|---|---|
| Phạm vi | Web local chạy trên máy người dùng (localhost), 1 người dùng |
| Stack | Python + Flask trong venv riêng; UI là 1 trang HTML + Tailwind (CDN) + JS thuần |
| Tùy chọn UI | Cho chọn ngôn ngữ, model, kiểu sub (cứng/mềm/srt) |
| Output | Tải về video đã nhúng sub + file .srt |
| Tiến độ | Chi tiết theo bước, có % khi parse được |
| Số lượng | 1 video mỗi lần (khóa 1 job) |
| Tab 2 — căn sub không timeline | Hướng 1: whisper nghe + align văn bản người dùng (không thêm phụ thuộc nặng) |
| Tab 2 — dạng văn bản | Tự nhận: có xuống dòng sẵn thì giữ, đoạn liền mạch thì tự cắt |
| Tab 2 — dời thời gian | Input "Bắt đầu sub từ giây thứ", mặc định 0, cho số âm |

## 3. Kiến trúc & module

```
web.sh                      # khởi chạy: tạo venv, cài flask, chạy server, mở trình duyệt
requirements.txt            # flask
webapp/
  server.py                 # Flask: route API, khóa 1-job, SSE, download
  pipeline.py               # LÕI xử lý — không phụ thuộc web, test được riêng
  subtitles.py              # tiện ích sub: parse/ghi .srt, dời offset, cắt dòng, align
  static/
    index.html              # UI 1 trang (Tailwind CDN + JS)
  jobs/                     # thư mục tạm mỗi job (gitignored)
docs/superpowers/specs/     # spec này
```

Nguyên tắc: `server.py` là lớp mỏng; toàn bộ logic xử lý nằm ở `pipeline.py` + `subtitles.py`
và dùng **đúng các lệnh ffmpeg/whisper như `run.sh`** (cùng thư mục model `~/whisper-models`,
cùng kiểm tra libass cho burn-in).

### `pipeline.py` — các hàm chính
- `transcribe(audio, lang, model, on_progress) -> srt_path` — Tab 1 (whisper → srt)
- `align_text(video, text, offset, on_progress) -> srt_path` — Tab 2, văn bản thuần
- `retime(sub_file, offset) -> srt_path` — Tab 2, sub có timeline (dời + chuẩn hoá về .srt)
- `burn_or_mux(video, srt, mode, on_progress) -> output_path` — bước nhúng dùng chung
- `process_auto(video, opts, on_progress) -> {video, srt}` — orchestrator Tab 1
- `process_merge(video, sub_file, offset, mode, on_progress) -> {video, srt}` — orchestrator Tab 2

`on_progress(step: str, percent: float|None, status: str)` là callback để đẩy tiến độ.

### `subtitles.py` — tiện ích
- `extract_text(path) -> str` — đọc `.txt` (thẳng) hoặc `.docx` (stdlib `zipfile` đọc
  `word/document.xml`, gom các đoạn `<w:p>` thành dòng; **không cần thư viện ngoài**)
- `split_into_cues(text) -> list[str]` — tự nhận: giữ dòng sẵn có; dòng quá dài (> ~90 ký tự)
  cắt theo dấu câu rồi theo độ dài
- `parse_srt(path) -> list[Cue]`, `write_srt(cues, path)`, `shift(cues, offset_seconds)`
- `align(cue_texts, whisper_words) -> list[Cue]` — gán thời gian (xem mục 5)

## 4. API (Flask)

| Route | Việc |
|---|---|
| `GET /` | Trả trang UI |
| `POST /api/auto` | multipart: video + {language, model, mode}. Lưu job, chạy nền, trả `job_id` |
| `POST /api/merge` | multipart: video + sub_file + {offset, mode}. Lưu job, chạy nền, trả `job_id` |
| `GET /api/jobs/<id>/events` | **SSE** đẩy event tiến độ realtime |
| `GET /api/jobs/<id>/download/video` | Tải video kết quả |
| `GET /api/jobs/<id>/download/srt` | Tải file .srt kết quả |

- Werkzeug stream file upload (vài GB) thẳng xuống đĩa.
- Khóa 1 job: nếu đang chạy mà có POST mới → trả **409** + thông báo "đang xử lý video khác".
- Event SSE dạng JSON: `{type: "progress"|"done"|"error", step, percent, message}`.

## 5. Thuật toán căn chỉnh (Tab 2, văn bản thuần — Hướng 1)

1. Tách audio 16kHz mono từ video (ffmpeg).
2. whisper.cpp nghe audio, xuất JSON (`-oj`) chứa **mốc thời gian theo token/từ**.
3. `extract_text` lấy văn bản; `split_into_cues` cắt thành danh sách dòng sub.
4. Chuẩn hoá (lowercase, bỏ dấu câu) chuỗi từ của người dùng và chuỗi từ whisper, dùng
   `difflib.SequenceMatcher` so khớp → mỗi từ người dùng nhận mốc thời gian của từ whisper
   tương ứng; từ không khớp thì nội suy giữa 2 mốc khớp gần nhất.
5. Mỗi dòng sub: start = thời gian từ đầu tiên, end = thời gian từ cuối (hoặc start dòng kế).
6. Dự phòng: nếu tỉ lệ khớp quá thấp → chia đều các dòng theo các đoạn có tiếng nói của whisper.
7. `write_srt` → `shift(offset)` → `burn_or_mux`.

## 6. Luồng tiến độ (các bước theo từng trường hợp)

| Trường hợp | Các bước hiển thị |
|---|---|
| Tab 1 (tự động) | Tách audio → Nhận diện giọng nói (%) → Nhúng (%) |
| Tab 2, sub có timeline | Chuẩn bị sub → Nhúng (%) |
| Tab 2, văn bản thuần | Tách audio → Nhận diện & căn chỉnh (%) → Nhúng (%) |

% lấy từ: whisper (`progress = N%` trên stderr) và ffmpeg burn (`-progress`, tính theo thời lượng).

## 7. Frontend (Tailwind CDN + JS thuần)

- Thanh tab: **[Tự động tạo sub] [Ghép sub có sẵn]**
- Tab 1: vùng kéo-thả video; select ngôn ngữ / model / kiểu sub; nút "Bắt đầu".
- Tab 2: 2 ô chọn (video, file sub); input số "Bắt đầu sub từ giây thứ" (default 0);
  select kiểu ghép; nút "Ghép phụ đề".
- Vùng tiến độ: danh sách bước với trạng thái (○ chờ / ⟳ đang chạy + % / ✓ xong), nghe SSE.
- Khi xong: nút "⬇ Tải video có sub" và "⬇ Tải .srt".
- Lỗi: hộp đỏ kèm thông điệp lý do.

> Tailwind nạp qua `https://cdn.tailwindcss.com` (cần mạng lúc mở UI). Nếu cần chạy offline
> hoàn toàn, tải sẵn 1 bản Tailwind về `static/` (ngoài phạm vi bản đầu).

## 8. Xử lý lỗi

- Mode `burn` mà ffmpeg thiếu libass → lỗi rõ ràng + gợi ý chạy `./install.sh` hoặc đổi sub mềm.
- Thiếu model whisper → lỗi rõ + gợi ý `./install.sh`.
- File upload sai đuôi (không phải video / sub không hỗ trợ) → từ chối kèm thông báo.
- Mỗi bước pipeline bọc try/except → đẩy event `error` + dừng; tự dọn file tạm (audio.wav).
- Đang bận job khác → 409.

## 9. Khởi chạy (`web.sh`)

1. Tạo `.venv` nếu chưa có; `pip install -r requirements.txt` (chỉ Flask — thuần Python, cài
   sạch trên Python 3.14).
2. Chạy `python webapp/server.py` (mặc định cổng 5005).
3. Mở trình duyệt tới `http://localhost:5005`.

`install.sh` bổ sung 1 dòng nhắc: sau khi cài xong có thể chạy `./web.sh` để mở UI.

## 10. Test

- `subtitles.py`: unit test cho `extract_text` (.txt/.docx mẫu), `split_into_cues`,
  `parse/write/shift srt`, và `align` với cặp (văn bản, danh sách từ-thời gian) giả lập.
- `pipeline.py`: test với clip ngắn (tạo từ mẫu jfk) — mode `srt` (nhanh, không encode) để
  kiểm tra ra file; smoke test `burn_or_mux`.
- Server: smoke test `GET /` 200; POST clip nhỏ → đọc SSE tới `done` → download trả file.

## 11. Ngoài phạm vi (YAGNI)

- Hàng đợi nhiều video, đa người dùng, xác thực.
- Sửa .srt trực tiếp trên UI (vẫn tải .srt về sửa tay được).
- Tailwind offline đóng gói sẵn.
- App desktop.
- Forced alignment bằng model chuyên dụng (aeneas/WhisperX).
