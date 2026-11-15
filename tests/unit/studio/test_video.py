"""Unit tests of short-video projects in the studio server: project details, scene states, storyboard writes, film
settings, scene styles, own pictures, sources, request checks, the phone version, /file ranges and the watcher."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from studio_server.video import check_storyboard, default_film, film_of, scene_state

from tests.settings_env import write_config
from tests.subproc import child_env, py_value

from .conftest import PNG, data_url

STORYBOARD = {
    "title": "Vaccines",
    "topic": "How a vaccine trains the immune system.",
    "scenes": [
        {"id": "opening", "template": "title", "narration": ["Welcome."], "beats": ["Vaccines"]},
        {"id": "injection", "image": "injection/v1.png", "brief": "Push in slowly.",
         "narration": ["A shot.", "It teaches."], "beats": ["arm", "cell"]},
        {"id": "morph", "engine": "clip"},
    ],
}


def make_video(root: Path, name: str = "film", storyboard: dict | None = STORYBOARD, meta: dict | None = None,
               pictures: dict[str, tuple[int, ...]] | None = None) -> Path:
    """A short-video project `<root>/short-video/<name>` with project.json (default film settings), storyboard.json
    (None: none) and the given picture versions per scene."""
    p = root / "short-video" / name
    p.mkdir(parents=True)
    (p / "project.json").write_text(json.dumps(
        {"name": name.title(), "brief": "a film", "kind": "short-video", "created": "2026-11-12T10:00:00+00:00",
         "autonomy": "step", "settings": {}, "film": default_film(), "style": {"name": "ink"}, "scene_styles": {},
         **(meta or {})}), encoding="utf-8")
    if storyboard is not None:
        (p / "storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")
    for scene, versions in (pictures if pictures is not None else {"injection": (1,)}).items():
        d = p / "images" / scene
        d.mkdir(parents=True)
        for n in versions:
            (d / f"v{n}.png").write_bytes(PNG)
            (d / f"v{n}.json").write_text(json.dumps({"prompt": f"{scene} {n}", "kind": "short-video"}))
    return p


def version(p: Path, *parts: str, meta_name: str = "meta.json", meta: object = None,
            files: tuple[str, ...] = ()) -> Path:
    """A version directory `p/<parts>` with its metadata file (unless `meta` is None) and empty `files`."""
    d = p.joinpath(*parts)
    d.mkdir(parents=True)
    if meta is not None:
        (d / meta_name).write_text(json.dumps(meta) if not isinstance(meta, str) else meta)
    for f in files:
        (d / f).write_bytes(b"x")
    return d


def music(p: Path, n: int, source: str | None, **studio) -> Path:
    d = version(p, "music", f"v{n}", meta={"source": "file", "file": "track.mp3", "created_at": "t"},
                files=("track.mp3",))
    if source is not None:
        (d / "studio.json").write_text(json.dumps({"source": source, "brief": "", "note": "calm", "duration": 60.0,
                                                   "created": "t", **studio}))
    return d


def film_version(p: Path, n: int, music_version: str | None = "v1") -> Path:
    return version(p, "film", f"v{n}", meta_name="manifest.json", files=("film.mp4",), meta={
        "version": f"v{n}", "duration": 61.5, "created_at": f"t{n}",
        "scenes": [{"id": "opening", "scene_version": "v1", "voice_version": "v1", "duration": 3.0}],
        "music": {"version": music_version, "file": "track.mp3", "gain_db": -14} if music_version else None})


def vreq(p: Path | None, action: str, **kw) -> dict:
    req = {"action": action, "kind": "short-video", "project": str(p) if p else None}
    if action == "storyboard":
        req |= {"brief": "How vaccines work", "refs": [], "sources": [], "style": "auto", "film": default_film()}
    req.update(kw)
    return req


def video_of(client, p: Path) -> dict:
    status, d = client.get(f"/api/project?dir={p}")
    assert status == 200
    return d


def mtime(p: Path) -> str:
    return str((p / "storyboard.json").stat().st_mtime_ns)


# Projects

def test_new_video_project(client, studio):
    """/api/new of kind short-video makes an untitled project with the default film settings, style null and no
    scene styles. Guards a blank short-video workspace."""
    _, body = client.post("/api/new", {"kind": "short-video"})
    p = Path(body["project"])
    assert p.parent == studio.root / "short-video"
    meta = json.loads((p / "project.json").read_text())
    assert meta["film"] == default_film() and meta["style"] is None and meta["scene_styles"] == {}
    assert default_film()["voice"] == {"model": None, "name": None, "speed": 1.0, "style": None}


def test_video_list(client, studio):
    """/api/projects?kind=short-video counts complete films (with manifest.json, a JSON object). Guards the left
    column."""
    p = make_video(studio.root)
    film_version(p, 1)
    film_version(p, 2)
    version(p, "film", "v3", files=("film.mp4",))
    version(p, "film", "v4", meta_name="manifest.json", meta="[]")
    _, projects = client.get("/api/projects?kind=short-video")
    assert [(x["dir"], x["versions"]) for x in projects] == [(str(p), 2)]


def test_video_details(client, studio):
    """/api/project of a short-video project: no top-level versions, sources directly in sources/, and `video` with
    the storyboard and its mtime, per scene its pictures, picture, recording and clip, the music with music_used,
    the films, the voice samples and status.json's time. Guards the film workspace."""
    p = make_video(studio.root, pictures={"injection": (1, 2), "opening": (1,)},
                   meta={"film": {**default_film(), "music": {"mode": "made", "brief": "", "volume": "normal",
                                                             "version": 1}}})
    (p / "sources" / "music").mkdir(parents=True)
    (p / "sources" / "notes.md").write_text("notes")
    (p / "sources" / "music" / "made.mp3").write_bytes(b"x")
    version(p, "voice", "injection", "v1", meta={"duration": 4.5, "voice": {"model": "kokoro:kokoro-v1.0"}, "created_at": "a"},
            files=("narration.wav",))
    version(p, "voice", "injection", "v2", meta={"duration": 5.0, "voice": {"model": "kokoro:kokoro-v1.0", "voice": "voice-a"},
                                                  "created_at": "b"}, files=("narration.wav",))
    version(p, "voice", "injection", "v3")  # not complete
    version(p, "voice", "injection", "v4", meta="[1]")  # metadata not an object: left out
    version(p, "scenes", "injection", "v1", meta={"duration": 5.2, "rendered_at": "c"})
    version(p, "scenes", "gone", "v1", meta={"duration": 1})
    music(p, 1, "made", brief="calm piano")
    music(p, 2, "own")
    music(p, 3, None)
    film_version(p, 1)
    (p / "film" / "v1" / "studio.json").write_text(json.dumps({"changes": "first film", "created": "t"}))
    review = {"created": "t", "model": "vertex:gemini-3.1-pro-preview",
              "findings": [{"k": 1, "start": 3.0, "end": 5.5, "problem": "still", "change": "pan"}]}
    (p / "film" / "v1" / "review.json").write_text(json.dumps(review))
    film_version(p, 2, music_version=None)
    (p / "film" / "v2" / "review.json").write_text("[1]")  # not an object: no review
    (p / "samples").mkdir()
    for k in (1, 2, 3):
        (p / "samples" / f"voice-{k}").mkdir()
        (p / "samples" / f"voice-{k}" / "narration.wav").write_bytes(b"x")
        if k < 3:  # sample 3 has no sidecar yet
            (p / "samples" / f"voice-{k}.json").write_text(json.dumps({"voice": {"model": "kokoro:kokoro-v1.0"},
                                                                       "text": f"s{k}"}))
    (p / "samples" / "voice-4.json").write_text("{}")  # no WAV
    (p / "status.json").write_text(json.dumps({"created": "2026-11-12T11:00:00+01:00", "film": default_film(),
                                               "speakers": None, "scenes": {}}))
    d = video_of(client, p)
    assert d["versions"] == [] and d["sources"] == [str(p / "sources" / "notes.md")]
    v = d["video"]
    assert v["storyboard"] == STORYBOARD and v["storyboard_mtime"] == mtime(p) and "error" not in v
    assert [s["id"] for s in v["scenes"]] == ["opening", "injection", "morph"]
    opening, injection, morph = v["scenes"]
    assert [x["n"] for x in injection["pictures"]] == [2, 1]
    assert injection["pictures"][0]["image"] == str(p / "images" / "injection" / "v2.png")
    assert injection["picture"] == 1 and opening["picture"] is None and morph["pictures"] == []
    assert injection["recording"] == {"n": 2, "path": str(p / "voice" / "injection" / "v2" / "narration.wav"),
                                      "duration": 5.0, "voice": {"model": "kokoro:kokoro-v1.0", "voice": "voice-a"},
                                      "created": "b"}
    assert injection["clip"] == {"n": 1, "path": str(p / "scenes" / "injection" / "v1" / "scene.mp4"),
                                 "contact": str(p / "scenes" / "injection" / "v1" / "contact.png"), "duration": 5.2,
                                 "created": "c"}
    assert opening["recording"] is None and opening["clip"] is None
    assert [(m["n"], m["source"]) for m in v["music"]] == [(3, None), (2, "own"), (1, "made")]
    assert v["music"][2] == {"n": 1, "path": str(p / "music" / "v1" / "track.mp3"), "source": "made",
                             "brief": "calm piano", "note": "calm", "duration": 60.0, "created": "t"}
    assert v["music"][0]["brief"] is None and v["music_used"] == 1
    assert [(f["n"], f["music"], f["changes"]) for f in v["films"]] == [(2, None, None), (1, 1, "first film")]
    assert v["films"][1]["path"] == str(p / "film" / "v1" / "film.mp4") and v["films"][1]["duration"] == 61.5
    assert v["films"][1]["created"] == "t1" and v["films"][1]["scenes"][0]["scene_version"] == "v1"
    assert v["films"][1]["review"] == review and v["films"][0]["review"] is None
    assert [(s["k"], s["text"]) for s in v["samples"]] == [(2, "s2"), (1, "s1")]
    assert v["samples"][0]["path"] == str(p / "samples" / "voice-2" / "narration.wav")
    assert v["status"] == "2026-11-12T11:00:00+01:00"


