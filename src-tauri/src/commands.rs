use crate::{pipeline, setup, tools};
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, Manager, Window};

/// True nếu model đã tải xong -> vào thẳng app; false -> hiện màn Setup.
#[tauri::command]
pub fn check_setup() -> bool {
    setup::model_exists()
}

/// Tải model large-v3, phát sự kiện "model-progress" (payload = %).
#[tauri::command]
pub async fn download_model(window: Window) -> Result<(), String> {
    setup::download_model(|pct| {
        let _ = window.emit("model-progress", pct);
    })
    .await
}

fn job_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("{:x}", n)
}

/// Tạo sub tự động cho video ở `path`. Phát "progress" {step, percent}; trả {video, srt}.
#[tauri::command]
pub async fn run_auto(app: AppHandle, path: String, opts: Value) -> Result<Value, String> {
    let resource_dir = app.path().resource_dir().ok();
    let model = setup::resolve_model_path().ok_or("Chưa có model large-v3")?;
    let t = tools::resolve(resource_dir, model);
    let job_dir = setup::data_dir().join("jobs").join(job_id());
    let video = std::path::PathBuf::from(&path);
    let app2 = app.clone();

    let (out, srt) = tauri::async_runtime::spawn_blocking(move || {
        pipeline::process_auto(&t, &video, &job_dir, &opts, |step, pct| {
            let _ = app2.emit("progress", json!({"step": step, "percent": pct}));
        })
    })
    .await
    .map_err(|e| e.to_string())??;

    Ok(json!({
        "video": out.to_string_lossy(),
        "srt": srt.to_string_lossy(),
    }))
}

/// Copy file kết quả ra đường dẫn user chọn (dùng cho nút Tải về).
#[tauri::command]
pub fn save_file(src: String, dest: String) -> Result<(), String> {
    std::fs::copy(&src, &dest)
        .map(|_| ())
        .map_err(|e| e.to_string())
}
