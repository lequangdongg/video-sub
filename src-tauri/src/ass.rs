use crate::srt::Cue;

// ---------------------------------------------------------------- helpers số

/// round nửa-về-chẵn (banker's) như Python round(); khác f64::round() ở đúng ca .5.
pub fn round_half_even(x: f64) -> f64 {
    let f = x.floor();
    let diff = x - f;
    if (diff - 0.5).abs() < 1e-9 {
        if (f as i64) % 2 == 0 {
            f
        } else {
            f + 1.0
        }
    } else {
        x.round()
    }
}
pub fn round_i(x: f64) -> i64 {
    round_half_even(x) as i64
}

/// Số thực kiểu Python "{:g}": 16.0->"16", 4.0->"4", 16.5->"16.5".
pub fn fmt_g(x: f64) -> String {
    if x == x.trunc() && x.abs() < 1e15 {
        return format!("{}", x as i64);
    }
    let mut s = format!("{:.6}", x);
    while s.contains('.') && s.ends_with('0') {
        s.pop();
    }
    if s.ends_with('.') {
        s.pop();
    }
    s
}

/// Số thực kiểu Python str(float): 4.0->"4.0" (dùng cho Outline của force_style box).
fn py_float(x: f64) -> String {
    format!("{:?}", x)
}

// ---------------------------------------------------------------- màu / thời gian

fn up(s: &str) -> String {
    s.to_uppercase()
}
fn expand_hex(hexcolor: &str) -> String {
    let h = hexcolor.trim_start_matches('#');
    if h.len() == 3 {
        h.chars().flat_map(|c| [c, c]).collect()
    } else {
        h.to_string()
    }
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
    let h = cs / 360_000;
    cs %= 360_000;
    let m = cs / 6000;
    cs %= 6000;
    let s = cs / 100;
    cs %= 100;
    format!("{}:{:02}:{:02}.{:02}", h, m, s, cs)
}

// ---------------------------------------------------------------- bề rộng ký tự

fn is_narrow(c: char) -> bool {
    "iíìỉĩịl.,:;!'|`ftjr()[]".contains(c)
}
fn is_wide(c: char) -> bool {
    "mwMW@".contains(c)
}

pub fn char_frac(c: char, bold: bool) -> f64 {
    let f = if c == ' ' {
        0.30
    } else if is_narrow(c) {
        0.32
    } else if is_wide(c) {
        0.60
    } else if c.is_ascii_digit() {
        0.42
    } else if c.is_uppercase() {
        0.52
    } else {
        0.40
    };
    f * if bold { 1.04 } else { 1.0 }
}

pub fn line_width(text: &str, fontpx: f64, bold: bool) -> f64 {
    fontpx * text.chars().map(|c| char_frac(c, bold)).sum::<f64>()
}

pub fn wrap_width(text: &str, fontpx: f64, bold: bool, max_w: f64) -> Vec<String> {
    let joined = text.replace('\n', " ");
    let words: Vec<&str> = joined.split_whitespace().collect();
    if words.is_empty() {
        return vec![String::new()];
    }
    let mut lines: Vec<String> = Vec::new();
    let mut cur = String::new();
    for w in words {
        let trial = if cur.is_empty() {
            w.to_string()
        } else {
            format!("{} {}", cur, w)
        };
        if cur.is_empty() || line_width(&trial, fontpx, bold) <= max_w {
            cur = trial;
        } else {
            lines.push(cur);
            cur = w.to_string();
        }
    }
    if !cur.is_empty() {
        lines.push(cur);
    }
    lines
}

// ---------------------------------------------------------------- style / force_style

#[derive(Debug, Default, Clone)]
pub struct Style {
    pub font: Option<String>,
    pub size: Option<String>,
    pub bold: bool,
    pub italic: bool,
    pub fill: Option<String>,
    pub outline: Option<String>,
    pub outline_color: Option<String>,
    pub outline_opacity: Option<String>,
    pub box_on: bool,
    pub box_color: Option<String>,
    pub box_opacity: Option<String>,
    pub align: Option<String>,
    pub margin: Option<String>,
}

fn align_num(a: &Option<String>) -> Option<i64> {
    match a.as_deref() {
        Some("bottom") => Some(2),
        Some("middle") => Some(5),
        Some("top") => Some(8),
        _ => None,
    }
}
fn parse_f(s: &Option<String>) -> Option<f64> {
    s.as_ref().and_then(|v| v.trim().parse::<f64>().ok())
}

