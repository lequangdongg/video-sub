# Plan 2 — Port lõi pipeline sang Rust + Golden test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port các phép biến đổi tất định của luồng auto-sub (parse/ghi SRT, sinh ASS nền băng, force_style, sửa từ) từ Python sang Rust, **khớp từng byte với bản Python** qua golden test.

**Architecture:** Thêm module thuần Rust `srt.rs`, `ass.rs`, `corrections.rs` trong `src-tauri/src/`. Không spawn tiến trình ở Plan này (whisper/ffmpeg là Plan 3). Golden fixture sinh từ chính hàm Python hiện có (`webapp/`), Rust đọc fixture JSON và assert bằng.

**Tech Stack:** Rust, `serde_json` (đọc fixture), `regex` + `unicode-normalization` (corrections), Python (sinh golden).

**Spec:** `docs/superpowers/specs/2026-07-23-tauri-desktop-app-design.md` (mục 3, 6)

**Nguồn Python để đối chiếu:** `webapp/pipeline.py`, `webapp/subtitles.py`

**Ngoài phạm vi (để Plan 3/4):** spawn whisper-cli/ffmpeg, `align`/`word_timings`/`.docx` (SequenceMatcher — Plan 4), nối commands/frontend (Plan 3).

---

## File Structure (Plan 2)

```
src-tauri/
├─ src/
│  ├─ srt.rs          # Cue, parse_ts/format_ts, parse_srt, write_srt, shift, hide_before
│  ├─ ass.rs          # round_half_even, fmt_g, hex_to_ass, ass_bgr, ass_alpha, ass_time,
│  │                  #   char_frac/line_width/wrap_width, build_force_style, write_band_ass
│  ├─ corrections.rs  # load_corrections, apply_corrections
│  └─ main.rs         # thêm `mod srt; mod ass; mod corrections;`
└─ tests/golden/      # *.json sinh từ Python
scripts/
└─ gen-golden.py      # sinh fixture từ webapp/*.py
```

Ba module thuần, không phụ thuộc Tauri → test nhanh bằng `cargo test`.

---

## Task 1: Bộ sinh golden + khai báo module + crate deps

**Files:**
- Create: `scripts/gen-golden.py`
- Create: `src-tauri/tests/golden/.gitkeep`
- Modify: `src-tauri/Cargo.toml` (thêm dev/deps: regex, unicode-normalization)
- Modify: `src-tauri/src/main.rs` (khai báo module)

- [ ] **Step 1: Thêm deps vào `src-tauri/Cargo.toml`**

Trong `[dependencies]` thêm:
```toml
regex = "1"
unicode-normalization = "0.1"
```

- [ ] **Step 2: Khai báo module trong `src-tauri/src/main.rs`**

Ngay dưới `mod commands;` thêm:
```rust
mod srt;
mod ass;
mod corrections;
```

- [ ] **Step 3: Tạo bộ sinh golden `scripts/gen-golden.py`**

```python
#!/usr/bin/env python3
"""Sinh golden fixture từ hàm Python hiện có để Rust đối chiếu byte-to-byte."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from webapp import subtitles, pipeline
from webapp.subtitles import Cue

OUT = os.path.join(ROOT, "src-tauri", "tests", "golden")
os.makedirs(OUT, exist_ok=True)

def dump(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# --- SRT round-trip / shift / hide_before ---
srt_text = (
    "1\n00:00:01,000 --> 00:00:02,500\nxin chào\n\n"
    "2\n00:00:03,000 --> 00:00:05,000\nnôn mưởng nhé\n"
)
tmp = os.path.join(OUT, "_in.srt")
open(tmp, "w", encoding="utf-8").write(srt_text)
cues = subtitles.parse_srt(tmp)
dump("srt_parse.json", [{"start": c.start, "end": c.end, "text": c.text} for c in cues])
outp = os.path.join(OUT, "_out.srt")
subtitles.write_srt(cues, outp)
dump("srt_write.json", {"content": open(outp, encoding="utf-8").read()})
sh = subtitles.shift(cues, 5.5)
dump("srt_shift.json", [{"start": c.start, "end": c.end, "text": c.text} for c in sh])
hb = subtitles.hide_before(cues, 2.0)
dump("srt_hide.json", [{"start": c.start, "end": c.end, "text": c.text} for c in hb])

# --- ass helpers ---
dump("ass_helpers.json", {
    "hex_black_opaque": pipeline.hex_to_ass("#000000", 0.0),
    "hex_white": pipeline.hex_to_ass("#ffffff"),
    "hex_blue_semi": pipeline.hex_to_ass("#2563eb", 0.25),
    "bgr_black": pipeline._ass_bgr("#000000"),
    "bgr_blue": pipeline._ass_bgr("#2563eb"),
    "alpha_1": pipeline._ass_alpha(1.0),
    "alpha_025": pipeline._ass_alpha(0.25),
    "time_0": pipeline._ass_time(0.0),
    "time_65_321": pipeline._ass_time(65.321),
    "time_neg": pipeline._ass_time(-3.0),
})

# --- char width / wrap ---
dump("wrap.json", {
    "w_short": pipeline._line_width("xin chào", 16.0, True),
    "wrap_long": pipeline._wrap_width(
        "đây là một câu rất dài để kiểm tra việc xuống dòng theo bề rộng hộp nền", 16.0, True, 120.0),
})

# --- build_force_style ---
style_box = {"font": "UTM Avo", "size": "16", "bold": True, "box": True,
             "box_color": "#000000", "box_opacity": 0.25, "outline": 4,
             "align": "bottom", "margin": 24, "fill": "#ffffff"}
style_stroke = {"font": "UTM Avo", "size": "18", "bold": False, "fill": "#ffff00",
                "outline": 2, "outline_color": "#000000", "outline_opacity": 1.0,
                "align": "bottom", "margin": 30}
dump("force_style.json", {
    "box": pipeline.build_force_style(style_box),
    "stroke": pipeline.build_force_style(style_stroke),
    "none": pipeline.build_force_style(None),
})

# --- write_band_ass (crown jewel) ---
cues2 = [
    Cue(1.0, 3.0, "xin chào các bạn"),
    Cue(3.0, 8.0, "đây là một câu rất dài cần xuống dòng và tách trang để kiểm tra hộp nền băng ngang ôm sát chữ"),
]
ass_path = os.path.join(OUT, "_band.ass")
pipeline.write_band_ass(cues2, ass_path, style_box, 1920, 1080)
dump("band_ass.json", {"content": open(ass_path, encoding="utf-8").read(),
                       "width": 1920, "height": 1080})

# --- corrections ---
corr = os.path.join(OUT, "_corr.txt")
open(corr, "w", encoding="utf-8").write("# ghi chú\nnôn mưởng => nôn mửa\nhà nội => Hà Nội\n")
srt2 = os.path.join(OUT, "_c.srt")
open(srt2, "w", encoding="utf-8").write(
    "1\n00:00:01,000 --> 00:00:02,000\nNôn mưởng quá\n\n"
    "2\n00:00:03,000 --> 00:00:04,000\ntôi ở hà nội\n")
old = pipeline.CORRECTIONS_FILE
pipeline.CORRECTIONS_FILE = corr
pipeline.apply_corrections(srt2)
pipeline.CORRECTIONS_FILE = old
dump("corrections.json", {"content": open(srt2, encoding="utf-8").read()})

for f in ["_in.srt", "_out.srt", "_band.ass", "_corr.txt", "_c.srt"]:
    p = os.path.join(OUT, f)
    if os.path.exists(p): os.remove(p)
print("golden written to", OUT)
```

