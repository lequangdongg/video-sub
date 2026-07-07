"use strict";
const $ = (id) => document.getElementById(id);

let activeTab = "auto";
let currentJob = null;
let pollTimer = null;
let jobKind = "sub";   // "sub" | "tts" -> quyết định link tải khi xong

/* ---------------------------------------------------------------- tabs */
function showTab(which) {
  activeTab = which;
  for (const t of ["auto", "merge", "tts"]) {
    $("panel-" + t).classList.toggle("hidden", which !== t);
    $("tab-" + t).setAttribute("aria-selected", which === t);
  }
  // khung xem trước/monitor chỉ dùng cho sub, ẩn bảng style khi ở tab đọc văn bản
  $("style-panel").classList.toggle("hidden", which === "tts" || activeMode() !== "burn");
}
$("tab-auto").onclick = () => { showTab("auto"); updateStylePanel(); };
$("tab-merge").onclick = () => { showTab("merge"); updateStylePanel(); };
$("tab-tts").onclick = () => { showTab("tts"); ttsLoadVoices(); };

/* ---------------------------------------------------------------- video preview / monitor */
function fmtTc(sec) {
  if (!isFinite(sec)) return "00:00:00,000";
  const ms = Math.round(sec * 1000);
  const h = String(Math.floor(ms / 3600000)).padStart(2, "0");
  const m = String(Math.floor((ms % 3600000) / 60000)).padStart(2, "0");
  const s = String(Math.floor((ms % 60000) / 1000)).padStart(2, "0");
  return `${h}:${m}:${s},${String(ms % 1000).padStart(3, "0")}`;
}

function setVideoPreview(file) {
  const mon = $("monitor"), v = $("preview");
  if (!file) { mon.classList.remove("has-video"); v.removeAttribute("src"); $("vname").textContent = "AUTOSUB · PREVIEW"; $("tc").textContent = "00:00:00,000"; return; }
  v.src = URL.createObjectURL(file);
  mon.classList.add("has-video");
  $("vname").textContent = file.name;
  v.onloadedmetadata = () => { $("tc").textContent = fmtTc(v.duration); };
}

function markFilepick(pickId, file) {
  const fp = $(pickId);
  fp.classList.toggle("set", !!file);
  fp.querySelector(".name").textContent = file ? file.name : fp.dataset.placeholder;
}

function assignToInput(input, file) {
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;
}

// the monitor is the video picker for BOTH tabs; sub file has its own filepick
function activeVideoInput() { return activeTab === "auto" ? $("auto-video") : $("merge-video"); }

$("auto-video").addEventListener("change", () => { const f = $("auto-video").files[0]; if (f) setVideoPreview(f); });
$("merge-video").addEventListener("change", () => { const f = $("merge-video").files[0]; if (f) setVideoPreview(f); });
$("merge-sub").addEventListener("change", () => markFilepick("pick-merge-sub", $("merge-sub").files[0]));

$("monitor").addEventListener("click", () => activeVideoInput().click());