pub fn build_force_style(style: Option<&Style>) -> String {
    let s = match style {
        Some(s) => s,
        None => return String::new(),
    };
    let mut parts: Vec<String> = Vec::new();
    if let Some(f) = &s.font {
        if !f.is_empty() {
            parts.push(format!("FontName={}", f));
        }
    }
    if let Some(sz) = parse_f(&s.size) {
        parts.push(format!("FontSize={}", sz as i64));
    }
    parts.push(if s.bold { "Bold=-1".into() } else { "Bold=0".into() });
    if s.italic {
        parts.push("Italic=-1".into());
    }
    if let Some(fill) = &s.fill {
        if !fill.is_empty() {
            parts.push(format!("PrimaryColour={}", hex_to_ass(fill, 0.0)));
        }
    }
    if s.box_on {
        parts.push("BorderStyle=3".into());
        parts.push("Shadow=0".into());
        let box_color = s.box_color.clone().unwrap_or_else(|| "#000000".into());
        let op = parse_f(&s.box_opacity).unwrap_or(1.0);
        parts.push(format!("OutlineColour={}", hex_to_ass(&box_color, 1.0 - op)));
        let pad = parse_f(&s.outline).unwrap_or(0.0);
        // Python: f"Outline={pad if pad>0 else 4}" — pad là float (str "4.0"), else int 4 ("4")
        let outline_str = if pad > 0.0 {
            py_float(pad)
        } else {
            "4".to_string()
        };
        parts.push(format!("Outline={}", outline_str));
    } else {
        if let Some(o) = &s.outline {
            if !o.is_empty() {
                parts.push(format!("Outline={}", o));
            }
        }
        if let Some(oc) = &s.outline_color {
            if !oc.is_empty() {
                let op = parse_f(&s.outline_opacity).unwrap_or(1.0);
                parts.push(format!("OutlineColour={}", hex_to_ass(oc, 1.0 - op)));
            }
        }
    }
    if let Some(a) = align_num(&s.align) {
        parts.push(format!("Alignment={}", a));
    }
    if let Some(m) = parse_f(&s.margin) {
        parts.push(format!("MarginV={}", m as i64));
    }
    parts.join(",")
}

/// escape đường dẫn cho filter subtitles của ffmpeg (\\ ' :).
pub fn esc_filter(p: &str) -> String {
    p.replace('\\', "\\\\").replace('\'', "\\'").replace(':', "\\:")
}

// ---------------------------------------------------------------- write_band_ass

const PLAYRES_Y: f64 = 288.0;

pub fn write_band_ass_str(cues: &[Cue], style: &Style, width: i64, height: i64) -> String {
    let h = height.max(1) as f64;
    let play_x = ((PLAYRES_Y * width as f64 / h).round() as i64).max(320);
    let font = style
        .font
        .clone()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "UTM Avo".into());
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

    let mut header = String::new();
    header.push_str("[Script Info]\n");
    header.push_str("ScriptType: v4.00+\n");
    header.push_str(&format!("PlayResX: {}\n", play_x));
    header.push_str(&format!("PlayResY: {}\n", PLAYRES_Y as i64));
    header.push_str("WrapStyle: 2\n");
    header.push_str("ScaledBorderAndShadow: yes\n\n");
    header.push_str("[V4+ Styles]\n");
    header.push_str("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n");
    header.push_str(&format!(
        "Style: Text,{},{},{},&H000000FF,{},&H00000000,{},{},0,0,100,100,0,0,1,{},0,{},{},{},{},1\n\n",
        font, fmt_g(fontpx), primary, outline_col, bold, italic, fmt_g(outline_w), align, side, side, margin_v
    ));
    header.push_str("[Events]\n");
    header.push_str("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n");

    let max_lines = 2usize;
    let mut lines_out: Vec<String> = Vec::new();
    for c in cues {
        let text = c.text.replace('{', "(").replace('}', ")");
        let wrapped = wrap_width(&text, fontpx, is_bold, max_text_w);
        let pages: Vec<Vec<String>> = wrapped.chunks(max_lines).map(|c| c.to_vec()).collect();
        let weights: Vec<f64> = pages
            .iter()
            .map(|pg| {
                let s: usize = pg.iter().map(|l| l.chars().count()).sum();
                if s == 0 {
                    1.0
                } else {
                    s as f64
                }
            })
            .collect();
        let total_w: f64 = weights.iter().sum();
        let dur = (c.end - c.start).max(0.0);
        let mut t = c.start;
        let n_pages = pages.len();
        for (idx, (pg, w)) in pages.iter().zip(weights.iter()).enumerate() {
            let p_start = t;
            let p_end = if idx == n_pages - 1 {
                c.end
            } else {
                t + dur * (w / total_w)
            };
            t = p_end;
            let n = pg.len() as f64;
            let block_h = n * line_h;
            let text_w = pg
                .iter()
                .map(|ln| line_width(ln, fontpx, is_bold))
                .fold(0.0_f64, f64::max);
            let box_w = (text_w + 2.0 * pad_x).min(max_box_w);
            let x1 = round_i((play_x as f64 - box_w) / 2.0);
            let x2 = round_i(x1 as f64 + box_w);
            let (y1, y2) = if align == 8 {
                (
                    margin_v as f64 - pad_top,
                    margin_v as f64 + block_h + pad_bot,
                )
            } else if align == 5 {
                let cy = PLAYRES_Y / 2.0;
                (cy - block_h / 2.0 - pad_top, cy + block_h / 2.0 + pad_bot)
            } else {
                let yb = PLAYRES_Y - margin_v as f64;
                (yb - block_h - pad_top, yb + pad_bot)
            };
            let iy1 = round_i(y1);
            let iy2 = round_i(y2);
            let band = format!(
                "{{\\p1\\an7\\pos(0,0)\\1c{}\\1a{}\\bord0\\shad0}}m {} {} l {} {} {} {} {} {}{{\\p0}}",
                band_bgr, band_a, x1, iy1, x2, iy1, x2, iy2, x1, iy2
            );
            let st = ass_time(p_start);
            let en = ass_time(p_end);
            let text_body = pg.join("\\N");
            lines_out.push(format!("Dialogue: 0,{},{},Text,,0,0,0,,{}", st, en, band));
            lines_out.push(format!("Dialogue: 1,{},{},Text,,0,0,0,,{}", st, en, text_body));
        }
    }
    format!("{}{}\n", header, lines_out.join("\n"))
}