- [ ] **Step 4: Chạy sinh golden**

Run: `cd /Users/dongquang/Desktop/audio_translate && .venv/bin/python scripts/gen-golden.py`
Expected: in `golden written to .../src-tauri/tests/golden`, có các file `srt_parse.json`, `band_ass.json`, … Không commit `_*.tmp` (đã tự xoá).

- [ ] **Step 5: `.gitkeep` + verify build vẫn xanh**

```bash
touch src-tauri/tests/golden/.gitkeep
```
Run: `cd src-tauri && cargo build 2>&1 | tail -3`
Expected: compile OK (module rỗng chưa có nội dung — tạo file rỗng `srt.rs`/`ass.rs`/`corrections.rs` với 1 dòng `// placeholder` để `mod` không lỗi; các Task sau điền vào).

- [ ] **Step 6: Commit**

```bash
git add scripts/gen-golden.py src-tauri/Cargo.toml src-tauri/Cargo.lock src-tauri/src/main.rs src-tauri/tests/golden
git commit -m "chore(port): bộ sinh golden + khai báo module srt/ass/corrections"
```

---

## Task 2: `srt.rs` — parse/format/shift/hide_before

**Files:**
- Create/replace: `src-tauri/src/srt.rs`
- Golden: `srt_parse.json`, `srt_write.json`, `srt_shift.json`, `srt_hide.json`

- [ ] **Step 1: Viết `srt.rs` với test đọc golden (test trước, sẽ fail vì chưa có hàm)**