def test_video_details_without_storyboard(client, studio):
    """Without storyboard.json `storyboard` and its mtime are null and no scene is listed; a storyboard.json that is
    not an object, or a storyboard.md, gives `error`. Guards a new film and a terminal-made project."""
    p = make_video(studio.root, storyboard=None, pictures={})
    v = video_of(client, p)["video"]
    assert (v["storyboard"], v["storyboard_mtime"], v["scenes"], v["status"]) == (None, None, [], None)
    assert v["music"] == [] and v["films"] == [] and v["samples"] == [] and "error" not in v
    (p / "storyboard.json").write_text("[1]")
    v = video_of(client, p)["video"]
    assert v["storyboard"] is None and v["storyboard_mtime"] == mtime(p) and "not a JSON object" in v["error"]
    (p / "storyboard.json").unlink()
    (p / "storyboard.md").write_text("# Film\n")
    assert "storyboard.md" in video_of(client, p)["video"]["error"]


def test_music_used(client, studio):
    """music_used: null for mode none; else film.music.version when it is a version of the mode, else the newest of
    the mode, else null. Guards "used in the film"."""
    p = make_video(studio.root)
    music(p, 1, "made")
    music(p, 2, "made")
    music(p, 3, "own")

    def used(mode: str, n: int | None) -> int | None:
        meta = json.loads((p / "project.json").read_text())
        meta["film"]["music"] = {"mode": mode, "brief": "", "volume": "normal", "version": n}
        (p / "project.json").write_text(json.dumps(meta))
        return video_of(client, p)["video"]["music_used"]

    assert [used("made", None), used("made", 1), used("made", 3), used("own", None), used("none", 1)] == \
        [2, 1, 2, 3, None]
    for d in (p / "music").iterdir():
        if d.name == "v3":
            (d / "studio.json").unlink()
    assert used("own", None) is None


# Scene state

def _status(scenes: dict, film: dict | None = None, speakers: object = None) -> dict:
    return {"created": "t", "film": film or default_film(), "speakers": speakers, "scenes": scenes}


def test_scene_state_rules():
    """The first rule of Scene state that applies: no entry; film voice or speakers changed; narration, speakers or
    voices changed; equal to its basis (a template scene also with equal author and brand); otherwise render when
    ready. Strings are compared with whitespace collapsed. Guards the state chips."""
    sb = copy.deepcopy(STORYBOARD)
    opening, injection, morph = sb["scenes"]
    film = default_film()
    assert scene_state(injection, sb, None, film) == "voice"
    assert scene_state(morph, sb, None, film) == "render"
    assert scene_state(injection, sb, _status({}), film) == "voice"
    assert scene_state(injection, sb, _status({"injection": {"state": "bogus", "basis": injection}}), film) == "voice"
    status = _status({s["id"]: {"state": "ready", "basis": copy.deepcopy(s)} for s in sb["scenes"]})
    assert [scene_state(s, sb, status, film) for s in sb["scenes"]] == ["ready", "ready", "ready"]
    # Rule 2: the film's voice or the speakers changed, for narrated scenes only.
    other = {**film, "voice": {**film["voice"], "speed": 1.1}}
    assert [scene_state(s, sb, status, other) for s in sb["scenes"]] == ["voice", "voice", "ready"]
    with_speakers = {**sb, "speakers": {"host": {"model": "kokoro:kokoro-v1.0"}}}
    assert scene_state(injection, with_speakers, status, film) == "voice"
    # Rule 3: narration, speakers or voices.
    assert scene_state({**injection, "narration": ["A shot.", "It learns."]}, sb, status, film) == "voice"
    assert scene_state({**injection, "voices": [None, None]}, sb, status, film) == "voice"
    assert scene_state({**morph, "speakers": []}, sb, status, film) == "voice"
    # Whitespace is collapsed on both sides.
    assert scene_state({**injection, "narration": ["A  shot. ", "It\nteaches."]}, sb, status, film) == "ready"
    # Rule 5: another key changed: render when ready, else the recorded state.
    assert scene_state({**injection, "brief": "Pan left."}, sb, status, film) == "render"
    assert scene_state({**injection, "preview": "x.png"}, sb, status, film) == "render"
    voice_status = _status({"injection": {"state": "voice", "basis": injection}})
    assert scene_state({**injection, "brief": "Pan left."}, sb, voice_status, film) == "voice"
    # Rule 4 and 5 for a template scene: author and brand.
    assert scene_state(opening, sb, status, {**film, "author": ["Ada"]}) == "render"
    assert scene_state(opening, sb, status, {**film, "brand": "acme"}) == "render"
    assert scene_state(injection, sb, status, {**film, "author": ["Ada"]}) == "ready"
    render_status = _status({"opening": {"state": "render", "basis": opening}})
    assert scene_state(opening, sb, render_status, {**film, "author": ["Ada"]}) == "render"


