"""Integration: a scene with two speakers through `script`, the voiceover skill, `voice`, `scaffold`, `render` and
`assemble`, each step a function call in process (`narration`, `voiceover_tool`, `dispatch`, `mix`) under TEST_CONFIG,
with the node directory and Manim environment of the wrapper (`wrapper_env`).

The speech model is `tasks.speech` of tests/config.yaml, a Kokoro model; the narrator speaks its default voice and the
speaker `guest` its voice `bm_george`. The model is loaded once, in the class setup; the autouse `_unload_local_models`
fixture drops it after the first test.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from short_video_tool import config, dispatch, media, mix, narration, projects, scenes, settings, storyboard
from tests.integration.short_video.fast_render import FPS, set_fps
from tests.integration.short_video.wrapper_env import ENV_DIR, NODE_DIR
from tests.prereq import requires
from tests.settings_env import TEST_CONFIG, model_entry, use_settings
from voiceover_tool.cli import synth
from voiceover_tool.script import read_script

# The default voice of the speech model.
VOICE = model_entry("speech")["voice"]

STORYBOARD = """\
# Two voices

Topic: A host and a guest.

| Speaker | Model | Voice | Speed | Style |
|---|---|---|---|---|
| guest | | bm_george | | |

## talk
Image: a.png
Brief: The image holds still.

<a href="images/a.png"><img src="images/a.png" width="30%"></a>

| Speaker | Narration | On screen |
|---|---|---|
| | Welcome. | hold |
| guest | Thank you. | hold |
| guest | Glad to be here. | hold |
| | Let us begin. | hold |
"""


def _synth(part: narration.ScriptPart) -> None:
    """Voice `part` with the voiceover skill's command function (`voiceover_tool.cli.synth`) as
    `voiceover.sh synth --script <part> --out-dir <its folder>` does, adding `--model`, `--voice` and `--speed` from
    the part's voice when `script` prints a voice line for it."""
    voice = part.voice if part.voice_line is not None else {"model": None, "name": None, "speed": 1.0}
    synth(read_script(part.path), part.path.parent, model=voice["model"], voice=voice["name"],
          speed=float(voice["speed"]))


@requires(shutil.which("ffmpeg") is not None, "ffmpeg not installed")
@requires(scenes.node_ready(NODE_DIR, config.NODE_SRC), "HyperFrames node_modules missing; run short-video.sh setup")
class TestSpeakersVoice(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        (tmp / "imgs").mkdir()
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=640x360",
                        "-frames:v", "1", str(tmp / "imgs" / "a.png")], check=True, timeout=25)
        cls.project = p = tmp / "film"
        with use_settings(TEST_CONFIG):
            projects.create(p, images=tmp / "imgs")
            (p / "storyboard.md").write_text(STORYBOARD, encoding="utf-8")
            with (p / "settings.yaml").open("a", encoding="utf-8") as f:
                f.write("\nauthor: [Test Author]\n")
            set_fps(p)
            settings.use_project(p)
            try:
                data = storyboard.load(p)
                v = storyboard.validate(data, p)
                assert v.ok, v.errors
                cls.parts = narration.write_scripts(p, data)
                for part in cls.parts:
                    _synth(part)
                for s in narration.voice_targets(p, data):
                    narration.import_voice(p, data, s)
                dispatch.scaffold(p, data, "talk", NODE_DIR)
                dispatch.render(p, data, "talk", NODE_DIR, config.env_dirs(ENV_DIR).manim_env)
                mix.assemble(p, data)
            finally:
                settings.use_project(None)
        cls.voice_dir = p / "voice" / "talk" / "v1"
        cls.timing = json.loads((cls.voice_dir / "timing.json").read_text())

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_script_writes_parts_and_prints_guest_voice(self) -> None:
        """`narration.write_scripts` writes one part script per speaker run and gives the guest's part the voice line
        `script` prints under it. Guards the output the agent passes to voiceover.sh."""
        d = self.project / "sources" / "narration" / "talk"
        self.assertEqual((d / "p2" / "script.txt").read_text(), "Thank you.\nGlad to be here.\n")
        self.assertTrue((d / "p3" / "script.txt").is_file())
        self.assertIn("speaker=guest name=bm_george speed=1.0", [part.voice_line for part in self.parts])

    def test_joined_timing(self) -> None:
        """`narration.import_voice` joins the Kokoro parts into one timing.json with speakers, renumbered sentences in
        time order and a duration equal to the WAV's. Guards speakers.join on real voiceover output."""
        self.assertEqual([s["speaker"] for s in self.timing["sentences"]], [None, "guest", "guest", None])
        self.assertEqual([s["index"] for s in self.timing["sentences"]], [1, 2, 3, 4])
        starts = [s["start"] for s in self.timing["sentences"]]
        self.assertEqual(starts, sorted(starts))
        self.assertAlmostEqual(media.duration(self.voice_dir / "narration.wav"), self.timing["duration"], delta=0.002)

    def test_meta_records_both_voices(self) -> None:
        """`narration.import_voice` records each sentence's speaker and resolved voice in meta.json and each part's
        voice in timing.json. Guards the voice record of a two-voice scene."""
        meta = json.loads((self.voice_dir / "meta.json").read_text())
        self.assertEqual([(s["speaker"], s["voice"]["name"]) for s in meta["speakers"]],
                         [(None, VOICE), ("guest", "bm_george"), ("guest", "bm_george"), (None, VOICE)])
        self.assertEqual([v["voice"] for v in self.timing["speakers"]], [VOICE, "bm_george", VOICE])

    def test_scene_length_is_narration_length(self) -> None:
        """`dispatch.render` of the joined two-voice narration gives a scene as long as the narration. Guards the
        joined timing driving the scene length."""
        scene = self.project / "scenes" / "talk" / "v1" / "scene.mp4"
        self.assertAlmostEqual(media.duration(scene), self.timing["duration"], delta=1 / FPS)

    def test_film_assembled(self) -> None:
        """`mix.assemble` of the two-voice scene gives a film as long as the narration. Guards the whole two-speaker
        pipeline from storyboard to film."""
        film = self.project / "film" / "v1" / "film.mp4"
        self.assertAlmostEqual(media.duration(film), self.timing["duration"], delta=2 / FPS)


if __name__ == "__main__":
    unittest.main()