```rust
use std::path::Path;

#[derive(Debug, Clone, PartialEq)]
pub struct Cue {
    pub start: f64,
    pub end: f64,
    pub text: String,
}

/// giây -> "HH:MM:SS,mmm" (khớp format_ts của Python: int(round(t*1000)))
pub fn format_ts(t: f64) -> String {
    let t = if t < 0.0 { 0.0 } else { t };
    let mut ms = (t * 1000.0).round() as i64; // xem chú thích round ở ass.rs
    let h = ms / 3_600_000; ms %= 3_600_000;
    let mi = ms / 60_000; ms %= 60_000;
    let se = ms / 1000; ms %= 1000;
    format!("{:02}:{:02}:{:02},{:03}", h, mi, se, ms)
}

fn parse_ts(s: &str) -> Result<f64, String> {
    // tìm HH:MM:SS[,.]mmm ở bất kỳ đâu trong chuỗi
    let bytes: Vec<char> = s.chars().collect();
    for i in 0..bytes.len() {
        let w: String = bytes.iter().skip(i).take(12).collect();
        if w.len() == 12 {
            let b = w.as_bytes();
            let digit = |k: usize| (b[k] as char).is_ascii_digit();
            if digit(0)&&digit(1)&&b[2]==b':'&&digit(3)&&digit(4)&&b[5]==b':'
               &&digit(6)&&digit(7)&&(b[8]==b','||b[8]==b'.')&&digit(9)&&digit(10)&&digit(11) {
                let h: f64 = w[0..2].parse().unwrap();
                let mi: f64 = w[3..5].parse().unwrap();
                let se: f64 = w[6..8].parse().unwrap();
                let mmm: f64 = w[9..12].parse().unwrap();
                return Ok(h*3600.0 + mi*60.0 + se + mmm/1000.0);
            }
        }
    }
    Err(format!("bad timestamp: {:?}", s))
}

pub fn parse_srt_str(raw: &str) -> Vec<Cue> {
    let raw = raw.trim_start_matches('\u{feff}'); // utf-8-sig
    let mut cues = Vec::new();
    // tách block theo dòng trống (\n\s*\n)
    let re = regex::Regex::new(r"\n\s*\n").unwrap();
    for block in re.split(raw.trim()) {
        let lines: Vec<&str> = block.lines().filter(|l| !l.trim().is_empty()).collect();
        if lines.len() < 2 { continue; }
        let ts_idx = match lines.iter().position(|l| l.contains("-->")) { Some(i) => i, None => continue };
        let parts: Vec<&str> = lines[ts_idx].splitn(2, "-->").collect();
        if parts.len() != 2 { continue; }
        let (start, end) = match (parse_ts(parts[0]), parse_ts(parts[1])) {
            (Ok(a), Ok(b)) => (a, b), _ => continue,
        };
        let text = lines[ts_idx+1..].join("\n").trim().to_string();
        cues.push(Cue { start, end, text });
    }
    cues
}

pub fn parse_srt(path: &Path) -> std::io::Result<Vec<Cue>> {
    Ok(parse_srt_str(&std::fs::read_to_string(path)?))
}

pub fn write_srt_str(cues: &[Cue]) -> String {
    let mut s = String::new();
    for (i, c) in cues.iter().enumerate() {
        s.push_str(&format!("{}\n{} --> {}\n{}\n\n",
            i+1, format_ts(c.start), format_ts(c.end), c.text));
    }
    s
}

pub fn shift(cues: &[Cue], offset: f64) -> Vec<Cue> {
    cues.iter().map(|c| Cue {
        start: (c.start + offset).max(0.0),
        end: (c.end + offset).max(0.0),
        text: c.text.clone(),
    }).collect()
}

pub fn hide_before(cues: &[Cue], t: f64) -> Vec<Cue> {
    if t <= 0.0 { return cues.to_vec(); }
    cues.iter().filter(|c| c.end > t).map(|c| Cue {
        start: c.start.max(t), end: c.end, text: c.text.clone(),
    }).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;
    fn golden(name: &str) -> Value {
        let p = format!("{}/tests/golden/{}", env!("CARGO_MANIFEST_DIR"), name);
        serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
    }
    const SRT_IN: &str =
        "1\n00:00:01,000 --> 00:00:02,500\nxin chào\n\n2\n00:00:03,000 --> 00:00:05,000\nnôn mưởng nhé\n";

    #[test]
    fn parse_matches_python() {
        let g = golden("srt_parse.json");
        let cues = parse_srt_str(SRT_IN);
        assert_eq!(cues.len(), g.as_array().unwrap().len());
        for (c, gc) in cues.iter().zip(g.as_array().unwrap()) {
            assert_eq!(c.start, gc["start"].as_f64().unwrap());
            assert_eq!(c.end, gc["end"].as_f64().unwrap());
            assert_eq!(c.text, gc["text"].as_str().unwrap());
        }
    }

    #[test]
    fn write_matches_python() {
        let g = golden("srt_write.json");
        let cues = parse_srt_str(SRT_IN);
        assert_eq!(write_srt_str(&cues), g["content"].as_str().unwrap());
    }

    #[test]
    fn shift_matches_python() {
        let g = golden("srt_shift.json");
        let out = shift(&parse_srt_str(SRT_IN), 5.5);
        for (c, gc) in out.iter().zip(g.as_array().unwrap()) {
            assert_eq!(c.start, gc["start"].as_f64().unwrap());
            assert_eq!(c.end, gc["end"].as_f64().unwrap());
        }
    }

    #[test]
    fn hide_before_matches_python() {
        let g = golden("srt_hide.json");
        let out = hide_before(&parse_srt_str(SRT_IN), 2.0);
        assert_eq!(out.len(), g.as_array().unwrap().len());
        for (c, gc) in out.iter().zip(g.as_array().unwrap()) {
            assert_eq!(c.start, gc["start"].as_f64().unwrap());
            assert_eq!(c.end, gc["end"].as_f64().unwrap());
        }
    }
}
```

- [ ] **Step 2: Chạy test — kỳ vọng PASS (golden đã có từ Task 1)**

Run: `cd src-tauri && cargo test srt 2>&1 | tail -20`
Expected: 4 test `srt::tests::*` PASS. Nếu lệch (vd round), so trực tiếp chuỗi để sửa `format_ts`.

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/srt.rs
git commit -m "feat(port): srt.rs parse/write/shift/hide_before — khớp golden Python"
```

---

## Task 3: `ass.rs` phần A — round/format + màu/thời gian

**Files:**
- Create: `src-tauri/src/ass.rs`
- Golden: `ass_helpers.json`

- [ ] **Step 1: Viết phần A + test**

```rust
use crate::srt::Cue;

