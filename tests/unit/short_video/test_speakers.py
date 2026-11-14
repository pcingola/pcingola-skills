"""short_video_tool.speakers: runs of sentences per speaker, the voice check,
and joining voiced parts into one narration."""
import json
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from short_video_tool import narration, settings, speakers, state, storyboard

SR = 24000


def part(sentences: list[tuple[str, float]], lead: float = 0.25, gap: float = 0.35, tail: float = 0.6,
         voice: str = "af_heart", value: int = 1000) -> tuple[np.ndarray, dict]:
    """A recording laid out as the voiceover skill writes it: `lead` silence,
    each sentence a constant non-zero block of its length, `gap` between,
    `tail` after; and its timing dict with one word per sentence."""
    chunks = [np.zeros(int(lead * SR), dtype="<i2")]
    pos = chunks[0].size
    timing_sentences = []
    for i, (text, length) in enumerate(sentences, 1):
        if i > 1:
            chunks.append(np.zeros(int(gap * SR), dtype="<i2"))
            pos += chunks[-1].size
        n = int(length * SR)
        chunks.append(np.full(n, value * i, dtype="<i2"))
        start, end = pos / SR, (pos + n) / SR
        timing_sentences.append({"index": i, "text": text, "start": start, "end": end, "aligned": True,
                                 "words": [{"text": text.split()[0], "start": start, "end": start + 0.1}]})
        pos += n
    chunks.append(np.zeros(int(tail * SR), dtype="<i2"))
    samples = np.concatenate(chunks)
    return samples, {"audio": "narration.wav", "sample_rate": SR, "duration": samples.size / SR,
                     "backend": "kokoro", "voice": voice, "speed": 1.0, "sentences": timing_sentences}


class TestRuns(unittest.TestCase):
    def test_without_speaker_column_one_default_run(self) -> None:
        """speakers.runs of a scene without a Speaker column is one default-voice run. Guards one-voice scenes
        keeping a single script.txt."""
        settings.use_project(None)
        film = storyboard.resolve_voice({})
        self.assertEqual(speakers.runs({}, {"narration": ["A.", "B."]}), [(None, film, 0, ["A.", "B."])])

    def test_consecutive_sentences_grouped(self) -> None:
        """speakers.runs groups consecutive sentences of one speaker and starts a new run at each change, with
        the first sentence index. Guards the part layout p<k>/script.txt."""
        settings.use_project(None)
        scene = {"narration": ["A.", "B.", "C.", "D.", "E."],
                 "speakers": ["host", "host", None, "host", None]}
        host, film = storyboard.resolve_voice(DATA_HOST, "host"), storyboard.resolve_voice(DATA_HOST)
        self.assertEqual(speakers.runs(DATA_HOST, scene), [
            ("host", host, 0, ["A.", "B."]), (None, film, 2, ["C."]), ("host", host, 3, ["D."]),
            (None, film, 4, ["E."])])

    def test_own_voice_settings_split_runs(self) -> None:
        """speakers.runs starts a new run where a sentence's own voice settings change its resolved voice, and
        keeps sentences with the same resolved voice together. Guards a sentence with its own settings being
        voiced as its own part."""
        settings.use_project(None)
        scene = {"narration": ["A.", "B.", "C.", "D."], "speakers": ["host", "host", "host", "host"],
                 "voices": [None, {"speed": 1.2}, {"speed": 1.2}, {"name": "bm_george"}]}
        got = speakers.runs(DATA_HOST, scene)
        self.assertEqual([(r[2], r[3]) for r in got], [(0, ["A."]), (1, ["B.", "C."]), (3, ["D."])])
        self.assertEqual([r[1] for r in got], [
            {"backend": "kokoro", "name": "bm_george", "speed": 1.1, "style": None},
            {"backend": "kokoro", "name": "bm_george", "speed": 1.2, "style": None},
            {"backend": "kokoro", "name": "bm_george", "speed": 1.1, "style": None}])

    def test_same_resolved_voice_one_run(self) -> None:
        """speakers.runs keeps a sentence whose own settings equal its speaker's voice in the speaker's run.
        Guards splitting on the resolved voice, not on the presence of settings."""
        settings.use_project(None)
        scene = {"narration": ["A.", "B."], "voices": [None, {"backend": "kokoro", "speed": 1.0}]}
        self.assertEqual(len(speakers.runs({}, scene)), 1)