def test_scene_states_listed(client, studio):
    """/api/project gives each scene the state computed from status.json. Guards the state chips."""
    p = make_video(studio.root)
    sb = STORYBOARD
    (p / "status.json").write_text(json.dumps(_status({
        "opening": {"state": "ready", "basis": sb["scenes"][0]},
        "injection": {"state": "ready", "basis": {**sb["scenes"][1], "brief": "Old brief."}}})))
    assert [s["state"] for s in video_of(client, p)["video"]["scenes"]] == ["ready", "render", "render"]


def test_drawn_scene(client, studio):
    """A storyboard with an HTML scene without `image` (a drawn scene) is written by /api/storyboard and listed by
    /api/project with no pictures and picture null, its state from status.json as for any scene; the scene with an
    empty `image` is refused. Guards scenes drawn in the page, which have no picture."""
    p = make_video(studio.root, storyboard=None, pictures={})
    sb = copy.deepcopy(STORYBOARD)
    drawn = {"id": "the_curve", "brief": "A bar chart grows bar by bar.", "narration": ["Cases fall."],
             "beats": ["the bars drop on \"fall\""]}
    sb["scenes"].insert(2, drawn)
    assert check_storyboard(sb) == []
    status, body = client.post("/api/storyboard", {"project": str(p), "storyboard": sb, "base": None})
    assert status == 200
    (p / "status.json").write_text(json.dumps(_status({"the_curve": {"state": "ready", "basis": drawn}})))
    scene = video_of(client, p)["video"]["scenes"][2]
    assert (scene["id"], scene["pictures"], scene["picture"], scene["state"]) == ("the_curve", [], None, "ready")
    bad = copy.deepcopy(sb)
    bad["scenes"][2]["image"] = ""
    status, body2 = client.post("/api/storyboard", {"project": str(p), "storyboard": bad, "base": body["storyboard_mtime"]})
    assert status == 400 and "`image` is empty" in json.dumps(body2)


# Storyboard writes

def test_storyboard_write(client, studio):
    """/api/storyboard writes the structure as given (indented, UTF-8, whitespace kept) when `base` is the current
    mtime (null without a file) and answers the new mtime. Guards the page's edits."""
    p = make_video(studio.root, storyboard=None)
    sb = copy.deepcopy(STORYBOARD)
    sb["scenes"][1]["narration"][0] = "A  shot — é."
    status, body = client.post("/api/storyboard", {"project": str(p), "storyboard": sb, "base": None})
    assert status == 200 and body == {"storyboard_mtime": mtime(p)}
    text = (p / "storyboard.json").read_text(encoding="utf-8")
    assert json.loads(text) == sb and text.startswith('{\n  "title"') and "A  shot — é." in text
    sb["title"] = "Vaccines, again"
    status, body2 = client.post("/api/storyboard", {"project": str(p), "storyboard": sb,
                                                    "base": body["storyboard_mtime"]})
    assert status == 200 and body2["storyboard_mtime"] == mtime(p)
    assert video_of(client, p)["video"]["storyboard"]["title"] == "Vaccines, again"


def test_storyboard_write_stale(client, studio):
    """A `base` that is not the current mtime, or null while the file exists, is a 409 with the file as it is and
    its mtime; nothing is written. Guards the page against overwriting the agent's storyboard."""
    p = make_video(studio.root)
    current = mtime(p)
    sb = {**STORYBOARD, "title": "Mine"}
    for base in (None, "123", str(int(current) - 1)):
        status, body = client.post("/api/storyboard", {"project": str(p), "storyboard": sb, "base": base})
        assert status == 409 and body["error"], base
        assert body["storyboard"] == STORYBOARD and body["storyboard_mtime"] == current
    (p / "storyboard.json").unlink()
    status, body = client.post("/api/storyboard", {"project": str(p), "storyboard": sb, "base": current})
    assert status == 409 and body["storyboard"] is None and body["storyboard_mtime"] is None
    assert client.post("/api/storyboard", {"project": str(p), "storyboard": sb, "base": 5})[0] == 400


def _scene(**kw) -> dict:
    return {"id": "s", "image": "a.png", "brief": "b", "narration": ["One."], "beats": ["one"], **kw}


def _sb(*scenes: dict, **top) -> dict:
    return {"title": "T", "topic": "t", "scenes": list(scenes), **top}


