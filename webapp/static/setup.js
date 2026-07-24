"use strict";
// Màn Setup chỉ chạy trong Tauri (có window.__TAURI__). Mở bằng trình duyệt thường thì bỏ qua.
(function () {
  if (!window.__TAURI__) return;
  const { invoke } = window.__TAURI__.core;
  const { listen } = window.__TAURI__.event;

  const dl = document.getElementById("dl");
  const bar = document.getElementById("bar");
  const fill = document.getElementById("fill");
  const pct = document.getElementById("pct");

  listen("model-progress", (e) => {
    const p = Math.round(e.payload);
    fill.style.width = p + "%";
    pct.textContent = p + "%";
  });

  dl.addEventListener("click", async () => {
    dl.disabled = true;
    bar.style.display = "block";
    try {
      await invoke("download_model");
      location.href = "./index.html"; // xong -> vào app chính
    } catch (err) {
      pct.textContent = "Lỗi: " + err;
      dl.disabled = false;
    }
  });
})();
