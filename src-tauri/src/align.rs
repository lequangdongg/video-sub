use crate::ass::round_half_even;
use crate::srt::Cue;
use crate::tools::Tools;
use regex::Regex;
use serde_json::Value;
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read};
use std::path::Path;
use std::process::{Command, Stdio};
use unicode_normalization::UnicodeNormalization;

fn round3(x: f64) -> f64 {
    round_half_even(x * 1000.0) / 1000.0
}

// ---------------------------------------------------------------- whisper word timings

/// Gộp subword token của whisper thành từ (text bắt đầu bằng dấu cách = từ mới).
pub fn parse_word_timings(obj: &Value) -> Vec<(String, f64, f64)> {
    let mut words: Vec<(String, f64, f64)> = Vec::new();
    let mut cur_text = String::new();
    let mut cur_from: Option<f64> = None;
    let mut cur_to: f64 = 0.0;
    if let Some(trans) = obj.get("transcription").and_then(|v| v.as_array()) {
        for seg in trans {
            let tokens = match seg.get("tokens").and_then(|v| v.as_array()) {
                Some(t) => t,
                None => continue,
            };
            for tok in tokens {
                let raw = tok.get("text").and_then(|v| v.as_str()).unwrap_or("");
                if raw.trim().starts_with('[') {
                    continue;
                }
                let piece = raw.trim();
                if piece.is_empty() {
                    continue;
                }
                let off = tok.get("offsets");
                let t0 = off
                    .and_then(|o| o.get("from"))
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0)
                    / 1000.0;
                let t1 = off
                    .and_then(|o| o.get("to"))
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0)
                    / 1000.0;
                let starts_word = raw.starts_with(' ') || cur_from.is_none();
                if starts_word && !cur_text.is_empty() {
                    words.push((cur_text.clone(), cur_from.unwrap(), cur_to));
                    cur_text.clear();
                    cur_from = None;
                }
                if cur_from.is_none() {
                    cur_from = Some(t0);
                }
                cur_text.push_str(piece);
                cur_to = t1;
            }
        }
    }
    if !cur_text.is_empty() {
        words.push((cur_text, cur_from.unwrap(), cur_to));
    }
    words
}

/// Chạy whisper -ojf để lấy word timings; on_progress("Nhận diện & căn chỉnh", %).
pub fn word_timings<F: Fn(&str, Option<f64>)>(
    t: &Tools,
    audio: &Path,
    lang: &str,
    on_progress: &F,
) -> Result<Vec<(String, f64, f64)>, String> {
    if !t.model.exists() {
        return Err(format!("Thiếu model whisper: {}", t.model.display()));
    }
    let base = {
        let mut b = audio.to_path_buf();
        b.set_extension("");
        b
    };
    let mut child = Command::new(&t.whisper_cli)
        .arg("-m")
        .arg(&t.model)
        .args(["-l", lang, "-t", "8", "-fa", "-pp", "-ojf", "-of"])
        .arg(&base)
        .arg("-f")
        .arg(audio)
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;
    let re = Regex::new(r"progress\s*=\s*(\d+)%").unwrap();
    if let Some(stderr) = child.stderr.take() {
        for line in BufReader::new(stderr).lines().map_while(Result::ok) {
            if let Some(c) = re.captures(&line) {
                if let Ok(p) = c[1].parse::<f64>() {
                    on_progress("Nhận diện & căn chỉnh", Some(p));
                }
            }
        }
    }
    let st = child.wait().map_err(|e| e.to_string())?;
    let json_path = {
        let mut p = base.clone();
        p.set_extension("json");
        p
    };
    if !st.success() || !json_path.exists() {
        return Err("whisper-cli (json) thất bại".into());
    }
    let data = std::fs::read_to_string(&json_path).map_err(|e| e.to_string())?;
    let obj: Value = serde_json::from_str(&data).map_err(|e| e.to_string())?;
    Ok(parse_word_timings(&obj))
}

// ---------------------------------------------------------------- text extract / segment

