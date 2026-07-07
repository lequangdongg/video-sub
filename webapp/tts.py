"""Đọc văn bản -> giọng nói qua VietTTS server (OpenAI-compatible HTTP).

App (venv py3.14) không chạy chung process với VietTTS (venv py3.11) nên gọi qua HTTP.
Bật server bằng ./tts_server.sh. URL cấu hình qua VIETTTS_URL.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request

from webapp import subtitles

VIETTTS_URL = os.environ.get("VIETTTS_URL", "http://127.0.0.1:8298").rstrip("/")

# Giới tính theo README của dangvansam/viet-tts (server /v1/voices không trả gender).
_MALE = {"nsnd-le-chuc", "atuan", "cdteam", "diep-chi", "doremon",
         "jack-sparrow", "son-tung-mtp"}
# Nhãn hiển thị đẹp hơn id
_LABELS = {
    "nu-nhe-nhang": "Nữ nhẹ nhàng",
    "quynh": "Quỳnh",
    "nguyen-ngoc-ngan": "Nguyễn Ngọc Ngạn",
    "nsnd-le-chuc": "NSND Lê Chức",
    "cdteam": "CD Team",
    "atuan": "A Tuấn",
    "diep-chi": "Diệp Chi",
    "doremon": "Doraemon",
    "jack-sparrow": "Jack Sparrow",
    "son-tung-mtp": "Sơn Tùng M-TP",
    "cross_lingual_prompt": "Nữ (cross-lingual)",
    "zero_shot_prompt": "Nữ (zero-shot)",
}


class TTSUnavailable(RuntimeError):
    """VietTTS server chưa chạy / không kết nối được."""


def _label(vid: str) -> str:
    if vid in _LABELS:
        return _LABELS[vid]
    if vid.startswith("speechify_"):
        return "Nữ " + vid.split("_")[1]
    return vid


def list_voices() -> dict:
    """Trả {'female': [...], 'male': [...]} lấy từ server, kèm nhãn đẹp."""
    try:
        with urllib.request.urlopen(f"{VIETTTS_URL}/v1/voices", timeout=5) as r:
            ids = json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise TTSUnavailable(
            "Chưa kết nối được VietTTS server. Chạy ./tts_server.sh trước.") from e
    female, male = [], []
    for vid in sorted(ids):
        item = {"id": vid, "label": _label(vid)}
        (male if vid in _MALE else female).append(item)
    return {"female": female, "male": male}


def synthesize(text: str, voice: str) -> bytes:
    """Gọi /v1/audio/speech, trả về bytes wav."""
    payload = json.dumps({"model": "tts-1", "input": text,
                          "voice": voice}).encode()
    req = urllib.request.Request(
        f"{VIETTTS_URL}/v1/audio/speech", data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer viet-tts"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.read()
    except (urllib.error.URLError, OSError) as e:
        raise TTSUnavailable(
            "VietTTS server không phản hồi. Kiểm tra ./tts_server.sh.") from e


def split_sentences(text: str) -> list[str]:
    """Tách văn bản thành câu (theo . ? ! ; xuống dòng) để mỗi câu là 1 cue srt."""
    text = re.sub(r"\s+", " ", text.replace("\r", "\n")).strip()
    parts = re.split(r"(?<=[.!?…;])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _wav_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def _concat_to_mp3(wavs: list[str], mp3_out: str) -> None:
    """Nối các wav (cùng nguồn/sample-rate) rồi encode mp3."""
    listfile = mp3_out + ".txt"
    with open(listfile, "w") as f:
        for w in wavs:
            f.write(f"file '{os.path.abspath(w)}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", listfile, "-ar", "24000", "-ac", "1",
         "-c:a", "libmp3lame", "-q:a", "3", mp3_out], check=True)
    os.remove(listfile)


def process_tts(text: str, voice: str, job_dir: str, on_progress=None) -> dict:
    """Đọc từng câu -> đo thời lượng -> dựng srt khớp audio -> nối thành mp3.

    Trả {'audio': <mp3>, 'srt': <srt>}.
    """
    sents = split_sentences(text)
    if not sents:
        raise ValueError("Chưa có nội dung để đọc.")
    wavs, cues, t = [], [], 0.0
    for i, s in enumerate(sents):
        data = synthesize(s, voice)
        wp = os.path.join(job_dir, f"part{i:04d}.wav")
        with open(wp, "wb") as f:
            f.write(data)
        dur = _wav_duration(wp)
        cues.append(subtitles.Cue(t, t + dur, s))
        t += dur
        wavs.append(wp)
        if on_progress:
            on_progress("Tổng hợp giọng nói", (i + 1) / len(sents) * 100.0)

    mp3 = os.path.join(job_dir, "output.mp3")
    _concat_to_mp3(wavs, mp3)
    srt = os.path.join(job_dir, "output.srt")
    subtitles.write_srt(cues, srt)
    return {"audio": mp3, "srt": srt}
