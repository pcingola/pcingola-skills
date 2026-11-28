"""`model_client.client` (`model-client`, docs/model_server.md, Command-line client): its core functions in process
against the real server of tests/config.yaml (`serve`) on a free port, with the tiny models: the model list with and
without the test models, one model's entry, a video job, an image, speech, the default output name, the refusal to
overwrite and a failed video job's error."""

import io
from datetime import datetime

import pytest
import torch
from PIL import Image

from model_client import client as cli
from tests.integration.model_server.conftest import serve
from tests.media import clip, png
from tests.prereq import requires
from tests.settings_env import TEST_CONFIG, model_entry, task_model
from tests.wav import read

NEEDS_GPU = requires(torch.cuda.is_available() or torch.backends.mps.is_available(),
                     f"local diffusers models need a CUDA or MPS GPU; torch {torch.__version__} sees neither")


@pytest.fixture(scope="module")
def server():
    """An `openai` client of the server of TEST_CONFIG made by `cli.connect` from the server's `/v1` URL."""
    with serve(TEST_CONFIG) as running:
        c = cli.connect(f"{running.url}/v1", timeout=25.0)
        yield c
        c.close()


def test_models_hides_test_models_and_groups_by_role(server):
    """`models` hides the test models (every local model of tests/config.yaml) and lists them with `tests`, each
    with its role and runtime, grouped in `ROLES` order; `model_lines` prints `server: <name>`, then one aligned
    line per model. `model` of the video model gives its kind, role, test marker and the entry's keys of
    tests/config.yaml."""
    local = {task_model(t) for t in ("image", "video", "presenter", "music", "speech", "align")}
    assert not local & {m.id for m in cli.models(server)}
    listed = cli.models(server, tests=True)
    by_id = {m.id: m for m in listed}
    assert local <= by_id.keys() and all(by_id[m].test for m in local)
    assert (by_id[task_model("video")].role, by_id[task_model("video")].runtime) == ("video", "diffusers")
    assert (by_id[task_model("speech")].role, by_id[task_model("speech")].runtime) == ("speech", "kokoro")
    ranks = [cli.ROLES.index(m.role) if m.role in cli.ROLES else len(cli.ROLES) for m in listed]
    assert ranks == sorted(ranks)
    lines = cli.model_lines("srv", [by_id[task_model("image")], by_id[task_model("speech")]])
    assert lines == ["server: srv", f"image   diffusers  {task_model('image')}",
                     f"speech  kokoro     {task_model('speech')}"]
    got = cli.model(server, task_model("video"))
    want = model_entry("video")
    assert (got["kind"], got["role"], got["test"]) == ("diffusers", "video", True)
    assert {k: got["entry"][k] for k in ("fps", "width", "height", "max_frames")} == {
        k: want[k] for k in ("fps", "width", "height", "max_frames")}


@NEEDS_GPU
def test_video_reports_status_changes_and_returns_the_mp4(server):
    """`video` creates the job, reports it queued and then at each change of status up to completed, and returns
    an H.264 MP4 at the model's size with the planned frames; `status` of the job is completed afterwards."""
    seen = []
    spec = model_entry("video")
    data = cli.video(server, task_model("video"), png(64, 84), "waves", seconds=0.3, seed=3, on_status=seen.append)
    statuses = [j.status for j in seen]
    assert statuses[0] == "queued" and statuses[-1] == "completed" and len(set(statuses)) == len(statuses)
    got = clip(data)
    assert (got.video_codec, got.width, got.height, got.frames) == ("h264", spec["width"], spec["height"], 9)
    assert cli.status(server, seen[0].id).status == "completed"


@NEEDS_GPU
def test_image_returns_a_png_at_size(server):
    """`image` returns the PNG of the image model at the requested size."""
    data = cli.image(server, task_model("image"), "a red cat", size="256x256", seed=1)
    assert Image.open(io.BytesIO(data)).size == (256, 256)


def test_speech_returns_a_wav_in_the_default_and_another_voice(server):
    """`speech` returns a WAV file of the Kokoro model without a voice (its default) and with one."""
    assert read(cli.speech(server, task_model("speech"), "Hi.")).seconds > 0
    assert read(cli.speech(server, task_model("speech"), "Hi.", voice="am_adam")).seconds > 0


def test_default_output_name_and_no_overwrite(tmp_path):
    """Without `-o` the file is `<model id, ':' and '/' as '_'>_<YYYYmmdd-HHMMSS>.<ext>` in the directory; an
    existing file, given or generated, is a `ClientError` and is not written."""
    when = datetime(2026, 1, 2, 3, 4, 5)
    path = cli.output_path(None, "diffusers:org/model", "png", tmp_path, when)
    assert path == tmp_path / "diffusers_org_model_20260102-030405.png"
    assert cli.save(b"one", path) == path
    with pytest.raises(cli.ClientError, match="exists"):
        cli.output_path(None, "diffusers:org/model", "png", tmp_path, when)
    with pytest.raises(cli.ClientError, match="exists"):
        cli.output_path(path, "diffusers:other", "png", tmp_path, when)
    with pytest.raises(cli.ClientError, match="exists"):
        cli.save(b"two", path)
    assert path.read_bytes() == b"one"


@NEEDS_GPU
def test_failed_video_job_raises_its_error(server):
    """A job whose `input_reference` is no image fails on the server; `video` raises a `ClientError` with the job's
    status and error code."""
    seen = []
    with pytest.raises(cli.ClientError, match=r"video job video_\w+ failed 0%: (model_error|server_error): ") as e:
        cli.video(server, task_model("video"), b"not an image", "waves", seconds=0.3, on_status=seen.append)
    assert seen[-1].status == "failed" and seen[-1].id in str(e.value)


def test_request_errors_are_one_line(server):
    """A model the server lacks is a `ClientError` naming the HTTP status and the error code."""
    with pytest.raises(cli.ClientError, match="HTTP 404 model_not_found"):
        cli.image(server, "diffusers:no-such-model", "a cat")
