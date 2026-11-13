import unittest
from pathlib import Path

from music_tool.fit import FitError, build_command


class TestBuildCommand(unittest.TestCase):
    def test_mp3_with_fades(self) -> None:
        """fit.build_command loops the input (-stream_loop -1), cuts at the target with -t and places the fade-
        out to end at the target. Guards the loop/trim command and the fade-out start time."""
        cmd = build_command(Path("in.mp3"), Path("out.mp3"), 45, fade_in=1, fade_out=2.5)
        self.assertEqual(cmd[cmd.index("-stream_loop") + 1], "-1")
        self.assertEqual(cmd[cmd.index("-af") + 1], "afade=t=in:d=1,afade=t=out:st=42.5:d=2.5")
        self.assertEqual(cmd[cmd.index("-t") + 1], "45")
        self.assertEqual(cmd[cmd.index("-c:a") + 1], "libmp3lame")
        self.assertEqual(cmd[-1], "out.mp3")

    def test_codec_from_extension(self) -> None:
        """fit.build_command picks the codec from the output extension, case-insensitively (.wav, .m4a, .MP3).
        Guards the extension-to-codec mapping of `fit`."""
        for ext, codec in [(".wav", "pcm_s16le"), (".m4a", "aac"), (".MP3", "libmp3lame")]:
            cmd = build_command(Path("in.mp3"), Path("out" + ext), 10)
            self.assertEqual(cmd[cmd.index("-c:a") + 1], codec)

    def test_no_fades_no_filter(self) -> None:
        """fit.build_command adds no -af filter when both fades are 0. Guards that an empty filter chain is not
        passed to FFmpeg."""
        self.assertNotIn("-af", build_command(Path("in.mp3"), Path("o.wav"), 10, 0, 0))

    def test_fades_longer_than_target(self) -> None:
        """fit.build_command refuses fades whose sum exceeds the target length. Guards the fade check done before
        FFmpeg runs."""
        with self.assertRaisesRegex(FitError, "exceed"):
            build_command(Path("in.mp3"), Path("o.wav"), 3, fade_in=2, fade_out=2)

    def test_bad_extension(self) -> None:
        """fit.build_command refuses an output extension other than .mp3, .wav or .m4a. Guards the supported
        output formats of `fit`."""
        with self.assertRaises(FitError):
            build_command(Path("in.mp3"), Path("o.ogg"), 10)


if __name__ == "__main__":
    unittest.main()