/// round nửa-về-chẵn (banker's rounding) như Python round(); chỉ khác f64::round() ở ca .5 đúng.
pub fn round_half_even(x: f64) -> f64 {
    let f = x.floor();
    let diff = x - f;
    if (diff - 0.5).abs() < 1e-9 {
        if (f as i64) % 2 == 0 { f } else { f + 1.0 }
    } else {
        x.round()
    }
}
pub fn round_i(x: f64) -> i64 { round_half_even(x) as i64 }

/// Định dạng số thực kiểu Python "{:g}" (6 chữ số nghĩa, bỏ số 0 thừa): 16.0->"16", 0.0->"0".
pub fn fmt_g(x: f64) -> String {
    if x == x.trunc() && x.abs() < 1e15 {
        return format!("{}", x as i64);
    }
    let mut s = format!("{:.6}", x);
    while s.contains('.') && s.ends_with('0') { s.pop(); }
    if s.ends_with('.') { s.pop(); }
    s
}

/// "#RRGGBB" + độ trong suốt -> ASS &HAABBGGRR (AA: 00 đục .. FF trong).
pub fn hex_to_ass(hexcolor: &str, transparency: f64) -> String {
    let h = expand_hex(hexcolor);
    let aa = ((transparency * 255.0).round() as i64).clamp(0, 255);
    format!("&H{:02X}{}{}{}", aa, up(&h[4..6]), up(&h[2..4]), up(&h[0..2]))
}

/// "#RRGGBB" -> "&Hbbggrr&" (cho \1c trong drawing).
pub fn ass_bgr(hexcolor: &str) -> String {
    let h = expand_hex(hexcolor);
    format!("&H{}{}{}&", up(&h[4..6]), up(&h[2..4]), up(&h[0..2]))
}

pub fn ass_alpha(opacity: f64) -> String {
    let aa = (((1.0 - opacity) * 255.0).round() as i64).clamp(0, 255);
    format!("&H{:02X}&", aa)
}

pub fn ass_time(t: f64) -> String {
    let t = if t < 0.0 { 0.0 } else { t };
    let mut cs = (t * 100.0).round() as i64;
    let h = cs / 360_000; cs %= 360_000;
    let m = cs / 6000; cs %= 6000;
    let s = cs / 100; cs %= 100;
    format!("{}:{:02}:{:02}.{:02}", h, m, s, cs)
}

fn up(s: &str) -> String { s.to_uppercase() }
fn expand_hex(hexcolor: &str) -> String {
    let h = hexcolor.trim_start_matches('#');
    if h.len() == 3 { h.chars().flat_map(|c| [c, c]).collect() } else { h.to_string() }
}

#[cfg(test)]
mod tests_a {
    use super::*;
    use serde_json::Value;
    fn golden() -> Value {
        let p = format!("{}/tests/golden/ass_helpers.json", env!("CARGO_MANIFEST_DIR"));
        serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
    }
    #[test]
    fn helpers_match_python() {
        let g = golden();
        assert_eq!(hex_to_ass("#000000", 0.0), g["hex_black_opaque"].as_str().unwrap());
        assert_eq!(hex_to_ass("#ffffff", 0.0), g["hex_white"].as_str().unwrap());
        assert_eq!(hex_to_ass("#2563eb", 0.25), g["hex_blue_semi"].as_str().unwrap());
        assert_eq!(ass_bgr("#000000"), g["bgr_black"].as_str().unwrap());
        assert_eq!(ass_bgr("#2563eb"), g["bgr_blue"].as_str().unwrap());
        assert_eq!(ass_alpha(1.0), g["alpha_1"].as_str().unwrap());
        assert_eq!(ass_alpha(0.25), g["alpha_025"].as_str().unwrap());
        assert_eq!(ass_time(0.0), g["time_0"].as_str().unwrap());
        assert_eq!(ass_time(65.321), g["time_65_321"].as_str().unwrap());
        assert_eq!(ass_time(-3.0), g["time_neg"].as_str().unwrap());
    }
}
```

> Lưu ý round: Python dùng round nửa-về-chẵn; nhưng `hex_to_ass`/`ass_alpha` dùng `round(x*255)` — ở đây `f64::round()` (nửa-ra-xa) khớp Python cho hầu hết giá trị. Nếu golden lệch đúng ca .5, đổi sang `round_half_even`. Golden test là trọng tài.

- [ ] **Step 2: Chạy test**

Run: `cd src-tauri && cargo test ass 2>&1 | tail -15`
Expected: `tests_a::helpers_match_python` PASS. Lệch chỗ nào -> sửa hàm tương ứng theo chuỗi kỳ vọng.

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/ass.rs
git commit -m "feat(port): ass.rs màu/thời gian + round/fmt_g — khớp golden"
```

---

## Task 4: `ass.rs` phần B — bề rộng ký tự + wrap

**Files:** Modify `src-tauri/src/ass.rs`; Golden `wrap.json`

- [ ] **Step 1: Thêm hàm + test**

```rust
// đặt sau phần A trong ass.rs

fn is_narrow(c: char) -> bool { "iíìỉĩịl.,:;!'|`ftjr()[]".contains(c) }
fn is_wide(c: char) -> bool { "mwMW@".contains(c) }

pub fn char_frac(c: char, bold: bool) -> f64 {
    let f = if c == ' ' { 0.30 }
        else if is_narrow(c) { 0.32 }
        else if is_wide(c) { 0.60 }
        else if c.is_ascii_digit() { 0.42 }
        else if c.is_uppercase() { 0.52 }
        else { 0.40 };
    f * if bold { 1.04 } else { 1.0 }
}