pub fn write_band_ass(
    cues: &[Cue],
    path: &std::path::Path,
    style: &Style,
    width: i64,
    height: i64,
) -> std::io::Result<()> {
    std::fs::write(path, write_band_ass_str(cues, style, width, height))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;
    fn golden(name: &str) -> Value {
        let p = format!("{}/tests/golden/{}", env!("CARGO_MANIFEST_DIR"), name);
        serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
    }

    #[test]
    fn helpers_match_python() {
        let g = golden("ass_helpers.json");
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

    #[test]
    fn width_and_wrap_match_python() {
        let g = golden("wrap.json");
        let w = line_width("xin chào", 16.0, true);
        assert!((w - g["w_short"].as_f64().unwrap()).abs() < 1e-9, "line_width lệch: {}", w);
        let wrapped = wrap_width(
            "đây là một câu rất dài để kiểm tra việc xuống dòng theo bề rộng hộp nền",
            16.0,
            true,
            120.0,
        );
        let exp: Vec<String> = g["wrap_long"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap().to_string())
            .collect();
        assert_eq!(wrapped, exp);
    }

    fn style_box() -> Style {
        Style {
            font: Some("UTM Avo".into()),
            size: Some("16".into()),
            bold: true,
            fill: Some("#ffffff".into()),
            box_on: true,
            box_color: Some("#000000".into()),
            box_opacity: Some("0.25".into()),
            outline: Some("4".into()),
            align: Some("bottom".into()),
            margin: Some("24".into()),
            ..Default::default()
        }
    }

    #[test]
    fn force_style_box_matches_python() {
        assert_eq!(
            build_force_style(Some(&style_box())),
            golden("force_style.json")["box"].as_str().unwrap()
        );
    }

    #[test]
    fn force_style_stroke_matches_python() {
        let s = Style {
            font: Some("UTM Avo".into()),
            size: Some("18".into()),
            bold: false,
            fill: Some("#ffff00".into()),
            outline: Some("2".into()),
            outline_color: Some("#000000".into()),
            outline_opacity: Some("1.0".into()),
            align: Some("bottom".into()),
            margin: Some("30".into()),
            ..Default::default()
        };
        assert_eq!(
            build_force_style(Some(&s)),
            golden("force_style.json")["stroke"].as_str().unwrap()
        );
    }

    #[test]
    fn force_style_none_is_empty() {
        assert_eq!(build_force_style(None), golden("force_style.json")["none"].as_str().unwrap());
    }

    #[test]
    fn band_ass_matches_python_byte_for_byte() {
        let g = golden("band_ass.json");
        let cues = vec![
            Cue { start: 1.0, end: 3.0, text: "xin chào các bạn".into() },
            Cue {
                start: 3.0,
                end: 8.0,
                text: "đây là một câu rất dài cần xuống dòng và tách trang để kiểm tra hộp nền băng ngang ôm sát chữ".into(),
            },
        ];
        let got = write_band_ass_str(&cues, &style_box(), 1920, 1080);
        assert_eq!(got, g["content"].as_str().unwrap());
    }
}
