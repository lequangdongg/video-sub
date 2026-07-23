#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod setup;
mod commands;
mod srt;
mod ass;
mod corrections;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            commands::check_setup,
            commands::download_model
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
