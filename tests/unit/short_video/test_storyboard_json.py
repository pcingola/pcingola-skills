"""short_video_tool: storyboard.json as the storyboard source, per-sentence voice
settings, and the `storyboard`, `status` and `init --json` commands."""
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from short_video_tool import cli, narration, scenes, settings, state, status, storyboard, versions

DATA = {
    "title": "Interview", "topic": "Two people talk.",
    "speakers": {"host": {"model": "kokoro:kokoro-v1.0", "name": "bm_george", "speed": 1.1, "style": None}},
    "scenes": [
        {"id": "title", "template": "title", "narration": ["Welcome."], "beats": ["Interview"]},
        {"id": "talk", "image": "a.png", "brief": "Two faces.", "narration": ["Hello.", "Hi.", "Bye."],
         "beats": ["host", "guest", "both"], "speakers": ["host", None, None],
         "voices": [None, {"model": "oai:tts", "style": "calm"}, None]},
    ],
}

VOICES_MD = """\
# Interview

Topic: Two people talk.

| Speaker | Model | Voice | Speed | Style |
|---|---|---|---|---|
| host | kokoro:kokoro-v1.0 | bm_george | 1.1 | |

## talk
Image: a.png
Brief: Two faces.

| Speaker | Narration | On screen | Style | Model |
|---|---|---|---|---|
| host | Hello. | host | | |
| | Hi. | guest | calm | oai:tts |
| | Bye. | both | | |
"""


def _json_error(data) -> str:
    with unittest.TestCase().assertRaises(storyboard.StoryboardError) as cm:
        storyboard.parse_json(json.dumps(data))
    return str(cm.exception)


