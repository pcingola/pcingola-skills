"""Unit tests for music_tool.analyze: inputs, briefs, checks and the summary."""

import json
import tempfile
import unittest
from pathlib import Path

from music_tool import analyze

BLOCKS = """Option 1
File: option1_synthwave.mp3 (also .wav)
Model: lyria-3-clip-preview (Lyria 3 Clip)
Prompt sent: Bright retro synthwave. Tempo: 110 BPM. Instrumental only, no vocals.
Raw duration: 30.772 s

Option 2
File: option2_reveal.mp3
Prompt: Cinematic strings, 100 bpm.
"""


def signal(**kw) -> dict:
    base = {"status": "ok", "tempo_bpm": 123.0, "beat_confidence": 0.6, "pulse": "regular", "ibi_cv": 0.018,
            "percussive_ratio": 0.19, "onset_rate_per_s": 5.5, "level": "building", "level_trend_db": 5.9,
            "key": "G", "mode": "minor", "correlation": 0.68, "integrated_lufs": -14.5, "true_peak_dbtp": -1.9}
    return {**base, **kw}


def model(**kw) -> dict:
    base = {"status": "ok", "model": "gemini-x", "genre": "progressive house", "mood": "uplifting",
            "energy": "high", "energy_change_description": "builds at 0:06", "vocals": False,
            "vocals_description": "none", "clip_brief_verdict": "fits", "clip_brief_reasons": ["kick present."],
            "style_brief_verdict": "partly", "style_brief_reasons": ["not futuristic"],
            "clip_brief": "house, 124 BPM", "style_brief": "futuristic bed"}
    return {**base, **kw}


class TestPrompts(unittest.TestCase):

    def test_blocks(self) -> None:
        """analyze.parse_prompts reads `File:` blocks with `Prompt:` or `Prompt sent:` lines and ignores the
        other lines. Guards the block form of the prompts file."""
        self.assertEqual(analyze.parse_prompts(BLOCKS), {
            "option1_synthwave.mp3": "Bright retro synthwave. Tempo: 110 BPM. Instrumental only, no vocals.",
            "option2_reveal.mp3": "Cinematic strings, 100 bpm.",
        })

    def test_json(self) -> None:
        """analyze.parse_prompts reads a JSON object prompts file. Guards the JSON form of the prompts file."""
        self.assertEqual(analyze.parse_prompts('{"a.wav": "calm"}'), {"a.wav": "calm"})

    def test_names_with_spaces(self) -> None:
        """analyze.parse_prompts keeps file names with spaces in line and block entries. Guards the name patterns
        of the prompts file regexes."""
        self.assertEqual(analyze.parse_prompts("my clip.mp3: calm piano 90 BPM\n"),
                         {"my clip.mp3": "calm piano 90 BPM"})
        self.assertEqual(analyze.parse_prompts("File: my clip.wav (also .mp3)\nPrompt: calm\n"),
                         {"my clip.wav": "calm"})

    def test_warnings(self) -> None:
        """analyze.prompt_warnings reports an entry that matches no input and an input without a clip brief, and
        nothing without a prompts file. Guards the warnings stated in the music SKILL.md."""
        files = [Path("/x/a.mp3"), Path("/x/b.mp3")]
        briefs = {files[0]: {"clip": "calm"}, files[1]: {"clip": None}}
        w = analyze.prompt_warnings({"a.mp3": "calm", "zzz.wav": "x"}, files, briefs)
        self.assertEqual(len(w), 2)
        self.assertIn("'zzz.wav' matches no input", w[0])
        self.assertIn("b.mp3: no clip brief", w[1])
        self.assertEqual(analyze.prompt_warnings({}, files, briefs), [])

    def test_lines(self) -> None:
        """analyze.parse_prompts reads `name: prompt` and tab-separated lines and skips lines whose name is not
        an audio file. Guards the line form of the prompts file."""
        text = "a.mp3: calm piano\nb.wav\tdrums, 120 BPM\nnot an entry: x\n"
        self.assertEqual(analyze.parse_prompts(text), {"a.mp3": "calm piano", "b.wav": "drums, 120 BPM"})

    def test_bad_json(self) -> None:
        """analyze.parse_prompts raises AnalyzeError for a prompts file that starts with `{` but is not JSON.
        Guards a clear error in place of falling through to the line form."""
        with self.assertRaises(analyze.AnalyzeError):
            analyze.parse_prompts("{not json")

    def test_lookup_by_name_then_stem(self) -> None:
        """analyze.lookup_prompt matches an entry by file name, else by stem, else returns None. Guards that
        `x.wav` finds the brief written for `x.mp3`."""
        prompts = analyze.parse_prompts(BLOCKS)
        self.assertEqual(analyze.lookup_prompt(prompts, Path("/x/option1_synthwave.wav")), prompts["option1_synthwave.mp3"])
        self.assertIsNone(analyze.lookup_prompt(prompts, Path("/x/other.mp3")))


