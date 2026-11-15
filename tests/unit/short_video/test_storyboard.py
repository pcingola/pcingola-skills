"""short_video_tool.storyboard: parsing storyboard.md, and validating what the
parser cannot check (files, settings, template positions, length)."""
import tempfile
import unittest
from pathlib import Path

from short_video_tool import settings, storyboard

MD = """\
<!-- a comment -->
# Vaccines

Topic: How a vaccine
trains the immune system.
Source: sources/notes.md

## title
Template: title

| Narration | On screen |
|---|---|
| This film is about vaccines. | How a vaccine works |

## injection
Image: a.png
Brief: Start wide.
<a href="images/a.png"><img src="images/a.png" width="30%"></a>

| Narration | On screen |
| :-- | --: |
| A cell \\| a virus. |   Label "cell" on "cell".   |

## end
Template: end

| Narration | On screen |
|---|---|
| Check your vaccinations. | Check them |
"""

PARSED = {
    "title": "Vaccines", "topic": "How a vaccine trains the immune system.", "source": "sources/notes.md",
    "scenes": [
        {"id": "title", "template": "title", "narration": ["This film is about vaccines."],
         "beats": ["How a vaccine works"]},
        {"id": "injection", "image": "a.png", "brief": "Start wide.", "preview": "images/a.png",
         "narration": ["A cell | a virus."], "beats": ['Label "cell" on "cell".']},
        {"id": "end", "template": "end", "narration": ["Check your vaccinations."], "beats": ["Check them"]},
    ],
}


def _error(text: str) -> str:
    with unittest.TestCase().assertRaises(storyboard.StoryboardError) as cm:
        storyboard.parse_markdown(text)
    return str(cm.exception)


class TestParse(unittest.TestCase):

    def test_parse(self) -> None:
        """storyboard.parse_markdown reads title, a multi-line topic, source, template and image scenes, the
        preview link, escaped pipes and aligned table rules into the scene dicts. Guards the deterministic parse
        of the storyboard format in references/storyboard.md."""
        self.assertEqual(storyboard.parse_markdown(MD), PARSED)

    def test_parse_without_image(self) -> None:
        """storyboard.parse_markdown reads an HTML scene with a Brief and no Image into a scene without `image`,
        with and without `Engine: html`. Guards scenes drawn in the page with no picture."""
        md = MD.replace("Image: a.png\n", "").replace(
            '<a href="images/a.png"><img src="images/a.png" width="30%"></a>\n', "")
        scene = storyboard.parse_markdown(md)["scenes"][1]
        self.assertEqual(scene, {"id": "injection", "brief": "Start wide.", "narration": ["A cell | a virus."],
                                 "beats": ['Label "cell" on "cell".']})
        scene = storyboard.parse_markdown(md.replace("## injection\n", "## injection\nEngine: html\n"))["scenes"][1]
        self.assertEqual((scene["engine"], "image" in scene), ("html", False))

    def test_errors_name_their_line(self) -> None:
        """storyboard.parse_markdown reports a missing brief, wrong cell count, empty narration, duplicate or
        invalid scene id, unknown template, Brief on a template, settings keys in the storyboard, unknown keys
        and text after the table, each with its line. Guards parse errors the agent can fix from the message."""
        cases = [  # (replace, with, line, fragment)
            ("Brief: Start wide.\n", "", 15, "missing `Brief:`"),
            ("| A cell \\| a virus. |", "| A cell | a virus. |", 22, "has 3 cells"),
            ("| A cell \\| a virus. |", "|  |", 22, "empty Narration"),
            ("## end", "## injection", 24, "duplicate scene id 'injection'"),
            ("## end", "## End-1", 24, "invalid scene id"),
            ("Template: end", "Template: outro", 25, "must be one of"),
            ("Template: title\n", "Template: title\nBrief: x\n", 10, "takes no `Brief:`"),
            ("Source: sources/notes.md", "Voice: backend=kokoro", 6, "settings.yaml (`voice:`)"),
            ("Source: sources/notes.md", "Author: Jane", 6, "settings.yaml (`author:`)"),
            ("Brief: Start wide.", "Brief: Start wide.\nDuration: 5", 18, "unknown key `Duration:`"),
            ("| Check them |", "| Check them |\nmore text", 30, "text after the table"),
        ]
        for old, new, line, fragment in cases:
            with self.subTest(fragment=fragment):
                msg = _error(MD.replace(old, new))
                prefix = f"storyboard.md line {line}: "
                self.assertTrue(any(m.startswith(prefix) and fragment in m for m in msg.splitlines()), msg)