/// Đọc văn bản thuần từ .txt hoặc .docx.
pub fn extract_text(path: &Path) -> Result<String, String> {
    let lower = path.to_string_lossy().to_lowercase();
    if lower.ends_with(".docx") {
        let file = std::fs::File::open(path).map_err(|e| e.to_string())?;
        let mut zip = zip::ZipArchive::new(file).map_err(|e| e.to_string())?;
        let mut xml = String::new();
        zip.by_name("word/document.xml")
            .map_err(|e| e.to_string())?
            .read_to_string(&mut xml)
            .map_err(|e| e.to_string())?;
        let para_re = Regex::new(r"</w:p>").unwrap();
        let run_re = Regex::new(r"(?s)<w:t[^>]*>(.*?)</w:t>").unwrap();
        let mut out = Vec::new();
        for para in para_re.split(&xml) {
            let mut line = String::new();
            for c in run_re.captures_iter(para) {
                line.push_str(&c[1]);
            }
            let line = html_unescape(&line);
            let line = line.trim();
            if !line.is_empty() {
                out.push(line.to_string());
            }
        }
        Ok(out.join("\n"))
    } else {
        let s = std::fs::read_to_string(path).map_err(|e| e.to_string())?;
        Ok(s.trim_start_matches('\u{feff}').trim().to_string())
    }
}

fn html_unescape(s: &str) -> String {
    s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&apos;", "'")
}

fn sent_split(line: &str) -> Vec<String> {
    // thay cho lookbehind (?<=[.!?…])\s+ của Python: tách sau dấu câu + khoảng trắng
    let chars: Vec<char> = line.chars().collect();
    let mut res = Vec::new();
    let mut start = 0usize;
    let mut i = 0usize;
    while i < chars.len() {
        if matches!(chars[i], '.' | '!' | '?' | '…') {
            let j = i + 1;
            if j < chars.len() && chars[j].is_whitespace() {
                res.push(chars[start..=i].iter().collect());
                let mut k = j;
                while k < chars.len() && chars[k].is_whitespace() {
                    k += 1;
                }
                start = k;
                i = k;
                continue;
            }
        }
        i += 1;
    }
    if start < chars.len() {
        res.push(chars[start..].iter().collect());
    }
    if res.is_empty() {
        res.push(String::new());
    }
    res
}

fn chunk_by_length(s: &str, max_chars: usize) -> Vec<String> {
    let words: Vec<&str> = s.split_whitespace().collect();
    let mut chunks = Vec::new();
    let mut cur = String::new();
    for w in words {
        if !cur.is_empty() && cur.chars().count() + 1 + w.chars().count() > max_chars {
            chunks.push(cur.clone());
            cur = w.to_string();
        } else {
            cur = if cur.is_empty() {
                w.to_string()
            } else {
                format!("{} {}", cur, w)
            };
        }
    }
    if !cur.is_empty() {
        chunks.push(cur);
    }
    chunks
}

pub fn split_into_cue_texts(text: &str, max_chars: usize) -> Vec<String> {
    let mut out = Vec::new();
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        if line.chars().count() <= max_chars {
            out.push(line.to_string());
            continue;
        }
        for sent in sent_split(line) {
            let sent = sent.trim();
            if sent.is_empty() {
                continue;
            }
            if sent.chars().count() <= max_chars {
                out.push(sent.to_string());
            } else {
                out.extend(chunk_by_length(sent, max_chars));
            }
        }
    }
    out
}

// ---------------------------------------------------------------- alignment

fn norm(w: &str) -> String {
    let lower = w.to_lowercase();
    lower
        .nfd()
        .filter(|c| !('\u{0300}'..='\u{036F}').contains(c)) // bỏ dấu thanh (Mn)
        .filter(|c| c.is_alphanumeric())
        .collect()
}

fn distribute(cue_texts: &[String], t0: f64, t1: f64) -> Vec<Cue> {
    let span = (t1 - t0).max(0.001);
    let weights: Vec<f64> = cue_texts
        .iter()
        .map(|t| t.chars().count().max(1) as f64)
        .collect();
    let total: f64 = weights.iter().sum();
    let mut cues = Vec::new();
    let mut cursor = t0;
    for (text, w) in cue_texts.iter().zip(weights.iter()) {
        let dur = span * w / total;
        cues.push(Cue {
            start: round3(cursor),
            end: round3(cursor + dur),
            text: text.clone(),
        });
        cursor += dur;
    }
    cues
}

