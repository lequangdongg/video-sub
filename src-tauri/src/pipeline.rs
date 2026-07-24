use crate::ass::Style;
use crate::tools::Tools;
use crate::{align, ffmpeg, srt, whisper};
use serde_json::Value;
use std::path::{Path, PathBuf};

const TIMED_EXTS: [&str; 3] = ["srt", "vtt", "ass"];

fn get_str(v: &Value, k: &str) -> Option<String> {
    v.get(k)
        .and_then(|x| x.as_str())
        .map(|s| s.to_string())
        .filter(|s| !s.is_empty())
}
fn get_bool(v: &Value, k: &str) -> bool {
    v.get(k).and_then(|x| x.as_bool()).unwrap_or(false)
}
fn get_num_str(v: &Value, k: &str) -> Option<String> {
    // chấp nhận cả số lẫn chuỗi từ frontend
    match v.get(k) {
        Some(Value::String(s)) if !s.is_empty() => Some(s.clone()),
        Some(Value::Number(n)) => Some(n.to_string()),
        _ => None,
    }
}

fn parse_offset(opts: &Value) -> f64 {
    match opts.get("offset") {
        Some(Value::Number(n)) => n.as_f64().unwrap_or(0.0),
        Some(Value::String(s)) => s.trim().parse().unwrap_or(0.0),
        _ => 0.0,
    }
}

pub fn style_from_json(style: Option<&Value>) -> Option<Style> {
    let s = style?;
    Some(Style {
        font: get_str(s, "font"),
        size: get_num_str(s, "size"),
        bold: get_bool(s, "bold"),
        italic: get_bool(s, "italic"),
        fill: get_str(s, "fill"),
        outline: get_num_str(s, "outline"),
        outline_color: get_str(s, "outline_color"),
        outline_opacity: get_num_str(s, "outline_opacity"),
        box_on: get_bool(s, "box"),
        box_color: get_str(s, "box_color"),
        box_opacity: get_num_str(s, "box_opacity"),
        align: get_str(s, "align"),
        margin: get_num_str(s, "margin"),
    })
}

fn output_video_path(job_dir: &Path, video: &Path) -> PathBuf {
    let ext = video
        .extension()
        .and_then(|e| e.to_str())
        .filter(|e| !e.is_empty())
        .unwrap_or("mp4");
    job_dir.join(format!("output.{}", ext))
}

/// Luồng tự động: tách audio -> whisper -> (offset) -> burn/mux. Trả (video_out, srt).
pub fn process_auto<F: Fn(&str, Option<f64>)>(
    t: &Tools,
    video: &Path,
    job_dir: &Path,
    opts: &Value,
    on_progress: F,
) -> Result<(PathBuf, PathBuf), String> {
    std::fs::create_dir_all(job_dir).map_err(|e| e.to_string())?;
    let lang = opts.get("language").and_then(|v| v.as_str()).unwrap_or("vi");
    let mode = opts.get("mode").and_then(|v| v.as_str()).unwrap_or("burn");
    let offset = parse_offset(opts);

    let wav = job_dir.join("audio.wav");
    let srt_path = job_dir.join("output.srt");

    on_progress("Tách audio", None);
    ffmpeg::extract_audio(t, video, &wav)?;
    on_progress("Tách audio", Some(100.0));

    whisper::transcribe(t, &wav, lang, &srt_path, &on_progress)?;

    if offset > 0.0 {
        let cues = srt::hide_before(&srt::parse_srt(&srt_path).map_err(|e| e.to_string())?, offset);
        srt::write_srt(&cues, &srt_path).map_err(|e| e.to_string())?;
    }

    let out = if mode == "srt" {
        srt_path.clone()
    } else {
        output_video_path(job_dir, video)
    };
    let style = if mode == "burn" {
        style_from_json(opts.get("style"))
    } else {
        None
    };
    ffmpeg::burn_or_mux(t, video, &srt_path, mode, &out, style.as_ref(), &on_progress)?;
    let _ = std::fs::remove_file(&wav);
    Ok((out, srt_path))
}

fn ext_lower(p: &Path) -> String {
    p.extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase()
}

