#!/usr/bin/env python3
"""Sinh golden fixture từ hàm Python hiện có để Rust đối chiếu byte-to-byte."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from webapp import subtitles, pipeline
from webapp.subtitles import Cue

OUT = os.path.join(ROOT, "src-tauri", "tests", "golden")
os.makedirs(OUT, exist_ok=True)

def dump(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# --- SRT round-trip / shift / hide_before ---
srt_text = (
    "1\n00:00:01,000 --> 00:00:02,500\nxin chào\n\n"
    "2\n00:00:03,000 --> 00:00:05,000\nnôn mưởng nhé\n"
)
tmp = os.path.join(OUT, "_in.srt")
open(tmp, "w", encoding="utf-8").write(srt_text)
cues = subtitles.parse_srt(tmp)
dump("srt_parse.json", [{"start": c.start, "end": c.end, "text": c.text} for c in cues])
outp = os.path.join(OUT, "_out.srt")
subtitles.write_srt(cues, outp)
dump("srt_write.json", {"content": open(outp, encoding="utf-8").read()})
sh = subtitles.shift(cues, 5.5)
dump("srt_shift.json", [{"start": c.start, "end": c.end, "text": c.text} for c in sh])
hb = subtitles.hide_before(cues, 2.0)
dump("srt_hide.json", [{"start": c.start, "end": c.end, "text": c.text} for c in hb])

# --- ass helpers ---
dump("ass_helpers.json", {
    "hex_black_opaque": pipeline.hex_to_ass("#000000", 0.0),
    "hex_white": pipeline.hex_to_ass("#ffffff"),
    "hex_blue_semi": pipeline.hex_to_ass("#2563eb", 0.25),
    "bgr_black": pipeline._ass_bgr("#000000"),
    "bgr_blue": pipeline._ass_bgr("#2563eb"),
    "alpha_1": pipeline._ass_alpha(1.0),
    "alpha_025": pipeline._ass_alpha(0.25),
    "time_0": pipeline._ass_time(0.0),
    "time_65_321": pipeline._ass_time(65.321),
    "time_neg": pipeline._ass_time(-3.0),
})

# --- char width / wrap ---
dump("wrap.json", {
    "w_short": pipeline._line_width("xin chào", 16.0, True),
    "wrap_long": pipeline._wrap_width(
        "đây là một câu rất dài để kiểm tra việc xuống dòng theo bề rộng hộp nền", 16.0, True, 120.0),
})

# --- build_force_style ---
style_box = {"font": "UTM Avo", "size": "16", "bold": True, "box": True,
             "box_color": "#000000", "box_opacity": 0.25, "outline": 4,
             "align": "bottom", "margin": 24, "fill": "#ffffff"}
style_stroke = {"font": "UTM Avo", "size": "18", "bold": False, "fill": "#ffff00",
                "outline": 2, "outline_color": "#000000", "outline_opacity": 1.0,
                "align": "bottom", "margin": 30}
dump("force_style.json", {
    "box": pipeline.build_force_style(style_box),
    "stroke": pipeline.build_force_style(style_stroke),
    "none": pipeline.build_force_style(None),
})

# --- write_band_ass (crown jewel) ---
cues2 = [
    Cue(1.0, 3.0, "xin chào các bạn"),
    Cue(3.0, 8.0, "đây là một câu rất dài cần xuống dòng và tách trang để kiểm tra hộp nền băng ngang ôm sát chữ"),
]
ass_path = os.path.join(OUT, "_band.ass")
pipeline.write_band_ass(cues2, ass_path, style_box, 1920, 1080)
dump("band_ass.json", {"content": open(ass_path, encoding="utf-8").read(),
                       "width": 1920, "height": 1080})

# --- corrections ---
corr = os.path.join(OUT, "_corr.txt")
open(corr, "w", encoding="utf-8").write("# ghi chú\nnôn mưởng => nôn mửa\nhà nội => Hà Nội\n")
srt2 = os.path.join(OUT, "_c.srt")
open(srt2, "w", encoding="utf-8").write(
    "1\n00:00:01,000 --> 00:00:02,000\nNôn mưởng quá\n\n"
    "2\n00:00:03,000 --> 00:00:04,000\ntôi ở hà nội\n")
old = pipeline.CORRECTIONS_FILE
pipeline.CORRECTIONS_FILE = corr
pipeline.apply_corrections(srt2)
pipeline.CORRECTIONS_FILE = old
dump("corrections.json", {"content": open(srt2, encoding="utf-8").read()})

for f in ["_in.srt", "_out.srt", "_band.ass", "_corr.txt", "_c.srt"]:
    p = os.path.join(OUT, f)
    if os.path.exists(p):
        os.remove(p)
print("golden written to", OUT)