["dragenter", "dragover"].forEach((ev) =>
  $("monitor").addEventListener(ev, (e) => { e.preventDefault(); $("monitor").classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) =>
  $("monitor").addEventListener(ev, (e) => { e.preventDefault(); $("monitor").classList.remove("drag"); }));
$("monitor").addEventListener("drop", (e) => {
  const f = e.dataTransfer.files[0];
  if (!f) return;
  const input = activeVideoInput();
  assignToInput(input, f);
  setVideoPreview(f);
});

/* ---------------------------------------------------------------- progress / SSE */
const STEP_ORDER = ["Tách audio", "Nhận diện giọng nói", "Nhận diện & căn chỉnh", "Chuẩn bị sub", "Nhúng phụ đề", "Tổng hợp giọng nói"];
const stepState = {};

function renderSteps() {
  const names = Object.keys(stepState).sort((a, b) => STEP_ORDER.indexOf(a) - STEP_ORDER.indexOf(b));
  $("steps").innerHTML = names.map((name) => {
    const s = stepState[name];
    const cls = s.done ? "done" : "active";
    const pct = (s.percent != null && !s.done) ? `${Math.round(s.percent)}%` : (s.done ? "✓" : "");
    const node = s.done ? "✓" : "";
    const barw = s.done ? 100 : (s.percent || 0);
    return `<div class="step ${cls}">
      <div class="node">${node}</div>
      <div class="name">${name}</div>
      <div class="pct">${pct}</div>
      ${s.done ? "" : `<div class="bar"><i style="width:${barw}%"></i></div>`}
    </div>`;
  }).join("");
}

function resetUI() {
  for (const k in stepState) delete stepState[k];
  $("stage").classList.remove("hidden");
  $("error").classList.add("hidden");
  $("result").classList.add("hidden");
  renderSteps();
}
function showError(msg) {
  $("stage").classList.remove("hidden");
  const e = $("error");
  e.querySelector("span").textContent = msg;
  e.classList.remove("hidden");
}

async function submit(url, form, btn) {
  btn.disabled = true;
  resetUI();
  jobKind = "sub";
  let res;
  try { res = await fetch(url, { method: "POST", body: form }); }
  catch (e) { showError("Không gửi được yêu cầu. Kiểm tra kết nối tới máy chủ."); btn.disabled = false; return; }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    showError(j.error || "Có lỗi khi gửi yêu cầu.");
    btn.disabled = false; return;
  }
  const { job_id } = await res.json();
  listen(job_id, btn);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function applyStatus(m, jobId, btn) {
  const steps = m.steps || {};
  const idxs = Object.keys(steps).map((s) => STEP_ORDER.indexOf(s));
  const maxIdx = idxs.length ? Math.max(...idxs) : -1;
  for (const [step, percent] of Object.entries(steps)) {
    const isLast = STEP_ORDER.indexOf(step) === maxIdx;
    stepState[step] = { percent, done: percent === 100 || !isLast };
  }
  renderSteps();
  if (m.status === "done") {
    for (const k in stepState) stepState[k].done = true;
    renderSteps();
    const audio = $("tts-audio");
    if (jobKind === "tts") {
      $("dl-video").href = `/api/jobs/${jobId}/download/audio`;
      $("dl-video").querySelector(".lbl").textContent = "Tải file mp3";
      $("dl-srt").href = `/api/jobs/${jobId}/download/srt`;
      audio.src = `/api/jobs/${jobId}/download/audio`;
      audio.classList.remove("hidden");
    } else {
      $("dl-video").href = `/api/jobs/${jobId}/download/video`;
      $("dl-video").querySelector(".lbl").textContent = "Tải video có sub";
      $("dl-srt").href = `/api/jobs/${jobId}/download/srt`;
      audio.classList.add("hidden"); audio.removeAttribute("src");
    }
    $("result").classList.remove("hidden");
    stopPolling(); btn.disabled = false;
  } else if (m.status === "error") {
    showError(m.error || "Có lỗi khi xử lý video.");
    stopPolling(); btn.disabled = false;
  }
}

// Polling thay cho SSE: bền với mạng/đệm/antivirus khi máy khác truy cập
function listen(jobId, btn) {
  currentJob = jobId;
  stopPolling();
  const poll = async () => {
    let m;
    try {
      const r = await fetch(`/api/jobs/${jobId}/status`, { cache: "no-store" });
      if (!r.ok) return;          // 404/khác -> thử lại nhịp sau
      m = await r.json();
    } catch (e) { return; }       // mạng chập chờn -> thử lại nhịp sau
    applyStatus(m, jobId, btn);
  };
  pollTimer = setInterval(poll, 1000);
  poll();
}

/* ---------------------------------------------------------------- subtitle style */
function activeMode() { return (activeTab === "auto" ? $("auto-mode") : $("merge-mode")).value; }

function updateStylePanel() {
  $("style-panel").classList.toggle("hidden", activeMode() !== "burn");
}

function collectStyle() {
  return {
    font: $("st-font").value,
    size: $("st-size").value,
    bold: $("st-bold").getAttribute("aria-pressed") === "true",
    italic: $("st-italic").getAttribute("aria-pressed") === "true",
    fill: $("st-fill").value,
    outline: $("st-outline").value,
    outline_color: $("st-outline-color").value,
    outline_opacity: $("st-outline-op").value,
    box: $("st-box").getAttribute("aria-pressed") === "true",
    box_color: $("st-box-color").value,
    box_opacity: $("st-box-op").value,
    align: $("st-align").value,
    margin: $("st-margin").value,
  };
}

function appendStyle(fd) {
  const s = collectStyle();
  for (const [k, v] of Object.entries(s)) fd.append(k, typeof v === "boolean" ? (v ? "1" : "") : v);
}

function applyStylePreview() {
  const s = collectStyle();
  const cap = document.querySelector("#monitor .caption");
  const span = cap.querySelector("span");
  const mon = $("monitor");
  const scale = (mon.clientHeight || 380) / 288; // ASS PlayResY default ~288
  span.style.fontFamily = s.font ? `"${s.font}", sans-serif` : "var(--body)";
  span.style.fontSize = Math.max(11, parseFloat(s.size || 18) * scale) + "px";
  span.style.fontWeight = s.bold ? "800" : "600";
  span.style.fontStyle = s.italic ? "italic" : "normal";
  span.style.color = s.fill || "#fff";
  const oc = s.outline_color || "#000000";
  const oop = s.outline_opacity == null ? 1 : parseFloat(s.outline_opacity);
  const or = parseInt(oc.slice(1, 3), 16), og = parseInt(oc.slice(3, 5), 16), ob = parseInt(oc.slice(5, 7), 16);
  const ocol = `rgba(${or},${og},${ob},${oop})`;
  const soft = `0 2px 6px rgba(${or},${og},${ob},${0.9 * oop})`;   // bóng đổ ăn theo màu viền
  const w = parseFloat(s.outline || 0) * scale * 0.5;
  span.style.textShadow = w > 0
    ? `-${w}px -${w}px 0 ${ocol}, ${w}px -${w}px 0 ${ocol}, -${w}px ${w}px 0 ${ocol}, ${w}px ${w}px 0 ${ocol}, ${soft}`
    : soft;
  cap.style.background = "transparent";
  cap.style.padding = "0";
  if (s.box) {
    // hộp nền ôm sát chữ, đệm nhỏ — khớp với video burn
    const op = parseFloat(s.box_opacity);
    const c = s.box_color;
    const r = parseInt(c.slice(1, 3), 16), g = parseInt(c.slice(3, 5), 16), b = parseInt(c.slice(5, 7), 16);
    span.style.background = `rgba(${r},${g},${b},${op})`;
    span.style.padding = "4px 6px";   // ~4px, ôm sát chữ (span inline-block tự bám text)
    span.style.borderRadius = "0";
    span.style.boxDecorationBreak = "clone";
    span.style.webkitBoxDecorationBreak = "clone";
  } else {
    span.style.background = "transparent";
    span.style.padding = "0";
  }
  const m = parseFloat(s.margin || 0) * scale;
  if (s.align === "top") { cap.style.top = m + "px"; cap.style.bottom = "auto"; cap.style.transform = "none"; }
  else if (s.align === "middle") { cap.style.top = "50%"; cap.style.bottom = "auto"; cap.style.transform = "translateY(-50%)"; }
  else { cap.style.bottom = m + "px"; cap.style.top = "auto"; cap.style.transform = "none"; }
}

// toggle buttons
["st-bold", "st-italic", "st-box"].forEach((id) => {
  $(id).addEventListener("click", () => {
    const on = $(id).getAttribute("aria-pressed") === "true";
    $(id).setAttribute("aria-pressed", String(!on));
    applyStylePreview();
  });
});
// live preview on any style change
["st-font", "st-size", "st-fill", "st-outline", "st-outline-color", "st-outline-op", "st-align", "st-margin", "st-box-color", "st-box-op"]
  .forEach((id) => $(id).addEventListener("input", applyStylePreview));

// mẫu (presets) — chữ trắng đậm + viền đen là kiểu phổ biến trong 2 ảnh
const PRESETS = {
  outline: { fill: "#ffffff", bold: true, outline: "1.2", outline_color: "#000000", outline_op: "1", box: false },
  thin:    { fill: "#ffffff", bold: true, outline: "0.7", outline_color: "#000000", outline_op: "1", box: false },
  box:     { fill: "#ffffff", bold: true, outline: "0", outline_color: "#000000", outline_op: "1", box: true, box_color: "#000000", box_op: "0.3" },
  yellow:  { fill: "#ffdd00", bold: true, outline: "1.2", outline_color: "#000000", outline_op: "1", box: false },
};

function applyPreset(name) {
  const p = PRESETS[name];
  if (!p) return;
  $("st-fill").value = p.fill;
  $("st-outline").value = p.outline;
  $("st-outline-color").value = p.outline_color;
  $("st-outline-op").value = p.outline_op;
  $("st-bold").setAttribute("aria-pressed", String(!!p.bold));
  $("st-box").setAttribute("aria-pressed", String(!!p.box));
  if (p.box_color) $("st-box-color").value = p.box_color;
  if (p.box_op) $("st-box-op").value = p.box_op;
  document.querySelectorAll("#style-presets .preset")
    .forEach((b) => b.classList.toggle("active", b.dataset.preset === name));
  applyStylePreview();
}
document.querySelectorAll("#style-presets .preset")
  .forEach((b) => b.addEventListener("click", () => applyPreset(b.dataset.preset)));
// show/hide panel on mode change
["auto-mode", "merge-mode"].forEach((id) => $(id).addEventListener("change", updateStylePanel));

/* ---------------------------------------------------------------- actions */
$("auto-start").onclick = () => {
  const f = $("auto-video").files[0];
  if (!f) return showError("Hãy chọn một video trước.");
  const fd = new FormData();
  fd.append("video", f);
  fd.append("language", $("auto-lang").value);
  fd.append("model", $("auto-model").value);
  fd.append("mode", $("auto-mode").value);
  fd.append("offset", $("auto-offset").value || "0");
  if ($("auto-mode").value === "burn") appendStyle(fd);
  submit("/api/auto", fd, $("auto-start"));
};

$("merge-start").onclick = () => {
  const v = $("merge-video").files[0], s = $("merge-sub").files[0];
  if (!v) return showError("Hãy chọn video.");
  if (!s) return showError("Hãy chọn file phụ đề để ghép.");
  const fd = new FormData();
  fd.append("video", v); fd.append("sub", s);
  fd.append("offset", $("merge-offset").value || "0");
  fd.append("mode", $("merge-mode").value);
  if ($("merge-mode").value === "burn") appendStyle(fd);
  submit("/api/merge", fd, $("merge-start"));
};

updateStylePanel();
applyStylePreview();

/* ---------------------------------------------------------------- đọc văn bản -> giọng nói (VietTTS) */
let ttsGender = "female";
let ttsVoicesLoaded = false;
let ttsPreviewAudio = null;

function activeVoice() { return $(ttsGender === "male" ? "tts-voice-male" : "tts-voice-female").value; }

function fillVoiceSelect(sel, list) {
  sel.innerHTML = "";
  for (const v of (list || [])) {
    const o = document.createElement("option");
    o.value = v.id; o.textContent = v.label; sel.appendChild(o);
  }
}

async function ttsLoadVoices() {
  if (ttsVoicesLoaded) return;
  const warn = $("tts-warn");
  try {
    const r = await fetch("/api/tts/voices", { cache: "no-store" });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "Không tải được danh sách giọng.");
    fillVoiceSelect($("tts-voice-female"), j.female);
    fillVoiceSelect($("tts-voice-male"), j.male);
    ttsVoicesLoaded = true;
    warn.classList.add("hidden");
    $("tts-start").disabled = false;
  } catch (e) {
    warn.textContent = "⚠ " + e.message + " — bật ./tts_server.sh rồi mở lại tab này.";
    warn.classList.remove("hidden");
    $("tts-start").disabled = true;
  }
}

