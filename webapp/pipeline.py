from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from webapp import subtitles

MODELS_DIR = os.environ.get("WHISPER_MODELS_DIR", os.path.expanduser("~/whisper-models"))
# fonts bundled in the repo (scoped to this project, not installed system-wide)
FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")
THREADS = os.environ.get("WHISPER_THREADS", "8")
ENCODER = os.environ.get("ENCODER", "hardware")      # hardware|software
VT_QUALITY = os.environ.get("VT_QUALITY", "60")
X264_CRF = os.environ.get("X264_CRF", "20")

TIMED_EXTS = (".srt", ".vtt", ".ass")


# ---------------------------------------------------------------- env / probes

def model_path(model: str) -> str:
    return os.path.join(MODELS_DIR, f"ggml-{model}.bin")


def have_libass() -> bool:
    if not shutil.which("ffmpeg"):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-buildconf"],
                         capture_output=True, text=True).stdout
    return "enable-libass" in out


def video_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def extract_audio(video: str, wav_out: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", video,
         "-vn", "-ac", "1", "-ar", "16000", wav_out], check=True)


# ---------------------------------------------------------------- whisper

_PROG = re.compile(r"progress\s*=\s*(\d+)%")


def _whisper_percent(line: str) -> float | None:
    m = _PROG.search(line)
    return float(m.group(1)) if m else None


def transcribe(audio: str, lang: str, model: str, srt_out: str, on_progress=None) -> None:
    mp = model_path(model)
    if not os.path.exists(mp):
        raise FileNotFoundError(f"Thiếu model whisper: {mp}. Chạy ./install.sh")
    base = srt_out[:-4] if srt_out.endswith(".srt") else srt_out
    proc = subprocess.Popen(
        ["whisper-cli", "-m", mp, "-l", lang, "-t", THREADS, "-fa", "-pp",
         "-osrt", "-of", base, "-f", audio],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    for line in proc.stderr:
        pct = _whisper_percent(line)
        if pct is not None and on_progress:
            on_progress("Nhận diện giọng nói", pct)
    proc.wait()
    if proc.returncode != 0 or not os.path.exists(srt_out):
        raise RuntimeError("whisper-cli thất bại")


def parse_word_timings(obj: dict) -> list[tuple[str, float, float]]:
    """Merge whisper subword tokens into words. A token whose text starts with a
    space (or is the first token) begins a new word; others append to it."""
    words: list[tuple[str, float, float]] = []
    cur_text, cur_from, cur_to = "", None, None
    for seg in obj.get("transcription", []):
        for tok in seg.get("tokens", []):
            raw = tok.get("text", "")
            if raw.strip().startswith("["):       # skip special tokens [_BEG_] etc.
                continue
            piece = raw.strip()
            if not piece:
                continue
            off = tok.get("offsets", {})
            t0 = off.get("from", 0) / 1000.0
            t1 = off.get("to", 0) / 1000.0
            starts_word = raw.startswith(" ") or cur_from is None
            if starts_word and cur_text:
                words.append((cur_text, cur_from, cur_to))
                cur_text, cur_from, cur_to = "", None, None
            if cur_from is None:
                cur_from = t0
            cur_text += piece
            cur_to = t1
    if cur_text:
        words.append((cur_text, cur_from, cur_to))
    return words


def word_timings(audio: str, lang: str, model: str, on_progress=None):
    mp = model_path(model)
    if not os.path.exists(mp):
        raise FileNotFoundError(f"Thiếu model whisper: {mp}. Chạy ./install.sh")
    base = audio[:-4] if audio.endswith(".wav") else audio
    proc = subprocess.Popen(
        ["whisper-cli", "-m", mp, "-l", lang, "-t", THREADS, "-fa", "-pp",
         "-ojf", "-of", base, "-f", audio],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    for line in proc.stderr:
        pct = _whisper_percent(line)
        if pct is not None and on_progress:
            on_progress("Nhận diện & căn chỉnh", pct)
    proc.wait()
    json_path = base + ".json"
    if proc.returncode != 0 or not os.path.exists(json_path):
        raise RuntimeError("whisper-cli (json) thất bại")
    with open(json_path, encoding="utf-8") as f:
        return parse_word_timings(json.load(f))


# ---------------------------------------------------------------- mux / burn

def hex_to_ass(hexcolor: str, transparency: float = 0.0) -> str:
    """#RRGGBB -> ASS &HAABBGGRR (AA: 00 opaque .. FF transparent)."""
    h = hexcolor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    rr, gg, bb = h[0:2], h[2:4], h[4:6]
    aa = max(0, min(255, round(transparency * 255)))
    return f"&H{aa:02X}{bb.upper()}{gg.upper()}{rr.upper()}"


_ALIGN = {"bottom": 2, "middle": 5, "top": 8}


def build_force_style(style: dict | None) -> str:
    """Build an ASS force_style string for the ffmpeg subtitles filter."""
    if not style:
        return ""
    parts: list[str] = []
    if style.get("font"):
        parts.append(f"FontName={style['font']}")
    if style.get("size"):
        parts.append(f"FontSize={int(float(style['size']))}")
    if style.get("bold"):
        parts.append("Bold=-1")
    if style.get("italic"):
        parts.append("Italic=-1")
    if style.get("fill"):
        parts.append(f"PrimaryColour={hex_to_ass(style['fill'])}")
    if style.get("outline") is not None and style.get("outline") != "":
        parts.append(f"Outline={style['outline']}")
    if style.get("outline_color"):
        parts.append(f"OutlineColour={hex_to_ass(style['outline_color'])}")
    if style.get("box"):
        parts.append("BorderStyle=3")
        if style.get("box_color"):
            opacity = float(style.get("box_opacity", 1.0))
            parts.append(f"BackColour={hex_to_ass(style['box_color'], 1.0 - opacity)}")
    if style.get("align") in _ALIGN:
        parts.append(f"Alignment={_ALIGN[style['align']]}")
    if style.get("margin") not in (None, ""):
        parts.append(f"MarginV={int(float(style['margin']))}")
    return ",".join(parts)


def _run_ffmpeg_progress(cmd: list[str], total: float, step: str, on_progress=None) -> None:
    proc = subprocess.Popen(cmd + ["-progress", "pipe:1", "-nostats"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    for line in proc.stdout:
        if line.startswith("out_time_ms=") and on_progress and total > 0:
            try:
                ms = int(line.strip().split("=", 1)[1])
                on_progress(step, min(99.0, ms / 1000.0 / total * 100.0))
            except ValueError:
                pass
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg thất bại ({step})")


def burn_or_mux(video: str, srt: str, mode: str, out_path: str, on_progress=None,
                style: dict | None = None) -> None:
    if mode == "srt":
        if os.path.abspath(srt) != os.path.abspath(out_path):
            shutil.copyfile(srt, out_path)
        on_progress and on_progress("Nhúng phụ đề", 100.0)
        return
    if mode == "soft":
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", srt,
             "-c", "copy", "-c:s", "mov_text", out_path], check=True)
        on_progress and on_progress("Nhúng phụ đề", 100.0)
        return
    if mode == "burn":
        if not have_libass():
            raise RuntimeError(
                "ffmpeg không có libass nên không burn-in được. "
                "Chạy ./install.sh hoặc chọn sub mềm.")
        def _escfilt(p):
            return p.replace("\\", "\\\\").replace("'", r"\'").replace(":", r"\:")
        sub_opt = f"f='{_escfilt(srt)}'"
        fs = build_force_style(style)
        if fs:
            sub_opt += f":force_style='{fs}'"
        # dùng font đi kèm repo (không cần cài vào máy)
        if os.path.isdir(FONTS_DIR):
            sub_opt += f":fontsdir='{_escfilt(FONTS_DIR)}'"
        venc = (["-c:v", "h264_videotoolbox", "-q:v", VT_QUALITY]
                if ENCODER == "hardware"
                else ["-c:v", "libx264", "-crf", X264_CRF, "-preset", "medium"])
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video,
               "-vf", f"subtitles={sub_opt}", *venc, "-c:a", "copy", out_path]
        _run_ffmpeg_progress(cmd, video_duration(video), "Nhúng phụ đề", on_progress)
        on_progress and on_progress("Nhúng phụ đề", 100.0)
        return
    raise ValueError(f"mode không hợp lệ: {mode}")


# ---------------------------------------------------------------- orchestrators

def _normalize_to_srt(sub_file: str, srt_out: str) -> None:
    if sub_file.lower().endswith(".srt"):
        shutil.copyfile(sub_file, srt_out)
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", sub_file, srt_out],
                       check=True)