SPEAKERS_MD = """\
# Interview

Topic: Two people talk.

| Speaker | Model | Voice | Speed | Style |
|---|---|---|---|---|
| host | kokoro:kokoro-v1.0 | bm_george | 1.1 | |
| guest | oai:tts | | | warm, curious |

## talk
Image: a.png
Brief: Two faces.

| Speaker | Narration | On screen |
|---|---|---|
| host | Welcome. | host face |
| guest | Thank you. | guest face |
|  | They talk. | both \\| faces |
"""


class TestSpeakers(unittest.TestCase):

    def test_parse(self) -> None:
        """storyboard.parse_markdown reads the header speaker table (empty cells as None, speed as a number) and
        a scene's Speaker column, empty for the default voice. Guards the speakers format."""
        data = storyboard.parse_markdown(SPEAKERS_MD)
        self.assertEqual(data["speakers"], {
            "host": {"model": "kokoro:kokoro-v1.0", "name": "bm_george", "speed": 1.1, "style": None},
            "guest": {"model": "oai:tts", "name": None, "speed": None, "style": "warm, curious"},
        })
        [scene] = data["scenes"]
        self.assertEqual(scene["narration"], ["Welcome.", "Thank you.", "They talk."])
        self.assertEqual(scene["beats"], ["host face", "guest face", "both | faces"])
        self.assertEqual(scene["speakers"], ["host", "guest", None])

    def test_without_speakers_no_new_keys(self) -> None:
        """storyboard.parse_markdown without a speaker table adds no `speakers` key to the film or its scenes.
        Guards one-voice films taking the single-voice path."""
        data = storyboard.parse_markdown(MD)
        self.assertNotIn("speakers", data)
        self.assertFalse(any("speakers" in s for s in data["scenes"]))

    def test_errors_name_their_line(self) -> None:
        """storyboard.parse_markdown reports duplicate and invalid speaker names, a non-numeric speed, wrong
        cell counts, a second header table, a table outside a scene, an undefined speaker and a wrong rule
        width, each with its line. Guards the speaker table checks."""
        cases = [  # (replace, with, line, fragment)
            ("| guest | oai:tts |", "| host | oai:tts |", 8, "duplicate speaker 'host' (first at line 7)"),
            ("| guest | oai:tts |", "| Guest-2 | oai:tts |", 8, "invalid speaker name 'Guest-2'"),
            ("| 1.1 |", "| fast |", 7, "Speed 'fast' is not a number"),
            ("| host | kokoro:kokoro-v1.0 | bm_george | 1.1 | |", "| host | kokoro:kokoro-v1.0 | bm_george |", 7, "needs 5"),
            ("Topic: Two people talk.\n", "Topic: Two people talk.\n\n| Speaker | Model | Voice | Speed | Style |\n"
             "|---|---|---|---|---|\n| x | kokoro:kokoro-v1.0 | | | |\n", 9, "a second table in the header"),
            ("| Speaker | Model |", "| Name | Model |", 5, "table outside a scene"),
            ("| guest | Thank you. |", "| critic | Thank you. |", 17, "speaker 'critic' is not defined"),
            ("| guest | Thank you. | guest face |", "| Thank you. | guest face |", 17, "has 2 cells, needs 3"),
            ("| On screen |\n|---|---|---|\n", "| On screen |\n|---|---|\n", 15, "`|---|---|---|`"),
        ]
        for old, new, line, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assertIn(old, SPEAKERS_MD)
                msg = _error(SPEAKERS_MD.replace(old, new))
                prefix = f"storyboard.md line {line}: "
                self.assertTrue(any(m.startswith(prefix) and fragment in m for m in msg.splitlines()), msg)

    def test_earlier_backend_column_names_its_replacement(self) -> None:
        """A speakers table or scene table with the earlier Backend column, and a storyboard.json voice with
        `backend`, are refused with a message that Backend became Model and how kokoro, chatterbox and speech map.
        Guards projects made before the voice named a speech model."""
        old = SPEAKERS_MD.replace("| Speaker | Model |", "| Speaker | Backend |")
        msg = _error(old)
        self.assertIn("storyboard.md line 5: speakers table column 'Backend': Backend (`backend`) became Model", msg)
        self.assertIn("a model of a provider of that kind", msg)
        scene = SPEAKERS_MD.replace("| Speaker | Narration | On screen |\n|---|---|---|",
                                    "| Speaker | Narration | On screen | Backend |\n|---|---|---|---|")
        self.assertIn("table column 'Backend': Backend (`backend`) became Model", _error(scene))
        data = storyboard.parse_markdown(SPEAKERS_MD)
        data["speakers"]["host"] = {"backend": "kokoro", "name": "bm_george"}
        problems = [m for _, m in storyboard.check(data)]
        self.assertTrue(any("became Model" in m and "for speech, an empty Model" in m for m in problems), problems)

    def test_earlier_backend_maps_to_the_configured_model(self) -> None:
        """storyboard.backend_model maps an earlier backend to the config's speech model of the provider kind of that
        name (None for speech and for a kind the config lacks), and the message names it. Guards one mapping, read
        from config.yaml, not from code."""
        from ai_models import config as ai_config

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.yaml"
            cfg.write_text("providers: {k: {kind: kokoro}}\nmodels: {speech: 'k:kokoro-v1.0'}\n")
            ai_config.use(cfg)
            try:
                self.assertEqual([storyboard.backend_model(b) for b in ("kokoro", "chatterbox", "speech")],
                                 ["k:kokoro-v1.0", None, None])
                self.assertIn("here kokoro is k:kokoro-v1.0", storyboard.backend_moved("kokoro"))
            finally:
                ai_config.use(None)

    def test_resolve_voice(self) -> None:
        """storyboard.resolve_voice fills a speaker's empty speed with 1.0, keeps an empty voice name null (the
        model's default) and gives the settings voice, whose null model is config.yaml's `speech` model, for no
        speaker. Guards the voice each part is checked against."""
        settings.use_project(None)
        data = storyboard.parse_markdown(SPEAKERS_MD)
        self.assertEqual(storyboard.resolve_voice(data, "guest"),
                         {"model": "oai:tts", "name": None, "speed": 1.0, "style": "warm, curious"})
        self.assertEqual(storyboard.resolve_voice(data),
                         {"model": None, "name": None, "speed": 1.0, "style": None})


