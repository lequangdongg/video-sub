# Plan 3 & 4 — Nối whisper/ffmpeg + Ghép sub (đã thực thi)

> Ghi lại sau khi thực thi (đã hoàn tất). Chi tiết trong git history nhánh `feat/tauri-desktop`.

## Plan 3 — Auto-sub end-to-end (đã xong)

**Backend Rust:**
- `tools.rs` — resolve đường dẫn binary/fonts/corrections (Resources của app, fallback dev `src-tauri/`).
- `ffmpeg.rs` — `extract_audio`, `video_dimensions`, `video_duration`, `burn_or_mux` (spawn ffmpeg bundle;
  box → `write_band_ass`, else `force_style`; `h264_videotoolbox`; progress qua `-progress pipe:1`).
- `whisper.rs` — `transcribe` (spawn whisper-cli `-bs 5 -bo 5 -fa -pp -osrt`, parse `progress=NN%`,
  áp `apply_corrections`).
- `pipeline.rs::process_auto` — tách audio → whisper → (offset `hide_before`) → burn/mux.
- `commands.rs` — `run_auto` (spawn_blocking, emit `progress`), `save_file`.
- Capabilities `capabilities/default.json` — core + dialog.

**Frontend (`app.js`, chỉ nhánh `window.__TAURI__`):**
- Chọn video: `dialog.open` (click) + `getCurrentWebview().onDragDropEvent` (kéo-thả) → path → preview `convertFileSrc`.
- `run_auto` qua `invoke`, tiến trình qua `listen("progress")`, tải về `dialog.save` + `save_file`.

**Verified:** test `#[ignore] full_auto_pipeline_smoke` — tạo video có tiếng (macOS `say`) →
whisper large-v3 nhận đúng → burn hộp nền → video h264 hợp lệ. Chạy: `cargo test --release -- --ignored full_auto`.

## Plan 4 — Ghép sub (đã xong)

**Backend:**
- `align.rs` — `parse_word_timings`, `word_timings` (whisper `-ojf`), `extract_text` (.txt/.docx qua `zip`),
  `split_into_cue_texts`, và `align` (port `difflib.SequenceMatcher` — `find_longest_match`/`matching_blocks`/
  `interp` — khớp Python).
- `pipeline.rs::process_merge` — sub timeline (.srt/.vtt/.ass) → shift; văn bản thuần (.txt/.docx) → whisper
  word timings + align + shift; rồi burn/mux.
- `commands.rs::run_merge`.

**Frontend:** tab "Ghép sub" — chọn sub qua `dialog.open`, `run_merge` qua `invoke`.

**Verified:** golden test `parse_word_timings`/`split_cues`/`align` khớp Python (20 test tổng, `cargo test`).

## Trạng thái kiểm thử

- ✅ 20 golden test (byte-to-byte với Python) + 1 smoke test end-to-end.
- ✅ Build `.dmg` ký ad-hoc, app mở & điều hướng Setup/skip.
- ⏳ Cần user bấm thử trong app: chọn/kéo-thả video, Tạo sub, Ghép sub, Tải về (GUI).

## Còn lại (tuỳ chọn, ngoài phạm vi 4 plan)

- Notarize (nếu phát rộng, $99/năm).
- Xoá thư mục `webapp/` Python (đang giữ làm golden reference — theo yêu cầu **không xoá**).