def _output_video_path(job_dir: str, video: str, mode: str) -> str:
    ext = os.path.splitext(video)[1] or ".mp4"
    return os.path.join(job_dir, f"output{ext}")


def process_auto(video: str, job_dir: str, opts: dict, on_progress=None) -> dict:
    lang = opts.get("language", "vi")
    model = opts.get("model", "large-v3-turbo")
    mode = opts.get("mode", "burn")
    wav = os.path.join(job_dir, "audio.wav")
    srt = os.path.join(job_dir, "output.srt")
    on_progress and on_progress("Tách audio", None)
    extract_audio(video, wav)
    on_progress and on_progress("Tách audio", 100.0)
    transcribe(wav, lang, model, srt, on_progress)
    out = srt if mode == "srt" else _output_video_path(job_dir, video, mode)
    burn_or_mux(video, srt, mode, out, on_progress, opts.get("style"))
    if os.path.exists(wav):
        os.remove(wav)
    return {"video": out, "srt": srt}


def process_merge(video, sub_file, job_dir, offset, mode, on_progress=None,
                  lang="vi", model="large-v3-turbo", style=None) -> dict:
    srt = os.path.join(job_dir, "output.srt")
    if sub_file.lower().endswith(TIMED_EXTS):
        on_progress and on_progress("Chuẩn bị sub", None)
        tmp = os.path.join(job_dir, "src.srt")
        _normalize_to_srt(sub_file, tmp)
        cues = subtitles.shift(subtitles.parse_srt(tmp), offset)
        subtitles.write_srt(cues, srt)
        on_progress and on_progress("Chuẩn bị sub", 100.0)
    else:
        wav = os.path.join(job_dir, "audio.wav")
        on_progress and on_progress("Tách audio", None)
        extract_audio(video, wav)
        on_progress and on_progress("Tách audio", 100.0)
        words = word_timings(wav, lang, model, on_progress)
        text = subtitles.extract_text(sub_file)
        cue_texts = subtitles.split_into_cue_texts(text)
        cues = subtitles.shift(subtitles.align(cue_texts, words), offset)
        subtitles.write_srt(cues, srt)
        if os.path.exists(wav):
            os.remove(wav)
    out = srt if mode == "srt" else _output_video_path(job_dir, video, mode)
    burn_or_mux(video, srt, mode, out, on_progress, style)
    return {"video": out, "srt": srt}