class TestJson(unittest.TestCase):

    def setUp(self) -> None:
        settings.use_project(None)

    def test_parse(self) -> None:
        """storyboard.parse_json returns the storyboard dict as stored, with whitespace in strings collapsed.
        Guards storyboard.json having the structure parse_markdown returns."""
        data = copy.deepcopy(DATA)
        data["scenes"][1]["brief"] = "Two\n  faces."
        self.assertEqual(storyboard.parse_json(json.dumps(data)), DATA)

    def test_markdown_voice_columns_same_dict(self) -> None:
        """storyboard.parse_markdown reads Model, Voice, Speed and Style columns after On screen, in any order,
        into `voices` (empty cells unset, a row with none null), the same dict as the JSON form without the title
        scene. Guards one structure for both files."""
        want = copy.deepcopy(DATA)
        del want["scenes"][0]
        self.assertEqual(storyboard.parse_markdown(VOICES_MD), want)

    def test_markdown_voice_column_errors(self) -> None:
        """storyboard.parse_markdown refuses an unknown or repeated column and a non-numeric Speed cell, each
        with its line. Guards the voice columns' syntax."""
        cases = [
            ("| Narration | On screen | Style", "| Narration | Screen | Style", 13, "the table header must be"),
        ]
        for old, new, line, fragment in cases:
            with self.subTest(new=new):
                with self.assertRaises(storyboard.StoryboardError) as cm:
                    storyboard.parse_markdown(VOICES_MD.replace(old, new))
                self.assertIn(f"storyboard.md line {line}: {fragment}", str(cm.exception))
        text = VOICES_MD.replace("| Style | Model |", "| Style | Speed |").replace("| calm | oai:tts |",
                                                                                    "| calm | fast |")
        with self.assertRaises(storyboard.StoryboardError) as cm:
            storyboard.parse_markdown(text)
        self.assertIn("storyboard.md line 16: scene 'talk' sentence 2: Speed 'fast' is not a number",
                      str(cm.exception))

    def test_model_override_takes_its_default_voice(self) -> None:
        """storyboard.resolve_voice gives a sentence whose own Model differs from its speaker's the new
        model's default voice, keeps the speaker's voice when the model is the same, and uses an own Voice
        when given. Guards a voice name of one model sent to another."""
        data = {"speakers": {"guest": {"model": "kokoro:kokoro-v1.0", "name": "am_adam", "speed": None, "style": None}}}
        self.assertIsNone(storyboard.resolve_voice(data, "guest", {"model": "oai:tts"})["name"])
        self.assertEqual(storyboard.resolve_voice(data, "guest", {"model": "kokoro:kokoro-v1.0"})["name"], "am_adam")
        self.assertEqual(storyboard.resolve_voice(data, "guest", {"model": "oai:tts", "name": "Puck"})["name"],
                         "Puck")

    def test_silent_clip_scene_without_lists(self) -> None:
        """storyboard.parse_json accepts a clip scene without `narration` and `beats` and reads it as silent;
        another scene without `narration` is refused once, naming the key. Guards the JSON form of a clip scene
        with no table."""
        data = copy.deepcopy(DATA)
        data["scenes"].append({"id": "morph", "engine": "clip"})
        scene = storyboard.parse_json(json.dumps(data))["scenes"][-1]
        self.assertEqual((scene["narration"], scene["beats"]), ([], []))
        del data["scenes"][1]["narration"]
        self.assertEqual(_json_error(data), "storyboard.json: scene 'talk': missing sentences in `narration` "
                                            "(only a scene with `engine` clip may have none)")

    def test_markdown_bad_header_one_error(self) -> None:
        """storyboard.parse_markdown reports a repeated or unknown voice column once, naming it, with no errors
        for the rest of that table. Guards a cascade of row errors from one header mistake."""
        for new, fragment in [("| Speed | Voice | Speed |", "table column 'Speed' given twice"),
                              ("| Style | Tone |", "unknown table column 'Tone'")]:
            with self.subTest(new=new):
                text = VOICES_MD.replace("| Style | Model |", new)
                with self.assertRaises(storyboard.StoryboardError) as cm:
                    storyboard.parse_markdown(text)
                self.assertEqual(str(cm.exception), f"storyboard.md line 13: {fragment}" + (
                    "; after On screen only Model, Voice, Speed, Style" if "unknown" in fragment else ""))

    def test_errors_name_scene_and_field(self) -> None:
        """storyboard.parse_json reports bad JSON with its line, and each structural problem naming the scene
        and field: unknown and moved keys, missing title, a template with a brief, an unknown engine, a missing
        brief, an empty image, list lengths, an undefined speaker, a bad voice field and wrong types. Guards the shared check on
        storyboard.json."""
        def changed(fn):
            d = copy.deepcopy(DATA)
            fn(d)
            return d

        cases = [
            (changed(lambda d: d.update(author="Jane")), "unknown key `author`; it is set in the project's "
                                                         "settings.yaml (`author:`)"),
            (changed(lambda d: d.pop("title")), "missing `title`"),
            (changed(lambda d: d.update(title=1)), "`title` must be a string"),
            (changed(lambda d: d["scenes"][0].update(brief="x")), "scene 'title': a template scene takes no `brief`"),
            (changed(lambda d: d["scenes"][1].update(engine="film")), "scene 'talk': `engine` must be one of"),
            (changed(lambda d: d["scenes"][1].pop("brief")), "scene 'talk': missing `brief`"),
            (changed(lambda d: d["scenes"][1].update(image="")), "scene 'talk': `image` is empty"),
            (changed(lambda d: d["scenes"][1]["beats"].pop()), "scene 'talk': `beats` must be a list of 3"),
            (changed(lambda d: d["scenes"][1]["voices"].pop()), "scene 'talk': `voices` must be a list of 3"),
            (changed(lambda d: d["scenes"][1]["speakers"].__setitem__(1, "guest")),
             "scene 'talk' sentence 2: speaker 'guest' is not defined; add it to `speakers` or use null"),
            (changed(lambda d: d["scenes"][1]["voices"].__setitem__(0, {"tone": "x"})),
             "scene 'talk' sentence 1: unknown key `tone`"),
            (changed(lambda d: d["scenes"][1]["voices"].__setitem__(0, {"speed": "fast"})),
             "scene 'talk' sentence 1: `speed` must be a number or null"),
            (changed(lambda d: d["scenes"][1].update(narration="Hello.")), "scene 'talk': `narration` must "
                                                                          "be a list"),
            (changed(lambda d: d["scenes"][0].update(id="Title")), "invalid scene id 'Title'"),
            (changed(lambda d: d["scenes"][1].update(id="title")), "duplicate scene id 'title'"),
            (changed(lambda d: d["scenes"][1].update(narration=[], beats=[], speakers=[], voices=[])),
             "scene 'talk': missing sentences in `narration` (only a scene with `engine` clip may have none)"),
        ]
        for data, fragment in cases:
            with self.subTest(fragment=fragment):
                msg = _json_error(data)
                self.assertTrue(any(m.startswith("storyboard.json: ") and fragment in m for m in msg.splitlines()),
                                msg)
        with self.assertRaises(storyboard.StoryboardError) as cm:
            storyboard.parse_json('{"title": "T",\n "topic": }')
        self.assertIn("storyboard.json line 2: not valid JSON", str(cm.exception))