class TestValidate(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        for d in ("images", "sources"):
            (self.project / d).mkdir()
        (self.project / "images" / "a.png").write_bytes(b"")
        (self.project / "sources" / "notes.md").write_text("")
        self.settings("author: [Jane Doe]\nlength: {min_seconds: 1}")

    def tearDown(self) -> None:
        settings.use_project(None)
        self._tmp.cleanup()

    def settings(self, text: str) -> None:
        (self.project / "settings.yaml").write_text(text)
        settings.use_project(self.project)

    def check(self, md: str = MD) -> storyboard.Validation:
        (self.project / "storyboard.md").write_text(md)
        return storyboard.validate(storyboard.load(self.project), self.project)

    def test_clean(self) -> None:
        """storyboard.validate of a complete storyboard, with and without speakers, gives no errors or warnings.
        Guards against false findings."""
        r = self.check()
        self.assertEqual((r.errors, r.warnings), ([], []))
        r = self.check(SPEAKERS_MD.replace("Brief: Two faces.\n", "Brief: Two faces.\n"
                                           '<a href="images/a.png"><img src="images/a.png" width="30%"></a>\n'))
        self.assertEqual((r.errors, r.warnings), ([], []))

    def test_errors(self) -> None:
        """storyboard.validate reports a missing image or source, invalid voice, music, critic and speaker
        settings, an obsolete `voice.backend` and a model that is not a model id. Guards the checks the parser cannot do, before any voice
        or render."""
        for settings_text, md, fragment in [
            ("", MD.replace("Image: a.png", "Image: b.png"), "image 'b.png' not found"),
            ("", MD.replace("notes.md", "other.md"), "sources/other.md does not exist"),
            ("voice: {backend: kokoro}", MD, "`voice.backend` is no longer read"),
            ("voice: {model: elevenlabs}", MD, "`voice.model` must be a speech model id"),
            ("voice: {speed: 3}", MD, "`voice.speed` must be"),
            ("music: {prompt: piano}", MD, "`music.prompt` is no longer read"),
            ("music: {file: m.mp3}", MD, "'m.mp3' does not exist"),
            ("voice: {speaker_gap: -1}", MD, "`voice.speaker_gap` must be"),
            ("critic: {claude: yes please}", MD, "`critic.claude` must be"),
            ("critic: {model: 4}", MD, "`critic.model` must be"),
            ("critic: {rounds: 0}", MD, "`critic.rounds` must be"),
            ("critic: {rounds: 1.5}", MD, "`critic.rounds` must be"),
            ("critic: {max_findings: -2}", MD, "`critic.max_findings` must be"),
            ("critic: {max_findings: true}", MD, "`critic.max_findings` must be"),
            ("", SPEAKERS_MD.replace("| oai:tts |", "| elevenlabs |"), "speaker 'guest': model must be"),
            ("", SPEAKERS_MD.replace("| 1.1 |", "| 9 |"), "speaker 'host': speed must be"),
        ]:
            with self.subTest(fragment=fragment):
                self.settings(f"author: [Jane Doe]\nlength: {{min_seconds: 1}}\n{settings_text}")
                self.assertTrue(any(fragment in e for e in self.check(md).errors), self.check(md).errors)

    def test_warnings(self) -> None:
        """storyboard.validate warns about title and end templates out of position, too many card rows, a
        missing or wrong image preview, a missing author and the estimated length, without making them errors.
        Guards the warning rules."""
        swapped = MD.replace("Template: title", "Template: x").replace("Template: end", "Template: title") \
            .replace("Template: x", "Template: end")
        rows = MD.replace("| Check them |", "| Check them |\n| Two. | 2 |\n| Three. | 3 |")
        for md, fragment in [
            (swapped, "usually the first scene"), (swapped, "usually the last scene"),
            (rows, "at most 2 rows"),
            (MD.replace('<a href="images/a.png"><img src="images/a.png" width="30%"></a>\n', ""), "no image preview"),
            (MD.replace('src="images/a.png"', 'src="images/b.png"'), "is not the scene's image"),
        ]:
            with self.subTest(fragment=fragment):
                r = self.check(md)
                self.assertTrue(r.ok, r.errors)
                self.assertTrue(any(fragment in w for w in r.warnings), r.warnings)
        self.settings("")
        self.assertTrue(any("author" in w for w in self.check().warnings))
        self.assertTrue(any("estimated length" in w for w in self.check().warnings))

    def test_clean_without_image(self) -> None:
        """storyboard.validate gives no error or preview warning for an HTML scene with a Brief and no Image.
        Guards scenes drawn in the page with no picture."""
        md = MD.replace("Image: a.png\n", "").replace(
            '<a href="images/a.png"><img src="images/a.png" width="30%"></a>\n', "")
        r = self.check(md)
        self.assertEqual(r.errors, [])
        self.assertFalse(any("injection" in w for w in r.warnings), r.warnings)

    def test_author_reaches_template_scenes_only(self) -> None:
        """storyboard.load adds the normalised author names to template scenes only, none without `author:`.
        Guards the byline on cards."""
        self.settings("author: [Alice  Smith, Bob Jones]")
        self.check()
        title, injection, _ = storyboard.load(self.project)["scenes"]
        self.assertEqual(title["author"], "Alice Smith, Bob Jones")
        self.assertNotIn("author", injection)
        self.settings("")
        self.assertNotIn("author", storyboard.load(self.project)["scenes"][0])

    def test_init_storyboard(self) -> None:
        """storyboard.template with one image gives a storyboard that validates with no preview warning. Guards
        init's starting storyboard."""
        r = self.check(storyboard.template("Demo", ["a.png"]))
        self.assertEqual(r.errors, [])
        self.assertFalse(any("preview" in w for w in r.warnings))

    def test_init_storyboard_without_images(self) -> None:
        """storyboard.template without images leaves no placeholder or blank-line run and gives the title and
        end scenes. Guards init without --images."""
        text = storyboard.template("Demo", [])
        self.assertNotIn("__IMAGE_SCENES__", text)
        self.assertNotIn("\n\n\n", text)
        r = self.check(text)
        self.assertEqual(r.errors, [])
        self.assertEqual([s["id"] for s in storyboard.load(self.project)["scenes"]], ["title", "end"])


if __name__ == "__main__":
    unittest.main()