# Storyboards with the verdict of media:short-video's structure check, shared with tests/unit/short_video so the
# two checks stay in step.
CASES = json.loads((Path(__file__).parents[1] / "short_video" / "storyboard_cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["case"] for c in CASES])
def test_storyboard_rules(case):
    """The server's check gives each shared storyboard case media:short-video's verdict. Guards the page's writes
    against false refusals and the agent against a storyboard its commands cannot read."""
    assert (check_storyboard(case["storyboard"]) == []) is case["valid"]


def test_storyboard_ids_as_written():
    """A scene id must match [a-z0-9_]+ as written, not only once whitespace is collapsed, since the server reads
    the ids of the file as written. Guards a scene vanishing from /api/project."""
    assert check_storyboard(_sb(_scene(id=" s ")))
    assert check_storyboard(_sb(_scene(id="s")) | {"speakers": {" h": {}}})



def test_storyboard_write_refused(client, studio):
    """A storyboard that breaks a rule is a 400 naming the problems and nothing is written; another kind's project is
    refused. Guards the endpoint wiring of the check."""
    p = make_video(studio.root)
    before = (p / "storyboard.json").read_bytes()
    status, body = client.post("/api/storyboard", {"project": str(p), "storyboard": _sb(_scene(id="Bad"), _scene(
        beats=[])), "base": mtime(p)})
    assert status == 400 and "Bad" in body["error"] and "beats" in body["error"]
    assert (p / "storyboard.json").read_bytes() == before
    image = studio.root / "images" / "cat"
    image.mkdir()
    (image / "project.json").write_text("{}")
    assert client.post("/api/storyboard", {"project": str(image), "storyboard": STORYBOARD, "base": None})[0] == 400


# Film settings and scene styles

def test_film(client, studio):
    """/api/film replaces each given key whole and answers the whole film settings. Guards the voice and music
    controls."""
    p = make_video(studio.root, storyboard=None)
    voice = {"model": "oai:tts", "name": "marin", "speed": 1.1, "style": "warm"}
    status, body = client.post("/api/film", {"project": str(p), "film": {"voice": voice, "length": 30}})
    assert status == 200 and body["film"] == {**default_film(), "voice": voice, "length": 30}
    assert json.loads((p / "project.json").read_text())["film"] == body["film"]
    _, body = client.post("/api/film", {"project": str(p), "film": {"shape": "9:16", "author": ["Ada", "Bo"],
                                                                     "brand": "acme"}})
    assert body["film"]["shape"] == "9:16" and body["film"]["voice"] == voice and body["film"]["brand"] == "acme"
    assert client.post("/api/film", {"project": str(p), "film": {"brand": None}})[1]["film"]["brand"] is None


def test_film_voice_of_the_earlier_form_maps_its_backend(tmp_path):
    """A stored film voice of the earlier `backend` form gets the config's speech model of the provider kind of its
    backend's name (`speech`, or a kind the config lacks: null, the config's speech model) and keeps its name, speed
    and style; a voice without either key is the default voice. Guards projects made before the voice named a speech
    model."""
    from ai_models import config as ai_config

    cfg = tmp_path / "config.yaml"
    cfg.write_text("providers: {kokoro: {kind: kokoro}, cb: {kind: chatterbox}}\n"
                   "models: {speech: 'kokoro:kokoro-v1.0'}\n")
    (tmp_path / "routes.md").write_text("| task | model | when | why |\n|---|---|---|---|\n"
                                        "| speech | cb:chatterbox-turbo | only when cloned | x |\n")
    ai_config.use(cfg)
    try:
        _check_old_voices()
    finally:
        ai_config.use(None)


def _check_old_voices():
    old = {"backend": "kokoro", "name": "bm_george", "speed": 1.1, "style": None}
    assert film_of({"film": {"voice": old, "length": 30}}) == {
        **default_film(), "length": 30, "voice": {"model": "kokoro:kokoro-v1.0", "name": "bm_george", "speed": 1.1,
                                                  "style": None}}
    assert film_of({"film": {"voice": {**old, "backend": "speech", "style": "calm"}}})["voice"] == {
        "model": None, "name": "bm_george", "speed": 1.1, "style": "calm"}
    assert film_of({"film": {"voice": {"backend": "chatterbox"}}})["voice"]["model"] == "cb:chatterbox-turbo"
    assert film_of({"film": {"voice": {"backend": "elevenlabs"}}})["voice"]["model"] is None
    assert film_of({"film": {"voice": {"name": "x"}}})["voice"] == default_film()["voice"]


BAD_FILMS = [
    None, [], {}, {"colour": 1},
    {"voice": None}, {"voice": {"model": "kokoro:kokoro-v1.0", "name": None, "speed": 1.0}},
    {"voice": {"backend": "espeak", "name": None, "speed": 1.0, "style": None}},
    {"voice": {"model": "kokoro", "name": None, "speed": 1.0, "style": None}},
    {"voice": {"model": "kokoro:kokoro-v1.0", "name": "", "speed": 1.0, "style": None}},
    {"voice": {"model": "kokoro:kokoro-v1.0", "name": None, "speed": 2.5, "style": None}},
    {"voice": {"model": "kokoro:kokoro-v1.0", "name": None, "speed": 0.4, "style": None}},
    {"voice": {"model": "kokoro:kokoro-v1.0", "name": None, "speed": True, "style": None}},
    {"voice": {"model": "kokoro:kokoro-v1.0", "name": None, "speed": 1.0, "style": 3}},
    {"voice": {"model": "kokoro:kokoro-v1.0", "name": None, "speed": 1.0, "style": None, "pitch": 1}},
    {"music": {"mode": "made", "brief": ""}},
    {"music": {"mode": "loud", "brief": "", "volume": "normal", "version": None}},
    {"music": {"mode": "made", "brief": 3, "volume": "normal", "version": None}},
    {"music": {"mode": "made", "brief": "", "volume": "max", "version": None}},
    {"music": {"mode": "made", "brief": "", "volume": "normal", "version": 0}},
    {"music": {"mode": "made", "brief": "", "volume": "normal", "version": "v1"}},
    {"shape": "4:3"}, {"length": 45}, {"length": "60"}, {"length": 60.0}, {"length": True},
    {"author": "Ada"}, {"author": ["Ada", " "]},
    {"brand": ""}, {"brand": 3},
    {"review": None}, {"review": "yes"}, {"review": 1},
]


@pytest.mark.parametrize("film", BAD_FILMS)
def test_film_refused(client, studio, film):
    """Film settings outside the table of Film settings are a 400 and nothing is written. Guards settings.yaml."""
    p = make_video(studio.root, storyboard=None)
    before = (p / "project.json").read_bytes()
    assert client.post("/api/film", {"project": str(p), "film": film})[0] == 400
    assert (p / "project.json").read_bytes() == before


def test_film_shape_and_music_version(client, studio):
    """Once the storyboard has a scene the shape cannot change (the same shape is accepted); music.version must be
    a complete music version whose studio.json source is the mode. Guards a phone version made in place and a
    track of the wrong kind."""
    p = make_video(studio.root)
    assert client.post("/api/film", {"project": str(p), "film": {"shape": "9:16"}})[0] == 400
    assert client.post("/api/film", {"project": str(p), "film": {"shape": "16:9"}})[0] == 200
    music(p, 1, "made")
    music(p, 2, "own")
    version(p, "music", "v3")
    m = {"mode": "made", "brief": "calm", "volume": "quiet"}
    assert client.post("/api/film", {"project": str(p), "film": {"music": {**m, "version": 1}}})[0] == 200
    for mode, n in (("made", 2), ("made", 3), ("own", 1), ("none", 1), ("made", 9)):
        assert client.post("/api/film", {"project": str(p), "film": {"music": {**m, "mode": mode, "version": n}}})[0] \
            == 400, (mode, n)
    assert client.post("/api/film", {"project": str(p), "film": {"music": {**m, "mode": "own", "version": 2}}})[0] \
        == 200


def test_scene_style(client, studio):
    """/api/scene-style sets and removes a scene's own style; the scene must be in the storyboard and the style a
    name or null. Guards "this scene's own style"."""
    p = make_video(studio.root)
    post = lambda **kw: client.post("/api/scene-style", {"project": str(p), **kw})
    assert post(scene="injection", style="blueprint") == (200, {"scene_styles": {"injection": "blueprint"}})
    assert post(scene="opening", style="ink")[1] == {"scene_styles": {"injection": "blueprint", "opening": "ink"}}
    assert post(scene="injection", style=None)[1] == {"scene_styles": {"opening": "ink"}}
    assert post(scene="injection", style=None)[1] == {"scene_styles": {"opening": "ink"}}
    assert json.loads((p / "project.json").read_text())["scene_styles"] == {"opening": "ink"}
    for bad in ({"scene": "nope", "style": "ink"}, {"scene": None, "style": "ink"},
                {"scene": "injection", "style": " "},
                {"scene": "injection", "style": 3}):
        assert post(**bad)[0] == 400, bad


# Own pictures

def test_picture(client, studio):
    """/api/picture writes the next picture version of the scene (after the highest v<N>.png or v<N>.json) and its
    sidecar. Guards "Use my own picture"."""
    p = make_video(studio.root, pictures={"injection": (1, 2)})
    (p / "images" / "injection" / "v4.json").write_text("{}")  # an agent's sidecar ahead of its PNG
    status, body = client.post("/api/picture", {"project": str(p), "scene": "injection", "name": "my photo.jpg",
                                                "data": data_url()})
    d = p / "images" / "injection"
    assert status == 200 and body == {"version": 5, "path": str(d / "v5.png")}
    assert (d / "v5.png").read_bytes() == PNG
    sidecar = json.loads((d / "v5.json").read_text())
    assert sidecar["action"] == "own-picture" and sidecar["original"] == "my photo.jpg"
    assert sidecar["kind"] == "short-video" and sidecar["shape"] == "16:9" and sidecar["refs"] == []
    assert all(sidecar[k] is None for k in ("prompt", "scene", "style", "brand", "model", "change", "source"))
    assert sidecar["created"]
    _, body = client.post("/api/picture", {"project": str(p), "scene": "opening", "name": "a.png", "data": data_url()})
    assert body == {"version": 1, "path": str(p / "images" / "opening" / "v1.png")}


def test_picture_refused(client, studio, tmp_path):
    """A picture that is not a PNG, a scene not in the storyboard, a missing name or a linked scene directory is a
    400. Guards the scene's picture versions."""
    p = make_video(studio.root, pictures={})
    post = lambda **kw: client.post("/api/picture", {"project": str(p), "scene": "injection", "name": "a.png",
                                                     "data": data_url(), **kw})
    for bad in ({"data": data_url(b"not a png")}, {"data": data_url(b"GIF89a", "image/gif")},
                {"data": data_url(b"\xff\xd8\xff", "image/jpeg")}, {"scene": "nope"}, {"name": None}):
        assert post(**bad)[0] == 400, bad
    (p / "images").mkdir()
    (p / "images" / "opening").write_text("a file")
    assert post(scene="opening")[0] == 400
    (p / "images" / "injection").symlink_to(tmp_path)
    assert post()[0] == 400
    assert list(tmp_path.glob("v*.png")) == []


def test_picture_busy(client, studio):
    """While the current or a queued request writes pictures of the scene (a change, variations or other-styles
    naming it, or a storyboard, use-style, style-samples or add-scene), /api/picture is a 409; a request on another
    scene, project or action is not; a state after one that named it, or `ended`, lets it through. Guards the picture
    numbering against the agent."""
    p = make_video(studio.root)
    other = make_video(studio.root, "other")
    post = lambda scene="injection": client.post(
        "/api/picture", {"project": str(p), "scene": scene, "name": "a.png", "data": data_url()})
    idle = {"kind": "state", "busy": False, "current": None, "queued": []}
    _, a = client.post("/api/request", vreq(p, "variations", scene="injection", version=1, count=3))
    assert post()[0] == 409 and post("opening")[0] == 200
    client.post("/event", {"kind": "state", "busy": True, "current": a["id"], "queued": []})
    assert client.post("/event", idle)[0] == 204
    assert post()[0] == 200
    _, b = client.post("/api/request", vreq(p, "add-scene", after=None, text="a lab"))
    client.post("/event", {"kind": "state", "busy": True, "current": "x", "queued": [b["id"]]})
    assert post()[0] == 409 and post("opening")[0] == 409
    client.post("/event", {"kind": "ended"})
    assert post()[0] == 200
    client.post("/api/request", vreq(p, "remake-scene", scene="injection"))
    client.post("/api/request", vreq(other, "storyboard"))
    client.post("/api/request", vreq(p, "message", text="hi", scene="injection"))
    assert post()[0] == 200
    for action in ("use-style", "style-samples", "storyboard"):
        req = {"use-style": vreq(p, "use-style", style="ink"), "style-samples": vreq(p, "style-samples", style="auto"),
               "storyboard": vreq(p, "storyboard")}[action]
        assert client.post("/api/request", req)[0] == 202, action
        assert post()[0] == 409, action
        client.post("/event", idle)
    assert a["id"]


def test_picture_busy_long_session(client, studio):
    """A pending request still blocks /api/picture after more events than the kept history. Guards a long session
    in which the agent posts many notes."""
    p = make_video(studio.root)
    _, a = client.post("/api/request", vreq(p, "variations", scene="injection", version=1, count=3))
    client.post("/event", {"kind": "state", "busy": True, "current": a["id"], "queued": []})
    for i in range(1001):
        studio.broadcast({"kind": "note", "text": f"note {i}"})
    assert client.post("/api/picture", {"project": str(p), "scene": "injection", "name": "a.png",
                                        "data": data_url()})[0] == 409


# Sources

def test_sources(client, studio):
    """/api/sources writes sources/<safe name>, numbered when taken, for the listed suffixes only, in short-video
    projects only. Guards source and own-music uploads."""
    p = make_video(studio.root)
    post = lambda name, project=p: client.post(
        "/api/sources", {"project": str(project), "name": name, "data": data_url(b"text", "text/plain")})
    assert post("My notes.MD") == (200, {"path": str(p / "sources" / "My-notes.MD")})
    assert post("My notes.MD")[1] == {"path": str(p / "sources" / "My-notes-2.MD")}
    assert post("../song.mp3")[1] == {"path": str(p / "sources" / "song.mp3")}
    for name in ("a.exe", "noext", "a.png", None):
        assert post(name)[0] == 400, name
    image = studio.root / "images" / "cat"
    image.mkdir()
    (image / "project.json").write_text("{}")
    assert post("a.md", image)[0] == 400
    assert client.post("/api/sources", {"project": str(p), "name": "a.md", "data": "text"})[0] == 400


# /api/marked

def test_marked_scene(client, studio, tmp_path):
    """/api/marked of a short-video project needs `scene` and writes into images/<scene>/marks/; a scene elsewhere,
    a scene not in the storyboard, a missing or linked images/<scene>/ and a version not in it are 400. Guards
    marked changes of scene pictures."""
    p = make_video(studio.root)
    body = {"project": str(p), "scene": "injection", "version": 1, "png": data_url()}
    status, out = client.post("/api/marked", body)
    assert status == 200 and out["path"] == str(p / "images" / "injection" / "marks" / "v1-marked-1.png")
    for bad in ({**body, "scene": None}, {**body, "scene": "nope"}, {**body, "scene": "opening"},
                {**body, "version": 2}, {**body, "slide": 1}):
        assert client.post("/api/marked", bad)[0] == 400, bad
    (p / "images" / "opening").symlink_to(tmp_path)
    assert client.post("/api/marked", {**body, "scene": "opening"})[0] == 400
    image = studio.root / "images" / "cat"
    image.mkdir()
    (image / "project.json").write_text("{}")
    (image / "v1.png").write_bytes(PNG)
    assert client.post("/api/marked", {**body, "project": str(image)})[0] == 400


# Requests

def test_storyboard_request_new(client, studio, emitted):
    """A storyboard with project null makes a project from the brief with the request's film, style null and no
    scene styles; refs must then be empty. Guards starting a film."""
    film = {**default_film(), "length": 30, "author": ["Ada"]}
    status, body = client.post("/api/request", vreq(None, "storyboard", brief="How vaccines work", film=film,
                                                    autonomy="auto"))
    p = Path(body["project"])
    assert status == 202 and p.parent == studio.root / "short-video"
    meta = json.loads((p / "project.json").read_text())
    assert meta["film"] == film and meta["style"] is None and meta["scene_styles"] == {}
    assert meta["name"] == "How vaccines work" and meta["autonomy"] == "auto" and meta["kind"] == "short-video"
    assert emitted[-1]["request"]["project"] == str(p) and emitted[-1]["request"]["skill"] == "videos"
    assert client.post("/api/request", vreq(None, "storyboard", refs=[str(p / "project.json")]))[0] == 400
    assert client.post("/api/request", vreq(None, "storyboard", autonomy="fast"))[0] == 400
    assert client.post("/api/request", vreq(None, "storyboard", film={**film, "music": {
        "mode": "made", "brief": "", "volume": "normal", "version": 1}}))[0] == 400


def test_storyboard_request_existing(client, studio, emitted):
    """A storyboard on an existing project writes its film into project.json before relaying, names an untitled
    project, and takes refs from refs/ and sources from sources/ only. Guards the storyboard step."""
    _, body = client.post("/api/new", {"kind": "short-video"})
    p = Path(body["project"])
    (p / "refs").mkdir()
    (p / "refs" / "a.png").write_bytes(PNG)
    (p / "sources" / "deep").mkdir(parents=True)
    (p / "sources" / "deep" / "n.md").write_text("n")
    (p / "other.md").write_text("o")
    film = {**default_film(), "brand": "acme"}
    req = vreq(p, "storyboard", brief="Vaccines for kids", refs=[str(p / "refs" / "a.png")],
               sources=[str(p / "sources" / "deep" / "n.md")], film=film, style="invent")
    assert client.post("/api/request", req)[0] == 202
    meta = json.loads((p / "project.json").read_text())
    assert meta["film"] == film and meta["name"] == "Vaccines for kids" and meta["brief"] == "Vaccines for kids"
    assert emitted[-1]["request"]["film"] == film
    bad = [
        {**req, "brief": " "}, {**req, "style": ""}, {**req, "refs": [str(p / "other.md")]},
        {**req, "sources": [str(p / "other.md")]}, {**req, "sources": [str(p / "refs" / "a.png")]},
        {**req, "sources": "x"}, {**req, "film": {**film, "shape": "1:1"}}, {**req, "film": {"voice": film["voice"]}},
        {**req, "film": None}, {**req, "slide": 1},
    ]
    for b in bad:
        assert client.post("/api/request", b)[0] == 400, b
    s = make_video(studio.root)
    assert client.post("/api/request", vreq(s, "storyboard", film={**default_film(), "shape": "9:16"}))[0] == 400
    assert client.post("/api/request", vreq(s, "storyboard"))[0] == 202


def test_video_version_actions(client, studio):
    """change, variations and other-styles of a film act on images/<scene>/: the scene must be in the storyboard
    with an existing directory, the version in it, the marked copy and mask in its marks/. Guards picture edits."""
    p = make_video(studio.root)
    marks = p / "images" / "injection" / "marks"
    marks.mkdir()
    (marks / "v1-marked-1.png").write_bytes(PNG)
    (marks / "v1-mask-1.png").write_bytes(PNG)
    change = vreq(p, "change", scene="injection", version=1, note="", marks=[
        {"n": 1, "kind": "box", "comment": "red", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}],
        marked=str(marks / "v1-marked-1.png"), mask=str(marks / "v1-mask-1.png"))
    assert client.post("/api/request", change)[0] == 202
    assert client.post("/api/request", vreq(p, "change", scene="injection", version=1, note="warmer", marks=[],
                                            marked=None, mask=None))[0] == 202
    assert client.post("/api/request", vreq(p, "variations", scene="injection", version=1, count=3))[0] == 202
    assert client.post("/api/request", vreq(p, "other-styles", scene="injection", version=1, styles=[]))[0] == 202
    bad = [
        {**change, "scene": None}, {**change, "scene": "nope"}, {**change, "scene": "opening"},
        {**change, "version": 2}, {**change, "slide": 1},
        {**change, "marked": str(p / "images" / "injection" / "v1.png")},
        vreq(p, "variations", scene="injection", version=1, count=0),
        vreq(p, "other-styles", scene="injection", version=1, styles="ink"),
    ]
    for b in bad:
        assert client.post("/api/request", b)[0] == 400, b


def test_use_style_and_samples(client, studio):
    """use-style takes exactly one of version (one of samples.versions, while samples.scene is in the storyboard)
    and style; style-samples takes auto or invent and needs a scene with a picture (an image or a template).
    Guards the style step and a film of drawn scenes only."""
    p = make_video(studio.root, meta={"samples": {"scene": "injection", "versions": [3, 4, 5], "style": "auto"}})
    ok = [vreq(p, "use-style", version=4), vreq(p, "use-style", style="ink"), vreq(p, "style-samples", style="auto"),
          vreq(p, "style-samples", style="invent")]
    for r in ok:
        assert client.post("/api/request", r)[0] == 202, r
    bad = [vreq(p, "use-style"), vreq(p, "use-style", version=4, style="ink"), vreq(p, "use-style", version=2),
           vreq(p, "use-style", style=" "), vreq(p, "style-samples", style="ink"), vreq(p, "style-samples")]
    for r in bad:
        assert client.post("/api/request", r)[0] == 400, r
    gone = make_video(studio.root, "gone", meta={"samples": {"scene": "deleted", "versions": [1], "style": "auto"}})
    assert client.post("/api/request", vreq(gone, "use-style", version=1))[0] == 400
    nosamples = make_video(studio.root, "plain")
    assert client.post("/api/request", vreq(nosamples, "use-style", version=1))[0] == 400
    empty = make_video(studio.root, "empty", storyboard=None)
    assert client.post("/api/request", vreq(empty, "style-samples", style="auto"))[0] == 400
    drawn = {**STORYBOARD, "scenes": [{"id": "chart", "brief": "A bar chart grows.", "narration": ["Cases fell."],
                                       "beats": ["bars"]}, {"id": "morph", "engine": "clip"}]}
    only_drawn = make_video(studio.root, "drawn", storyboard=drawn, pictures={})
    assert client.post("/api/request", vreq(only_drawn, "style-samples", style="auto"))[0] == 400
    titled = make_video(studio.root, "titled", storyboard={**drawn, "scenes": [STORYBOARD["scenes"][0], *drawn["scenes"]]},
                        pictures={})
    assert client.post("/api/request", vreq(titled, "style-samples", style="invent"))[0] == 202


def test_scene_actions(client, studio, emitted):
    """add-scene (after a scene or null, non-blank text, a storyboard needed), remake-scene (a scene; the server adds
    film), music (non-blank brief; film added), own-music (an audio file directly in sources/), voice-sample (a
    voice as film.voice) and message (an optional scene). Guards the scene and music requests."""
    p = make_video(studio.root, meta={"film": {**default_film(), "length": 120}})
    (p / "sources" / "music").mkdir(parents=True)
    (p / "sources" / "song.mp3").write_bytes(b"x")
    (p / "sources" / "notes.md").write_text("n")
    (p / "sources" / "music" / "made.mp3").write_bytes(b"x")
    voice = {"model": "oai:tts", "name": "Kore", "speed": 1.0, "style": "calm"}
    ok = [vreq(p, "add-scene", after="opening", text="a lab"), vreq(p, "add-scene", after=None, text="a lab"),
          vreq(p, "remake-scene", scene="morph"), vreq(p, "music", brief="calm piano"),
          vreq(p, "own-music", file=str(p / "sources" / "song.mp3")), vreq(p, "voice-sample", voice=voice),
          vreq(p, "message", text="shorter", scene="injection"), vreq(p, "message", text="shorter")]
    for r in ok:
        emitted.clear()
        assert client.post("/api/request", r)[0] == 202, r
        if r["action"] in ("remake-scene", "music"):
            assert emitted[-1]["request"]["film"]["length"] == 120
    bad = [vreq(p, "add-scene", after="nope", text="x"), vreq(p, "add-scene", after=None, text=" "),
           vreq(p, "remake-scene"), vreq(p, "remake-scene", scene="nope"), vreq(p, "music", brief=""),
           vreq(p, "own-music", file=str(p / "sources" / "notes.md")),
           vreq(p, "own-music", file=str(p / "sources" / "music" / "made.mp3")), vreq(p, "own-music", file="song.mp3"),
           vreq(p, "own-music", file=str(p / "sources" / "missing.mp3")),
           vreq(p, "voice-sample", voice={**voice, "speed": 3}), vreq(p, "voice-sample", voice=None),
           vreq(p, "message", text="x", scene="nope"), vreq(None, "message", text="x", scene="injection"),
           vreq(p, "generate"), vreq(p, "assemble")]
    for r in bad:
        assert client.post("/api/request", r)[0] == 400, r
    empty = make_video(studio.root, "empty", storyboard=None)
    assert client.post("/api/request", vreq(empty, "add-scene", after=None, text="a lab"))[0] == 400


def test_make_film(client, studio, emitted):
    """make-film gets film added, also with an empty author, and is refused without a scene, with samples or with
    own music and no own track. Guards "Make the film" and an empty "Made by" not stopping it."""
    film = {**default_film(), "author": ["Ada"]}
    p = make_video(studio.root, meta={"film": film})
    assert client.post("/api/request", vreq(p, "make-film"))[0] == 202
    assert emitted[-1]["request"]["film"] == film
    cases = [
        make_video(studio.root, "a", storyboard=None, meta={"film": film}),
        make_video(studio.root, "b", meta={"film": film, "samples": {"scene": "injection", "versions": [1]}}),
        make_video(studio.root, "d", meta={"film": {**film, "music": {"mode": "own", "brief": "", "volume": "normal",
                                                                    "version": None}}}),
    ]
    for c in cases:
        assert client.post("/api/request", vreq(c, "make-film"))[0] == 400, c.name
    assert client.post("/api/request", vreq(make_video(studio.root, "c", meta={"film": {**film, "author": []}}),
                                            "make-film"))[0] == 202
    music(cases[2], 1, "own")
    assert client.post("/api/request", vreq(cases[2], "make-film"))[0] == 202


def test_review_setting(client, studio):
    """film.review is true by default, in /api/config too, and set by /api/film. Guards "Review each new film", on
    unless switched off."""
    p = make_video(studio.root, storyboard=None)
    assert default_film()["review"] is True
    assert client.get("/api/config")[1]["film"]["review"] is True
    assert client.post("/api/film", {"project": str(p), "film": {"review": False}})[1]["film"]["review"] is False


def test_review(client, studio, emitted):
    """review of a complete film is accepted with its version; a film that is not complete is a 400. Guards "Review
    this film"."""
    p = make_video(studio.root, "vax")
    film_version(p, 2, music_version=None)
    version(p, "film", "v3", files=("film.mp4",))
    assert client.post("/api/request", vreq(p, "review", version=2))[0] == 202
    assert emitted[-1]["request"]["action"] == "review" and emitted[-1]["request"]["version"] == 2
    assert client.post("/api/request", vreq(p, "review", version=3))[0] == 400
    assert client.post("/api/request", vreq(p, "review"))[0] == 400


def test_fix(client, studio, emitted):
    """fix of a complete film is accepted with findings of its review.json and a note, either possibly empty but
    not both, and gets film added; findings without review.json, not listed in it, repeated or not numbers, a
    missing note and a film that is not complete are a 400. Guards "Fix" under a reviewed film."""
    film = {**default_film(), "author": ["Ada"]}
    p = make_video(studio.root, "vax", meta={"film": film})
    film_version(p, 1, music_version=None)
    film_version(p, 2, music_version=None)
    version(p, "film", "v3", files=("film.mp4",))
    (p / "film" / "v2" / "review.json").write_text(json.dumps({"created": "t", "model": "m", "findings": [
        {"k": 1, "start": 0.0, "end": 2.0, "problem": "a", "change": "b"},
        {"k": 2, "start": 4.0, "end": 6.0, "problem": "c", "change": "d"}]}))
    for fields in ({"findings": [1, 2], "note": ""}, {"findings": [2], "note": "slower"},
                   {"findings": [], "note": "louder voice"}):
        assert client.post("/api/request", vreq(p, "fix", version=2, **fields))[0] == 202, fields
        assert emitted[-1]["request"]["action"] == "fix" and emitted[-1]["request"]["film"] == film
        assert emitted[-1]["request"]["findings"] == fields["findings"]
    assert client.post("/api/request", vreq(p, "fix", version=1, findings=[], note="louder"))[0] == 202
    for fields in ({"version": 2, "findings": [], "note": "  "}, {"version": 2, "findings": [3], "note": ""},
                   {"version": 2, "findings": [1, 1], "note": ""}, {"version": 2, "findings": ["1"], "note": ""},
                   {"version": 2, "findings": [True], "note": ""}, {"version": 2, "findings": 1, "note": ""},
                   {"version": 2, "findings": [1]}, {"version": 2, "note": "x"},
                   {"version": 1, "findings": [1], "note": ""}, {"version": 3, "findings": [], "note": "x"},
                   {"findings": [], "note": "x"}):
        assert client.post("/api/request", vreq(p, "fix", **fields))[0] == 400, fields
    (p / "film" / "v1" / "review.json").write_text("[1]")
    assert client.post("/api/request", vreq(p, "fix", version=1, findings=[1], note=""))[0] == 400
    # Refused as make-film is: no scene, samples waiting, own music without a track.
    own = {**film, "music": {"mode": "own", "brief": "", "volume": "normal", "version": None}}
    for name, kw in (("a", {"storyboard": None}), ("b", {"meta": {"film": film, "samples": {"scene": "injection",
                                                                                             "versions": [1]}}}),
                     ("d", {"meta": {"film": own}})):
        c = make_video(studio.root, name, **kw)
        film_version(c, 1, music_version=None)
        assert client.post("/api/request", vreq(c, "fix", version=1, findings=[], note="x"))[0] == 400, name


def test_default_film_author(tmp_path):
    """A new film's author is the AUTHOR_NAME setting of config.yaml split on commas, blanks dropped; [] when unset.
    Guards "Made by" defaulting to the user's name."""
    imports = "from studio_server.video import default_film"
    base = {"HOME": str(tmp_path / "home"), "CLAUDE_PLUGIN_DATA": str(tmp_path / "pd")}
    cfg = write_config(tmp_path / "config.yaml", {"AUTHOR_NAME": " Ada  Lovelace , ,Bob "})
    assert py_value(imports, 'default_film()["author"]', child_env({**base, "SKILLS_CONFIG": str(cfg)})) == [
        "Ada Lovelace", "Bob"]
    assert py_value(imports, 'default_film()["author"]', child_env(base)) == []


def test_phone(client, studio, emitted):
    """phone of a complete film creates a new project folder next to the original with the original's brief, autonomy,
    style and film in 9:16 at 60 s, origin, and the music version that film used copied in as music version 1; the
    202 has target; a film that is not complete is a 400; 503 removes it. Guards the phone version."""
    m = {"mode": "made", "brief": "calm", "volume": "normal", "version": 2}
    film = {**default_film(), "length": 180, "author": ["Ada"], "music": m}
    p = make_video(studio.root, "vax", meta={"film": film, "autonomy": "auto", "scene_styles": {"opening": "ink"}})
    music(p, 2, "made", brief="calm")
    music(p, 3, "made")
    film_version(p, 2, music_version="v2")
    film_version(p, 4, music_version=None)
    version(p, "film", "v3", files=("film.mp4",))
    status, body = client.post("/api/request", vreq(p, "phone", version=2))
    target = Path(body["target"])
    assert status == 202 and body == {"id": body["id"], "project": str(p), "target": str(target)}
    assert target.parent == p.parent and target != p
    assert emitted[-1]["request"]["target"] == str(target)
    meta = json.loads((target / "project.json").read_text())
    assert meta["name"] == "Vax (phone)" and meta["brief"] == "a film" and meta["autonomy"] == "auto"
    assert meta["kind"] == "short-video" and meta["settings"] == {} and meta["scene_styles"] == {}
    assert meta["film"] == {**film, "shape": "9:16", "length": 60, "music": {**m, "version": 1}}
    assert meta["style"] == {"name": "ink"}
    assert meta["origin"] == {"project": str(p), "film": 2} and meta["created"] == emitted[-1]["request"]["time"]
    v = video_of(client, target)["video"]
    assert [(x["n"], x["source"], x["brief"]) for x in v["music"]] == [(1, "made", "calm")]
    assert v["music"][0]["path"] == str(target / "music" / "v1" / "track.mp3") and v["music_used"] == 1
    _, body = client.post("/api/request", vreq(p, "phone", version=4))
    meta = json.loads((Path(body["target"]) / "project.json").read_text())
    assert meta["film"]["music"]["version"] is None and not (Path(body["target"]) / "music").exists()
    second = body["target"]
    _, body = client.post("/api/request", vreq(p, "phone", version=2))
    assert len({str(target), second, body["target"]}) == 3
    # The mode follows the copied track: a film made with a made track, from a project now set to own music.
    own = {**film, "music": {**m, "mode": "own"}}
    q = make_video(studio.root, "own", meta={"film": own})
    music(q, 2, "made")
    film_version(q, 1, music_version="v2")
    _, body = client.post("/api/request", vreq(q, "phone", version=1))
    meta = json.loads((Path(body["target"]) / "project.json").read_text())
    assert meta["film"]["music"]["mode"] == "made" and meta["film"]["music"]["version"] == 1
    assert video_of(client, Path(body["target"]))["video"]["music_used"] == 1
    for n in (3, 1, 0, None):
        assert client.post("/api/request", vreq(p, "phone", version=n))[0] == 400, n

    def fail(message):
        raise OSError("closed")
    studio.emit = fail
    before = set((studio.root / "short-video").iterdir())
    assert client.post("/api/request", vreq(p, "phone", version=2))[0] == 503
    assert client.post("/api/request", vreq(None, "storyboard", brief="Gone film"))[0] == 503
    assert set((studio.root / "short-video").iterdir()) == before


def test_markdown_project(client, studio, tmp_path):
    """A project holding storyboard.md takes only messages, autonomy, rename and delete: every other request and
    every write is a 400. Guards projects made in the terminal."""
    studio.trash_root = tmp_path / "Trash"
    p = make_video(studio.root, storyboard=None)
    (p / "storyboard.md").write_text("# Film\n")
    assert client.post("/api/request", vreq(p, "message", text="hi"))[0] == 202
    for r in (vreq(p, "storyboard"), vreq(p, "music", brief="calm"), vreq(p, "make-film")):
        assert client.post("/api/request", r)[0] == 400, r
    writes = [("/api/storyboard", {"storyboard": STORYBOARD, "base": None}), ("/api/film", {"film": {"length": 30}}),
              ("/api/scene-style", {"scene": "injection", "style": "ink"}),
              ("/api/picture", {"scene": "injection", "name": "a.png", "data": data_url()}),
              ("/api/sources", {"name": "a.md", "data": data_url(b"x", "text/plain")}),
              ("/api/refs", {"name": "a.png", "data": data_url()}),
              ("/api/marked", {"scene": "injection", "version": 1, "png": data_url()})]
    for path, body in writes:
        status, out = client.post(path, {"project": str(p), **body})
        assert status == 400 and "storyboard.md" in out["error"], path
    assert client.post("/api/autonomy", {"project": str(p), "autonomy": "auto"}) == (200, {"autonomy": "auto"})
    assert client.post("/api/name", {"project": str(p), "name": "Terminal film"}) == (200, {"name": "Terminal film"})
    meta = json.loads((p / "project.json").read_text())
    assert meta["autonomy"] == "auto" and meta["name"] == "Terminal film"
    client.post("/event", {"kind": "ended"})
    status, body = client.post("/api/delete", {"project": str(p)})
    assert status == 200 and not p.exists() and (Path(body["trash"]) / "storyboard.md").is_file()


def test_scene_refused_elsewhere(client, studio):
    """A `scene` is refused in requests of other kinds. Guards the field's scope."""
    image = studio.root / "images" / "cat"
    image.mkdir()
    (image / "project.json").write_text("{}")
    assert client.post("/api/request", {"action": "message", "kind": "image", "project": str(image), "text": "x",
                                        "scene": "a"})[0] == 400


# /file ranges

def test_file_range(client, studio):
    """/file answers a single byte range with 206 and Content-Range, a range outside the file with 416, and the
    whole file otherwise, always with accept-ranges. Guards seeking in the audio and video players."""
    p = make_video(studio.root)
    data = bytes(range(256)) * 4
    f = p / "film.mp4"
    f.write_bytes(data)
    url = f"/file?path={f}"
    status, headers, body = client.call("GET", url)
    assert status == 200 and body == data and headers["accept-ranges"] == "bytes"
    assert headers["content-type"] == "video/mp4"
    cases = {"bytes=0-9": (0, 9), "bytes=1000-": (1000, 1023), "bytes=-24": (1000, 1023),
             "bytes=1020-5000": (1020, 1023)}
    for rng, (first, last) in cases.items():
        status, headers, body = client.call("GET", url, headers={"range": rng})
        assert status == 206 and body == data[first:last + 1], rng
        assert headers["content-range"] == f"bytes {first}-{last}/1024" and headers["content-length"] == str(
            last - first + 1)
        assert headers["accept-ranges"] == "bytes"
    for rng in ("bytes=1024-", "bytes=-0"):
        status, headers, _ = client.call("GET", url, headers={"range": rng})
        assert status == 416 and headers["content-range"] == "bytes */1024", rng
    for rng in ("bytes=0-1,5-9", "items=0-1", "bytes=9-1", "bytes=-"):
        status, _, body = client.call("GET", url, headers={"range": rng})
        assert status == 200 and body == data, rng


# Watched paths

def test_watched_video_paths(studio):
    """In a short-video project the watcher sees the listed paths and not sources/narration/, sources/music/ or a
    version's subdirectories. Guards the page's refresh of a film being made."""
    p = make_video(studio.root, pictures={"injection": (1,)})
    for d in ("sources/narration", "sources/music", "voice/injection/v1", "scenes/injection/v1/frames",
              "music/v1", "film/v1/media", "samples/voice-1", "images/injection/marks", "refs"):
        (p / d).mkdir(parents=True, exist_ok=True)
    studio.poll()
    changed = [{"kind": "changed", "project_kind": "short-video", "project": str(p)}]
    for f in ("status.json", "storyboard.json", "refs/a.png", "sources/a.md", "samples/voice-1.json",
              "samples/voice-1/narration.wav",
              "images/injection/v2.png", "images/injection/marks/v1-marked-1.png", "voice/x.json",
              "voice/injection/a", "voice/injection/v1/meta.json", "scenes/injection/a",
              "scenes/injection/v1/meta.json",
              "music/a", "music/v1/meta.json", "film/a", "film/v1/manifest.json", "film/v1/studio.json",
              "film/v1/review.json"):
        (p / f).write_bytes(b"x")
        assert studio.poll() == changed, f
    for f in ("sources/narration/a.wav", "sources/music/a.mp3", "scenes/injection/v1/frames/1.png",
              "film/v1/media/a.mp4"):
        (p / f).write_bytes(b"x")
        assert studio.poll() == [], f
    (p / "scenes" / "new_scene" / "v1").mkdir(parents=True)
    studio.poll()
    (p / "scenes" / "new_scene" / "v1" / "meta.json").write_text("{}")
    assert studio.poll() == changed


def test_watched_links_not_followed(studio, tmp_path):
    """A watched directory that is a symbolic link (images/, samples/, refs/, a scene's directory) is not read.
    Guards the watcher against reading outside the project."""
    p = make_video(studio.root, pictures={})
    outside = tmp_path / "outside"
    (outside / "scene_a").mkdir(parents=True)
    for name in ("images", "samples", "refs", "voice"):
        (p / name).symlink_to(outside)
    studio.poll()
    (outside / "a.png").write_bytes(PNG)
    (outside / "scene_a" / "v1.png").write_bytes(PNG)
    assert studio.poll() == []


def test_storyboard_request_make_film(client, studio, emitted):
    """`make_film` is an optional boolean, relayed as given, also with no Made by names. Guards Make the film on a
    blank workspace."""
    film = {**default_film(), "author": ["Ada"]}
    assert client.post("/api/request", vreq(None, "storyboard", brief="Vaccines", film=film, make_film=True))[0] == 202
    assert emitted[-1]["request"]["make_film"] is True
    assert client.post("/api/request", vreq(None, "storyboard", brief="Vaccines two", film=film, make_film="yes"))[0] == 400
    assert client.post("/api/request", vreq(None, "storyboard", brief="Vaccines three",
                                            film={**film, "author": []}, make_film=True))[0] == 202