class Project(unittest.TestCase):
    """A project folder with settings, images/a.png and `settings.use_project`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / "images").mkdir()
        (self.project / "images" / "a.png").write_bytes(b"png")
        (self.project / "settings.yaml").write_text("author: [Jane Doe]\nlength: {min_seconds: 1}\n")
        settings.use_project(self.project)

    def tearDown(self) -> None:
        settings.use_project(None)
        self._tmp.cleanup()

    def write(self, data: dict = DATA) -> None:
        (self.project / storyboard.JSON_FILE).write_text(json.dumps(data))

    def run_cli(self, argv: list[str]) -> tuple[str, str]:
        out, err = io.StringIO(), io.StringIO()
        args = cli._build_parser().parse_args(argv)
        with redirect_stdout(out), redirect_stderr(err):
            try:
                args.func(args)
            except SystemExit:
                pass
        return out.getvalue(), err.getvalue()


class TestLoad(Project):

    def test_load_json_and_refuse_both(self) -> None:
        """storyboard.load reads storyboard.json with the author added to template scenes, refuses a project
        with both files naming both, and names storyboard.md when there is neither. Guards which file a
        command reads."""
        with self.assertRaisesRegex(storyboard.StoryboardError, "storyboard.md not found"):
            storyboard.load(self.project)
        self.write()
        self.assertEqual(storyboard.load(self.project)["scenes"][0]["author"], "Jane Doe")
        self.assertNotIn("author", storyboard.read(self.project)["scenes"][0])
        (self.project / storyboard.MD_FILE).write_text(VOICES_MD)
        with self.assertRaisesRegex(storyboard.StoryboardError, "both storyboard.md and storyboard.json"):
            storyboard.load(self.project)

    def test_validate_json_voices_and_no_preview_warning(self) -> None:
        """storyboard.validate checks each sentence's resolved voice with the `voice:` rules and gives no image
        preview warning for storyboard.json. Guards a sentence model that is not a model id."""
        self.write()
        r = storyboard.validate(storyboard.load(self.project), self.project)
        self.assertEqual((r.errors, r.warnings), ([], []))
        bad = copy.deepcopy(DATA)
        bad["scenes"][1]["voices"][1] = {"model": "kokoro", "style": "calm"}
        self.write(bad)
        r = storyboard.validate(storyboard.load(self.project), self.project)
        self.assertTrue(any(e.startswith("scene talk sentence 2: model must be") for e in r.errors), r.errors)

    def test_storyboard_command(self) -> None:
        """cli storyboard prints the storyboard.md of a project as storyboard.json stores it, without the
        author, and that output reads back as the same dict. Guards the JSON view of a Markdown project."""
        (self.project / storyboard.MD_FILE).write_text(VOICES_MD)
        out, err = self.run_cli(["storyboard", "-p", str(self.project)])
        self.assertEqual(err, "")
        self.assertEqual(json.loads(out), storyboard.parse_markdown(VOICES_MD))
        self.assertEqual(storyboard.parse_json(out), json.loads(out))

    def test_init_json(self) -> None:
        """cli init --json writes storyboard.json (the starting storyboard.md as a dict, no previews) and no
        storyboard.md, and it validates. Guards a project started from the page."""
        with tempfile.TemporaryDirectory() as tmp:
            images = Path(tmp) / "pngs"
            images.mkdir()
            (images / "a.png").write_bytes(b"png")
            project = Path(tmp) / "film"
            out, err = self.run_cli(["init", str(project), "--json", "--images", str(images)])
            self.assertIn("storyboard.json", out, err)
            self.assertFalse((project / storyboard.MD_FILE).exists())
            data = storyboard.read(project)
            self.assertEqual([s["id"] for s in data["scenes"]], ["title", "scene_1", "end"])
            self.assertFalse(any("preview" in s for s in data["scenes"]))
            settings.use_project(project)
            self.assertEqual(storyboard.validate(storyboard.load(project), project).errors, [])

    def test_script_writes_part_per_voice(self) -> None:
        """cli script writes one part per run of resolved voice and prints each part's voice unless it is the
        film's. Guards a sentence with its own settings being voiced on its own."""
        self.write()
        out, _ = self.run_cli(["script", "-p", str(self.project), "--scene", "talk"])
        d = narration.script_dir(self.project, "talk")
        self.assertEqual([(d / f"p{k}" / "script.txt").read_text() for k in (1, 2, 3)],
                         ["Hello.\n", "Hi.\n", "Bye.\n"])
        self.assertIn("speaker=host model=kokoro:kokoro-v1.0 name=bm_george speed=1.1", out)
        self.assertIn("model=oai:tts speed=1.0 style=calm", out)
        self.assertEqual(out.count("model="), 2)