fn find_longest_match(
    a: &[String],
    b2j: &HashMap<&str, Vec<usize>>,
    alo: usize,
    ahi: usize,
    blo: usize,
    bhi: usize,
) -> (usize, usize, usize) {
    let (mut besti, mut bestj, mut bestsize) = (alo, blo, 0usize);
    let mut j2len: HashMap<usize, usize> = HashMap::new();
    for i in alo..ahi {
        let mut newj2len: HashMap<usize, usize> = HashMap::new();
        if let Some(js) = b2j.get(a[i].as_str()) {
            for &j in js {
                if j < blo {
                    continue;
                }
                if j >= bhi {
                    break;
                }
                let k = j2len.get(&j.wrapping_sub(1)).copied().unwrap_or(0) + 1;
                newj2len.insert(j, k);
                if k > bestsize {
                    besti = i + 1 - k;
                    bestj = j + 1 - k;
                    bestsize = k;
                }
            }
        }
        j2len = newj2len;
    }
    (besti, bestj, bestsize)
}

fn matching_blocks(a: &[String], b: &[String]) -> Vec<(usize, usize, usize)> {
    let la = a.len();
    let lb = b.len();
    let mut b2j: HashMap<&str, Vec<usize>> = HashMap::new();
    for (j, x) in b.iter().enumerate() {
        b2j.entry(x.as_str()).or_default().push(j);
    }
    let mut queue = vec![(0usize, la, 0usize, lb)];
    let mut blocks = Vec::new();
    while let Some((alo, ahi, blo, bhi)) = queue.pop() {
        let (i, j, k) = find_longest_match(a, &b2j, alo, ahi, blo, bhi);
        if k > 0 {
            blocks.push((i, j, k));
            if alo < i && blo < j {
                queue.push((alo, i, blo, j));
            }
            if i + k < ahi && j + k < bhi {
                queue.push((i + k, ahi, j + k, bhi));
            }
        }
    }
    blocks.sort();
    let mut merged: Vec<(usize, usize, usize)> = Vec::new();
    let (mut i1, mut j1, mut k1) = (0usize, 0usize, 0usize);
    for (i2, j2, k2) in blocks {
        if i1 + k1 == i2 && j1 + k1 == j2 {
            k1 += k2;
        } else {
            if k1 > 0 {
                merged.push((i1, j1, k1));
            }
            i1 = i2;
            j1 = j2;
            k1 = k2;
        }
    }
    if k1 > 0 {
        merged.push((i1, j1, k1));
    }
    merged.push((la, lb, 0));
    merged
}

fn interp(seq: &mut [Option<f64>], lo: f64, hi: f64) {
    let known: Vec<(usize, f64)> = seq
        .iter()
        .enumerate()
        .filter_map(|(i, t)| t.map(|v| (i, v)))
        .collect();
    let n = seq.len();
    for idx in 0..n {
        if seq[idx].is_some() {
            continue;
        }
        let prev = known
            .iter()
            .filter(|k| k.0 < idx)
            .max_by_key(|k| k.0)
            .copied()
            .unwrap_or((0, lo));
        let nxt = known
            .iter()
            .filter(|k| k.0 > idx)
            .min_by_key(|k| k.0)
            .copied()
            .unwrap_or((n - 1, hi));
        if nxt.0 == prev.0 {
            seq[idx] = Some(prev.1);
        } else {
            let frac = (idx as f64 - prev.0 as f64) / (nxt.0 as f64 - prev.0 as f64);
            seq[idx] = Some(prev.1 + frac * (nxt.1 - prev.1));
        }
    }
}

