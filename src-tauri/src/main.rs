#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod setup;
mod commands;
mod srt;
mod ass;
mod corrections;
mod tools;
mod ffmpeg;
mod whisper;
mod align;
mod pipeline;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            commands::check_setup,
            commands::download_model,
            commands::run_auto,
            commands::run_merge,
            commands::save_file
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
