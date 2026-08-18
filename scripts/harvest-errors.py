#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đo lỗi nhận diện thật của whisper thay vì đoán.

Đọc file câu mẫu (mỗi dòng 1 câu, đây là ĐÁP ÁN), đọc thành audio bằng giọng
tiếng Việt của macOS, cho whisper nhận diện lại rồi so với đáp án. Các chỗ lệch
chính là ứng viên để thêm vào webapp/corrections.txt.

    python3 scripts/harvest-errors.py scripts/corpus-yte.txt

Lưu ý: giọng TTS không giống hệt giọng người thật, nên đây là nguồn gợi ý -
vẫn phải tự xem lại trước khi chép vào từ điển.
"""
from __future__ import annotations

import difflib
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from webapp import pipeline  # noqa: E402

VOICE = os.environ.get("TTS_VOICE", "Linh")
MODEL = os.environ.get("MODEL", "large-v3")
BATCH = int(os.environ.get("BATCH", "10"))   # số câu mỗi lần đọc


def norm(s: str) -> str:
    return unicodedata.normalize("NFC", s)


# Tiếng Việt có 2 lối đặt dấu đều hợp lệ: "hòa/khỏe/tọa" và "hoà/khoẻ/toạ".
# Whisper dùng lối trước. Đây KHÔNG phải lỗi nhận diện nên phải bỏ qua khi so,
# nếu không nó lấn át hết lỗi thật.
_TONES = "\u0300\u0301\u0303\u0309\u0323"          # huyền sắc ngã hỏi nặng
_STYLE = re.compile(f"([oOuU])([{_TONES}])([aeyAEY])")


def style_norm(s: str) -> str:
    """Dồn dấu thanh về nguyên âm sau trong cụm oa/oe/uy để so cho công bằng."""
    d = unicodedata.normalize("NFD", s)
    return unicodedata.normalize("NFD", _STYLE.sub(r"\1\3\2", d))


def is_noise(got: str, want: str) -> bool:
    """Bỏ qua chênh lệch không phải lỗi nhận diện."""
    if style_norm(got.lower()) == style_norm(want.lower()):
        return True                                   # chỉ khác lối đặt dấu
    if re.fullmatch(r"[\d.,%\s]+", got):
        return True                                   # whisper ghi chữ số
    if len(got.split()) > 6 or len(want.split()) > 6:
        return True                                   # rác do lệch căn chỉnh
    return False


def synth(text: str, wav: str) -> None:
    aiff = wav[:-4] + ".aiff"
    subprocess.run(["say", "-v", VOICE, "-o", aiff, text], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", aiff,
                    "-ac", "1", "-ar", "16000", wav], check=True)
    os.unlink(aiff)


def recognise(wav: str) -> str:
    """Chạy whisper đúng cấu hình pipeline (kể cả prompt), trả text thô."""
    cmd = ["whisper-cli", "-m", pipeline.model_path(MODEL), "-l", "vi",
           "-t", pipeline.THREADS, "-bs", "5", "-bo", "5", "-fa", "-pp",
           "-nt", "-f", wav]
    prompt = pipeline._load_prompt()
    if prompt:
        cmd += ["--prompt", prompt, "--carry-initial-prompt"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    return norm(re.sub(r"\s+", " ", out).strip())


def fix(text: str) -> str:
    """Áp corrections.txt hiện có, để chỉ còn lại lỗi CHƯA xử được."""
    fd, p = tempfile.mkstemp(suffix=".srt")
    os.close(fd)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    pipeline.apply_corrections(p)
    r = open(p, encoding="utf-8").read()
    os.unlink(p)
    return r


def words(s: str) -> list[str]:
    return re.findall(r"[^\s]+", s)


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else "scripts/corpus-yte.txt"
    lines = [norm(l.strip()) for l in open(src, encoding="utf-8")
             if l.strip() and not l.startswith("#")]
    print(f"{len(lines)} câu, model {MODEL}, giọng {VOICE}\n")

    found: list[tuple[str, str]] = []
    tmpd = tempfile.mkdtemp()
    for i in range(0, len(lines), BATCH):
        chunk = lines[i:i + BATCH]
        wav = os.path.join(tmpd, f"b{i}.wav")
        synth(" ".join(chunk), wav)
        got = fix(recognise(wav))
        os.unlink(wav)

        a, b = words(" ".join(chunk)), words(got)
        sm = difflib.SequenceMatcher(None,
                                     [w.lower().strip(".,:;!?") for w in a],
                                     [w.lower().strip(".,:;!?") for w in b])
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            want = " ".join(a[i1:i2]).strip(".,:;!?")
            got_s = " ".join(b[j1:j2]).strip(".,:;!?")
            if (want and got_s and want.lower() != got_s.lower()
                    and not is_noise(got_s, want)):
                ctx = " ".join(a[max(0, i1 - 3):i2 + 3])
                found.append((got_s, want, ctx))
        print(f"  câu {i + 1}-{i + len(chunk)}: {len(found)} lệch tích luỹ")

    print("\n=== ỨNG VIÊN (nghe ra => đáp án) ===")
    seen = set()
    for got_s, want, ctx in found:
        k = got_s.lower()
        if k in seen:
            continue
        seen.add(k)
        print(f"{got_s} => {want}")
        print(f"      ngữ cảnh: ...{ctx}...")


if __name__ == "__main__":
    main()
