import zipfile

from webapp.subtitles import (
    Cue, align, extract_text, format_ts, parse_srt, shift,
    split_into_cue_texts, write_srt,
)


SAMPLE = """1
00:00:01,000 --> 00:00:03,500
Xin chào

2
00:00:04,000 --> 00:00:05,250
Tạm biệt
"""


def test_parse_srt_roundtrip(tmp_path):
    p = tmp_path / "a.srt"
    p.write_text(SAMPLE, encoding="utf-8")
    cues = parse_srt(str(p))
    assert len(cues) == 2
    assert cues[0] == Cue(start=1.0, end=3.5, text="Xin chào")
    assert cues[1] == Cue(start=4.0, end=5.25, text="Tạm biệt")


def test_format_ts():
    assert format_ts(3.5) == "00:00:03,500"
    assert format_ts(3661.234) == "01:01:01,234"


def test_write_srt(tmp_path):
    cues = [Cue(1.0, 3.5, "Xin chào"), Cue(4.0, 5.25, "Tạm biệt")]
    out = tmp_path / "b.srt"
    write_srt(cues, str(out))
    assert parse_srt(str(out)) == cues


def test_shift_positive_and_clamp():
    cues = [Cue(1.0, 3.5, "a"), Cue(4.0, 5.0, "b")]
    assert shift(cues, 2.0) == [Cue(3.0, 5.5, "a"), Cue(6.0, 7.0, "b")]
    assert shift(cues, -10.0) == [Cue(0.0, 0.0, "a"), Cue(0.0, 0.0, "b")]


# ---- extract_text

def test_extract_text_txt(tmp_path):
    p = tmp_path / "s.txt"
    p.write_text("Dòng một\nDòng hai\n", encoding="utf-8")
    assert extract_text(str(p)) == "Dòng một\nDòng hai"


def _make_docx(path, paragraphs):
    doc_xml = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
        + "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc_xml)


def test_extract_text_docx(tmp_path):
    p = tmp_path / "s.docx"
    _make_docx(p, ["Câu một.", "Câu hai."])
    assert extract_text(str(p)) == "Câu một.\nCâu hai."


# ---- split

def test_split_keeps_existing_lines():
    text = "Dòng một\nDòng hai\nDòng ba"
    assert split_into_cue_texts(text) == ["Dòng một", "Dòng hai", "Dòng ba"]


def test_split_long_paragraph_by_sentence():
    text = "Câu một dài. Câu hai cũng dài! Câu ba nữa?"
    # short enough to stay as one line unless > max_chars; force split via small max
    assert split_into_cue_texts(text, max_chars=20) == [
        "Câu một dài.",
        "Câu hai cũng dài!",
        "Câu ba nữa?",
    ]


def test_split_long_line_without_punctuation_by_length():
    text = "a " * 80
    out = split_into_cue_texts(text, max_chars=90)
    assert len(out) >= 2
    assert all(len(c) <= 90 for c in out)


# ---- align

def test_align_exact_match():
    words = [
        ("xin", 0.0, 0.5), ("chào", 0.5, 1.0),
        ("tạm", 2.0, 2.4), ("biệt", 2.4, 3.0),
    ]
    cues = align(["Xin chào", "Tạm biệt"], words)
    assert len(cues) == 2
    assert cues[0].text == "Xin chào"
    assert abs(cues[0].start - 0.0) < 1e-6
    assert abs(cues[0].end - 1.0) < 1e-6
    assert abs(cues[1].start - 2.0) < 1e-6
    assert abs(cues[1].end - 3.0) < 1e-6


def test_align_with_recognition_error_still_times():
    words = [("xin", 0.0, 0.5), ("chao", 0.5, 1.0)]
    cues = align(["Xin chào!"], words)
    assert cues[0].start == 0.0
    assert cues[0].end == 1.0


def test_align_fallback_distributes_when_no_match():
    words = [("alpha", 0.0, 2.0), ("beta", 2.0, 4.0)]
    cues = align(["hoàn toàn khác", "không liên quan"], words)
    assert len(cues) == 2
    assert cues[0].start == 0.0
    assert cues[1].end <= 4.0 + 1e-6
    assert cues[0].end <= cues[1].start + 1e-6