pub fn align(cue_texts: &[String], words: &[(String, f64, f64)]) -> Vec<Cue> {
    if words.is_empty() {
        return distribute(cue_texts, 0.0, (cue_texts.len() as f64).max(1.0));
    }
    let span0 = words[0].1;
    let span1 = words[words.len() - 1].2;

    let mut user_words: Vec<(usize, String)> = Vec::new();
    for (ci, text) in cue_texts.iter().enumerate() {
        for tok in text.split_whitespace() {
            let n = norm(tok);
            if !n.is_empty() {
                user_words.push((ci, n));
            }
        }
    }
    if user_words.is_empty() {
        return distribute(cue_texts, span0, span1);
    }
    let w_norm: Vec<String> = words.iter().map(|w| norm(&w.0)).collect();
    let u_norm: Vec<String> = user_words.iter().map(|u| u.1.clone()).collect();

    let blocks = matching_blocks(&u_norm, &w_norm);
    let mut starts: Vec<Option<f64>> = vec![None; user_words.len()];
    let mut ends: Vec<Option<f64>> = vec![None; user_words.len()];
    let mut matched = 0usize;
    for (ai, bj, size) in &blocks {
        for k in 0..*size {
            starts[ai + k] = Some(words[bj + k].1);
            ends[ai + k] = Some(words[bj + k].2);
            matched += 1;
        }
    }
    if (matched as f64) < (user_words.len().max(1) as f64) * 0.25 {
        return distribute(cue_texts, span0, span1);
    }
    interp(&mut starts, span0, span1);
    interp(&mut ends, span0, span1);

    let mut by_cue: HashMap<usize, Vec<(f64, f64)>> = HashMap::new();
    for (i, (ci, _)) in user_words.iter().enumerate() {
        by_cue
            .entry(*ci)
            .or_default()
            .push((starts[i].unwrap(), ends[i].unwrap()));
    }
    let mut cues: Vec<Cue> = Vec::new();
    for (ci, text) in cue_texts.iter().enumerate() {
        if let Some(pairs) = by_cue.get(&ci) {
            let mn = pairs.iter().map(|p| p.0).fold(f64::INFINITY, f64::min);
            let mx = pairs.iter().map(|p| p.1).fold(f64::NEG_INFINITY, f64::max);
            cues.push(Cue {
                start: round3(mn),
                end: round3(mx),
                text: text.clone(),
            });
        } else {
            let anchor = cues.last().map(|c| c.end).unwrap_or(span0);
            cues.push(Cue {
                start: round3(anchor),
                end: round3(anchor),
                text: text.clone(),
            });
        }
    }
    for i in 0..cues.len() {
        if cues[i].end < cues[i].start {
            cues[i].end = cues[i].start;
        }
        if i + 1 < cues.len() && cues[i].end > cues[i + 1].start {
            cues[i].end = cues[i + 1].start;
        }
    }
    cues
}

#[cfg(test)]
mod tests {
    use super::*;
    fn golden(name: &str) -> Value {
        let p = format!("{}/tests/golden/{}", env!("CARGO_MANIFEST_DIR"), name);
        serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
    }

    #[test]
    fn parse_word_timings_matches_python() {
        let wj = serde_json::json!({"transcription": [{"tokens": [
            {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}},
            {"text": " một", "offsets": {"from": 0, "to": 300}},
            {"text": " hai", "offsets": {"from": 300, "to": 600}},
            {"text": " ba", "offsets": {"from": 600, "to": 900}},
            {"text": " bốn", "offsets": {"from": 900, "to": 1200}}
        ]}]});
        let words = parse_word_timings(&wj);
        let g = golden("word_timings.json");
        let arr = g.as_array().unwrap();
        assert_eq!(words.len(), arr.len());
        for (w, gw) in words.iter().zip(arr) {
            assert_eq!(w.0, gw["text"].as_str().unwrap());
            assert_eq!(w.1, gw["from"].as_f64().unwrap());
            assert_eq!(w.2, gw["to"].as_f64().unwrap());
        }
    }

    #[test]
    fn split_cues_matches_python() {
        let g = golden("split_cues.json");
        let a = split_into_cue_texts("Dòng một.\nDòng hai vẫn ngắn.", 90);
        let exp_a: Vec<String> = g["a"].as_array().unwrap().iter().map(|v| v.as_str().unwrap().to_string()).collect();
        assert_eq!(a, exp_a);
        let b = split_into_cue_texts("Một câu. Câu hai! Câu ba?", 90);
        let exp_b: Vec<String> = g["b"].as_array().unwrap().iter().map(|v| v.as_str().unwrap().to_string()).collect();
        assert_eq!(b, exp_b);
    }

    #[test]
    fn align_matches_python() {
        let g = golden("align.json");
        let cue_texts = vec!["một hai".to_string(), "ba bốn".to_string()];
        let words = vec![
            ("một".to_string(), 0.0, 0.3),
            ("hai".to_string(), 0.3, 0.6),
            ("ba".to_string(), 0.6, 0.9),
            ("bốn".to_string(), 0.9, 1.2),
        ];
        let cues = align(&cue_texts, &words);
        let arr = g.as_array().unwrap();
        assert_eq!(cues.len(), arr.len());
        for (c, gc) in cues.iter().zip(arr) {
            assert_eq!(c.start, gc["start"].as_f64().unwrap());
            assert_eq!(c.end, gc["end"].as_f64().unwrap());
            assert_eq!(c.text, gc["text"].as_str().unwrap());
        }
    }
}
