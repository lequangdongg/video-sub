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


def video_dimensions(path: str) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True).stdout.strip()
    try:
        w, h = (int(x) for x in out.split("x")[:2])
        return w, h
    except (ValueError, IndexError):
        return 1920, 1080


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
    # luôn ghi Bold tường minh: tránh libass tự "giả đậm" hoặc chọn nhầm face Bold
    parts.append("Bold=-1" if style.get("bold") else "Bold=0")
    if style.get("italic"):
        parts.append("Italic=-1")
    if style.get("fill"):
        parts.append(f"PrimaryColour={hex_to_ass(style['fill'])}")
    if style.get("box"):
        # Nền hộp (giống Background của Premiere): BorderStyle=3 TÔ hộp bằng
        # OutlineColour (không phải BackColour), kích thước hộp = Outline (đệm).
        # Outline=0 -> hộp biến mất, nên luôn để đệm > 0.
        parts.append("BorderStyle=3")
        parts.append("Shadow=0")
        box_color = style.get("box_color") or "#000000"
        op = float(style.get("box_opacity", 1.0) or 1.0)
        parts.append(f"OutlineColour={hex_to_ass(box_color, 1.0 - op)}")
        try:
            pad = float(style.get("outline"))
        except (TypeError, ValueError):
            pad = 0.0
        parts.append(f"Outline={pad if pad > 0 else 4}")
    else:
        # Viền chữ thường (stroke)
        if style.get("outline") is not None and style.get("outline") != "":
            parts.append(f"Outline={style['outline']}")
        if style.get("outline_color"):
            op = float(style.get("outline_opacity", 1.0) or 1.0)
            parts.append(f"OutlineColour={hex_to_ass(style['outline_color'], 1.0 - op)}")
    if style.get("align") in _ALIGN:
        parts.append(f"Alignment={_ALIGN[style['align']]}")
    if style.get("margin") not in (None, ""):
        parts.append(f"MarginV={int(float(style['margin']))}")
    return ",".join(parts)


# ---------------------------------------------------------------- nền băng ngang (1 khối)
# libass vẽ hộp opaque theo TỪNG dòng -> nhiều dòng thành hình bậc thang ("nhiều cụm").
# Muốn 1 dải nền liền chạy ngang, ta tự sinh file .ass và vẽ 1 hình chữ nhật phía sau.

_PLAYRES_Y = 288  # giữ nguyên ý nghĩa cỡ chữ như force_style hiện tại


def _ass_time(t: float) -> str:
    if t < 0:
        t = 0.0
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_bgr(hexcolor: str) -> str:
    """#RRGGBB -> &Hbbggrr& (dùng cho \\1c trong drawing)."""
    h = hexcolor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return f"&H{h[4:6].upper()}{h[2:4].upper()}{h[0:2].upper()}&"


def _ass_alpha(opacity: float) -> str:
    aa = max(0, min(255, round((1.0 - opacity) * 255)))
    return f"&H{aa:02X}&"


# Bề rộng ký tự (theo loại) để hộp ôm SÁT chữ, co giãn động theo nội dung thật
# thay vì một hệ số cố định. Đơn vị: phần của cỡ chữ (px).
_W_NARROW = set("iíìỉĩịl.,:;!'|`ftjr()[]")
_W_WIDE = set("mwMW@")


def _char_frac(ch: str, bold: bool) -> float:
    if ch == " ":
        f = 0.30
    elif ch in _W_NARROW:
        f = 0.32
    elif ch in _W_WIDE:
        f = 0.60
    elif ch.isdigit():
        f = 0.42
    elif ch.isupper():
        f = 0.52
    else:
        f = 0.40
    return f * (1.04 if bold else 1.0)


def _line_width(text: str, fontpx: float, bold: bool) -> float:
    return fontpx * sum(_char_frac(c, bold) for c in text)


