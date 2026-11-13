"""second-opinion file transcoding with FFmpeg (ffmpeg and ffprobe must be on PATH)."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from second_opinion_tool import files


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def probe(path: Path) -> list[dict]:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,height",
                          "-of", "json", str(path)], capture_output=True, check=True, text=True).stdout
    return json.loads(out)["streams"]


class TestTranscode(unittest.TestCase):
    def test_video_over_limit_is_transcoded_to_720p_h264_aac(self):
        """files.load transcodes a video over the limit to 720p H.264 with AAC and records the
        original size and MIME type. Guards TRANSCODE_ARGS and the transcoded_from record.
        """
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "big.mov"
            ffmpeg("-f", "lavfi", "-i", "testsrc=s=1920x1080:r=30:d=2", "-f", "lavfi", "-i", "sine=f=440:d=2",
                   "-c:v", "mjpeg", "-q:v", "2", "-c:a", "pcm_s16le", str(src))
            size = src.stat().st_size
            f = files.load(str(src), limit=size - 1)
            self.assertEqual((f.kind, f.mime), ("video", "video/mp4"))
            self.assertEqual(f.transcoded, {"bytes": size, "mime_type": "video/quicktime"})
            out = Path(tmp) / "sent.mp4"
            out.write_bytes(f.data)
            streams = {s["codec_type"]: s for s in probe(out)}
            self.assertEqual(streams["video"]["codec_name"], "h264")
            self.assertEqual(streams["video"]["height"], 720)
            self.assertEqual(streams["audio"]["codec_name"], "aac")

    def test_video_transcoded_when_the_set_is_over_limit(self):
        """files.load_all transcodes a video under the limit when the set exceeds it and leaves the
        text file untouched, ending under the limit. Guards the set-level transcode rule.
        """
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "film.mov"
            ffmpeg("-f", "lavfi", "-i", "testsrc=s=1280x720:r=25:d=1", "-c:v", "mjpeg", "-q:v", "2", str(src))
            notes = Path(tmp) / "storyboard.md"
            notes.write_text("# Film\n" * 100)
            limit = src.stat().st_size + notes.stat().st_size - 1
            video, text = files.load_all([str(src), str(notes)], limit=limit)
            self.assertEqual(video.transcoded["mime_type"], "video/quicktime")
            self.assertEqual(video.mime, "video/mp4")
            self.assertIsNone(text.transcoded)
            self.assertLessEqual(video.size + text.size, limit)


if __name__ == "__main__":
    unittest.main()