pub fn line_width(text: &str, fontpx: f64, bold: bool) -> f64 {
    fontpx * text.chars().map(|c| char_frac(c, bold)).sum::<f64>()
}

pub fn wrap_width(text: &str, fontpx: f64, bold: bool, max_w: f64) -> Vec<String> {
    let words: Vec<&str> = text.replace('\n', " ").split_whitespace().map(|s| s).collect::<Vec<_>>()
        .iter().map(|s| *s).collect();
    // giữ nguyên chuỗi từ (split_whitespace bỏ khoảng trắng thừa như Python .split())
    let words: Vec<String> = text.replace('\n', " ").split_whitespace().map(|s| s.to_string()).collect();
    if words.is_empty() { return vec![String::new()]; }
    let mut lines: Vec<String> = Vec::new();
    let mut cur = String::new();
    for w in &words {
        let trial = if cur.is_empty() { w.clone() } else { format!("{} {}", cur, w) };
        if cur.is_empty() || line_width(&trial, fontpx, bold) <= max_w {
            cur = trial;
        } else {
            lines.push(cur);
            cur = w.clone();
        }
    }
    if !cur.is_empty() { lines.push(cur); }
    lines
}

#[cfg(test)]
mod tests_b {
    use super::*;
    use serde_json::Value;
    fn golden() -> Value {
        let p = format!("{}/tests/golden/wrap.json", env!("CARGO_MANIFEST_DIR"));
        serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
    }
    #[test]
    fn width_and_wrap_match_python() {
        let g = golden();
        let w = line_width("xin chào", 16.0, true);
        assert!((w - g["w_short"].as_f64().unwrap()).abs() < 1e-9, "line_width lệch");
        let wrapped: Vec<String> = wrap_width(
            "đây là một câu rất dài để kiểm tra việc xuống dòng theo bề rộng hộp nền", 16.0, true, 120.0);
        let exp: Vec<String> = g["wrap_long"].as_array().unwrap().iter()
            .map(|v| v.as_str().unwrap().to_string()).collect();
        assert_eq!(wrapped, exp);
    }
}
```

> **Bẫy NFC:** các ký tự tiếng Việt trong `is_narrow` (í ì ỉ ĩ ị) phải cùng chuẩn hoá NFC như chuỗi đầu vào. File .rs lưu UTF-8 NFC; whisper xuất NFC nên khớp. Nếu `line_width` lệch, kiểm chuẩn hoá.

- [ ] **Step 2: Chạy test**

Run: `cd src-tauri && cargo test ass 2>&1 | tail -15`
Expected: `tests_b::width_and_wrap_match_python` PASS.

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/ass.rs
git commit -m "feat(port): ass.rs char_frac/line_width/wrap_width — khớp golden"
```

---

## Task 5: `ass.rs` phần C — build_force_style + escape filter

**Files:** Modify `src-tauri/src/ass.rs`; Golden `force_style.json`

- [ ] **Step 1: Định nghĩa `Style` + `build_force_style` + `esc_filter` + test**