DATA_HOST = {"speakers": {"host": {"backend": "kokoro", "name": "bm_george", "speed": 1.1, "style": None}}}


class TestJoin(unittest.TestCase):
    def setUp(self) -> None:
        self.a, self.ta = part([("One two.", 1.0), ("Three.", 0.5)])
        self.b, self.tb = part([("Four five.", 0.75)], voice="bm_george", value=7000)
        self.c, self.tc = part([("Six.", 0.5)])
        self.audio, self.timing = speakers.join(
            [(None, self.a, SR, self.ta), ("guest", self.b, SR, self.tb), (None, self.c, SR, self.tc)], 0.35)

    def test_length_exact_to_the_sample(self) -> None:
        # lead + 1.0 + gap + 0.5 | gap | 0.75 | gap | 0.5 + tail
        """speakers.join keeps the first part's lead, the last part's tail and speaker_gap at each change, and
        the total length is exact to the sample. Guards the joined narration matching its timing.json."""
        want = 0.25 + 1.0 + 0.35 + 0.5 + 0.35 + 0.75 + 0.35 + 0.5 + 0.6
        self.assertEqual(self.audio.size, round(want * SR))
        self.assertEqual(self.timing["duration"], round(want, 3))

    def test_silences_and_speech_where_expected(self) -> None:
        """speakers.join places every sentence's samples and every silence at the expected times. Guards
        trimming of each part's lead and tail at the joins."""
        def block(start: float, length: float) -> np.ndarray:
            return self.audio[round(start * SR):round((start + length) * SR)]

        lead, gap = 0.25, 0.35
        self.assertTrue((block(0, lead) == 0).all())
        self.assertTrue((block(lead, 1.0) == 1000).all())
        self.assertTrue((block(1.6, 0.5) == 2000).all())
        self.assertTrue((block(2.1, gap) == 0).all())
        self.assertTrue((block(2.45, 0.75) == 7000).all())
        self.assertTrue((block(3.2, gap) == 0).all())
        self.assertTrue((block(3.55, 0.5) == 1000).all())
        self.assertTrue((block(4.05, 0.6) == 0).all())

    def test_shifted_times_and_indexes(self) -> None:
        """speakers.join shifts sentence and word times by each part's offset, renumbers sentences and records
        each sentence's speaker. Guards word timings of later parts."""
        got = [(s["index"], s["text"], s["start"], s["end"], s["speaker"]) for s in self.timing["sentences"]]
        self.assertEqual(got, [
            (1, "One two.", 0.25, 1.25, None),
            (2, "Three.", 1.6, 2.1, None),
            (3, "Four five.", 2.45, 3.2, "guest"),
            (4, "Six.", 3.55, 4.05, None),
        ])
        self.assertEqual(self.timing["sentences"][2]["words"], [{"text": "Four", "start": 2.45, "end": 2.55}])

    def test_voice_fields(self) -> None:
        """speakers.join takes the top-level voice fields from the first part and lists every part's speaker and
        voice. Guards the voice record in meta.json."""
        self.assertEqual((self.timing["backend"], self.timing["voice"], self.timing["speed"]),
                         ("kokoro", "af_heart", 1.0))
        self.assertEqual([(v["speaker"], v["voice"], v["sentences"]) for v in self.timing["speakers"]],
                         [(None, "af_heart", 2), ("guest", "bm_george", 1), (None, "af_heart", 1)])

    def test_recorded_voices(self) -> None:
        """speakers.recorded_voices gives each sentence of a joined recording its part's voice, from the part
        sizes or, without them, from runs of `speaker`; a single recording gives its own voice to every
        sentence. Guards the voice check of stored voice versions in `status`."""
        self.assertEqual([v["voice"] for v in speakers.recorded_voices(self.timing)],
                         ["af_heart", "af_heart", "bm_george", "af_heart"])
        old = {**self.timing, "speakers": [{k: v for k, v in p.items() if k != "sentences"}
                                           for p in self.timing["speakers"]]}
        self.assertEqual([v["voice"] for v in speakers.recorded_voices(old)],
                         ["af_heart", "af_heart", "bm_george", "af_heart"])
        self.assertEqual(speakers.recorded_voices(self.ta), [self.ta, self.ta])

    def test_sample_rate_mismatch_refused(self) -> None:
        """speakers.join refuses parts with different sample rates. Guards joining samples at the wrong speed."""
        with self.assertRaisesRegex(narration.NarrationError, "different sample rates: 24000, 48000"):
            speakers.join([(None, self.a, SR, self.ta), ("guest", self.b, 48000, self.tb)], 0.35)

    def test_one_speaker_two_voices_refused(self) -> None:
        """speakers.join refuses two parts of one speaker voiced with different voices. Guards a speaker whose
        voice name is null (the speech provider's default) changing voice inside a scene."""
        _, other = part([("Six.", 0.5)], voice="bf_emma")
        with self.assertRaisesRegex(narration.NarrationError, "part 3.*'bf_emma'.*'af_heart'"):
            speakers.join([(None, self.a, SR, self.ta), ("guest", self.b, SR, self.tb), (None, self.c, SR, other)],
                          0.35)

    def test_own_voice_name_allowed(self) -> None:
        """speakers.join accepts a part of the default voice whose sentence names its own voice (same backend,
        speed and style, another name), as the storyboard's per-sentence Voice column allows
        (references/storyboard.md, "Voice settings per sentence"). Guards refusing a voice-name-only change."""
        _, own = part([("Six.", 0.5)], voice="bf_emma")
        _, timing = speakers.join([(None, self.a, SR, self.ta), ("guest", self.b, SR, self.tb),
                                   (None, self.c, SR, own)], 0.35, [None, None, "bf_emma"])
        self.assertEqual([p["voice"] for p in timing["speakers"]], ["af_heart", "bm_george", "bf_emma"])

    def test_one_null_name_two_voices_refused_with_names(self) -> None:
        """speakers.join still refuses two default-voice parts with null names voiced with different voices when
        another part has its own name. Guards the default voice changing inside a scene."""
        _, own = part([("Six.", 0.5)], voice="bf_emma")
        _, other = part([("Seven.", 0.5)], voice="bf_isabella")
        with self.assertRaisesRegex(narration.NarrationError, "part 4.*'bf_isabella'.*'af_heart'"):
            speakers.join([(None, self.a, SR, self.ta), ("guest", self.b, SR, self.tb), (None, self.c, SR, own),
                           (None, self.c, SR, other)], 0.35, [None, None, "bf_emma", None])


