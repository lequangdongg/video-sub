# Plan 1 — Nền tảng & Khử rủi ro (Tauri Desktop App) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng bộ khung Tauri v2 chạy được trên macOS arm64, bundle sẵn `ffmpeg`(có libass) + `whisper-cli` + `ffprobe`, có màn hình Setup tải model large-v3, và xuất `.dmg` ký ad-hoc — chứng minh hướng "download & use" khả thi trước khi port pipeline.

**Architecture:** Hybrid Tauri (lõi Rust + webview dùng `webapp/static` hiện có). Binary media bundle trong `.app/Contents/Resources`. Model tải về `~/Library/Application Support/AutoSub/models/`. Frontend gọi Rust bằng `invoke`, tiến trình đẩy qua `emit`/`listen`.

**Tech Stack:** Rust, Tauri v2, `reqwest` (tải model), `dirs` (data dir), whisper.cpp (build tĩnh), ffmpeg static arm64 (có libass), `codesign` (ad-hoc).

**Spec:** `docs/superpowers/specs/2026-07-23-tauri-desktop-app-design.md`

---

## File Structure (tạo trong Plan 1)

```
src-tauri/
├─ Cargo.toml
├─ tauri.conf.json
├─ build.rs
├─ src/
│  ├─ main.rs          # bootstrap + đăng ký commands
│  ├─ setup.rs         # data_dir / model_path / model_exists / MODEL_URL / download_model
│  └─ commands.rs      # check_setup, download_model (Tauri commands, mỏng — gọi setup.rs)
├─ binaries/           # ffmpeg, ffprobe, whisper-cli (arm64) — bundle
└─ icons/              # icon mặc định tauri
webapp/static/
├─ setup.html          # màn Setup (mới)
└─ setup.js            # logic tải model (mới)
scripts/
└─ fetch-binaries.sh   # lấy/dựng 3 binary vào src-tauri/binaries (spike R1)
```

`main.rs` mỏng (bootstrap + register). `setup.rs` chứa toàn bộ logic thuần (có unit test). `commands.rs` chỉ là lớp `#[tauri::command]` mỏng gọi `setup.rs`.

---

## Task 0: Cài toolchain Rust + Tauri CLI

**Files:** none (môi trường)