def _timing(texts: list[str], voice: dict | None = None) -> dict:
    v = voice or {"model": "kokoro:kokoro-v1.0", "voice": "af_heart", "speed": 1.0}
    sentences = [{"index": i, "text": t, "start": i - 1.0, "end": i - 0.5, "words": []}
                 for i, t in enumerate(texts, 1)]
    return {"audio": "narration.wav", "sample_rate": 24000, "duration": float(len(texts)), **v,
            "sentences": sentences}


def _voice_version(project: Path, sid: str, timing: dict) -> Path:
    vdir = versions.next_version(state.voice_root(project, sid))
    (vdir / "timing.json").write_text(json.dumps(timing))
    state.write_meta(vdir, {"scene": sid, "duration": timing["duration"]})
    return vdir


def _render(project: Path, scene: dict, vdir: Path) -> Path:
    """A rendered scene version as scaffold and render leave it."""
    sdir = versions.next_version(state.scene_root(project, scene["id"]))
    timing = json.loads((vdir / "timing.json").read_text())
    (sdir / "timing.json").write_text(json.dumps(timing))
    (sdir / "voice_version").write_text(vdir.name + "\n")
    (sdir / "brief.md").write_text(scenes.brief_markdown(scene, timing, vdir.name))
    if scene.get("template"):
        (sdir / scenes.CARD_JS).write_text(scenes.card_js(scene))
    if scene.get("image"):
        (sdir / scenes.BACKGROUND).write_bytes(storyboard.image_path(project, scene["image"]).read_bytes())
    state.write_meta(sdir, {"scene": scene["id"], "voice_version": vdir.name})
    return sdir


PLAIN = {"title": "T", "topic": "x.", "scenes": [
    {"id": "title", "template": "title", "narration": ["Welcome."], "beats": ["T"]},
    {"id": "a", "image": "a.png", "brief": "Hold.", "narration": ["One.", "Two."], "beats": ["1", "2"]},
]}


