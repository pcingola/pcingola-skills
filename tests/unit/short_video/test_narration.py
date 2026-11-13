import json
import tempfile
import unittest
from pathlib import Path

from short_video_tool import narration, settings, state

SCENE = {"id": "intro", "narration": ["Count to five.", "Then  stop."]}


def timing(*texts: str) -> dict:
    return {"duration": 3.2, "backend": "kokoro", "voice": "af_heart", "speed": 1.0,
            "sentences": [{"index": i, "text": t} for i, t in enumerate(texts, 1)]}


class TestNarration(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def voiced(self, t: dict) -> Path:
        [(script, _)] = narration.write_script(self.project, SCENE)
        d = script.parent
        (d / "narration.wav").write_bytes(b"RIFF")
        (d / "timing.json").write_text(json.dumps(t))
        return d

    def test_script_one_sentence_per_line(self) -> None:
        """narration.write_script writes a one-speaker scene's narration to
        sources/narration/<scene>/script.txt, one sentence per line, with the default voice. Guards the script
        layout the voiceover skill reads."""
        [(p, speaker)] = narration.write_script(self.project, SCENE)
        self.assertIsNone(speaker)
        self.assertEqual(p, self.project / "sources" / "narration" / "intro" / "script.txt")
        self.assertEqual(p.read_text(), "Count to five.\nThen  stop.\n")

    def test_import(self) -> None:
        """narration.import_voice copies the voiced directory to voice/<scene>/v1 and records duration, voice
        settings and source in meta.json, matching sentences whitespace-normalised. Guards the voice version
        layout."""
        src = self.voiced(timing("Count to five.", "Then stop."))
        out = narration.import_voice(self.project, {}, SCENE, src)
        self.assertEqual(out, self.project / "voice" / "intro" / "v1")
        for f in narration.FILES:
            self.assertTrue((out / f).is_file(), f)
        meta = state.read_meta(out)
        self.assertEqual(meta["duration"], 3.2)
        self.assertEqual(meta["voice"], {"backend": "kokoro", "voice": "af_heart", "speed": 1.0})
        self.assertEqual(meta["source"], "sources/narration/intro")
        self.assertEqual(state.latest_voice(self.project, "intro"), out)

    def test_sentence_count_mismatch(self) -> None:
        """narration.import_voice refuses a recording with fewer sentences than the storyboard and creates no
        voice version. Guards importing a stale recording."""
        src = self.voiced(timing("Count to five."))
        with self.assertRaisesRegex(narration.NarrationError, "1 sentences voiced, the storyboard has 2"):
            narration.import_voice(self.project, {}, SCENE, src)
        self.assertFalse((self.project / "voice").exists())

    def test_stale_text(self) -> None:
        """narration.import_voice refuses a recording whose sentence text differs, naming the sentence. Guards a
        voiced script that no longer matches the storyboard."""
        src = self.voiced(timing("Count to four.", "Then stop."))
        with self.assertRaisesRegex(narration.NarrationError, "sentence 1"):
            narration.import_voice(self.project, {}, SCENE, src)

    def test_missing_files(self) -> None:
        """narration.import_voice on a directory with only script.txt names the missing narration.wav and
        timing.json. Guards import before voicing."""
        d = narration.write_script(self.project, SCENE)[0][0].parent
        with self.assertRaisesRegex(narration.NarrationError, "narration.wav, timing.json"):
            narration.import_voice(self.project, {}, SCENE, d)


class TestPronounce(unittest.TestCase):
    SCENE = {"id": "end", "narration": ["Visit acme-ai.com, from ACME-AI."]}

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / "settings.yaml").write_text(
            'pronounce: {"ACME-AI": "Acme A.I.", "acme-ai.com": "Acme A.I. dot com"}\n')
        settings.use_project(self.project)

    def tearDown(self) -> None:
        settings.use_project(None)
        self._tmp.cleanup()

    def test_spoken_longest_key_first(self) -> None:
        """narration.spoken replaces `pronounce:` keys longest first, case-sensitively. Guards a key that is a
        prefix of another."""
        self.assertEqual(narration.spoken("acme-ai.com and ACME-AI, not acme-ai"),
                         "Acme A.I. dot com and Acme A.I., not acme-ai")

    def test_script_spoken_import_written(self) -> None:
        """narration.write_script writes the spoken form and import_voice stores the written text with the words
        voicing one written word merged into one timed word. Guards word timings of pronounced words matching
        the storyboard text."""
        [(script, _)] = narration.write_script(self.project, self.SCENE)
        said = "Visit Acme A.I. dot com, from Acme A.I.."
        self.assertEqual(script.read_text(), said + "\n")
        words = [{"text": w, "start": float(i), "end": i + 0.5} for i, w in enumerate(said.split())]
        t = {**timing(said), "sentences": [{"index": 1, "text": said, "words": words}]}
        (script.parent / "narration.wav").write_bytes(b"RIFF")
        (script.parent / "timing.json").write_text(json.dumps(t))
        out = narration.import_voice(self.project, {}, self.SCENE, script.parent)
        [s] = json.loads((out / "timing.json").read_text())["sentences"]
        self.assertEqual(s["text"], "Visit acme-ai.com, from ACME-AI.")
        self.assertEqual([(w["text"], w["start"], w["end"]) for w in s["words"]],
                         [("Visit", 0.0, 0.5), ("acme-ai.com,", 1.0, 4.5), ("from", 5.0, 5.5), ("ACME-AI.", 6.0, 7.5)])
        self.assertEqual((out / "script.txt").read_text(), said + "\n")

    def test_other_text_refused(self) -> None:
        """narration.check refuses a sentence that is neither the written nor the spoken form and quotes the
        spoken form. Guards the pronounce check."""
        t = timing("Visit Acme dot com, from Acme.")
        with self.assertRaisesRegex(narration.NarrationError, "spoken 'Visit Acme A.I. dot com"):
            narration.check(self.SCENE, t)


if __name__ == "__main__":
    unittest.main()
