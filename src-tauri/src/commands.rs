use crate::setup;
use tauri::{Emitter, Window};

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
