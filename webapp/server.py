from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import uuid

from flask import Flask, Response, jsonify, request, send_file

# global single-job state (one video at a time)
_STATE = {"busy": False}
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def create_app(jobs_root: str | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    here = os.path.dirname(__file__)
    app.config["JOBS_ROOT"] = jobs_root or os.path.join(here, "jobs")
    os.makedirs(app.config["JOBS_ROOT"], exist_ok=True)

    from webapp import pipeline

    def _reject_if_busy():
        with _LOCK:
            if _STATE["busy"]:
                return jsonify(error="Đang xử lý video khác, vui lòng đợi."), 409
            return None

    def _job_dir(job_id):
        d = os.path.join(app.config["JOBS_ROOT"], job_id)
        os.makedirs(d, exist_ok=True)
        return d

    def _start_job(work):
        job_id = uuid.uuid4().hex[:12]
        q: queue.Queue = queue.Queue()
        _JOBS[job_id] = {"queue": q, "result": None, "error": None}

        def on_progress(step, percent):
            q.put({"type": "progress", "step": step, "percent": percent})

        def run():
            try:
                _JOBS[job_id]["result"] = work(on_progress)
                q.put({"type": "done"})
            except Exception as e:
                _JOBS[job_id]["error"] = str(e)
                q.put({"type": "error", "message": str(e)})
            finally:
                q.put(None)
                with _LOCK:
                    _STATE["busy"] = False

        with _LOCK:
            _STATE["busy"] = True
        threading.Thread(target=run, daemon=True).start()
        return job_id

    @app.get("/")
    def index():
        return send_file(os.path.join(here, "static", "index.html"))

    @app.post("/api/auto")
    def api_auto():
        busy = _reject_if_busy()
        if busy:
            return busy
        if "video" not in request.files:
            return jsonify(error="Thiếu file video."), 400
        opts = {
            "language": request.form.get("language", "vi"),
            "model": request.form.get("model", "large-v3-turbo"),
            "mode": request.form.get("mode", "burn"),
        }
        d = _job_dir(uuid.uuid4().hex[:12])
        vf = request.files["video"]
        vpath = os.path.join(d, "input" + (os.path.splitext(vf.filename)[1] or ".mp4"))
        vf.save(vpath)

        def work(on_progress):
            return pipeline.process_auto(vpath, d, opts, on_progress)

        job_id = _start_job(work)
        _JOBS[job_id]["dir"] = d
        return jsonify(job_id=job_id), 202

    @app.post("/api/merge")
    def api_merge():
        busy = _reject_if_busy()
        if busy:
            return busy
        if "video" not in request.files or "sub" not in request.files:
            return jsonify(error="Cần cả video và file sub."), 400
        try:
            offset = float(request.form.get("offset", "0") or "0")
        except ValueError:
            offset = 0.0
        mode = request.form.get("mode", "burn")
        lang = request.form.get("language", "vi")
        model = request.form.get("model", "large-v3-turbo")
        d = _job_dir(uuid.uuid4().hex[:12])
        vf = request.files["video"]
        sf = request.files["sub"]
        vpath = os.path.join(d, "input" + (os.path.splitext(vf.filename)[1] or ".mp4"))
        spath = os.path.join(d, "sub" + (os.path.splitext(sf.filename)[1] or ".txt"))
        vf.save(vpath)
        sf.save(spath)

        def work(on_progress):
            return pipeline.process_merge(vpath, spath, d, offset, mode,
                                          on_progress, lang, model)

        job_id = _start_job(work)
        _JOBS[job_id]["dir"] = d
        return jsonify(job_id=job_id), 202

    @app.get("/api/jobs/<job_id>/events")
    def api_events(job_id):
        job = _JOBS.get(job_id)
        if not job:
            return jsonify(error="job không tồn tại"), 404

        def stream():
            q = job["queue"]
            while True:
                evt = q.get()
                if evt is None:
                    break
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

        return Response(stream(), mimetype="text/event-stream")

    @app.get("/api/jobs/<job_id>/download/<kind>")
    def api_download(job_id, kind):
        job = _JOBS.get(job_id)
        if not job or not job.get("result"):
            return jsonify(error="chưa có kết quả"), 404
        path = job["result"].get("video" if kind == "video" else "srt")
        if not path or not os.path.exists(path):
            return jsonify(error="file không tồn tại"), 404
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    @app.post("/api/jobs/<job_id>/delete")
    def api_delete(job_id):
        job = _JOBS.pop(job_id, None)
        if job is None:
            return jsonify(error="job không tồn tại"), 404
        d = job.get("dir")
        if d and os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
        return jsonify(ok=True)

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5005"))
    create_app().run(host="127.0.0.1", port=port, threaded=True)
