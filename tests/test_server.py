import io
import os

import pytest

from webapp.server import create_app
from tests.conftest import needs_ffmpeg


@pytest.fixture
def client(tmp_path):
    app = create_app(jobs_root=str(tmp_path))
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Auto Sub" in r.data
    assert "Ghép sub".encode() in r.data


def test_basic_auth_blocks_and_allows(tmp_path):
    import base64
    app = create_app(jobs_root=str(tmp_path))
    app.config.update(TESTING=True, AUTH_USER="admin", AUTH_PASS="secret")
    c = app.test_client()
    assert c.get("/").status_code == 401                       # thiếu creds
    bad = base64.b64encode(b"admin:wrong").decode()
    assert c.get("/", headers={"Authorization": f"Basic {bad}"}).status_code == 401
    ok = base64.b64encode(b"admin:secret").decode()
    assert c.get("/", headers={"Authorization": f"Basic {ok}"}).status_code == 200


def test_busy_returns_409(client):
    from webapp import server
    server._STATE["busy"] = True
    try:
        r = client.post("/api/auto", data={})
        assert r.status_code == 409
    finally:
        server._STATE["busy"] = False


def test_auto_requires_video(client):
    r = client.post("/api/auto", data={"language": "vi"})
    assert r.status_code == 400


def test_auto_accepts_and_returns_job_id(client, monkeypatch):
    from webapp import pipeline

    def fake_auto(video, job_dir, opts, on_progress=None):
        on_progress and on_progress("Tách audio", 100.0)
        return {"video": video, "srt": video + ".srt"}

    monkeypatch.setattr(pipeline, "process_auto", fake_auto)
    data = {"language": "vi", "model": "large-v3-turbo", "mode": "srt",
            "video": (io.BytesIO(b"fakevideo"), "clip.mp4")}
    r = client.post("/api/auto", data=data, content_type="multipart/form-data")
    assert r.status_code == 202
    assert "job_id" in r.get_json()


def test_events_stream_and_download(client, monkeypatch):
    from webapp import pipeline

    def fake_auto(video, job_dir, opts, on_progress=None):
        on_progress("Tách audio", 100.0)
        srt = video + ".srt"
        open(srt, "w").write("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
        return {"video": video, "srt": srt}

    monkeypatch.setattr(pipeline, "process_auto", fake_auto)
    data = {"mode": "srt", "video": (io.BytesIO(b"x"), "c.mp4")}
    r = client.post("/api/auto", data=data, content_type="multipart/form-data")
    job_id = r.get_json()["job_id"]

    body = b"".join(client.get(f"/api/jobs/{job_id}/events").response)
    assert b"done" in body
    assert "Tách audio".encode() in body

    d = client.get(f"/api/jobs/{job_id}/download/srt")
    assert d.status_code == 200
    assert b"00:00:00,000" in d.data


def test_delete_job_removes_dir(client, monkeypatch):
    from webapp import pipeline, server

    def fake_auto(video, job_dir, opts, on_progress=None):
        return {"video": video, "srt": video}

    monkeypatch.setattr(pipeline, "process_auto", fake_auto)
    data = {"mode": "srt", "video": (io.BytesIO(b"x"), "c.mp4")}
    r = client.post("/api/auto", data=data, content_type="multipart/form-data")
    job_id = r.get_json()["job_id"]
    b"".join(client.get(f"/api/jobs/{job_id}/events").response)  # drain to done

    d = server._JOBS[job_id]["dir"]
    assert os.path.isdir(d)
    dr = client.post(f"/api/jobs/{job_id}/delete")
    assert dr.status_code == 200 and dr.get_json()["ok"] is True
    assert not os.path.exists(d)
    assert job_id not in server._JOBS

    assert client.post("/api/jobs/nope/delete").status_code == 404


@needs_ffmpeg
def test_e2e_merge_timed_srt(client, sample_video):
    srt = sample_video + ".in.srt"
    open(srt, "w", encoding="utf-8").write("1\n00:00:00,000 --> 00:00:01,000\nXin chào\n")
    data = {
        "mode": "soft", "offset": "0.5",
        "video": (open(sample_video, "rb"), "clip.mp4"),
        "sub": (open(srt, "rb"), "in.srt"),
    }
    r = client.post("/api/merge", data=data, content_type="multipart/form-data")
    assert r.status_code == 202
    job_id = r.get_json()["job_id"]
    body = b"".join(client.get(f"/api/jobs/{job_id}/events").response)
    assert b"done" in body and b'"type": "error"' not in body
    dv = client.get(f"/api/jobs/{job_id}/download/video")
    assert dv.status_code == 200 and len(dv.data) > 1000
