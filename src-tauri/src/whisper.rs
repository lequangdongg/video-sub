use crate::corrections;
use crate::tools::Tools;
use regex::Regex;
use std::io::{BufRead, BufReader};
use std::path::Path;
use std::process::{Command, Stdio};

/// Nhận diện giọng nói -> ghi srt_out; on_progress("Nhận diện giọng nói", %).
pub fn transcribe<F: Fn(&str, Option<f64>)>(
    t: &Tools,
    audio: &Path,
    lang: &str,
    srt_out: &Path,
    on_progress: &F,
) -> Result<(), String> {
    if !t.model.exists() {
        return Err(format!("Thiếu model whisper: {}", t.model.display()));
    }
    // base = srt_out bỏ đuôi .srt (whisper thêm .srt)
    let base = {
        let mut b = srt_out.to_path_buf();
        b.set_extension("");
        b
    };
    let mut child = Command::new(&t.whisper_cli)
        .arg("-m").arg(&t.model)
        .args(["-l", lang, "-t", "8", "-bs", "5", "-bo", "5", "-fa", "-pp", "-osrt", "-of"])
        .arg(&base)
        .arg("-f").arg(audio)
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;

    let re = Regex::new(r"progress\s*=\s*(\d+)%").unwrap();
    if let Some(stderr) = child.stderr.take() {
        let reader = BufReader::new(stderr);
        for line in reader.lines().map_while(Result::ok) {
            if let Some(c) = re.captures(&line) {
                if let Ok(p) = c[1].parse::<f64>() {
                    on_progress("Nhận diện giọng nói", Some(p));
                }
            }
        }
    }
    let st = child.wait().map_err(|e| e.to_string())?;
    if !st.success() || !srt_out.exists() {
        return Err("whisper-cli thất bại".into());
    }
    apply_corrections_file(t, srt_out)?;
    Ok(())
}

fn apply_corrections_file(t: &Tools, srt_out: &Path) -> Result<(), String> {
    let corr_text = match std::fs::read_to_string(&t.corrections_file) {
        Ok(s) => s,
        Err(_) => return Ok(()), // không có file -> bỏ qua
    };
    let pairs = corrections::load_corrections(&corr_text);
    if pairs.is_empty() {
        return Ok(());
    }
    let srt = std::fs::read_to_string(srt_out).map_err(|e| e.to_string())?;
    let fixed = corrections::apply_corrections(&srt, &pairs);
    std::fs::write(srt_out, fixed).map_err(|e| e.to_string())?;
    Ok(())
}
