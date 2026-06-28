"use strict";
const $ = (id) => document.getElementById(id);

let activeTab = "auto";
let currentJob = null;

/* ---------------------------------------------------------------- tabs */
function showTab(which) {
  activeTab = which;
  $("panel-auto").classList.toggle("hidden", which !== "auto");
  $("panel-merge").classList.toggle("hidden", which !== "merge");
  $("tab-auto").setAttribute("aria-selected", which === "auto");
  $("tab-merge").setAttribute("aria-selected", which === "merge");
}
$("tab-auto").onclick = () => showTab("auto");
$("tab-merge").onclick = () => showTab("merge");

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
const STEP_ORDER = ["Tách audio", "Nhận diện giọng nói", "Nhận diện & căn chỉnh", "Chuẩn bị sub", "Nhúng phụ đề"];
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

function listen(jobId, btn) {
  currentJob = jobId;
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  es.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "progress") {
      for (const k in stepState) if (k !== m.step) stepState[k].done = true;
      stepState[m.step] = { percent: m.percent, done: m.percent === 100 };
      renderSteps();
    } else if (m.type === "done") {
      for (const k in stepState) stepState[k].done = true;
      renderSteps();
      $("dl-video").href = `/api/jobs/${jobId}/download/video`;
      $("dl-srt").href = `/api/jobs/${jobId}/download/srt`;
      $("result").classList.remove("hidden");
      es.close(); btn.disabled = false;
    } else if (m.type === "error") {
      showError(m.message); es.close(); btn.disabled = false;
    }
  };
  es.onerror = () => es.close();
}

/* ---------------------------------------------------------------- actions */
$("auto-start").onclick = () => {
  const f = $("auto-video").files[0];
  if (!f) return showError("Hãy chọn một video trước.");
  const fd = new FormData();
  fd.append("video", f);
  fd.append("language", $("auto-lang").value);
  fd.append("model", $("auto-model").value);
  fd.append("mode", $("auto-mode").value);
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
  submit("/api/merge", fd, $("merge-start"));
};

$("clear-job").onclick = async () => {
  if (currentJob) {
    try { await fetch(`/api/jobs/${currentJob}/delete`, { method: "POST" }); } catch (e) {}
    currentJob = null;
  }
  $("stage").classList.add("hidden");
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
