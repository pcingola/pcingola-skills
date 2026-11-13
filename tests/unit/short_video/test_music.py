import json
import tempfile
import unittest
from pathlib import Path

from short_video_tool import music, state


class TestImportFile(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_plain_file(self) -> None:
        """music.import_file copies a file to music/v1/music.<lower-case suffix> and records source, file and
        original name, with no lyrics.txt. Guards the music version layout assemble reads."""
        src = self.project / "track.WAV"
        src.write_bytes(b"RIFF")
        dest = music.import_file(self.project, src)
        self.assertEqual(dest, self.project / "music" / "v1" / "music.wav")
        meta = state.read_meta(dest.parent)
        self.assertEqual((meta["source"], meta["file"], meta["original"]), ("file", "music.wav", "track.WAV"))
        self.assertFalse((dest.parent / "lyrics.txt").exists())

    def test_music_skill_sidecars(self) -> None:
        """music.import_file merges the music skill's <file>.json into meta.json with its own `file` winning and
        copies <file>.txt to lyrics.txt. Guards the sidecar merge order."""
        src = self.project / "sources" / "song.mp3"
        src.parent.mkdir()
        src.write_bytes(b"ID3")
        src.with_name("song.mp3.json").write_text(json.dumps(
            {"model": "lyria-3-pro-preview", "prompt": "calm piano.", "file": "ignored"}))
        src.with_name("song.mp3.txt").write_text("[Verse] la la\n")
        dest = music.import_file(self.project, src)
        meta = state.read_meta(dest.parent)
        self.assertEqual(meta["model"], "lyria-3-pro-preview")
        self.assertEqual(meta["prompt"], "calm piano.")
        self.assertEqual(meta["file"], "music.mp3")
        self.assertEqual((dest.parent / "lyrics.txt").read_text(), "[Verse] la la\n")

    def test_versions_increase(self) -> None:
        """music.import_file of the same file twice makes v2. Guards never overwriting a music version."""
        src = self.project / "t.mp3"
        src.write_bytes(b"x")
        music.import_file(self.project, src)
        self.assertEqual(music.import_file(self.project, src).parent.name, "v2")


if __name__ == "__main__":
    unittest.main()
