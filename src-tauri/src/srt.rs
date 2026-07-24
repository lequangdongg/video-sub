use regex::Regex;
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
    let mut ms = (t * 1000.0).round() as i64;
    let h = ms / 3_600_000;
    ms %= 3_600_000;
    let mi = ms / 60_000;
    ms %= 60_000;
    let se = ms / 1000;
    ms %= 1000;
    format!("{:02}:{:02}:{:02},{:03}", h, mi, se, ms)
}

fn parse_ts(s: &str) -> Result<f64, String> {
    let re = Regex::new(r"(\d\d):(\d\d):(\d\d)[,.](\d\d\d)").unwrap();
    match re.captures(s) {
        Some(c) => {
            let h: f64 = c[1].parse().unwrap();
            let mi: f64 = c[2].parse().unwrap();
            let se: f64 = c[3].parse().unwrap();
            let ms: f64 = c[4].parse().unwrap();
            Ok(h * 3600.0 + mi * 60.0 + se + ms / 1000.0)
        }
        None => Err(format!("bad timestamp: {:?}", s)),
    }
}

pub fn parse_srt_str(raw: &str) -> Vec<Cue> {
    let raw = raw.trim_start_matches('\u{feff}'); // utf-8-sig
    let mut cues = Vec::new();
    let re = Regex::new(r"\n\s*\n").unwrap();
    for block in re.split(raw.trim()) {
        let lines: Vec<&str> = block.lines().filter(|l| !l.trim().is_empty()).collect();
        if lines.len() < 2 {
            continue;
        }
        let ts_idx = match lines.iter().position(|l| l.contains("-->")) {
            Some(i) => i,
            None => continue,
        };
        let parts: Vec<&str> = lines[ts_idx].splitn(2, "-->").collect();
        if parts.len() != 2 {
            continue;
        }
        let (start, end) = match (parse_ts(parts[0]), parse_ts(parts[1])) {
            (Ok(a), Ok(b)) => (a, b),
            _ => continue,
        };
        let text = lines[ts_idx + 1..].join("\n").trim().to_string();
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
        s.push_str(&format!(
            "{}\n{} --> {}\n{}\n\n",
            i + 1,
            format_ts(c.start),
            format_ts(c.end),
            c.text
        ));
    }
    s
}

pub fn write_srt(cues: &[Cue], path: &Path) -> std::io::Result<()> {
    std::fs::write(path, write_srt_str(cues))
}

pub fn shift(cues: &[Cue], offset: f64) -> Vec<Cue> {
    cues.iter()
        .map(|c| Cue {
            start: (c.start + offset).max(0.0),
            end: (c.end + offset).max(0.0),
            text: c.text.clone(),
        })
        .collect()
}

pub fn hide_before(cues: &[Cue], t: f64) -> Vec<Cue> {
    if t <= 0.0 {
        return cues.to_vec();
    }
    cues.iter()
        .filter(|c| c.end > t)
        .map(|c| Cue {
            start: c.start.max(t),
            end: c.end,
            text: c.text.clone(),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;
    fn golden(name: &str) -> Value {
        let p = format!("{}/tests/golden/{}", env!("CARGO_MANIFEST_DIR"), name);
        serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
    }
    const SRT_IN: &str = "1\n00:00:01,000 --> 00:00:02,500\nxin chào\n\n2\n00:00:03,000 --> 00:00:05,000\nnôn mưởng nhé\n";

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