```rust
// Struct style dùng chung (map từ form của frontend). None = không đặt.
#[derive(Debug, Default, Clone)]
pub struct Style {
    pub font: Option<String>,
    pub size: Option<String>,
    pub bold: bool,
    pub italic: bool,
    pub fill: Option<String>,
    pub outline: Option<String>,        // dùng làm "đệm" khi box, hoặc độ dày viền
    pub outline_color: Option<String>,
    pub outline_opacity: Option<String>,
    pub box_on: bool,
    pub box_color: Option<String>,
    pub box_opacity: Option<String>,
    pub align: Option<String>,          // "top"|"middle"|"bottom"
    pub margin: Option<String>,
}

fn align_num(a: &Option<String>) -> Option<i64> {
    match a.as_deref() { Some("bottom") => Some(2), Some("middle") => Some(5), Some("top") => Some(8), _ => None }
}
fn parse_f(s: &Option<String>) -> Option<f64> {
    s.as_ref().and_then(|v| v.trim().parse::<f64>().ok())
}

pub fn build_force_style(style: Option<&Style>) -> String {
    let s = match style { Some(s) => s, None => return String::new() };
    let mut parts: Vec<String> = Vec::new();
    if let Some(f) = &s.font { if !f.is_empty() { parts.push(format!("FontName={}", f)); } }
    if let Some(sz) = parse_f(&s.size) { parts.push(format!("FontSize={}", sz as i64)); }
    parts.push(if s.bold { "Bold=-1".into() } else { "Bold=0".into() });
    if s.italic { parts.push("Italic=-1".into()); }
    if let Some(fill) = &s.fill { if !fill.is_empty() { parts.push(format!("PrimaryColour={}", hex_to_ass(fill, 0.0))); } }
    if s.box_on {
        parts.push("BorderStyle=3".into());
        parts.push("Shadow=0".into());
        let box_color = s.box_color.clone().unwrap_or_else(|| "#000000".into());
        let op = parse_f(&s.box_opacity).unwrap_or(1.0);
        parts.push(format!("OutlineColour={}", hex_to_ass(&box_color, 1.0 - op)));
        let pad = parse_f(&s.outline).unwrap_or(0.0);
        parts.push(format!("Outline={}", fmt_g(if pad > 0.0 { pad } else { 4.0 })));
    } else {
        if let Some(o) = &s.outline { if !o.is_empty() { parts.push(format!("Outline={}", o)); } }
        if let Some(oc) = &s.outline_color { if !oc.is_empty() {
            let op = parse_f(&s.outline_opacity).unwrap_or(1.0);
            parts.push(format!("OutlineColour={}", hex_to_ass(oc, 1.0 - op)));
        }}
    }
    if let Some(a) = align_num(&s.align) { parts.push(format!("Alignment={}", a)); }
    if let Some(m) = parse_f(&s.margin) { parts.push(format!("MarginV={}", m as i64)); }
    parts.join(",")
}

/// escape đường dẫn cho filter subtitles của ffmpeg (\\ ' :).
pub fn esc_filter(p: &str) -> String {
    p.replace('\\', "\\\\").replace('\'', "\\'").replace(':', "\\:")
}

#[cfg(test)]
mod tests_c {
    use super::*;
    use serde_json::Value;
    fn golden() -> Value {
        let p = format!("{}/tests/golden/force_style.json", env!("CARGO_MANIFEST_DIR"));
        serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
    }
    #[test]
    fn force_style_box_matches_python() {
        let g = golden();
        let s = Style {
            font: Some("UTM Avo".into()), size: Some("16".into()), bold: true,
            fill: Some("#ffffff".into()), box_on: true, box_color: Some("#000000".into()),
            box_opacity: Some("0.25".into()), outline: Some("4".into()),
            align: Some("bottom".into()), margin: Some("24".into()), ..Default::default()
        };
        assert_eq!(build_force_style(Some(&s)), g["box"].as_str().unwrap());
    }
    #[test]
    fn force_style_stroke_matches_python() {
        let g = golden();
        let s = Style {
            font: Some("UTM Avo".into()), size: Some("18".into()), bold: false,
            fill: Some("#ffff00".into()), outline: Some("2".into()),
            outline_color: Some("#000000".into()), outline_opacity: Some("1.0".into()),
            align: Some("bottom".into()), margin: Some("30".into()), ..Default::default()
        };
        assert_eq!(build_force_style(Some(&s)), g["stroke"].as_str().unwrap());
    }
    #[test]
    fn force_style_none_is_empty() {
        assert_eq!(build_force_style(None), golden()["none"].as_str().unwrap());
    }
}
```

> **Chú ý thứ tự khoá:** `parts` phải theo đúng thứ tự Python để chuỗi khớp. So golden nếu lệch. `box_opacity`/`outline` truyền dạng chuỗi ("0.25","4") giống form thật.

- [ ] **Step 2: Chạy test**

Run: `cd src-tauri && cargo test ass 2>&1 | tail -15`
Expected: 3 test `tests_c::*` PASS.

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/ass.rs
git commit -m "feat(port): ass.rs build_force_style + esc_filter — khớp golden"
```

---

## Task 6: `ass.rs` phần D — write_band_ass (trọng điểm)

**Files:** Modify `src-tauri/src/ass.rs`; Golden `band_ass.json`

- [ ] **Step 1: Viết `write_band_ass_str` + test golden**

```rust
const PLAYRES_Y: f64 = 288.0;

