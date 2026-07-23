use futures_util::StreamExt;
use std::fs;
use std::io::Write;
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

/// ~/Library/Application Support/AutoSub
pub fn data_dir() -> PathBuf {
    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("AutoSub")
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

/// % tải: tỉ lệ * 100, chặn trần 100; total=0 -> 0 (chưa biết dung lượng).
pub fn download_pct(done: u64, total: u64) -> f64 {
    if total == 0 {
        return 0.0;
    }
    ((done as f64 / total as f64) * 100.0).min(100.0)
}

/// Tải model large-v3 về models_dir; gọi on_pct(percent) khi có tiến triển.
/// Ghi ra file .part rồi rename (atomic) để không để lại file dở nếu đứt mạng.
pub async fn download_model<F: Fn(f64)>(on_pct: F) -> Result<(), String> {
    if model_exists() {
        on_pct(100.0);
        return Ok(());
    }
    fs::create_dir_all(models_dir()).map_err(|e| e.to_string())?;
    let tmp = model_path().with_extension("part");

    let resp = reqwest::get(model_url()).await.map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("tải model lỗi HTTP {}", resp.status()));
    }
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
    fs::rename(&tmp, model_path()).map_err(|e| e.to_string())?;
    on_pct(100.0);
    Ok(())
}

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
        assert!(p
            .to_string_lossy()
            .ends_with("AutoSub/models/ggml-large-v3.bin"));
    }

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
}
