"""Integration: a scene with two speakers through `script`, the voiceover
skill, `voice`, `scaffold`, `render` and `assemble`, each CLI run as
`python -m` in a child process of the root `dev` environment (the working
tree's lib/), with the user's settings file hidden, TEST_CONFIG in
SKILLS_CONFIG and the wrapper's PLUGIN_ENV_DIR (HyperFrames).

The speech model is `tasks.speech` of tests/config.yaml, a Kokoro model; the
narrator speaks its default voice and the speaker `guest` its voice
`bm_george`.
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from short_video_tool import config, media, scenes
from tests.integration.short_video.fast_render import FPS, set_fps
from tests.integration.short_video.wrapper_env import ENV_DIR, NODE_DIR
from tests.prereq import requires
from tests.settings_env import TEST_CONFIG, model_entry
from tests.subproc import child_env, run_module

# The CLIs' environment: no user settings file, the tiny models of tests/config.yaml, the wrapper's environment
# directory for HyperFrames.
ENV = child_env(SKILLS_CONFIG=str(TEST_CONFIG), PLUGIN_ENV_DIR=str(ENV_DIR))
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


def _run(module: str, *args: str | Path) -> str:
    """The stdout of `python -m <module> <args>` in ENV; fails with its output when it exits non-zero."""
    r = run_module(module, [str(a) for a in args], ENV)
    if r.returncode != 0:
        raise AssertionError(f"{module} {' '.join(map(str, args))} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r.stdout


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
        _run("short_video_tool", "init", p, "--images", tmp / "imgs")
        (p / "storyboard.md").write_text(STORYBOARD, encoding="utf-8")
        with (p / "settings.yaml").open("a", encoding="utf-8") as f:
            f.write("\nauthor: [Test Author]\n")
        set_fps(p)
        _run("short_video_tool", "validate", "-p", p)

        cls.script_out = _run("short_video_tool", "script", "-p", p)
        lines = cls.script_out.splitlines()
        for i, line in enumerate(lines):
            if not line.endswith("script.txt"):
                continue
            extra: list[str] = []
            if i + 1 < len(lines) and lines[i + 1].startswith("  speaker="):
                m = re.search(r"(?:model=(\S+) )?name=(\S+) speed=(\S+)", lines[i + 1])
                extra = (["--model", m.group(1)] if m.group(1) else []) + ["--voice", m.group(2), "--speed", m.group(3)]
            script = Path(line)
            _run("voiceover_tool", "synth", "--script", script, "--out-dir", script.parent, *extra)

        _run("short_video_tool", "voice", "-p", p)
        _run("short_video_tool", "scaffold", "-p", p, "--scene", "talk")
        _run("short_video_tool", "render", "-p", p, "--scene", "talk")
        _run("short_video_tool", "assemble", "-p", p)
        cls.voice_dir = p / "voice" / "talk" / "v1"
        cls.timing = json.loads((cls.voice_dir / "timing.json").read_text())

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_script_writes_parts_and_prints_guest_voice(self) -> None:
        """short-video.sh script writes one part script per speaker run and prints the guest's voice arguments
        under its script. Guards the output the agent passes to voiceover.sh."""
        d = self.project / "sources" / "narration" / "talk"
        self.assertEqual((d / "p2" / "script.txt").read_text(), "Thank you.\nGlad to be here.\n")
        self.assertTrue((d / "p3" / "script.txt").is_file())
        self.assertIn("  speaker=guest name=bm_george speed=1.0", self.script_out.splitlines())

    def test_joined_timing(self) -> None:
        """short-video.sh voice joins the Kokoro parts into one timing.json with speakers, renumbered sentences
        in time order and a duration equal to the WAV's. Guards speakers.join on real voiceover output."""
        self.assertEqual([s["speaker"] for s in self.timing["sentences"]], [None, "guest", "guest", None])
        self.assertEqual([s["index"] for s in self.timing["sentences"]], [1, 2, 3, 4])
        starts = [s["start"] for s in self.timing["sentences"]]
        self.assertEqual(starts, sorted(starts))
        self.assertAlmostEqual(media.duration(self.voice_dir / "narration.wav"), self.timing["duration"], delta=0.002)

    def test_meta_records_both_voices(self) -> None:
        """short-video.sh voice records each sentence's speaker and resolved voice in meta.json and each part's
        voice in timing.json. Guards the voice record of a two-voice scene."""
        meta = json.loads((self.voice_dir / "meta.json").read_text())
        self.assertEqual([(s["speaker"], s["voice"]["name"]) for s in meta["speakers"]],
                         [(None, VOICE), ("guest", "bm_george"), ("guest", "bm_george"), (None, VOICE)])
        self.assertEqual([v["voice"] for v in self.timing["speakers"]], [VOICE, "bm_george", VOICE])

    def test_scene_length_is_narration_length(self) -> None:
        """short-video.sh render of the joined two-voice narration gives a scene as long as the narration.
        Guards the joined timing driving the scene length."""
        scene = self.project / "scenes" / "talk" / "v1" / "scene.mp4"
        self.assertAlmostEqual(media.duration(scene), self.timing["duration"], delta=1 / FPS)

    def test_film_assembled(self) -> None:
        """short-video.sh assemble of the two-voice scene gives a film as long as the narration. Guards the
        whole two-speaker pipeline through the wrappers."""
        film = self.project / "film" / "v1" / "film.mp4"
        self.assertAlmostEqual(media.duration(film), self.timing["duration"], delta=2 / FPS)


if __name__ == "__main__":
    unittest.main()