/// Sinh nội dung .ass (1 dải nền băng ngang mỗi cue) — port write_band_ass của Python.
pub fn write_band_ass_str(cues: &[Cue], style: &Style, width: i64, height: i64) -> String {
    let h = height.max(1) as f64;
    let play_x = ((PLAYRES_Y * width as f64 / h).round() as i64).max(320);
    let font = style.font.clone().filter(|s| !s.is_empty()).unwrap_or_else(|| "UTM Avo".into());
    let fontpx = parse_f(&style.size).unwrap_or(16.0);
    let bold = if style.bold { -1 } else { 0 };
    let italic = if style.italic { -1 } else { 0 };
    let primary = hex_to_ass(style.fill.as_deref().unwrap_or("#ffffff"), 0.0);
    let outline_col = hex_to_ass(style.outline_color.as_deref().unwrap_or("#000000"), 0.0);
    let outline_w = parse_f(&style.outline).unwrap_or(0.0);
    let align = align_num(&style.align).unwrap_or(2);
    let margin_v = parse_f(&style.margin).unwrap_or(24.0) as i64;
    let band_bgr = ass_bgr(style.box_color.as_deref().unwrap_or("#000000"));
    let band_a = ass_alpha(parse_f(&style.box_opacity).unwrap_or(1.0));

    let is_bold = style.bold;
    let to_units = PLAYRES_Y / h;
    let side = ((play_x as f64 * 0.04).round() as i64).max(10);
    let pad_x = (5.0 * to_units).max(1.5);
    let pad_top = (8.0 * to_units).max(2.0);
    let pad_bot = (5.0 * to_units).max(1.5);
    let max_box_w = play_x as f64 - 2.0 * side as f64;
    let max_text_w = max_box_w - 2.0 * pad_x;
    let line_h = fontpx * 1.22;

    let header = format!(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: {play_x}\nPlayResY: {}\nWrapStyle: 2\n\
ScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, \
SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, \
Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n\
Style: Text,{font},{fontpx_g},{primary},&H000000FF,{outline_col},&H00000000,{bold},{italic},0,0,\
100,100,0,0,1,{outline_w_g},0,{align},{side},{side},{margin_v},1\n\n[Events]\nFormat: Layer, Start, \
End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n",
        PLAYRES_Y as i64, play_x = play_x, font = font, fontpx_g = fmt_g(fontpx),
        primary = primary, outline_col = outline_col, bold = bold, italic = italic,
        outline_w_g = fmt_g(outline_w), align = align, side = side, margin_v = margin_v
    );

    let max_lines = 2usize;
    let mut lines_out: Vec<String> = Vec::new();
    for c in cues {
        let text = c.text.replace('{', "(").replace('}', ")");
        let wrapped = wrap_width(&text, fontpx, is_bold, max_text_w);
        let pages: Vec<Vec<String>> = wrapped.chunks(max_lines).map(|c| c.to_vec()).collect();
        let weights: Vec<f64> = pages.iter()
            .map(|pg| { let s: usize = pg.iter().map(|l| l.chars().count()).sum(); if s == 0 {1.0} else {s as f64} })
            .collect();
        let total_w: f64 = weights.iter().sum();
        let dur = (c.end - c.start).max(0.0);
        let mut t = c.start;
        let n_pages = pages.len();
        for (idx, (pg, w)) in pages.iter().zip(weights.iter()).enumerate() {
            let p_start = t;
            let p_end = if idx == n_pages - 1 { c.end } else { t + dur * (w / total_w) };
            t = p_end;
            let n = pg.len() as f64;
            let block_h = n * line_h;
            let text_w = pg.iter().map(|ln| line_width(ln, fontpx, is_bold)).fold(0.0_f64, f64::max);
            let box_w = (text_w + 2.0 * pad_x).min(max_box_w);
            let x1 = round_i((play_x as f64 - box_w) / 2.0);
            let x2 = round_i(x1 as f64 + box_w);
            let (y1, y2) = if align == 8 {
                (margin_v as f64 - pad_top, margin_v as f64 + block_h + pad_bot)
            } else if align == 5 {
                let cy = PLAYRES_Y / 2.0;
                (cy - block_h / 2.0 - pad_top, cy + block_h / 2.0 + pad_bot)
            } else {
                let yb = PLAYRES_Y - margin_v as f64;
                (yb - block_h - pad_top, yb + pad_bot)
            };
            let iy1 = round_i(y1); let iy2 = round_i(y2);
            let band = format!(
                "{{\\p1\\an7\\pos(0,0)\\1c{}\\1a{}\\bord0\\shad0}}m {} {} l {} {} {} {} {} {}{{\\p0}}",
                band_bgr, band_a, x1, iy1, x2, iy1, x2, iy2, x1, iy2);
            let st = ass_time(p_start); let en = ass_time(p_end);
            let text_body = pg.join("\\N");
            lines_out.push(format!("Dialogue: 0,{},{},Text,,0,0,0,,{}", st, en, band));
            lines_out.push(format!("Dialogue: 1,{},{},Text,,0,0,0,,{}", st, en, text_body));
        }
    }
    format!("{}{}\n", header, lines_out.join("\n"))
}

#[cfg(test)]
mod tests_d {
    use super::*;
    use serde_json::Value;
    #[test]
    fn band_ass_matches_python_byte_for_byte() {
        let p = format!("{}/tests/golden/band_ass.json", env!("CARGO_MANIFEST_DIR"));
        let g: Value = serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap();
        let style = Style {
            font: Some("UTM Avo".into()), size: Some("16".into()), bold: true,
            fill: Some("#ffffff".into()), box_on: true, box_color: Some("#000000".into()),
            box_opacity: Some("0.25".into()), outline: Some("4".into()),
            align: Some("bottom".into()), margin: Some("24".into()), ..Default::default()
        };
        let cues = vec![
            Cue { start: 1.0, end: 3.0, text: "xin chào các bạn".into() },
            Cue { start: 3.0, end: 8.0, text: "đây là một câu rất dài cần xuống dòng và tách trang để kiểm tra hộp nền băng ngang ôm sát chữ".into() },
        ];
        let got = write_band_ass_str(&cues, &style, 1920, 1080);
        assert_eq!(got, g["content"].as_str().unwrap());
    }
}

/// Ghi ra file (dùng ở Plan 3).
pub fn write_band_ass(cues: &[Cue], path: &std::path::Path, style: &Style, width: i64, height: i64) -> std::io::Result<()> {
    std::fs::write(path, write_band_ass_str(cues, style, width, height))
}
```

- [ ] **Step 2: Chạy test — đây là bài kiểm tra "không được sai"**

Run: `cd src-tauri && cargo test ass 2>&1 | tail -25`
Expected: `tests_d::band_ass_matches_python_byte_for_byte` PASS. Nếu FAIL: in cả hai chuỗi, tìm dòng lệch (thường do `round_i`, `fmt_g`, thứ tự, hoặc `\\N`). Sửa tới khi khớp từng byte.

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/ass.rs
git commit -m "feat(port): write_band_ass — khớp golden byte-to-byte (lõi không-được-sai)"
```

---

## Task 7: `corrections.rs` — sửa từ nhận nhầm

**Files:** Create `src-tauri/src/corrections.rs`; Golden `corrections.json`

- [ ] **Step 1: Viết + test**