fn normalize_to_srt(t: &Tools, sub_file: &Path, srt_out: &Path) -> Result<(), String> {
    if ext_lower(sub_file) == "srt" {
        std::fs::copy(sub_file, srt_out).map_err(|e| e.to_string())?;
    } else {
        let st = std::process::Command::new(&t.ffmpeg)
            .args(["-y", "-loglevel", "error", "-i"])
            .arg(sub_file)
            .arg(srt_out)
            .status()
            .map_err(|e| e.to_string())?;
        if !st.success() {
            return Err("chuyển sub sang .srt thất bại".into());
        }
    }
    Ok(())
}

/// Ghép sub có sẵn: sub có timeline -> dời offset; sub văn bản thuần -> whisper căn chỉnh.
pub fn process_merge<F: Fn(&str, Option<f64>)>(
    t: &Tools,
    video: &Path,
    sub_file: &Path,
    job_dir: &Path,
    offset: f64,
    mode: &str,
    lang: &str,
    style: Option<&Style>,
    on_progress: F,
) -> Result<(PathBuf, PathBuf), String> {
    std::fs::create_dir_all(job_dir).map_err(|e| e.to_string())?;
    let srt_path = job_dir.join("output.srt");

    if TIMED_EXTS.contains(&ext_lower(sub_file).as_str()) {
        on_progress("Chuẩn bị sub", None);
        let tmp = job_dir.join("src.srt");
        normalize_to_srt(t, sub_file, &tmp)?;
        let cues = srt::shift(&srt::parse_srt(&tmp).map_err(|e| e.to_string())?, offset);
        srt::write_srt(&cues, &srt_path).map_err(|e| e.to_string())?;
        on_progress("Chuẩn bị sub", Some(100.0));
    } else {
        let wav = job_dir.join("audio.wav");
        on_progress("Tách audio", None);
        ffmpeg::extract_audio(t, video, &wav)?;
        on_progress("Tách audio", Some(100.0));
        let words = align::word_timings(t, &wav, lang, &on_progress)?;
        let text = align::extract_text(sub_file)?;
        let cue_texts = align::split_into_cue_texts(&text, 90);
        let cues = srt::shift(&align::align(&cue_texts, &words), offset);
        srt::write_srt(&cues, &srt_path).map_err(|e| e.to_string())?;
        let _ = std::fs::remove_file(&wav);
    }

    let out = if mode == "srt" {
        srt_path.clone()
    } else {
        output_video_path(job_dir, video)
    };
    ffmpeg::burn_or_mux(t, video, &srt_path, mode, &out, style, &on_progress)?;
    Ok((out, srt_path))
}

#[cfg(test)]
mod it {
    use super::*;
    use crate::{setup, tools};

    // Smoke test end-to-end: cần model large-v3. Chạy: cargo test -- --ignored full_auto
    #[test]
    #[ignore]
    fn full_auto_pipeline_smoke() {
        let model = setup::resolve_model_path().expect("cần model large-v3 ở ~/whisper-models");
        let t = tools::resolve(None, model);
        let dir = std::env::temp_dir().join("autosub_it");
        std::fs::create_dir_all(&dir).unwrap();
        let audio = dir.join("sp.aiff");
        let video = dir.join("in.mp4");
        std::process::Command::new("say")
            .arg("-o")
            .arg(&audio)
            .arg("Hello, this is a subtitle test. One two three.")
            .status()
            .expect("say");
        std::process::Command::new(&t.ffmpeg)
            .args(["-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=640x360"])
            .arg("-i")
            .arg(&audio)
            .args(["-shortest", "-c:v", "h264_videotoolbox"])
            .arg(&video)
            .status()
            .expect("ffmpeg make video");
        let opts = serde_json::json!({
            "language": "vi", "mode": "burn", "offset": "0",
            "style": {"font": "UTM Avo", "size": "16", "bold": true, "box": true,
                      "box_color": "#000000", "box_opacity": "0.25", "outline": "4",
                      "align": "bottom", "margin": "24", "fill": "#ffffff"}
        });
        let job = dir.join("job");
        let (out, srt) = process_auto(&t, &video, &job, &opts, |s, p| eprintln!("{} {:?}", s, p))
            .expect("pipeline chạy");
        assert!(out.exists() && std::fs::metadata(&out).unwrap().len() > 0, "video ra rỗng");
        assert!(srt.exists(), "srt thiếu");
        eprintln!("OK -> {}", out.display());
    }
}