def _wrap_width(text: str, fontpx: float, bold: bool, max_w: float) -> list[str]:
    words = text.replace("\n", " ").split()
    if not words:
        return [""]
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if not cur or _line_width(trial, fontpx, bold) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def write_band_ass(cues, ass_path: str, style: dict, width: int, height: int) -> None:
    """Sinh .ass với 1 dải nền băng ngang liền phía sau chữ (mỗi cue 1 dải)."""
    play_x = max(320, round(_PLAYRES_Y * width / max(1, height)))
    font = style.get("font") or "UTM Avo"
    fontpx = float(style.get("size") or 16)
    bold = -1 if style.get("bold") else 0
    italic = -1 if style.get("italic") else 0
    primary = hex_to_ass(style.get("fill") or "#ffffff")
    outline_col = hex_to_ass(style.get("outline_color") or "#000000")
    try:
        outline_w = float(style.get("outline") or 0)
    except (TypeError, ValueError):
        outline_w = 0.0
    align = _ALIGN.get(style.get("align"), 2)
    try:
        margin_v = int(float(style.get("margin") or 24))
    except (TypeError, ValueError):
        margin_v = 24
    band_bgr = _ass_bgr(style.get("box_color") or "#000000")
    band_a = _ass_alpha(float(style.get("box_opacity", 1.0) or 1.0))

    is_bold = bool(style.get("bold"))
    to_units = _PLAYRES_Y / max(1, height)     # đổi px video -> đơn vị script
    side = max(10, round(play_x * 0.04))       # giới hạn bề rộng tối đa của hộp
    pad_x = max(1.5, 5 * to_units)             # đệm ngang ~5px video (ôm sát chữ)
    pad_top = max(2.0, 8 * to_units)           # đệm trên (chừa dấu thanh)
    pad_bot = max(1.5, 5 * to_units)
    max_box_w = play_x - 2 * side
    max_text_w = max_box_w - 2 * pad_x
    line_h = fontpx * 1.22

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_x}\n"
        f"PlayResY: {_PLAYRES_Y}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Text,{font},{fontpx:g},{primary},&H000000FF,{outline_col},"
        f"&H00000000,{bold},{italic},0,0,100,100,0,0,1,{outline_w:g},0,{align},"
        f"{side},{side},{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )

    lines_out = []
    for c in cues:
        text = (c.text or "").replace("{", "(").replace("}", ")")
        wrapped = _wrap_width(text, fontpx, is_bold, max_text_w)
        n = len(wrapped)
        block_h = n * line_h
        # hộp ôm sát chữ: rộng theo bề rộng THẬT của dòng dài nhất + đệm, căn giữa
        text_w = max((_line_width(ln, fontpx, is_bold) for ln in wrapped), default=0)
        box_w = min(max_box_w, text_w + 2 * pad_x)
        x1 = round((play_x - box_w) / 2)
        x2 = round(x1 + box_w)
        if align == 8:      # top
            y1 = margin_v - pad_top
            y2 = margin_v + block_h + pad_bot
        elif align == 5:    # middle
            cy = _PLAYRES_Y / 2
            y1 = cy - block_h / 2 - pad_top
            y2 = cy + block_h / 2 + pad_bot
        else:               # bottom
            yb = _PLAYRES_Y - margin_v
            y1 = yb - block_h - pad_top
            y2 = yb + pad_bot
        iy1, iy2 = round(y1), round(y2)
        band = (f"{{\\p1\\an7\\pos(0,0)\\1c{band_bgr}\\1a{band_a}\\bord0\\shad0}}"
                f"m {x1} {iy1} l {x2} {iy1} {x2} {iy2} {x1} {iy2}{{\\p0}}")
        st, en = _ass_time(c.start), _ass_time(c.end)
        lines_out.append(f"Dialogue: 0,{st},{en},Text,,0,0,0,,{band}")
        lines_out.append(f"Dialogue: 1,{st},{en},Text,,0,0,0,,{'\\N'.join(wrapped)}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines_out) + "\n")


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
        # Nền băng ngang (1 khối): tự sinh .ass vẽ dải nền liền, thay cho hộp per-dòng.
        if style and style.get("box"):
            w, h = video_dimensions(video)
            ass_path = (srt[:-4] if srt.lower().endswith(".srt") else srt) + ".ass"
            write_band_ass(subtitles.parse_srt(srt), ass_path, style, w, h)
            sub_opt = f"f='{_escfilt(ass_path)}'"
        else:
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
    try:
        start_at = float(opts.get("offset") or 0)
    except (TypeError, ValueError):
        start_at = 0.0
    wav = os.path.join(job_dir, "audio.wav")
    srt = os.path.join(job_dir, "output.srt")
    on_progress and on_progress("Tách audio", None)
    extract_audio(video, wav)
    on_progress and on_progress("Tách audio", 100.0)
    transcribe(wav, lang, model, srt, on_progress)
    if start_at > 0:
        # whisper định giờ nguyên video -> ẩn phần trước start_at, hiện ra từ start_at;
        # câu đang nói khi chạm mốc thì hiện tiếp -> vẫn khớp đúng tiếng nói
        cues = subtitles.hide_before(subtitles.parse_srt(srt), start_at)
        subtitles.write_srt(cues, srt)
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