```rust
use regex::Regex;
use unicode_normalization::UnicodeNormalization;

/// Đọc file: mỗi dòng "sai => đúng" (# là ghi chú). Trả cặp (wrong, right).
pub fn load_corrections(text: &str) -> Vec<(String, String)> {
    let mut pairs = Vec::new();
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') || !line.contains("=>") { continue; }
        let mut it = line.splitn(2, "=>");
        let wrong = it.next().unwrap().trim().to_string();
        let right = it.next().unwrap_or("").trim().to_string();
        if !wrong.is_empty() { pairs.push((wrong, right)); }
    }
    pairs
}

/// Thay các cụm hay nghe nhầm trong nội dung .srt (không phân biệt hoa/thường, giữ hoa chữ đầu).
pub fn apply_corrections(srt: &str, pairs: &[(String, String)]) -> String {
    let mut text: String = srt.nfc().collect(); // chuẩn hoá NFC để khớp dấu tiếng Việt
    for (wrong, right) in pairs {
        let wrong_nfc: String = wrong.nfc().collect();
        let right_nfc: String = right.nfc().collect();
        let re = Regex::new(&format!("(?i){}", regex::escape(&wrong_nfc))).unwrap();
        text = re.replace_all(&text, |caps: &regex::Captures| {
            let m = caps.get(0).unwrap().as_str();
            let first_upper = m.chars().next().map(|c| c.is_uppercase()).unwrap_or(false);
            if first_upper {
                let mut ch = right_nfc.chars();
                match ch.next() {
                    Some(f) => f.to_uppercase().collect::<String>() + ch.as_str(),
                    None => String::new(),
                }
            } else {
                right_nfc.clone()
            }
        }).into_owned();
    }
    text
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;
    #[test]
    fn corrections_match_python() {
        let p = format!("{}/tests/golden/corrections.json", env!("CARGO_MANIFEST_DIR"));
        let g: Value = serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap();
        let pairs = load_corrections("# ghi chú\nnôn mưởng => nôn mửa\nhà nội => Hà Nội\n");
        let srt = "1\n00:00:01,000 --> 00:00:02,000\nNôn mưởng quá\n\n2\n00:00:03,000 --> 00:00:04,000\ntôi ở hà nội\n";
        assert_eq!(apply_corrections(srt, &pairs), g["content"].as_str().unwrap());
    }
}
```

> **Bẫy:** Python `re.IGNORECASE` + `re.escape`, giữ hoa chữ đầu bằng `s[:1].isupper()`. Rust `(?i)` + `regex::escape`, chữ đầu `is_uppercase()`. NFC hai đầu để "hà nội"/"Hà Nội" khớp dấu. Nếu golden lệch ở "Hà Nội" (H hoa sẵn trong right) — chú ý: Python trả `right[:1].upper()+right[1:]` khi match viết hoa; với right="Hà Nội" thì vẫn "Hà Nội". Khớp.

- [ ] **Step 2: Chạy test**

Run: `cd src-tauri && cargo test corrections 2>&1 | tail -12`
Expected: `corrections::tests::corrections_match_python` PASS.

- [ ] **Step 3: Chạy TOÀN BỘ test đảm bảo không hồi quy**

Run: `cd src-tauri && cargo test 2>&1 | tail -20`
Expected: tất cả PASS (setup 6 + srt 4 + ass 6 + corrections 1 = 17).

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/corrections.rs
git commit -m "feat(port): corrections.rs sửa từ (NFC, giữ hoa chữ đầu) — khớp golden"
```

---

## Self-Review (đã kiểm khi viết plan)

- **Spec coverage (mục 3/6):** `parse_srt/write_srt/shift/hide_before` (T2 ✓), `hex_to_ass/_ass_bgr/_ass_alpha/_ass_time` (T3 ✓), `_char_frac/_line_width/_wrap_width` (T4 ✓), `build_force_style`+escape (T5 ✓), `write_band_ass` (T6 ✓), `apply_corrections/_load_corrections` (T7 ✓). Golden byte-to-byte cho mọi hàm dễ lệch (mục 6 ✓). `align/word_timings/.docx` → Plan 4 (có chủ đích, ghi rõ). `transcribe`/`burn_or_mux` spawn → Plan 3.
- **Placeholder:** không có TBD; mọi hàm có code đầy đủ + test có input/expected cụ thể (qua golden).
- **Type consistency:** `Cue` định nghĩa ở `srt.rs`, `ass.rs` import `crate::srt::Cue`. `Style` định nghĩa ở `ass.rs` (T5) dùng lại ở T6. `round_i/fmt_g/hex_to_ass/ass_bgr/ass_alpha/line_width/wrap_width/parse_f/align_num` khai báo T3–T5, dùng trong `write_band_ass` T6 — khớp tên & chữ ký. `write_band_ass(path)` trả `io::Result` dùng ở Plan 3.
- **Rủi ro còn lại:** nếu golden lệch, sửa hàm theo chuỗi kỳ vọng (round_half_even vs round, fmt_g). Đó là cơ chế thiết kế — test làm trọng tài.

## Điều kiện chuyển Plan 3

Toàn bộ `cargo test` xanh (17 test), đặc biệt `band_ass_matches_python_byte_for_byte`. Khi đó lõi tất định đã khớp Python tuyệt đối → Plan 3 chỉ còn spawn whisper/ffmpeg + nối frontend.
