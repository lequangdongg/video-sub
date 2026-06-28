import shutil
import subprocess

import pytest

HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_WHISPER = shutil.which("whisper-cli") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
needs_whisper = pytest.mark.skipif(not HAS_WHISPER, reason="whisper-cli not installed")


@pytest.fixture
def sample_video(tmp_path):
    """A 2s black 320x240 clip with a 1kHz tone, for fast ffmpeg-only tests."""
    out = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=black:s=320x240:r=15:d=2",
         "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
        check=True)
    return str(out)