- [ ] **Step 1: Cài Rust**

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
```

- [ ] **Step 2: Verify**

Run: `rustc --version && cargo --version`
Expected: in ra `rustc 1.x` và `cargo 1.x` (không còn MISSING).

- [ ] **Step 3: Cài Tauri CLI**

```bash
cargo install tauri-cli --version "^2.0.0"
```

- [ ] **Step 4: Verify**

Run: `cargo tauri --version`
Expected: in ra `tauri-cli 2.x`.

---

## Task 1: Spike R1 — dựng 3 binary bundle (CỔNG GÁC)

**Mục tiêu:** có `src-tauri/binaries/{ffmpeg,ffprobe,whisper-cli}` chạy độc lập, ffmpeg **có libass**, whisper-cli không phụ thuộc dylib Homebrew. **Nếu task này thất bại, DỪNG và báo lại — cả plan phụ thuộc vào đây.**

**Files:**
- Create: `scripts/fetch-binaries.sh`
- Create: `src-tauri/binaries/` (chứa 3 binary)

- [ ] **Step 1: Tạo thư mục**

```bash
mkdir -p src-tauri/binaries scripts
```

- [ ] **Step 2: Build whisper-cli TĨNH từ whisper.cpp**

```bash
cd /tmp && rm -rf whisper.cpp && git clone --depth 1 https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
cmake -B build -DBUILD_SHARED_LIBS=OFF -DCMAKE_BUILD_TYPE=Release -DWHISPER_METAL=ON
cmake --build build -j --config Release
```

- [ ] **Step 3: Copy whisper-cli vào binaries + kiểm phụ thuộc dylib**

```bash
cp /tmp/whisper.cpp/build/bin/whisper-cli src-tauri/binaries/whisper-cli
otool -L src-tauri/binaries/whisper-cli
```

Expected: chỉ thấy `/usr/lib/*` và `/System/Library/Frameworks/*` (Metal, Accelerate). **KHÔNG** được có `/opt/homebrew/...`. Nếu có → build lại với `-DBUILD_SHARED_LIBS=OFF`.

- [ ] **Step 4: Lấy ffmpeg + ffprobe static arm64 có libass**

```bash
# Nguồn static arm64 có libass (osxexperts). Nếu link đổi, tìm build "ffmpeg 7.x arm64 static".
cd /tmp
curl -L -o ffmpeg.zip https://www.osxexperts.net/ffmpeg711arm.zip
curl -L -o ffprobe.zip https://www.osxexperts.net/ffprobe711arm.zip
unzip -o ffmpeg.zip && unzip -o ffprobe.zip
cp /tmp/ffmpeg /Users/dongquang/Desktop/audio_translate/src-tauri/binaries/ffmpeg
cp /tmp/ffprobe /Users/dongquang/Desktop/audio_translate/src-tauri/binaries/ffprobe
chmod +x /Users/dongquang/Desktop/audio_translate/src-tauri/binaries/*
```

Ghi lại các lệnh trên vào `scripts/fetch-binaries.sh` để tái lập.

- [ ] **Step 5: Verify ffmpeg CÓ libass + không phụ thuộc Homebrew**

Run:
```bash
./src-tauri/binaries/ffmpeg -hide_banner -buildconf | grep -q enable-libass && echo "LIBASS OK" || echo "LIBASS MISSING"
otool -L src-tauri/binaries/ffmpeg | grep -c /opt/homebrew
```
Expected: `LIBASS OK` và số đếm homebrew = `0`. Nếu `LIBASS MISSING` → đổi nguồn hoặc build ffmpeg từ source với `--enable-libass` (fallback R1).

- [ ] **Step 6: Burn thử end-to-end bằng đúng binary bundle (bằng chứng spike đạt)**

Run:
```bash
# tạo clip test 3s + srt tối thiểu
./src-tauri/binaries/ffmpeg -y -f lavfi -i color=c=black:s=640x360:d=3 -f lavfi -i sine=frequency=440:d=3 /tmp/t.mp4
printf '1\n00:00:00,000 --> 00:00:02,000\nxin chao\n' > /tmp/t.srt
./src-tauri/binaries/ffmpeg -y -i /tmp/t.mp4 -vf "subtitles=/tmp/t.srt" -c:v h264_videotoolbox /tmp/out.mp4
ls -la /tmp/out.mp4
```
Expected: `/tmp/out.mp4` tồn tại, size > 0, ffmpeg không lỗi. → **Spike R1 ĐẠT.**

- [ ] **Step 7: Commit**

```bash
git add scripts/fetch-binaries.sh
git commit -m "chore(tauri): spike R1 — bundle ffmpeg(libass)+whisper-cli arm64, burn test OK"
```
(Không commit binary vào git — thêm `src-tauri/binaries/` vào `.gitignore` ở Task 2 Step 4.)

---

## Task 2: Scaffold Tauri v2 trỏ vào webapp/static

**Files:**
- Create: `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`, `src-tauri/build.rs`, `src-tauri/src/main.rs`
- Modify: `.gitignore`

- [ ] **Step 1: Khởi tạo khung Tauri (không tạo project mới, cấu hình tay để dùng webapp/static)**

Tạo `src-tauri/Cargo.toml`:
```toml
[package]
name = "autosub"
version = "0.1.0"
edition = "2021"

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2", features = [] }
tauri-plugin-dialog = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
reqwest = { version = "0.12", features = ["stream"] }
tokio = { version = "1", features = ["full"] }
futures-util = "0.3"
dirs = "5"

[lib]
name = "autosub_lib"
crate-type = ["staticlib", "cdylib", "rlib"]
```

- [ ] **Step 2: `src-tauri/build.rs`**

```rust
fn main() {
    tauri_build::build()
}
```

- [ ] **Step 3: `src-tauri/tauri.conf.json`** (frontend = webapp/static, bundle binary + fonts)

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "AutoSub",
  "version": "0.1.0",
  "identifier": "com.dong.autosub",
  "build": {
    "frontendDist": "../webapp/static"
  },
  "app": {
    "windows": [
      { "title": "Auto Sub", "width": 1100, "height": 820 }
    ],
    "security": {
      "csp": "default-src 'self'; media-src 'self' asset: http://asset.localhost; img-src 'self' asset: http://asset.localhost data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'",
      "assetProtocol": { "enable": true, "scope": ["**"] }
    }
  },
  "bundle": {
    "active": true,
    "targets": ["dmg", "app"],
    "resources": {
      "binaries/ffmpeg": "binaries/ffmpeg",
      "binaries/ffprobe": "binaries/ffprobe",
      "binaries/whisper-cli": "binaries/whisper-cli",
      "../assets/fonts": "assets/fonts",
      "../webapp/corrections.txt": "corrections.txt"
    }
  }
}
```

- [ ] **Step 4: `.gitignore` — bỏ qua binary + target**

Thêm vào `.gitignore`:
```
/src-tauri/binaries/
/src-tauri/target/
/src-tauri/gen/
```

- [ ] **Step 5: `src-tauri/src/main.rs` tối thiểu (chạy được)**

```rust
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod setup;
mod commands;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            commands::check_setup,
            commands::download_model
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

- [ ] **Step 6: Verify build khung compile** (sau khi Task 3+4 tạo setup.rs/commands.rs; tạm thời stub để compile)

Run: `cd src-tauri && cargo build 2>&1 | tail -5`
Expected: compile được (có thể cần stub `setup.rs`/`commands.rs` ở Task 3–4 trước). Nếu chạy Task theo thứ tự, verify ở cuối Task 4.

- [ ] **Step 7: Commit**

```bash
git add src-tauri/Cargo.toml src-tauri/build.rs src-tauri/tauri.conf.json src-tauri/src/main.rs .gitignore
git commit -m "feat(tauri): scaffold Tauri v2 shell trỏ vào webapp/static"
```

---

## Task 3: `setup.rs` — đường dẫn data dir + kiểm model (TDD)

**Files:**
- Create: `src-tauri/src/setup.rs`
- Test: cùng file (`#[cfg(test)] mod tests`)

- [ ] **Step 1: Viết test thất bại**

Trong `src-tauri/src/setup.rs`:
```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn model_filename_is_large_v3() {
        assert_eq!(model_filename(), "ggml-large-v3.bin");
    }

    #[test]
    fn model_url_points_to_huggingface_large_v3() {
        assert_eq!(
            model_url(),
            "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin"
        );
    }

    #[test]
    fn model_path_is_under_models_subdir() {
        let p = model_path();
        assert!(p.ends_with("AutoSub/models/ggml-large-v3.bin"));
    }
}
```

- [ ] **Step 2: Chạy test — xác nhận fail**

Run: `cd src-tauri && cargo test --lib setup 2>&1 | tail -20`
Expected: FAIL — `cannot find function model_filename` (chưa định nghĩa).

- [ ] **Step 3: Cài đặt tối thiểu**

Đầu file `src-tauri/src/setup.rs`:
```rust
use std::path::PathBuf;

pub const MODEL: &str = "large-v3";

pub fn model_filename() -> String {
    format!("ggml-{}.bin", MODEL)
}

pub fn model_url() -> String {
    format!(
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{}",
        model_filename()
    )
}

pub fn data_dir() -> PathBuf {
    // ~/Library/Application Support/AutoSub
    dirs::data_dir().unwrap_or_else(|| PathBuf::from(".")).join("AutoSub")
}

pub fn models_dir() -> PathBuf {
    data_dir().join("models")
}

pub fn model_path() -> PathBuf {
    models_dir().join(model_filename())
}

pub fn model_exists() -> bool {
    model_path().exists()
}
```

- [ ] **Step 4: Chạy test — xác nhận pass**

Run: `cd src-tauri && cargo test --lib setup 2>&1 | tail -20`
Expected: PASS 3 test. (Lưu ý `model_path()` trả `PathBuf`; test dùng `.ends_with` trên `Path` — nếu cần đổi sang so `to_string_lossy().ends_with(...)`.)

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/setup.rs
git commit -m "feat(setup): data dir + model path/url cho large-v3 (TDD)"
```

---

## Task 4: `download_model` với tiến trình + `check_setup` (TDD phần tính %)

**Files:**
- Modify: `src-tauri/src/setup.rs` (thêm `pct` + `download_model`)
- Create: `src-tauri/src/commands.rs`

- [ ] **Step 1: Viết test thất bại cho hàm tính %**

Thêm vào `mod tests` của `setup.rs`:
```rust
#[test]
fn pct_is_ratio_times_100_capped() {
    assert_eq!(download_pct(0, 100), 0.0);
    assert_eq!(download_pct(50, 100), 50.0);
    assert_eq!(download_pct(100, 100), 100.0);
}

#[test]
fn pct_zero_total_returns_zero() {
    assert_eq!(download_pct(10, 0), 0.0);
}
```

- [ ] **Step 2: Chạy test — xác nhận fail**

Run: `cd src-tauri && cargo test --lib setup 2>&1 | tail -20`
Expected: FAIL — `cannot find function download_pct`.

- [ ] **Step 3: Cài đặt `download_pct` + `download_model`**

Thêm vào `setup.rs`:
```rust
use futures_util::StreamExt;
use std::fs;
use std::io::Write;

pub fn download_pct(done: u64, total: u64) -> f64 {
    if total == 0 { return 0.0; }
    ((done as f64 / total as f64) * 100.0).min(100.0)
}

/// Tải model large-v3 về models_dir, gọi `on_pct(percent)` khi có tiến triển.
pub async fn download_model<F: Fn(f64)>(on_pct: F) -> Result<(), String> {
    if model_exists() {
        on_pct(100.0);
        return Ok(());
    }
    fs::create_dir_all(models_dir()).map_err(|e| e.to_string())?;
    let tmp = model_path().with_extension("part");

    let resp = reqwest::get(model_url()).await.map_err(|e| e.to_string())?;
    let total = resp.content_length().unwrap_or(0);
    let mut file = fs::File::create(&tmp).map_err(|e| e.to_string())?;
    let mut done: u64 = 0;
    let mut stream = resp.bytes_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| e.to_string())?;
        file.write_all(&chunk).map_err(|e| e.to_string())?;
        done += chunk.len() as u64;
        on_pct(download_pct(done, total));
    }
    file.flush().map_err(|e| e.to_string())?;
    fs::rename(&tmp, model_path()).map_err(|e| e.to_string())?;   // atomic: chỉ đổi tên khi xong
    on_pct(100.0);
    Ok(())
}
```

- [ ] **Step 4: Chạy test — xác nhận pass**

Run: `cd src-tauri && cargo test --lib setup 2>&1 | tail -20`
Expected: PASS (4 test cũ + 2 test %).

- [ ] **Step 5: `src-tauri/src/commands.rs` — lớp Tauri mỏng**

```rust
use crate::setup;
use tauri::{Emitter, Window};

#[tauri::command]
pub fn check_setup() -> bool {
    setup::model_exists()
}

#[tauri::command]
pub async fn download_model(window: Window) -> Result<(), String> {
    setup::download_model(|pct| {
        let _ = window.emit("model-progress", pct);
    })
    .await
}
```

- [ ] **Step 6: Verify toàn bộ compile + test**

Run: `cd src-tauri && cargo build 2>&1 | tail -5 && cargo test --lib 2>&1 | tail -10`
Expected: build OK, test PASS.

- [ ] **Step 7: Commit**

```bash
git add src-tauri/src/setup.rs src-tauri/src/commands.rs
git commit -m "feat(setup): download_model có tiến trình + commands check_setup/download_model"
```

---

## Task 5: Màn hình Setup (frontend) + điều hướng

**Files:**
- Create: `webapp/static/setup.html`, `webapp/static/setup.js`
- Modify: `webapp/static/app.js` (chèn cổng check_setup khi vào app)

- [ ] **Step 1: `webapp/static/setup.html`**

```html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Cài đặt — Auto Sub</title>
<link rel="stylesheet" href="/app.css"></head>
<body>
  <main style="max-width:520px;margin:12vh auto;text-align:center;font-family:system-ui">
    <h1>Auto Sub</h1>
    <p>Cần tải model nhận diện giọng nói <b>large-v3</b> (~3GB) trước khi dùng.</p>
    <button id="dl" style="padding:12px 20px;font-size:16px">⬇ Tải model large-v3</button>
    <div id="bar" style="display:none;margin-top:20px">
      <div style="height:10px;background:#eee;border-radius:6px;overflow:hidden">
        <div id="fill" style="height:100%;width:0;background:#2563eb"></div>
      </div>
      <p id="pct">0%</p>
    </div>
  </main>
  <script type="module" src="/setup.js"></script>
</body>
</html>
```

- [ ] **Step 2: `webapp/static/setup.js`**

```js
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const dl = document.getElementById("dl");
const bar = document.getElementById("bar");
const fill = document.getElementById("fill");
const pct = document.getElementById("pct");

listen("model-progress", (e) => {
  const p = Math.round(e.payload);
  fill.style.width = p + "%";
  pct.textContent = p + "%";
});

dl.addEventListener("click", async () => {
  dl.disabled = true;
  bar.style.display = "block";
  try {
    await invoke("download_model");
    location.href = "/index.html";      // xong -> vào app chính
  } catch (err) {
    pct.textContent = "Lỗi: " + err;
    dl.disabled = false;
  }
});
```

- [ ] **Step 3: Chèn cổng vào đầu `webapp/static/app.js`**

Thêm ngay đầu file (bọc trong IIFE để không phá logic cũ):
```js
// Cổng Setup: nếu chạy trong Tauri và chưa có model -> chuyển sang màn Setup.
if (window.__TAURI__) {
  window.__TAURI__.core.invoke("check_setup").then((ready) => {
    if (!ready) location.href = "/setup.html";
  });
}
```

- [ ] **Step 4: Chạy app dev, kiểm điều hướng**

Run: `cd src-tauri && cargo tauri dev`
Expected: cửa sổ mở; vì chưa có model → app tự chuyển sang `setup.html`. Bấm "Tải model" → thanh % chạy. (Có thể huỷ giữa chừng để khỏi tải hết 3GB khi test; kiểm % nhảy là đủ.)

- [ ] **Step 5: Commit**

```bash
git add webapp/static/setup.html webapp/static/setup.js webapp/static/app.js
git commit -m "feat(ui): màn Setup tải model + cổng check_setup khi vào app"
```

---

## Task 6: Đóng gói `.dmg` + ký ad-hoc + verify launch

**Files:**
- Create: `scripts/build-dmg.sh`
- Create: `DIST-README.md` (hướng dẫn user mở lần đầu)

- [ ] **Step 1: Build bản release**

Run: `cd src-tauri && cargo tauri build 2>&1 | tail -20`
Expected: tạo `src-tauri/target/release/bundle/macos/AutoSub.app` và `.../dmg/AutoSub_0.1.0_aarch64.dmg`.

- [ ] **Step 2: Ký ad-hoc cả app + binary con**

Tạo `scripts/build-dmg.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
APP="src-tauri/target/release/bundle/macos/AutoSub.app"
# ký binary con trước (bên trong Resources), rồi ký app ngoài cùng
find "$APP/Contents/Resources/binaries" -type f -exec codesign --force -s - {} \;
codesign --deep --force -s - "$APP"
codesign --verify --deep --verbose=2 "$APP"
```
Run: `chmod +x scripts/build-dmg.sh && ./scripts/build-dmg.sh`
Expected: `codesign --verify` in `valid on disk` / `satisfies its Designated Requirement`.

- [ ] **Step 3: Verify app chạy được từ bản đã ký (mô phỏng quarantine)**

Run:
```bash
xattr -w com.apple.quarantine "0081;00000000;Safari;" "src-tauri/target/release/bundle/macos/AutoSub.app" 2>/dev/null || true
open "src-tauri/target/release/bundle/macos/AutoSub.app"
```
Expected: app mở (lần đầu có thể phải chuột phải → Open). Binary con **không** bị macOS giết (nhờ ad-hoc sign). Nếu bị chặn → kiểm lại `find ... codesign` ở Step 2 đã ký hết binary chưa.

- [ ] **Step 4: `DIST-README.md` — hướng dẫn user**

```markdown
# Auto Sub — cách mở lần đầu

1. Mở file `.dmg`, kéo **AutoSub** vào thư mục Applications.
2. Lần đầu mở: **chuột phải vào AutoSub → Open → Open** (vì app chưa notarize).
3. Bấm **Tải model large-v3** (~3GB, chỉ lần đầu). Xong là dùng được.

Nếu vẫn báo chặn, mở Terminal chạy:
    xattr -dr com.apple.quarantine /Applications/AutoSub.app
```

- [ ] **Step 5: Commit**

```bash
git add scripts/build-dmg.sh DIST-README.md
git commit -m "feat(dist): đóng gói .dmg + ký ad-hoc + hướng dẫn mở lần đầu"
```

---

## Self-Review (đã kiểm khi viết plan)

- **Spec coverage:** bundle binary (mục 7 ✓ T1), scaffold Hybrid (mục 1–2 ✓ T2), Setup + tải large-v3 nhớ trạng thái (mục 4 ✓ T3–T5), `.dmg` + ad-hoc sign (mục 7/R2 ✓ T6), CSP asset cho preview (R7 ✓ T2 conf). Port pipeline + golden test (mục 3/6) và frontend đầy đủ (mục 5) → **thuộc Plan 2/3, ngoài phạm vi P1** (có chủ đích).
- **Placeholder:** không còn TBD/TODO; mọi step có lệnh/mã cụ thể. Nguồn ffmpeg static có ghi chú fallback build-from-source nếu link/đặc điểm libass đổi.
- **Type consistency:** `model_filename/model_url/model_path/model_exists/download_pct/download_model` dùng thống nhất giữa `setup.rs` và `commands.rs`; event tên `model-progress` khớp giữa Rust `emit` và JS `listen`; command `check_setup`/`download_model` khớp `generate_handler!` và JS `invoke`.

## Điều kiện chuyển Plan 2

Chỉ sang Plan 2 (port pipeline + golden test) khi: Task 1 spike ĐẠT (ffmpeg libass OK, burn test ra file), app dev điều hướng Setup↔index chạy, `.dmg` ký ad-hoc mở được sau khi gắn cờ quarantine.