class TestBriefs(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_requested_bpm_order(self) -> None:
        """analyze.requested_bpm takes the sidecar's bpm, else the first N BPM in the clip brief, else in the
        style brief. Guards the requested-tempo order stated in the music SKILL.md."""
        self.assertEqual(analyze.requested_bpm("x 90 BPM", "y 100 bpm", {"options": {"bpm": 124}}), 124.0)
        self.assertEqual(analyze.requested_bpm("Tempo: 90 BPM.", "100 bpm", None), 90.0)
        self.assertEqual(analyze.requested_bpm("calm", "style at 100 bpm", None), 100.0)
        self.assertIsNone(analyze.requested_bpm("calm", None, {"options": {}}))

    def test_generate_sidecar_is_the_clip_brief(self) -> None:
        """analyze.resolve_brief uses the `generate` sidecar's prompt as the clip brief and its bpm option as the
        requested tempo. Guards the sidecar fallback for clips without a prompts entry."""
        clip = self.dir / "a.mp3"
        clip.write_bytes(b"")
        (self.dir / "a.mp3.json").write_text(json.dumps({"prompt": "lofi. Tempo: 80 BPM.", "options": {"bpm": 82}}))
        b = analyze.resolve_brief(clip, {}, "style")
        self.assertEqual(b, {"clip": "lofi. Tempo: 80 BPM.", "clip_source": "a.mp3.json", "style": "style",
                             "requested_bpm": 82.0})

    def test_prompts_file_wins_over_sidecar(self) -> None:
        """analyze.resolve_brief prefers the prompts-file entry over the `generate` sidecar. Guards the clip
        brief precedence."""
        clip = self.dir / "a.mp3"
        (self.dir / "a.mp3.json").write_text(json.dumps({"prompt": "sidecar"}))
        b = analyze.resolve_brief(clip, {"a.mp3": "from file, 70 BPM"}, None)
        self.assertEqual((b["clip"], b["clip_source"], b["style"], b["requested_bpm"]),
                         ("from file, 70 BPM", "prompts file", None, 70.0))

    def test_merge_keeps_earlier_brief(self) -> None:
        """analyze.merge_brief keeps an earlier report's brief when the run gives none, and drops the old
        requested tempo when the clip brief changes. Guards the rule that the old tempo is kept only when both
        briefs are unchanged."""
        old = {"clip": "house, 124 BPM", "clip_source": "prompts file", "style": "bed", "requested_bpm": 124.0}
        new = {"clip": None, "clip_source": None, "style": None, "requested_bpm": None}
        self.assertEqual(analyze.merge_brief(new, old), old)
        newer = {"clip": "ambient", "clip_source": "prompts file", "style": None, "requested_bpm": None}
        merged = analyze.merge_brief(newer, old)
        self.assertEqual(merged["clip"], "ambient")
        self.assertIsNone(merged["requested_bpm"])  # the old tempo belonged to the replaced brief


class TestInputs(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        for name in ("a.mp3", "a.wav", "b.mp3", "notes.txt"):
            (self.dir / name).write_bytes(b"")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_folder(self) -> None:
        """analyze.collect takes the audio files of a folder, sorted, without other files, and default_out_dir is
        `<folder>/analysis`. Guards input collection and the default report directory."""
        files, dirs = analyze.collect([str(self.dir)])
        self.assertEqual([f.name for f in files], ["a.mp3", "a.wav", "b.mp3"])
        self.assertEqual(analyze.default_out_dir(dirs), self.dir.resolve() / "analysis")

    def test_names_disambiguate_shared_stems(self) -> None:
        """analyze.clip_names uses the file name for inputs that share a stem and the stem otherwise. Guards
        against two clips writing the same report."""
        files, _ = analyze.collect([str(self.dir)])
        self.assertEqual(sorted(analyze.clip_names(files).values()), ["a.mp3", "a.wav", "b"])

    def test_names_across_folders(self) -> None:
        """analyze.clip_names gives four unique names for inputs sharing stems and names across folders,
        `<folder>_<name>` for a shared name. Guards the collision rules of report names."""
        files = [Path("/a/short.wav"), Path("/b/short.wav"), Path("/b/short.mp3"), Path("/c/a/short.wav")]
        names = analyze.clip_names(files)
        self.assertEqual(len(set(names.values())), 4, names)
        self.assertEqual(names[Path("/b/short.mp3")], "short.mp3")
        self.assertEqual(names[Path("/b/short.wav")], "b_short.wav")

    def test_out_dir_with_inputs_refused(self) -> None:
        """analyze.run refuses an --out-dir that holds input files. Guards that a report cannot replace a
        `generate` sidecar."""
        with self.assertRaises(analyze.AnalyzeError):
            analyze.run([str(self.dir / "a.mp3")], None, None, ["signal"], None, str(self.dir), 1)

    def test_refusals(self) -> None:
        """analyze.collect refuses a non-audio file, a missing path and a folder without audio, and
        default_out_dir refuses inputs from several folders. Guards the input errors of `analyze`."""
        with self.assertRaises(analyze.AnalyzeError):
            analyze.collect([str(self.dir / "notes.txt")])
        with self.assertRaises(analyze.AnalyzeError):
            analyze.collect([str(self.dir / "missing.mp3")])
        empty = self.dir / "empty"
        empty.mkdir()
        with self.assertRaises(analyze.AnalyzeError):
            analyze.collect([str(empty)])
        with self.assertRaises(analyze.AnalyzeError):
            analyze.default_out_dir({self.dir, empty})


class TestChecksAndSummary(unittest.TestCase):

    def test_flags(self) -> None:
        """analyze.checks flags a tempo that differs, a true peak above -1 dBTP, a sparse level and vocals heard
        in an instrumental brief. Guards each flag rule of the checks section."""
        rec = {"brief": {"clip": "Instrumental only.", "requested_bpm": 90.0},
               "signal": signal(tempo_bpm=118.0, true_peak_dbtp=-0.1, level="sparse"),
               "model": model(vocals=True, vocals_description="female choir")}
        c = analyze.checks(rec)
        self.assertEqual(c["tempo"]["relation"], "differs")
        self.assertEqual(len(c["flags"]), 4)
        self.assertTrue(any("vocals heard" in f for f in c["flags"]))

    def test_no_flags(self) -> None:
        """analyze.checks gives a `match` tempo and no flags for a clip within every limit. Guards against false
        flags."""
        c = analyze.checks({"brief": {"requested_bpm": 124.0}, "signal": signal(), "model": model()})
        self.assertEqual((c["tempo"]["relation"], c["flags"]), ("match", []))

    def test_paragraph_uses_the_judged_briefs(self) -> None:
        """analyze.paragraph states the verdicts of the briefs the model answer was judged against, even when the
        current brief is empty, plus tempo, reasons and image links. Guards the summary after a rerun of other
        sections with --only."""
        rec = {"brief": {"clip": None, "style": None, "requested_bpm": 124.0}, "signal": signal(), "model": model(),
               "images": {"status": "ok", "spectrogram": "x_spec.png", "waveform": "x_wave.png"}}
        rec["checks"] = analyze.checks(rec)
        p = analyze.paragraph(rec)
        self.assertTrue(p.startswith("Verdict: fits the clip brief; partly fits the style brief (gemini-x)."), p)
        self.assertIn("Tempo 123 BPM measured vs 124 requested (match)", p)
        self.assertIn("Reasons: kick present; not futuristic.", p)
        self.assertIn("[spectrogram](x_spec.png)", p)

    def test_paragraph_without_model(self) -> None:
        """analyze.paragraph names the skip reason of the model section and says no tempo was measured. Guards
        the paragraph of a clip without a model verdict or a tempo."""
        rec = {"brief": {}, "signal": signal(tempo_bpm=None, pulse="none", ibi_cv=None),
               "model": {"status": "skipped", "reason": "no audio model in the config"}}
        rec["checks"] = analyze.checks(rec)
        p = analyze.paragraph(rec)
        self.assertTrue(
            p.startswith("Verdict: no model verdict (no audio model in the config). No tempo measured;"), p)

    def test_paragraph_silent(self) -> None:
        """analyze.paragraph of a silent clip says `No key` and flags it silent. Guards the paragraph for a clip
        with no key or tempo."""
        rec = {"brief": {}, "signal": signal(tempo_bpm=None, pulse="none", ibi_cv=None, level="silent", key=None,
                                             mode=None, correlation=None)}
        rec["checks"] = analyze.checks(rec)
        p = analyze.paragraph(rec)
        self.assertIn("No key", p)
        self.assertIn("Flags: silent.", p)

    def test_stale_requested_confidence_not_shown(self) -> None:
        """analyze.paragraph shows the beat confidence at the requested tempo only when the signal section was
        computed for that tempo. Guards the stored requested_bpm against a stale confidence after the brief
        changed."""
        rec = {"brief": {"requested_bpm": 90.0}, "signal": signal(requested_bpm=100.0, requested_bpm_confidence=0.3)}
        rec["checks"] = analyze.checks(rec)
        self.assertNotIn("beat confidence at 90", analyze.paragraph(rec))
        rec["signal"]["requested_bpm"] = 90.0
        self.assertIn("beat confidence at 90 BPM 0.30", analyze.paragraph(rec))

    def test_incomplete_report_does_not_stop_summary(self) -> None:
        """analyze.write_summary writes a note for a report with missing fields and still writes the other clips.
        Guards safe_paragraph."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "a.json").write_text(json.dumps({"tool": analyze.TOOL, "name": "a", "signal": {"status": "ok"}}))
            (out / "b.json").write_text(json.dumps({"tool": analyze.TOOL, "name": "b", "signal": signal()}))
            text = analyze.write_summary(out).read_text()
            self.assertIn("Incomplete report", text)
            self.assertIn("Tempo 123 BPM measured", text)

    def test_summary_reads_only_reports(self) -> None:
        """analyze.write_summary reads only JSON files with `"tool": "music analyze"`, sorted by name, with the
        scope note. Guards that sidecars and other JSON in the report directory are not summarised."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for name in ("b", "a"):
                rec = {"tool": analyze.TOOL, "name": name, "brief": {}, "signal": signal()}
                (out / f"{name}.json").write_text(json.dumps(rec))
            (out / "other.json").write_text(json.dumps({"name": "zzz"}))
            text = analyze.write_summary(out).read_text()
            self.assertLess(text.index("## a"), text.index("## b"))
            self.assertNotIn("zzz", text)
            self.assertIn("not musical quality", text)


if __name__ == "__main__":
    unittest.main()
