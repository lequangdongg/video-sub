from __future__ import annotations

import html
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(eq=True)
class Cue:
    start: float  # seconds
    end: float    # seconds
    text: str


# ---------------------------------------------------------------- srt I/O

_TS = re.compile(r"(\d\d):(\d\d):(\d\d)[,.](\d\d\d)")


def _parse_ts(s: str) -> float:
    m = _TS.search(s)
    if not m:
        raise ValueError(f"bad timestamp: {s!r}")
    h, mi, se, ms = (int(x) for x in m.groups())
    return h * 3600 + mi * 60 + se + ms / 1000.0


def format_ts(t: float) -> str:
    if t < 0:
        t = 0.0
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    mi, ms = divmod(ms, 60_000)
    se, ms = divmod(ms, 1000)
    return f"{h:02d}:{mi:02d}:{se:02d},{ms:03d}"


def parse_srt(path: str) -> list[Cue]:
    raw = open(path, encoding="utf-8-sig").read()
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if len(lines) < 2:
            continue
        ts_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if ts_idx is None:
            continue
        start_s, end_s = lines[ts_idx].split("-->")
        text = "\n".join(lines[ts_idx + 1:]).strip()
        cues.append(Cue(_parse_ts(start_s), _parse_ts(end_s), text))
    return cues


def write_srt(cues: list[Cue], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i, c in enumerate(cues, 1):
            f.write(f"{i}\n{format_ts(c.start)} --> {format_ts(c.end)}\n{c.text}\n\n")


def shift(cues: list[Cue], offset: float) -> list[Cue]:
    return [Cue(max(0.0, c.start + offset), max(0.0, c.end + offset), c.text) for c in cues]


def hide_before(cues: list[Cue], t: float) -> list[Cue]:
    """Ẩn phụ đề trước giây t, hiện ra từ giây t:
    - cue kết thúc trước t        -> bỏ
    - cue đang nói khi chạm t     -> hiện từ t đến hết (cắt start = t), end giữ nguyên
    - cue bắt đầu sau t           -> giữ nguyên mốc thật
    nên phần còn lại vẫn khớp đúng tiếng nói."""
    if t <= 0:
        return cues
    out: list[Cue] = []
    for c in cues:
        if c.end <= t:
            continue
        out.append(Cue(max(c.start, t), c.end, c.text))
    return out


# ---------------------------------------------------------------- text extract

def extract_text(path: str) -> str:
    """Return plain text from a .txt or .docx file (stdlib only)."""
    lower = path.lower()
    if lower.endswith(".docx"):
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        paras = re.split(r"</w:p>", xml)
        out = []
        for para in paras:
            runs = re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, flags=re.DOTALL)
            line = html.unescape("".join(runs)).strip()
            if line:
                out.append(line)
        return "\n".join(out)
    return open(path, encoding="utf-8-sig").read().strip()


# ---------------------------------------------------------------- segmentation

_SENT_END = re.compile(r"(?<=[.!?…])\s+")


def _chunk_by_length(s: str, max_chars: int) -> list[str]:
    words = s.split()
    chunks, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            chunks.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def split_into_cue_texts(text: str, max_chars: int = 90) -> list[str]:
    """Auto: keep existing line breaks; split over-long lines by sentence then length."""
    out: list[str] = []
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if len(line) <= max_chars:
            out.append(line)
            continue
        for sent in _SENT_END.split(line):
            sent = sent.strip()
            if not sent:
                continue
            if len(sent) <= max_chars:
                out.append(sent)
            else:
                out.extend(_chunk_by_length(sent, max_chars))
    return out


# ---------------------------------------------------------------- alignment

def _norm(w: str) -> str:
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")  # strip diacritics
    return "".join(c for c in w if c.isalnum())


def _distribute(cue_texts: list[str], t0: float, t1: float) -> list[Cue]:
    span = max(0.001, t1 - t0)
    weights = [max(1, len(t)) for t in cue_texts]
    total = sum(weights)
    cues, cursor = [], t0
    for text, w in zip(cue_texts, weights):
        dur = span * w / total
        cues.append(Cue(round(cursor, 3), round(cursor + dur, 3), text))
        cursor += dur
    return cues


def align(cue_texts: list[str], words: list[tuple[str, float, float]]) -> list[Cue]:
    if not words:
        return _distribute(cue_texts, 0.0, max(1.0, len(cue_texts)))
    span0, span1 = words[0][1], words[-1][2]

    user_words: list[tuple[int, str]] = []
    for ci, text in enumerate(cue_texts):
        for tok in text.split():
            n = _norm(tok)
            if n:
                user_words.append((ci, n))
    if not user_words:
        return _distribute(cue_texts, span0, span1)

    w_norm = [_norm(w[0]) for w in words]
    u_norm = [u[1] for u in user_words]
    sm = SequenceMatcher(a=u_norm, b=w_norm, autojunk=False)

    starts: list[float | None] = [None] * len(user_words)
    ends: list[float | None] = [None] * len(user_words)
    matched = 0
    for ai, bj, size in sm.get_matching_blocks():
        for k in range(size):
            starts[ai + k] = words[bj + k][1]
            ends[ai + k] = words[bj + k][2]
            matched += 1
    if matched < max(1, len(user_words)) * 0.25:
        return _distribute(cue_texts, span0, span1)

    def _interp(seq: list[float | None], lo: float, hi: float) -> None:
        known = [(i, t) for i, t in enumerate(seq) if t is not None]
        for idx in range(len(seq)):
            if seq[idx] is not None:
                continue
            prev = max((k for k in known if k[0] < idx), default=(0, lo))
            nxt = min((k for k in known if k[0] > idx), default=(len(seq) - 1, hi))
            if nxt[0] == prev[0]:
                seq[idx] = prev[1]
            else:
                frac = (idx - prev[0]) / (nxt[0] - prev[0])
                seq[idx] = prev[1] + frac * (nxt[1] - prev[1])

    _interp(starts, span0, span1)
    _interp(ends, span0, span1)

    by_cue: dict[int, list[tuple[float, float]]] = {}
    for (ci, _), s, e in zip(user_words, starts, ends):
        by_cue.setdefault(ci, []).append((s, e))

    cues: list[Cue] = []
    for ci, text in enumerate(cue_texts):
        pairs = by_cue.get(ci)
        if pairs:
            cues.append(Cue(round(min(p[0] for p in pairs), 3),
                            round(max(p[1] for p in pairs), 3), text))
        else:
            anchor = cues[-1].end if cues else span0
            cues.append(Cue(round(anchor, 3), round(anchor, 3), text))

    for i in range(len(cues)):
        if cues[i].end < cues[i].start:
            cues[i].end = cues[i].start
        if i + 1 < len(cues) and cues[i].end > cues[i + 1].start:
            cues[i].end = cues[i + 1].start
    return cues
