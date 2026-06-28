import os

from webapp import pipeline
from webapp.subtitles import Cue, parse_srt, write_srt
from tests.conftest import needs_ffmpeg


def test_video_duration(sample_video):
    d = pipeline.video_duration(sample_video)
    assert 1.8 < d < 2.4


@needs_ffmpeg
def test_extract_audio(sample_video, tmp_path):
    wav = str(tmp_path / "a.wav")
    pipeline.extract_audio(sample_video, wav)
    assert os.path.exists(wav) and os.path.getsize(wav) > 1000


def test_parse_whisper_percent():
    assert pipeline._whisper_percent("whisper_print_progress_callback: progress =  42%") == 42.0
    assert pipeline._whisper_percent("no percent here") is None


def test_parse_word_timings_from_tokens():
    obj = {
        "transcription": [
            {
                "offsets": {"from": 0, "to": 1000},
                "tokens": [
                    {"text": " xin", "offsets": {"from": 0, "to": 500}},
                    {"text": " chào", "offsets": {"from": 500, "to": 1000}},
                ],
            }
        ]
    }
    words = pipeline.parse_word_timings(obj)
    assert words == [("xin", 0.0, 0.5), ("chào", 0.5, 1.0)]


def test_parse_word_timings_merges_subword_tokens():
    obj = {
        "transcription": [
            {
                "offsets": {"from": 0, "to": 800},
                "tokens": [
                    {"text": " ba", "offsets": {"from": 0, "to": 300}},
                    {"text": "nh", "offsets": {"from": 300, "to": 500}},
                    {"text": " mai", "offsets": {"from": 500, "to": 800}},
                ],
            }
        ]
    }
    words = pipeline.parse_word_timings(obj)
    assert words == [("banh", 0.0, 0.5), ("mai", 0.5, 0.8)]


@needs_ffmpeg
def test_burn_soft_modes(sample_video, tmp_path):
    srt = str(tmp_path / "s.srt")
    write_srt([Cue(0.0, 1.5, "Xin chào")], srt)

    soft = str(tmp_path / "soft.mp4")
    pipeline.burn_or_mux(sample_video, srt, "soft", soft)
    assert os.path.exists(soft) and os.path.getsize(soft) > 1000

    if pipeline.have_libass():
        burn = str(tmp_path / "burn.mp4")
        pipeline.burn_or_mux(sample_video, srt, "burn", burn)
        assert os.path.exists(burn) and os.path.getsize(burn) > 1000


@needs_ffmpeg
def test_process_merge_timed_srt_offset(sample_video, tmp_path):
    sub = str(tmp_path / "in.srt")
    write_srt([Cue(0.0, 1.0, "Một"), Cue(1.0, 2.0, "Hai")], sub)
    res = pipeline.process_merge(
        sample_video, sub, str(tmp_path), offset=2.0, mode="srt",
        on_progress=None, lang="vi", model="large-v3-turbo")
    cues = parse_srt(res["srt"])
    assert cues[0].start == 2.0 and cues[1].end == 4.0