["female", "male"].forEach((g) => {
  $("tts-gender-" + g).addEventListener("click", () => {
    ttsGender = g;
    $("tts-gender-female").setAttribute("aria-pressed", String(g === "female"));
    $("tts-gender-male").setAttribute("aria-pressed", String(g === "male"));
  });
});

async function ttsPreview(voice, btn) {
  if (!voice) return showError("Chưa có giọng để nghe. Bật ./tts_server.sh trước.");
  const old = btn.textContent; btn.disabled = true; btn.textContent = "…";
  try {
    const r = await fetch("/api/tts/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("tts-text").value.trim(), voice }),
    });
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.error || "Lỗi nghe trước."); }
    const blob = await r.blob();
    if (ttsPreviewAudio) ttsPreviewAudio.pause();
    ttsPreviewAudio = new Audio(URL.createObjectURL(blob));
    ttsPreviewAudio.play();
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false; btn.textContent = old;
  }
}
$("tts-prev-female").onclick = () => ttsPreview($("tts-voice-female").value, $("tts-prev-female"));
$("tts-prev-male").onclick = () => ttsPreview($("tts-voice-male").value, $("tts-prev-male"));

$("tts-start").onclick = async () => {
  const text = $("tts-text").value.trim();
  if (!text) return showError("Hãy nhập nội dung cần đọc.");
  const voice = activeVoice();
  if (!voice) return showError("Chưa có giọng. Bật ./tts_server.sh rồi thử lại.");
  const btn = $("tts-start");
  btn.disabled = true; resetUI(); jobKind = "tts";
  let res;
  try {
    res = await fetch("/api/tts", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice }),
    });
  } catch (e) { showError("Không gửi được yêu cầu."); btn.disabled = false; return; }
  if (!res.ok) { const j = await res.json().catch(() => ({})); showError(j.error || "Lỗi tạo giọng nói."); btn.disabled = false; return; }
  const { job_id } = await res.json();
  listen(job_id, btn);
};