class TestStatus(Project):

    def setUp(self) -> None:
        super().setUp()
        self.write(PLAIN)

    def entry(self, sid: str) -> dict:
        report = status.report(self.project, storyboard.load(self.project))
        return next(s for s in report["scenes"] if s["id"] == sid)

    def done(self) -> None:
        data = storyboard.load(self.project)
        for s in data["scenes"]:
            _render(self.project, s, _voice_version(self.project, s["id"], _timing(s["narration"])))

    def test_nothing_made(self) -> None:
        """status of a new project: every scene needs a voice and a render, with no versions. Guards the
        report's starting state."""
        self.assertEqual(self.entry("a"), {
            "id": "a", "narrated": True, "voice_version": None, "needs_voice": True,
            "voice_reasons": ["no voice version"], "scene_version": None, "needs_render": True,
            "render_reasons": ["no rendered version"]})

    def test_up_to_date(self) -> None:
        """status after every scene is voiced and rendered from the current storyboard needs nothing. Guards
        against false reasons, through the command's JSON output."""
        self.done()
        out, err = self.run_cli(["status", "-p", str(self.project)])
        for s in json.loads(out)["scenes"]:
            self.assertEqual((s["needs_voice"], s["voice_reasons"], s["needs_render"], s["render_reasons"]),
                             (False, [], False, []), s)
        self.assertEqual(self.entry("a")["voice_version"], "v1")
        self.assertEqual(self.entry("a")["scene_version"], "v1")

    def test_changes_make_scenes_stale(self) -> None:
        """status names what changed: a sentence, a sentence's voice settings, the brief, the On screen text,
        the image and a newer voice version. Guards each input the report compares."""
        self.done()
        cases = [
            (lambda d: d["scenes"][1]["narration"].__setitem__(1, "Three."), "voice", "sentence 2: voiced"),
            (lambda d: d["scenes"][1].update(voices=[None, {"speed": 1.2}]), "voice",
             "scene a sentence 2: voiced with speed 1.0, the storyboard gives 1.2"),
            (lambda d: d["scenes"][1].update(brief="Zoom."), "render", "brief.md differs"),
            (lambda d: d["scenes"][1]["beats"].__setitem__(0, "one"), "render", "brief.md differs"),
            (lambda d: d["scenes"][0]["beats"].__setitem__(0, "U"), "render", "card.js differs"),
        ]
        for change, kind, fragment in cases:
            with self.subTest(fragment=fragment):
                data = copy.deepcopy(PLAIN)
                change(data)
                self.write(data)
                sid = "title" if fragment.startswith("card") else "a"
                e = self.entry(sid)
                self.assertTrue(e[f"needs_{kind}"], e)
                self.assertTrue(any(fragment in r for r in e[f"{kind}_reasons"]), e)
        self.write(PLAIN)
        (self.project / "images" / "a.png").write_bytes(b"other")
        self.assertIn("the image a.png differs from the one rendered", self.entry("a")["render_reasons"])
        (self.project / "images" / "a.png").write_bytes(b"png")
        _voice_version(self.project, "a", _timing(["One.", "Two."]))
        self.assertEqual(self.entry("a")["render_reasons"],
                         ["rendered with voice v1, the latest voice version is v2"])
        versions.next_version(state.scene_root(self.project, "a"))
        self.assertIn("version v2 is scaffolded and not rendered", self.entry("a")["render_reasons"])

    def test_voice_change_in_settings(self) -> None:
        """status marks a recording made in another voice than the film's `voice:` as needing a new voice.
        Guards the resolved-voice comparison for scenes without speakers."""
        self.done()
        (self.project / "settings.yaml").write_text("author: [Jane Doe]\nvoice: {model: \"oai:tts\"}\n")
        settings.use_project(self.project)
        self.assertTrue(any("voiced with model 'kokoro:kokoro-v1.0', the storyboard gives 'oai:tts'" in r
                            for r in self.entry("a")["voice_reasons"]))


if __name__ == "__main__":
    unittest.main()
