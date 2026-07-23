use crate::ass::{self, Style};
use crate::srt::Cue;
use crate::tools::Tools;
use std::io::{BufRead, BufReader};
use std::path::Path;
use std::process::{Command, Stdio};

fn ok(status: std::process::ExitStatus, what: &str) -> Result<(), String> {
    if status.success() {
        Ok(())
    } else {
        Err(format!("{} thất bại", what))
    }
}

pub fn extract_audio(t: &Tools, video: &Path, wav: &Path) -> Result<(), String> {
    let st = Command::new(&t.ffmpeg)
        .args(["-y", "-loglevel", "error", "-i"])
        .arg(video)
        .args(["-vn", "-ac", "1", "-ar", "16000"])
        .arg(wav)
        .status()
        .map_err(|e| e.to_string())?;
    ok(st, "tách audio")
}

pub fn video_dimensions(t: &Tools, video: &Path) -> (i64, i64) {
    let out = Command::new(&t.ffprobe)
        .args([
            "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x",
        ])
        .arg(video)
        .output();
    if let Ok(o) = out {
        let s = String::from_utf8_lossy(&o.stdout);
        let s = s.trim();
        let parts: Vec<&str> = s.split('x').collect();
        if parts.len() >= 2 {
            if let (Ok(w), Ok(h)) = (parts[0].trim().parse::<i64>(), parts[1].trim().parse::<i64>()) {
                return (w, h);
            }
        }
    }
    (1920, 1080)
}

pub fn video_duration(t: &Tools, video: &Path) -> f64 {
    let out = Command::new(&t.ffprobe)
        .args([
            "-v", "error", "-show_entries", "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1",
        ])
        .arg(video)
        .output();
    if let Ok(o) = out {
        if let Ok(v) = String::from_utf8_lossy(&o.stdout).trim().parse::<f64>() {
            return v;
        }
    }
    0.0
}

/// burn (cháy vào hình) | soft (sub mềm) | srt (chỉ .srt). on_progress(step, percent).
pub fn burn_or_mux<F: Fn(&str, Option<f64>)>(
    t: &Tools,
    video: &Path,
    srt: &Path,
    mode: &str,
    out_path: &Path,
    style: Option<&Style>,
    on_progress: &F,
) -> Result<(), String> {
    match mode {
        "srt" => {
            if srt != out_path {
                std::fs::copy(srt, out_path).map_err(|e| e.to_string())?;
            }
            on_progress("Nhúng phụ đề", Some(100.0));
            Ok(())
        }
        "soft" => {
            let st = Command::new(&t.ffmpeg)
                .args(["-y", "-loglevel", "error", "-i"])
                .arg(video)
                .arg("-i")
                .arg(srt)
                .args(["-c", "copy", "-c:s", "mov_text"])
                .arg(out_path)
                .status()
                .map_err(|e| e.to_string())?;
            ok(st, "ghép sub mềm")?;
            on_progress("Nhúng phụ đề", Some(100.0));
            Ok(())
        }
        "burn" => {
            let mut sub_opt: String;
            if let Some(s) = style {
                if s.box_on {
                    let (w, h) = video_dimensions(t, video);
                    let ass_path = with_ext(srt, "ass");
                    let cues: Vec<Cue> = crate::srt::parse_srt(srt).map_err(|e| e.to_string())?;
                    ass::write_band_ass(&cues, &ass_path, s, w, h).map_err(|e| e.to_string())?;
                    sub_opt = format!("f='{}'", ass::esc_filter(&ass_path.to_string_lossy()));
                } else {
                    sub_opt = format!("f='{}'", ass::esc_filter(&srt.to_string_lossy()));
                    let fs = ass::build_force_style(Some(s));
                    if !fs.is_empty() {
                        sub_opt.push_str(&format!(":force_style='{}'", fs));
                    }
                }
            } else {
                sub_opt = format!("f='{}'", ass::esc_filter(&srt.to_string_lossy()));
            }
            if t.fonts_dir.is_dir() {
                sub_opt.push_str(&format!(
                    ":fontsdir='{}'",
                    ass::esc_filter(&t.fonts_dir.to_string_lossy())
                ));
            }
            let total = video_duration(t, video);
            let mut cmd = Command::new(&t.ffmpeg);
            cmd.args(["-y", "-loglevel", "error", "-i"])
                .arg(video)
                .args(["-vf", &format!("subtitles={}", sub_opt)])
                .args(["-c:v", "h264_videotoolbox", "-q:v", "60", "-c:a", "copy"])
                .arg(out_path)
                .args(["-progress", "pipe:1", "-nostats"])
                .stdout(Stdio::piped())
                .stderr(Stdio::null());
            let mut child = cmd.spawn().map_err(|e| e.to_string())?;
            if let Some(stdout) = child.stdout.take() {
                let reader = BufReader::new(stdout);
                for line in reader.lines().map_while(Result::ok) {
                    if let Some(rest) = line.strip_prefix("out_time_ms=") {
                        if total > 0.0 {
                            if let Ok(ms) = rest.trim().parse::<i64>() {
                                let pct = (ms as f64 / 1000.0 / total * 100.0).min(99.0);
                                on_progress("Nhúng phụ đề", Some(pct));
                            }
                        }
                    }
                }
            }
            let st = child.wait().map_err(|e| e.to_string())?;
            ok(st, "nhúng phụ đề (burn)")?;
            on_progress("Nhúng phụ đề", Some(100.0));
            Ok(())
        }
        _ => Err(format!("mode không hợp lệ: {}", mode)),
    }
}

fn with_ext(p: &Path, ext: &str) -> std::path::PathBuf {
    let mut pb = p.to_path_buf();
    pb.set_extension(ext);
    pb
}
