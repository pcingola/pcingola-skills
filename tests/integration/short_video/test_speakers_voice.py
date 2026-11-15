"""Integration: a scene with two speakers through `script`, the voiceover
skill, `voice`, `scaffold`, `render` and `assemble`, all run through the
wrappers as the agent runs them.

The speech model is `models.speech` of the user's config.yaml, a Kokoro model
whose default voice is `af_heart` (`voice:` in settings); the speaker `guest`
is its voice `bm_george`. Fails until that config and HyperFrames are in
place.
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from short_video_tool import config, media, scenes
from tests.prereq import requires
from tests.integration.short_video.wrapper_env import NODE_DIR

SKILLS = Path(__file__).resolve().parents[3] / "plugins" / "media" / "skills"
SHORT_VIDEO = SKILLS / "short-video" / "scripts" / "short-video.sh"
VOICEOVER = SKILLS / "voiceover" / "scripts" / "voiceover.sh"
FPS = 30

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
| | Welcome to the show. | hold |
| guest | Thank you for having me. | hold |
| guest | It is good to be here. | hold |
| | Let us begin. | hold |
"""


def _kokoro_speech() -> bool:
    """Whether the user's config.yaml has a Kokoro `speech` model with the default voice `af_heart` and an align
    model."""
    from ai_models import AIModelsError, speech
    from ai_models import config as ai_config

    try:
        m = speech.model_of()
        return m.kind == "kokoro" and m.default_voice == "af_heart" and bool(ai_config.model_for("align"))
    except AIModelsError:
        return False


def _run(*args: str) -> str:
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise AssertionError(f"{' '.join(map(str, args))} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r.stdout


@requires(shutil.which("ffmpeg") is not None, "ffmpeg not installed")
@requires(_kokoro_speech(), "config.yaml has no Kokoro speech model with voice af_heart and no align model")
@requires(scenes.node_ready(NODE_DIR, config.NODE_SRC), "HyperFrames node_modules missing; run short-video.sh setup")
class TestSpeakersVoice(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        (tmp / "imgs").mkdir()
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=640x360",
                        "-frames:v", "1", str(tmp / "imgs" / "a.png")], check=True)
        cls.project = p = tmp / "film"
        _run(SHORT_VIDEO, "init", p, "--images", tmp / "imgs")
        (p / "storyboard.md").write_text(STORYBOARD, encoding="utf-8")
        with (p / "settings.yaml").open("a", encoding="utf-8") as f:
            f.write("\nauthor: [Test Author]\n")
        _run(SHORT_VIDEO, "validate", "-p", p)

        cls.script_out = _run(SHORT_VIDEO, "script", "-p", p)
        lines = cls.script_out.splitlines()
        for i, line in enumerate(lines):
            if not line.endswith("script.txt"):
                continue
            extra: list[str] = []
            if i + 1 < len(lines) and lines[i + 1].startswith("  speaker="):
                m = re.search(r"(?:model=(\S+) )?name=(\S+) speed=(\S+)", lines[i + 1])
                extra = (["--model", m.group(1)] if m.group(1) else []) + ["--voice", m.group(2), "--speed", m.group(3)]
            script = Path(line)
            _run(VOICEOVER, "synth", "--script", script, "--out-dir", script.parent, *extra)

        _run(SHORT_VIDEO, "voice", "-p", p)
        _run(SHORT_VIDEO, "scaffold", "-p", p, "--scene", "talk")
        _run(SHORT_VIDEO, "render", "-p", p, "--scene", "talk")
        _run(SHORT_VIDEO, "assemble", "-p", p)
        cls.voice_dir = p / "voice" / "talk" / "v1"
        cls.timing = json.loads((cls.voice_dir / "timing.json").read_text())

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_script_writes_parts_and_prints_guest_voice(self) -> None:
        """short-video.sh script writes one part script per speaker run and prints the guest's voice arguments
        under its script. Guards the output the agent passes to voiceover.sh."""
        d = self.project / "sources" / "narration" / "talk"
        self.assertEqual((d / "p2" / "script.txt").read_text(), "Thank you for having me.\nIt is good to be here.\n")
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
                         [(None, "af_heart"), ("guest", "bm_george"), ("guest", "bm_george"), (None, "af_heart")])
        self.assertEqual([v["voice"] for v in self.timing["speakers"]], ["af_heart", "bm_george", "af_heart"])

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