$("clear-job").onclick = async () => {
  stopPolling();
  if (currentJob) {
    try { await fetch(`/api/jobs/${currentJob}/delete`, { method: "POST" }); } catch (e) {}
    currentJob = null;
  }
  // reset progress + các banner (Hoàn tất / lỗi)
  for (const k in stepState) delete stepState[k];
  renderSteps();
  $("stage").classList.add("hidden");
  $("error").classList.add("hidden");
  $("result").classList.add("hidden");
  // mở lại nút bấm + reset input + banner preview
  $("auto-start").disabled = false;
  $("merge-start").disabled = false;
  $("tts-start").disabled = false;
  const au = $("tts-audio"); au.pause(); au.classList.add("hidden");
  ["auto-video", "merge-video", "merge-sub"].forEach((id) => { $(id).value = ""; });
  markFilepick("pick-merge-sub", null);
  setVideoPreview(null);
};

/* ---------------------------------------------------------------- waveform */
(function buildWave() {
  const wave = $("wave"); if (!wave) return;
  const N = 56;
  for (let i = 0; i < N; i++) {
    const bar = document.createElement("i");
    const h = 25 + Math.round(60 * Math.abs(Math.sin(i * 0.5)) + 15 * Math.abs(Math.sin(i * 1.7)));
    bar.style.height = Math.min(100, h) + "%";
    bar.style.animationDelay = (i * 0.045).toFixed(2) + "s";
    bar.style.animationDuration = (1.1 + (i % 5) * 0.12).toFixed(2) + "s";
    wave.appendChild(bar);
  }
})();
