"""`media.check_ffmpeg`, the ffmpeg check of `short-video setup`, against the ffmpeg on PATH."""
import shutil

from short_video_tool import media


def test_ffmpeg_on_path_has_the_required_filters() -> None:
    """check_ffmpeg returns the ffmpeg on PATH when it lists every filter of REQUIRED_FILTERS (drawtext). Guards
    the setup check that an ffmpeg build without drawtext fails at setup, not at the first caption."""
    assert media.check_ffmpeg() == shutil.which("ffmpeg")
