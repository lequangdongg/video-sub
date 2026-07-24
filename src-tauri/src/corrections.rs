use regex::Regex;
use unicode_normalization::UnicodeNormalization;

/// Đọc file: mỗi dòng "sai => đúng" (# là ghi chú). Trả cặp (wrong, right).
pub fn load_corrections(text: &str) -> Vec<(String, String)> {
    let mut pairs = Vec::new();
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') || !line.contains("=>") {
            continue;
        }
        let mut it = line.splitn(2, "=>");
        let wrong = it.next().unwrap().trim().to_string();
        let right = it.next().unwrap_or("").trim().to_string();
        if !wrong.is_empty() {
            pairs.push((wrong, right));
        }
    }
    pairs
}

/// Thay cụm hay nghe nhầm trong nội dung .srt (không phân biệt hoa/thường, giữ hoa chữ đầu).
pub fn apply_corrections(srt: &str, pairs: &[(String, String)]) -> String {
    let mut text: String = srt.nfc().collect();
    for (wrong, right) in pairs {
        let wrong_nfc: String = wrong.nfc().collect();
        let right_nfc: String = right.nfc().collect();
        let re = Regex::new(&format!("(?i){}", regex::escape(&wrong_nfc))).unwrap();
        text = re
            .replace_all(&text, |caps: &regex::Captures| {
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
            })
            .into_owned();
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
