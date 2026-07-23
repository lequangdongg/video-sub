use std::path::PathBuf;

/// Đường dẫn các công cụ + tài nguyên bundle. Dev: lấy từ src-tauri/; app thật: từ Resources.
#[derive(Clone, Debug)]
pub struct Tools {
    pub ffmpeg: PathBuf,
    pub ffprobe: PathBuf,
    pub whisper_cli: PathBuf,
    pub fonts_dir: PathBuf,
    pub corrections_file: PathBuf,
    pub model: PathBuf,
}

/// Chọn đường dẫn tồn tại đầu tiên trong danh sách (ưu tiên Resources, fallback dev).
fn first_existing(cands: &[PathBuf]) -> PathBuf {
    cands
        .iter()
        .find(|p| p.exists())
        .cloned()
        .unwrap_or_else(|| cands[0].clone())
}

/// Dựng Tools từ thư mục Resources (app bundle) + fallback thư mục dev.
pub fn resolve(resource_dir: Option<PathBuf>, model: PathBuf) -> Tools {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR")); // src-tauri/
    let dev_bin = manifest.join("binaries");
    let dev_fonts = manifest.parent().unwrap().join("assets/fonts");
    let dev_corr = manifest.parent().unwrap().join("webapp/corrections.txt");
    let res = resource_dir.unwrap_or_else(|| dev_bin.clone());

    Tools {
        ffmpeg: first_existing(&[res.join("binaries/ffmpeg"), dev_bin.join("ffmpeg")]),
        ffprobe: first_existing(&[res.join("binaries/ffprobe"), dev_bin.join("ffprobe")]),
        whisper_cli: first_existing(&[res.join("binaries/whisper-cli"), dev_bin.join("whisper-cli")]),
        fonts_dir: first_existing(&[res.join("assets/fonts"), dev_fonts]),
        corrections_file: first_existing(&[res.join("corrections.txt"), dev_corr]),
        model,
    }
}