class TestReadWav(unittest.TestCase):
    def test_stereo_refused(self) -> None:
        """speakers.read_wav refuses a stereo 16-bit WAV with a NarrationError naming the file. Guards
        the mono 16-bit check before a part is joined sample by sample."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stereo.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(24000)
                w.writeframes(np.zeros(200, dtype="<i2").tobytes())
            with self.assertRaisesRegex(narration.NarrationError, r"stereo\.wav: not mono 16-bit PCM"):
                speakers.read_wav(path)


class TestCheckVoice(unittest.TestCase):
    def test_wrong_voice_refused(self) -> None:
        """speakers.check_voice refuses a recording in another voice, naming the speaker and both voices. Guards
        a part voiced in the wrong voice."""
        timing = {"backend": "kokoro", "voice": "af_heart", "speed": 1.0}
        voice = {"backend": "kokoro", "name": "bm_george", "speed": 1.0, "style": None}
        with self.assertRaisesRegex(narration.NarrationError, "speaker 'guest'.*'af_heart'.*'bm_george'"):
            speakers.check_voice(timing, voice, "guest")

    def test_wrong_speed_and_style_refused(self) -> None:
        """speakers.check_voice refuses a missing style and a wrong speed, naming the default voice. Guards
        every voice field being checked."""
        voice = {"backend": "speech", "name": "Kore", "speed": 1.0, "style": "warm"}
        with self.assertRaisesRegex(narration.NarrationError, "style"):
            speakers.check_voice({"backend": "speech", "voice": "Kore", "speed": 1.0}, voice, "guest")
        with self.assertRaisesRegex(narration.NarrationError, "default voice.*speed 1.2"):
            speakers.check_voice({"backend": "speech", "voice": "Kore", "speed": 1.2, "style": "warm"},
                                 voice, None)

    def test_chatterbox_path_compared_resolved(self) -> None:
        """speakers.check_voice compares a chatterbox voice path after expanding ~ and refuses another path.
        Guards voice-cloning paths recorded as absolute by voiceover."""
        voice = {"backend": "chatterbox", "name": "~/voices/anna.wav", "speed": 1.0, "style": None}
        recorded = str(Path("~/voices/anna.wav").expanduser())
        speakers.check_voice({"backend": "chatterbox", "voice": recorded, "speed": 1.0}, voice, "anna")
        with self.assertRaisesRegex(narration.NarrationError, "voice"):
            speakers.check_voice({"backend": "chatterbox", "voice": "/other/anna.wav", "speed": 1.0}, voice, "anna")

    def test_null_name_resolves_to_backend_default(self) -> None:
        """storyboard.resolve_voice resolves an empty voice to the backend default (null for speech, whose
        default depends on the provider); check_voice accepts the voice recorded with it and refuses a recording
        without one. Guards speakers defined with empty Voice cells."""
        data = {"speakers": {"guest": {"backend": "speech", "name": None, "speed": None, "style": None}}}
        voice = storyboard.resolve_voice(data, "guest")
        self.assertEqual(voice, {"backend": "speech", "name": None, "speed": 1.0, "style": None})
        speakers.check_voice({"backend": "speech", "voice": "Kore", "speed": 1.0}, voice, "guest")
        speakers.check_voice({"backend": "speech", "voice": "marin", "speed": 1.0}, voice, "guest")
        with self.assertRaisesRegex(narration.NarrationError, "records no voice"):
            speakers.check_voice({"backend": "speech", "speed": 1.0}, voice, "guest")
        speakers.check_voice({"backend": "kokoro", "voice": "af_heart", "speed": 1.0},
                             storyboard.resolve_voice(data), None)


DATA = {"speakers": {"guest": {"backend": "kokoro", "name": "bm_george", "speed": None, "style": None}}}
ONE = {"id": "talk", "narration": ["Hello.", "Hi."]}
TWO = {"id": "talk", "narration": ["Hello.", "Hi."], "speakers": [None, "guest"]}


class TestScenes(unittest.TestCase):
    """`write_script` and `import_voice` on scenes with and without speakers."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        settings.use_project(None)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def voice(self, d: Path, texts: list[str], voice: str = "af_heart") -> None:
        samples, timing = part([(t, 0.5) for t in texts], voice=voice)
        speakers.write_wav(d / "narration.wav", samples, SR)
        (d / "timing.json").write_text(json.dumps(timing))

    def test_two_speakers_write_parts(self) -> None:
        """narration.write_script of a two-speaker scene writes p1 and p2 scripts with their speakers and no
        scene script.txt. Guards the multi-speaker script layout."""
        written = narration.write_script(self.project, DATA, TWO)
        scene_dir = narration.script_dir(self.project, "talk")
        self.assertEqual([w[:2] for w in written], [(scene_dir / "p1" / "script.txt", None),
                                                    (scene_dir / "p2" / "script.txt", "guest")])
        self.assertEqual(written[1][2]["name"], "bm_george")
        self.assertEqual((scene_dir / "p2" / "script.txt").read_text(), "Hi.\n")
        self.assertFalse((scene_dir / "script.txt").exists())

    def test_stale_parts_removed_when_one_speaker_left(self) -> None:
        """narration.write_script removes part directories and the joined recording when a scene goes back to
        one speaker. Guards importing a recording of the old layout."""
        narration.write_script(self.project, DATA, TWO)
        scene_dir = narration.script_dir(self.project, "talk")
        self.voice(scene_dir / "p1", ["Hello."])
        self.voice(scene_dir / "p2", ["Hi."], "bm_george")
        narration.join_parts(self.project, DATA, TWO, scene_dir)
        self.assertTrue((scene_dir / "timing.json").is_file())

        written = narration.write_script(self.project, DATA, ONE)
        self.assertEqual([w[:2] for w in written], [(scene_dir / "script.txt", None)])
        self.assertEqual(sorted(p.name for p in scene_dir.iterdir()), ["script.txt"])

    def test_stale_recording_removed_when_speakers_added(self) -> None:
        """narration.write_script removes the scene's single recording when speakers are added. Guards importing
        a one-voice recording of a two-voice scene."""
        narration.write_script(self.project, DATA, ONE)
        scene_dir = narration.script_dir(self.project, "talk")
        self.voice(scene_dir, ["Hello.", "Hi."])
        narration.write_script(self.project, DATA, TWO)
        self.assertEqual(sorted(p.name for p in scene_dir.iterdir()), ["p1", "p2"])

    def test_rewritten_one_run_script_drops_old_recording(self) -> None:
        # A scene first spoken by `guest`, then given back to the default voice:
        # the guest recording must not be importable, though its sentences match.
        """narration.write_script removes a one-run recording made in a speaker's voice when the scene goes back
        to the default voice, so import_voice refuses. Guards a recording in the wrong voice whose sentences
        still match."""
        guest = {"id": "talk", "narration": ["Hello.", "Hi."], "speakers": ["guest", "guest"]}
        narration.write_script(self.project, DATA, guest)
        scene_dir = narration.script_dir(self.project, "talk")
        self.voice(scene_dir, ["Hello.", "Hi."], "bm_george")
        narration.write_script(self.project, DATA, ONE)
        self.assertEqual(sorted(p.name for p in scene_dir.iterdir()), ["script.txt"])
        with self.assertRaisesRegex(narration.NarrationError, "has no narration.wav, timing.json"):
            narration.import_voice(self.project, DATA, ONE, scene_dir)

    def test_import_from_src_outside_project_leaves_it_unchanged(self) -> None:
        """narration.import_voice of part directories outside the project joins them into the project's scene
        directory and leaves the source unchanged. Guards writing into a directory the user passed."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp)
            for k, (texts, voice) in enumerate([(["Hello."], "af_heart"), (["Hi."], "bm_george")], 1):
                (src / f"p{k}").mkdir()
                (src / f"p{k}" / "script.txt").write_text("\n".join(texts) + "\n")
                self.voice(src / f"p{k}", texts, voice)
            out = narration.import_voice(self.project, DATA, TWO, src)
            self.assertEqual(sorted(p.name for p in src.iterdir()), ["p1", "p2"])
        self.assertEqual(len(json.loads((out / "timing.json").read_text())["sentences"]), 2)
        self.assertTrue((narration.script_dir(self.project, "talk") / "timing.json").is_file())

    def test_import_two_speakers(self) -> None:
        """narration.import_voice joins two voiced parts into one voice version with the scene's script and
        records each sentence's speaker and voice in meta.json. Guards the multi-speaker import end to end."""
        narration.write_script(self.project, DATA, TWO)
        scene_dir = narration.script_dir(self.project, "talk")
        self.voice(scene_dir / "p1", ["Hello."])
        self.voice(scene_dir / "p2", ["Hi."], "bm_george")
        out = narration.import_voice(self.project, DATA, TWO, scene_dir)
        timing = json.loads((out / "timing.json").read_text())
        self.assertEqual([s["text"] for s in timing["sentences"]], ["Hello.", "Hi."])
        self.assertEqual((out / "script.txt").read_text(), "Hello.\nHi.\n")
        meta = state.read_meta(out)
        self.assertEqual([(s["speaker"], s["voice"]["name"]) for s in meta["speakers"]],
                         [(None, "af_heart"), ("guest", "bm_george")])

    def test_import_refuses_part_in_wrong_voice(self) -> None:
        """narration.import_voice refuses a part voiced in another voice and creates no voice version. Guards
        the per-part voice check."""
        narration.write_script(self.project, DATA, TWO)
        scene_dir = narration.script_dir(self.project, "talk")
        self.voice(scene_dir / "p1", ["Hello."])
        self.voice(scene_dir / "p2", ["Hi."])
        with self.assertRaisesRegex(narration.NarrationError, "speaker 'guest'"):
            narration.import_voice(self.project, DATA, TWO, scene_dir)
        self.assertFalse((self.project / "voice").exists())

    def test_import_refuses_part_with_stale_text(self) -> None:
        """narration.import_voice refuses a part whose sentence differs, naming part and sentence. Guards the
        per-part sentence check."""
        narration.write_script(self.project, DATA, TWO)
        scene_dir = narration.script_dir(self.project, "talk")
        self.voice(scene_dir / "p1", ["Hello."])
        self.voice(scene_dir / "p2", ["Bye."], "bm_george")
        with self.assertRaisesRegex(narration.NarrationError, "part 2 sentence 1"):
            narration.import_voice(self.project, DATA, TWO, scene_dir)

    def test_part_with_own_settings_named_by_them(self) -> None:
        """narration.import_voice names a part with its own voice settings and no speaker by those settings in
        its error. Guards a message that blamed the film's voice for a sentence's own settings."""
        scene = {"id": "talk", "narration": ["Hello.", "Hi."], "voices": [None, {"name": "bm_george"}]}
        narration.write_script(self.project, DATA, scene)
        scene_dir = narration.script_dir(self.project, "talk")
        self.voice(scene_dir / "p1", ["Hello."])
        self.voice(scene_dir / "p2", ["Hi."])
        with self.assertRaisesRegex(narration.NarrationError, "part 2: sentence 2's own voice settings: voiced"):
            narration.import_voice(self.project, DATA, scene, scene_dir)

    def test_one_run_with_speaker_column_checked(self) -> None:
        """narration.import_voice checks a one-run scene with a speaker against that speaker's voice and records
        it. Guards the voice check on single-run speaker scenes."""
        scene = {"id": "talk", "narration": ["Hello.", "Hi."], "speakers": ["guest", "guest"]}
        narration.write_script(self.project, DATA, scene)
        scene_dir = narration.script_dir(self.project, "talk")
        self.voice(scene_dir, ["Hello.", "Hi."])
        with self.assertRaisesRegex(narration.NarrationError, "speaker 'guest'"):
            narration.import_voice(self.project, DATA, scene, scene_dir)
        self.voice(scene_dir, ["Hello.", "Hi."], "bm_george")
        out = narration.import_voice(self.project, DATA, scene, scene_dir)
        self.assertEqual([s["speaker"] for s in state.read_meta(out)["speakers"]], ["guest", "guest"])


if __name__ == "__main__":
    unittest.main()
