"""Unit tests of the studio server's HTTP endpoints, path checks and events, on a temporary projects root."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from studio_server.projects import KINDS

from .conftest import PNG, data_url, make_project, png


def gen(project_dir: Path | None, **kw) -> dict:
    req = {"action": "generate", "kind": "image", "kind": "image", "project": str(project_dir) if project_dir else None, "brief": "a cat", "refs": [],
           "brand": None, "shape": "1:1", "model": "best", "count": 1, "style": "auto"}
    req.update(kw)
    return req


# Root and page

def test_config(client, studio):
    """/api/config has the resolved root and every kind with its label, directory, skill and readiness. Guards the
    page's left column and the kind-to-skill mapping."""
    status, cfg = client.get("/api/config")
    assert status == 200
    assert cfg["root"] == str(studio.root)
    assert cfg["kinds"] == [
        {"id": "image", "label": "Images", "directory": "images", "skill": "images", "ready": True},
        {"id": "infographic", "label": "Infographics", "directory": "infographics", "skill": "images", "ready": True},
        {"id": "slide", "label": "Slides", "directory": "slides", "skill": "images", "ready": True},
        {"id": "short-video", "label": "Short videos", "directory": "short-video", "skill": "short-video",
         "ready": False},
    ]
    assert [k["id"] for k in cfg["kinds"]] == [k.id for k in KINDS]


def test_index_and_static(client):
    """/ is index.html; /static/<file> serves page files with their content types. Guards the page assets."""
    status, headers, body = client.call("GET", "/")
    assert status == 200 and headers["content-type"] == "text/html; charset=utf-8" and b"Studio" in body
    status, headers, _ = client.call("GET", "/static/studio.css")
    assert status == 200 and headers["content-type"] == "text/css; charset=utf-8"
    status, headers, _ = client.call("GET", "/static/shell.js")
    assert status == 200 and headers["content-type"] == "text/javascript; charset=utf-8"
    assert client.call("GET", "/static/missing.js")[0] == 404


def test_static_traversal(client, page, tmp_path):
    """No path, encoded or linked, leaves the page directory. Guards /static against reading other files."""
    (tmp_path / "secret.txt").write_text("secret")
    (page / "link.txt").symlink_to(tmp_path / "secret.txt")
    for path in ("/static/../secret.txt", "/static/%2e%2e/secret.txt", "/static/..%2fsecret.txt",
                 "/static/link.txt", f"/static/{tmp_path}/secret.txt", "/static/"):
        status, _, body = client.call("GET", path)
        assert status == 403, path
        assert b"secret" != body


def test_unknown_path(client):
    """Unknown paths are 404 with a JSON error. Guards the router."""
    status, body = client.get("/nothing")
    assert status == 404 and "error" in body


# Projects

def test_projects_newest_first(client, studio):
    """/api/projects lists projects with project.json, newest first, with ISO times. Guards the project list."""
    old = make_project(studio.root, "old")
    new = make_project(studio.root, "new")
    (studio.root / "images" / "no-project-json").mkdir()
    for f in old.rglob("*"):
        os.utime(f, (time.time() - 3600, time.time() - 3600))
    status, projects = client.get("/api/projects?kind=image")
    assert status == 200
    assert [p["dir"] for p in projects] == [str(new), str(old)]
    assert projects[0]["name"] == "New" and projects[0]["brief"] == "a new"
    assert projects[0]["versions"] == 1
    datetime.fromisoformat(projects[0]["updated"])
    assert client.get("/api/projects?kind=slide") == (200, [])


def test_projects_version_count(client, studio):
    """versions counts v<N>.png with v<N>.json only. Guards the count shown in the project list."""
    p = make_project(studio.root, "cat", versions=(1, 2, 3))
    (p / "v2.json").unlink()
    (p / "v4.png").write_bytes(PNG)
    (p / "refs").mkdir()
    (p / "refs" / "v5.json").write_text("{}")
    (p / "refs" / "v5.png").write_bytes(PNG)
    _, projects = client.get("/api/projects?kind=image")
    assert projects[0]["versions"] == 2


def test_projects_bad_json_and_skill(client, studio):
    """A project.json being written still lists the project by its directory name; an unknown skill is 400.
    Guards the list against partial files and the skill check."""
    p = make_project(studio.root, "half")
    (p / "project.json").write_text("{", encoding="utf-8")
    _, projects = client.get("/api/projects?kind=image")
    assert projects[0]["name"] == "half" and projects[0]["brief"] == ""
    assert client.get("/api/projects?kind=nope")[0] == 400
    assert client.get("/api/projects")[0] == 400


def test_project_details(client, studio):
    """/api/project returns project.json, complete versions newest first and refs. Guards the version view."""
    p = make_project(studio.root, "cat", versions=(1, 2, 3))
    (p / "v2.png").unlink()
    (p / "v4.json").write_text("{", encoding="utf-8")
    (p / "v4.png").write_bytes(PNG)
    (p / "refs").mkdir()
    (p / "refs" / "a.png").write_bytes(PNG)
    status, d = client.get(f"/api/project?dir={p}")
    assert status == 200
    assert d["dir"] == str(p) and d["project"]["name"] == "Cat"
    assert [v["n"] for v in d["versions"]] == [3, 1]
    assert d["versions"][0]["image"] == str(p / "v3.png") and d["versions"][0]["prompt"] == "prompt 3"
    assert d["refs"] == [str(p / "refs" / "a.png")]


def test_project_path_checks(client, studio, tmp_path):
    """Project paths outside the root, traversing out of it, linked out of it, or not a project directory are 400;
    a missing project is 404. Guards every project lookup."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "project.json").write_text("{}")
    (studio.root / "images" / "link").symlink_to(outside)
    for bad in (str(outside), f"{studio.root}/images/../../elsewhere", str(studio.root / "images" / "link"),
                str(studio.root / "images"), str(studio.root / "nope" / "x"), "images/cat"):
        assert client.get(f"/api/project?dir={bad}")[0] == 400, bad
    assert client.get(f"/api/project?dir={studio.root / 'images' / 'missing'}")[0] == 404


# Files

def test_file_inside_root(client, studio):
    """/file serves files inside the root with their type; download=1 adds an attachment header. Guards images
    and downloads."""
    p = make_project(studio.root)
    status, headers, body = client.call("GET", f"/file?path={p / 'v1.png'}")
    assert status == 200 and body == PNG and headers["content-type"] == "image/png"
    assert "content-disposition" not in headers
    status, headers, _ = client.call("GET", f"/file?path={p / 'v1.png'}&download=1")
    assert headers["content-disposition"] == 'attachment; filename="v1.png"'
    assert client.call("GET", f"/file?path={p / 'v9.png'}")[0] == 404


def test_file_outside_root(client, studio, tmp_path):
    """Files outside the root, reached by traversal or by a link, and relative paths are refused. Guards /file
    against reading any other file."""
    secret = tmp_path / "secret.png"
    secret.write_bytes(PNG)
    p = make_project(studio.root)
    (p / "escape.png").symlink_to(secret)
    for bad in (str(secret), f"{p}/../../../secret.png", str(p / "escape.png")):
        assert client.call("GET", f"/file?path={bad}")[0] == 403, bad
    assert client.call("GET", "/file?path=secret.png")[0] == 400
    assert client.call("GET", "/file")[0] == 400


# Events

def test_event_broadcast(client, events):
    """POST /event reaches every connected page unchanged. Guards the mod's events to the page."""
    a, b = events(), events()
    event = {"kind": "state", "busy": True, "current": "r1", "queued": []}
    assert client.post("/event", event)[0] == 204
    assert a.next() == event and b.next() == event
    assert client.post("/event", {"text": "no kind"})[0] == 400
    assert client.post("/event", raw=b"not json")[0] == 400


def test_change_notices(studio, events):
    """A new project gives `projects`; a file written or changed in a project gives `changed`; a removed project
    gives `projects`. Guards the page refresh."""
    ev = events()
    assert studio.poll() == []
    p = make_project(studio.root, "cat")
    assert studio.poll() == [{"kind": "projects", "project_kind": "image"}]
    assert ev.next() == {"kind": "projects", "project_kind": "image"}
    (p / "v2.png").write_bytes(PNG)
    assert studio.poll() == [{"kind": "changed", "project_kind": "image", "project": str(p)}]
    assert ev.next()["kind"] == "changed"
    (p / "marks").mkdir()
    (p / "marks" / "v1-marked.png").write_bytes(PNG)
    assert studio.poll() == [{"kind": "changed", "project_kind": "image", "project": str(p)}]
    for f in sorted(p.rglob("*"), reverse=True):
        f.unlink() if f.is_file() else f.rmdir()
    p.rmdir()
    assert studio.poll() == [{"kind": "projects", "project_kind": "image"}]


# Requests

def test_request_accepted(client, studio, events, emitted):
    """A valid request is answered 202 with an id; it is printed for the mod and broadcast with id and local
    time. Guards the request path page -> server -> mod."""
    p = make_project(studio.root)
    ev = events()
    emitted.clear()
    status, body = client.post("/api/request", gen(p))
    assert status == 202 and re.fullmatch(r"[0-9a-f]{12}", body["id"]) and body["project"] == str(p)
    assert len(emitted) == 1 and emitted[0]["type"] == "request"
    req = emitted[0]["request"]
    assert req["id"] == body["id"] and req["action"] == "generate" and req["project"] == str(p)
    t = datetime.fromisoformat(req["time"])
    assert t.utcoffset() is not None and abs(t.timestamp() - time.time()) < 60
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", req["time"])
    assert ev.next() == {"kind": "request", "request": req}


def test_request_ids_and_times_from_server(client, studio, emitted):
    """The page cannot set id or time. Guards request identity."""
    p = make_project(studio.root)
    client.post("/api/request", gen(p, id="mine", time="yesterday"))
    req = emitted[-1]["request"]
    assert req["id"] != "mine" and req["time"] != "yesterday"


def test_request_rejected(client, studio, tmp_path, emitted):
    """Requests with an unknown skill or action, a project outside the root, a bad field or a ref outside the
    root are 400 and reach neither the mod nor the page. Guards the agent against malformed requests."""
    p = make_project(studio.root)
    secret = tmp_path / "secret.png"
    secret.write_bytes(PNG)
    bad = [
        gen(p, kind="nope"), gen(p, kind=None), gen(p, skill="short-video"), gen(p, kind="infographic"),
        gen(p, action="delete"), gen(p, project=str(tmp_path)),
        gen(p, project=f"{p}/../../.."), gen(p, shape="2:1"), gen(p, model="dall-e"), gen(p, count=0),
        gen(p, count=True), gen(p, style=""), gen(p, refs=[str(secret)]), gen(p, refs=["refs/a.png"]),
        gen(p, refs="x"), gen(p, brand=3),
        {"action": "generate", "kind": "short-video", "project": str(studio.root / "short-video" / "x"), "text": "x"},
        [1, 2],
    ]
    emitted.clear()
    for req in bad:
        status, body = client.post("/api/request", req)
        assert status == 400 and body["error"], req
    assert client.post("/api/request", raw=b"{")[0] == 400
    assert emitted == []


def test_request_models(client, studio, emitted):
    """A generate takes the image-gen tiers best, fast and multi-ref and the older names gpt-image-2,
    nano-banana-pro and nano-banana-2, passed on unchanged, and refuses any other name. Guards the tiers the
    agent passes to image-gen as --tier, and projects saved by earlier pages."""
    p = make_project(studio.root)
    for model in ("best", "fast", "multi-ref", "gpt-image-2", "nano-banana-pro", "nano-banana-2"):
        assert client.post("/api/request", gen(p, model=model))[0] == 202, model
        assert emitted[-1]["request"]["model"] == model
    assert client.post("/api/request", gen(p, model="gemini-x"))[0] == 400


def test_request_refs_resolved(client, studio, emitted):
    """Refs inside the root are accepted and passed resolved. Guards references from refs/."""
    p = make_project(studio.root)
    (p / "refs").mkdir()
    (p / "refs" / "a.png").write_bytes(PNG)
    assert client.post("/api/request", gen(p, refs=[f"{p}/refs/../refs/a.png"]))[0] == 202
    assert emitted[-1]["request"]["refs"] == [str(p / "refs" / "a.png")]


def test_generate_new_project(client, studio, emitted):
    """A generate with project null creates <root>/images/<slug of the brief's first words> with its project.json,
    fills project in the request and answers it; a taken slug gets -2. Guards starting a project with its first
    generate."""
    brief = "A ginger cat on a windowsill at dusk, watercolour"
    status, body = client.post("/api/request", gen(None, project=None, brief=brief))
    assert status == 202
    p = studio.root / "images" / "a-ginger-cat-on-a-windowsill"
    assert body["project"] == str(p) and emitted[-1]["request"]["project"] == str(p)
    meta = json.loads((p / "project.json").read_text())
    assert meta == {"name": "A ginger cat on a windowsill", "brief": brief, "kind": "image",
                    "created": emitted[-1]["request"]["time"], "autonomy": "step", "settings": {}}
    _, body = client.post("/api/request", gen(None, project=None, brief=brief))
    assert body["project"] == str(p) + "-2"
    _, body = client.post("/api/request", gen(None, project=None, brief="?!"))
    assert body["project"] == str(studio.root / "images" / "untitled")


def test_kinds_of_skill_images(client, studio, emitted):
    """An infographic request gets skill images filled in; its new project is made under infographics/ with the kind
    in project.json; listing, events and /api/new follow the kind. A project of another kind's directory is refused.
    Guards the kind-to-directory and kind-to-skill mapping."""
    _, body = client.post("/api/request", gen(None, kind="infographic", skill=None, project=None,
                                               brief="How a vaccine works"))
    req = emitted[-1]["request"]
    assert req["skill"] == "images" and req["kind"] == "infographic"
    p = studio.root / "infographics" / "how-a-vaccine-works"
    assert body["project"] == str(p)
    assert json.loads((p / "project.json").read_text())["kind"] == "infographic"
    _, projects = client.get("/api/projects?kind=infographic")
    assert [x["dir"] for x in projects] == [str(p)]
    assert client.get("/api/projects?kind=image") == (200, [])
    assert client.post("/api/request", gen(p, kind="infographic"))[0] == 202
    assert client.post("/api/request", gen(p, kind="image"))[0] == 400
    assert client.post("/api/request", gen(make_project(studio.root, "deck", directory="slides"), kind="slide",
                                                shape="16:9"))[0] \
        == 202
    _, body = client.post("/api/new", {"kind": "infographic"})
    assert Path(body["project"]).parent == studio.root / "infographics"
    assert json.loads((Path(body["project"]) / "project.json").read_text())["kind"] == "infographic"
    studio.poll()
    (p / "v1.png").write_bytes(PNG)
    assert studio.poll() == [{"kind": "changed", "project_kind": "infographic", "project": str(p)}]


def test_leftover_infographic_directory(client, studio):
    """A leftover `<root>/infographic/` directory is neither listed nor accepted as a project directory. Guards
    the old layout on users' disks."""
    old = make_project(studio.root, "old", directory="infographic")
    assert client.get("/api/projects?kind=infographic") == (200, [])
    assert client.get(f"/api/project?dir={old}")[0] == 400


def test_generate_invent_style(client, studio, emitted):
    """generate accepts style "invent" and passes it on. Guards the invented-styles choice."""
    p = make_project(studio.root)
    assert client.post("/api/request", gen(p, style="invent"))[0] == 202
    assert emitted[-1]["request"]["style"] == "invent"


def test_generate_new_project_autonomy(client, studio, emitted):
    """A new project's generate may carry autonomy (default step), written to project.json and kept in the
    request; another value is 400. Guards the autonomy chosen on a blank workspace."""
    _, body = client.post("/api/request", gen(None, project=None, brief="auto cat", autonomy="auto"))
    assert json.loads((Path(body["project"]) / "project.json").read_text())["autonomy"] == "auto"
    assert emitted[-1]["request"]["autonomy"] == "auto"
    _, body = client.post("/api/request", gen(None, project=None, brief="step cat"))
    assert json.loads((Path(body["project"]) / "project.json").read_text())["autonomy"] == "step"
    assert client.post("/api/request", gen(None, project=None, brief="bad cat", autonomy="fast"))[0] == 400


def test_untitled_project_named_by_first_generate(client, studio, emitted):
    """/api/new makes an untitled project (for a reference image added to a blank workspace) with the given
    autonomy; its first generate names it from the brief and a later one does not rename it. Guards adding a
    reference before the first Generate."""
    code, body = client.post("/api/new", {"kind": "image", "autonomy": "auto"})
    assert code == 200
    p = Path(body["project"])
    meta = json.loads((p / "project.json").read_text())
    assert (meta["name"], meta["brief"], meta["autonomy"]) == ("Untitled", "", "auto")
    code, ref = client.post("/api/refs", {"project": str(p), "name": "sketch.png", "data": data_url()})
    assert code == 200
    assert client.post("/api/request", gen(p, brief="a red bicycle by the sea", refs=[ref["path"]]))[0] == 202
    meta = json.loads((p / "project.json").read_text())
    assert (meta["name"], meta["brief"]) == ("a red bicycle by the sea", "a red bicycle by the sea")
    client.post("/api/request", gen(p, brief="something else"))
    assert json.loads((p / "project.json").read_text())["name"] == "a red bicycle by the sea"
    assert client.post("/api/new", {"kind": "nope"})[0] == 400
    assert client.post("/api/new", {"kind": "image", "autonomy": "fast"})[0] == 400


def test_generate_new_project_concurrent(client, studio):
    """Requests at once with the same brief each get their own directory. Guards the atomic creation."""
    results = []
    threads = [threading.Thread(target=lambda: results.append(
        client.post("/api/request", gen(None, project=None, brief="same brief")))) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    dirs = [b["project"] for status, b in results if status == 202]
    assert len(dirs) == 8 and len(set(dirs)) == 8


def test_generate_new_project_invalid(client, studio):
    """An invalid generate with project null, a blank brief included, creates nothing; other actions still need an existing project; the
    new-project action is gone. Guards stray project directories."""
    assert client.post("/api/request", gen(None, project=None, shape="2:1"))[0] == 400
    for blank in ("", "   \n"):
        assert client.post("/api/request", gen(None, project=None, brief=blank))[0] == 400
    assert list((studio.root / "images").iterdir()) == []
    assert client.post("/api/request", {"action": "variations", "kind": "image", "project": None,
                                        "version": 1, "count": 3})[0] == 400
    assert client.post("/api/request", {"action": "new-project", "kind": "image", "name": "x",
                                        "brief": "x"})[0] == 400


def test_project_name_and_slug_length():
    """The name is the brief's first words, cut so the slug fits in 40 characters. Guards long briefs."""
    from studio_server.paths import slug
    from studio_server.projects import project_name
    name = project_name("Extraordinarily detailed panoramic illustration of a mountain village")
    assert len(slug(name)) <= 40 and name.startswith("Extraordinarily detailed")
    assert slug(name) == slug(name, max_len=None)


def test_message(client, studio, emitted):
    """A message needs text; its project may be null. Guards the Claude column input."""
    assert client.post("/api/request", {"action": "message", "kind": "image", "project": None, "text": "hi"})[0] \
        == 202
    assert emitted[-1]["request"]["project"] is None
    p = make_project(studio.root)
    assert client.post("/api/request", {"action": "message", "kind": "image", "project": str(p),
                                        "text": "hi"})[0] == 202
    assert client.post("/api/request", {"action": "message", "kind": "image", "text": " "})[0] == 400
    assert client.post("/api/request", {"action": "message", "kind": "short-video", "text": "hi"})[0] == 202


def test_change(client, studio):
    """change needs an existing version, valid marks and the version's marked copy. Guards marked changes."""
    p = make_project(studio.root)
    (p / "marks").mkdir()
    marked = p / "marks" / "v1-marked-2.png"
    marked.write_bytes(PNG)
    (p / "marks" / "v1-marked.png").write_bytes(PNG)
    marks = [{"n": 1, "kind": "box", "comment": "redder", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5},
             {"n": 2, "kind": "point", "comment": "a bird", "x": 0.9, "y": 0},
             {"n": 3, "kind": "loop", "comment": "remove", "points": [[0, 0], [1, 0], [1, 1]]}]
    mask = p / "marks" / "v1-mask-2.png"
    mask.write_bytes(PNG)
    (p / "marks" / "v1-mask-1.png").write_bytes(PNG)
    req = {"action": "change", "kind": "image", "project": str(p), "version": 1, "marks": marks, "note": "",
           "marked": str(marked), "mask": str(mask)}
    assert client.post("/api/request", req)[0] == 202
    assert client.post("/api/request", {**req, "marks": [], "note": "brighter", "marked": None, "mask": None})[0] == 202
    bad = [
        {**req, "version": 2}, {**req, "marks": [{**marks[0], "w": 1.5}]}, {**req, "marks": [{**marks[1], "kind": "x"}]},
        {**req, "marks": [{**marks[2], "points": [[0, 2]]}]}, {**req, "marks": [{**marks[0], "n": 0}]},
        {**req, "marks": [{**marks[0], "comment": None}]}, {**req, "marked": str(p / "v1.png")},
        {**req, "marked": str(p / "marks" / "v1-marked.png")}, {**req, "marked": str(p / "marks" / "v1-marked-3.png")},
        {**req, "marked": f"{p}/../{p.name}/v1-marked-2.png"},
        {**req, "marks": [], "note": " ", "marked": None, "mask": None}, {**req, "marks": "x"},
        {**req, "mask": None}, {**req, "mask": str(marked)}, {**req, "mask": str(p / "marks" / "v1-mask-1.png")},
        {**req, "mask": str(p / "marks" / "v1-mask-3.png")}, {**req, "mask": str(p / "v1.png")},
        {**req, "mask": str(p / "marks" / "v2-mask-2.png")}, {**req, "mask": "marks/v1-mask-2.png"},
        {**req, "marks": [], "note": "brighter", "marked": None},
    ]
    for b in bad:
        assert client.post("/api/request", b)[0] == 400, b


def test_variations_and_other_styles(client, studio):
    """variations and other-styles need an existing version; other-styles a list of names. Guards both actions."""
    p = make_project(studio.root)
    base = {"kind": "image", "project": str(p), "version": 1}
    assert client.post("/api/request", {**base, "action": "variations", "count": 3})[0] == 202
    assert client.post("/api/request", {**base, "action": "variations", "count": 3, "version": 5})[0] == 400
    assert client.post("/api/request", {**base, "action": "other-styles", "styles": []})[0] == 202
    assert client.post("/api/request", {**base, "action": "other-styles", "styles": ["ink", "pop"]})[0] == 202
    assert client.post("/api/request", {**base, "action": "other-styles", "styles": "ink"})[0] == 400


# Writes

def test_marked(client, studio):
    """/api/marked writes a new marks/v<N>-marked-<k>.png per call, k from 1, and never replaces one. Guards a
    queued change keeping its own marked copy."""
    p = make_project(studio.root)
    status, body = client.post("/api/marked", {"project": str(p), "version": 1, "png": data_url()})
    assert status == 200 and body["path"] == str(p / "marks" / "v1-marked-1.png")
    assert (p / "marks" / "v1-marked-1.png").read_bytes() == PNG
    _, body = client.post("/api/marked", {"project": str(p), "version": 1, "png": data_url(b"new")})
    assert body["path"] == str(p / "marks" / "v1-marked-2.png")
    assert (p / "marks" / "v1-marked-1.png").read_bytes() == PNG
    assert (p / "marks" / "v1-marked-2.png").read_bytes() == b"new"


def test_marked_mask(client, studio):
    """/api/marked with a mask writes marks/v<N>-mask-<k>.png with the k of the marked copy and answers both paths.
    Guards the pairing of a change's mask with its marked copy."""
    p = make_project(studio.root)
    (p / "v1.png").write_bytes(png(6, 4))
    (p / "marks").mkdir()
    (p / "marks" / "v1-marked-1.png").write_bytes(PNG)
    mask = png(6, 4, alpha=True)
    status, body = client.post("/api/marked", {"project": str(p), "version": 1, "png": data_url(), "mask": data_url(mask)})
    assert status == 200
    assert body == {"path": str(p / "marks" / "v1-marked-2.png"), "mask": str(p / "marks" / "v1-mask-2.png")}
    assert (p / "marks" / "v1-mask-2.png").read_bytes() == mask
    status, body = client.post("/api/marked", {"project": str(p), "version": 1, "png": data_url(), "mask": None})
    assert status == 200 and body == {"path": str(p / "marks" / "v1-marked-3.png")}
    assert not (p / "marks" / "v1-mask-3.png").exists()


def test_marked_mask_rejected(client, studio):
    """A mask that is not a PNG data URL, not a PNG, or not the pixel size of v<N>.png is refused, and nothing is
    written. Guards the mask sent to the model matching the image."""
    p = make_project(studio.root)
    (p / "v1.png").write_bytes(png(6, 4))
    base = {"project": str(p), "version": 1, "png": data_url()}
    for mask in (data_url(png(4, 6, alpha=True)), data_url(png(6, 5, alpha=True)), data_url(b"not a png"),
                 data_url(png(6, 4)[:20]), data_url(png(6, 4, alpha=True), mime="image/jpeg"), "nope"):
        status, body = client.post("/api/marked", {**base, "mask": mask})
        assert status == 400 and "error" in body, mask[:40]
    assert not (p / "marks").exists() or list((p / "marks").iterdir()) == []


def test_marked_mask_then_change(client, studio, emitted):
    """The paths /api/marked answers with a mask are accepted as `marked` and `mask` of a change; a marked change
    without a mask is refused. Guards the page flow."""
    p = make_project(studio.root)
    _, body = client.post("/api/marked", {"project": str(p), "version": 1, "png": data_url(), "mask": data_url()})
    req = {"action": "change", "kind": "image", "project": str(p), "version": 1, "note": "",
           "marks": [{"n": 1, "kind": "point", "comment": "here", "x": 0.5, "y": 0.5}], "marked": body["path"],
           "mask": body["mask"]}
    assert client.post("/api/request", req)[0] == 202
    assert emitted[-1]["request"]["marked"] == body["path"] and emitted[-1]["request"]["mask"] == body["mask"]
    assert client.post("/api/request", {k: v for k, v in req.items() if k != "mask"})[0] == 400


def test_marked_rejected(client, studio, tmp_path):
    """Bad versions, data URLs, projects and a marks/ link out of the project are refused. Guards writes."""
    p = make_project(studio.root)
    for body in ({"project": str(p), "version": 2, "png": data_url()},
                 {"project": str(p), "version": "1", "png": data_url()},
                 {"project": str(p), "version": 1, "png": data_url(mime="image/jpeg")},
                 {"project": str(p), "version": 1, "png": "nope"},
                 {"project": str(tmp_path), "version": 1, "png": data_url()}):
        assert client.post("/api/marked", body)[0] == 400, body
    outside = tmp_path / "out"
    outside.mkdir()
    (p / "marks").symlink_to(outside)
    assert client.post("/api/marked", {"project": str(p), "version": 1, "png": data_url()})[0] == 400
    assert list(outside.iterdir()) == []


def test_cross_site_fetch(client, studio):
    """A request a browser marks as cross-site or same-site is 403; same-origin, none and no header pass. Guards
    /events and /file against other web pages."""
    p = make_project(studio.root)
    for site in ("cross-site", "same-site"):
        assert client.call("GET", "/events", headers={"sec-fetch-site": site})[0] == 403
        assert client.call("GET", f"/file?path={p / 'v1.png'}", headers={"sec-fetch-site": site})[0] == 403
    for site in ("same-origin", "none"):
        assert client.call("GET", f"/file?path={p / 'v1.png'}", headers={"sec-fetch-site": site})[0] == 200
    assert client.call("GET", f"/file?path={p / 'v1.png'}")[0] == 200


def test_stdout_failure_is_503(client, studio, emitted):
    """A request that cannot be written to stdout is 503. Guards the page against believing a
    lost request was sent."""
    def broken(message):
        raise BrokenPipeError("stdout closed")
    studio.emit = broken
    status, body = client.post("/api/request", {"action": "message", "kind": "image", "text": "hi"})
    assert status == 503 and body["error"]


def test_stdout_failure_removes_new_project(client, studio):
    """A new project's generate that cannot be written to stdout is 503 and leaves no project directory. Guards
    an empty project in the page's list."""
    def broken(message):
        raise BrokenPipeError("stdout closed")
    studio.emit = broken
    assert client.post("/api/request", gen(None, project=None, brief="lost cat"))[0] == 503
    assert list((studio.root / "images").iterdir()) == []


def test_watched_files(studio):
    """Changes at a project's top level, in refs/ and in marks/ are noticed; deeper files are not walked. Guards
    the polling scope."""
    studio.poll()
    p = make_project(studio.root, "cat")
    (p / "deep" / "er").mkdir(parents=True)
    studio.poll()
    (p / "deep" / "er" / "x.png").write_bytes(PNG)
    assert studio.poll() == []
    for sub in ("refs", "marks"):
        (p / sub).mkdir()
        (p / sub / "a.png").write_bytes(PNG)
        assert studio.poll() == [{"kind": "changed", "project_kind": "image", "project": str(p)}], sub


def test_refs(client, studio):
    """/api/refs writes refs/<safe name>, numbered when taken, with the suffix of its type. Guards uploads."""
    p = make_project(studio.root)
    post = lambda name, mime="image/png": client.post(  # noqa: E731
        "/api/refs", {"project": str(p), "name": name, "data": data_url(mime=mime)})
    assert post("../../my photo.png") == (200, {"path": str(p / "refs" / "my-photo.png")})
    assert post("my photo.png")[1]["path"] == str(p / "refs" / "my-photo-2.png")
    assert post("pic.jpg", "image/jpeg")[1]["path"] == str(p / "refs" / "pic.jpg")
    assert post("pic.png", "image/webp")[1]["path"] == str(p / "refs" / "pic.webp")
    assert post("notes.txt")[1]["path"] == str(p / "refs" / "notes.txt.png")
    assert post("")[1]["path"] == str(p / "refs" / "ref.png")
    assert (p / "refs" / "my-photo.png").read_bytes() == PNG
    assert post("x.svg", "image/svg+xml")[0] == 400
    assert client.post("/api/refs", {"project": str(p), "data": data_url()})[0] == 400


def test_autonomy(client, studio):
    """/api/autonomy sets autonomy in project.json and keeps the other keys; other values are 400. Guards the
    autonomy switch."""
    p = make_project(studio.root)
    assert client.post("/api/autonomy", {"project": str(p), "autonomy": "auto"}) == (200, {"autonomy": "auto"})
    meta = json.loads((p / "project.json").read_text())
    assert meta["autonomy"] == "auto" and meta["name"] == "Cat"
    assert client.post("/api/autonomy", {"project": str(p), "autonomy": "fast"})[0] == 400
    (studio.root / "images" / "empty").mkdir()
    assert client.post("/api/autonomy", {"project": str(studio.root / "images" / "empty"),
                                         "autonomy": "auto"})[0] == 404


# Host and origin

def test_foreign_host_and_origin(client, studio):
    """Requests with another Host (DNS rebinding) and POSTs from another origin are 403; the page's own origin and
    the mod (no Origin) are accepted. Guards project files and the session against other web pages."""
    p = make_project(studio.root)
    assert client.call("GET", "/api/config", headers={"host": "evil.example.com"})[0] == 403
    assert client.call("GET", f"/file?path={p / 'v1.png'}", headers={"host": f"evil.example.com:{studio.port}"})[0] \
        == 403
    msg = {"action": "message", "kind": "image", "text": "hi"}
    assert client.post("/api/request", msg, headers={"origin": "https://evil.example.com"})[0] == 403
    assert client.post("/heartbeat", headers={"origin": "null"})[0] == 403
    assert client.post("/api/request", msg, headers={"origin": studio.url})[0] == 202
    assert client.post("/api/request", msg, headers={"host": f"localhost:{studio.port}",
                                                     "origin": f"http://localhost:{studio.port}"})[0] == 202
    assert client.post("/api/request", msg)[0] == 202


def test_state_and_ask_sent_on_connect(client, events):
    """A page connecting gets the kept history, then the last state and the open ask; ask-done clears the ask.
    Guards a page opened or reconnected while the session is busy or waiting for approval."""
    old = {"kind": "state", "busy": True, "current": "r1", "queued": ["r2"]}
    state = {"kind": "state", "busy": True, "current": "r2", "queued": []}
    ask = {"kind": "ask", "tool": "Bash", "text": "run image-gen"}
    note = {"kind": "note", "text": "working"}
    for e in (old, state, ask, note):
        assert client.post("/event", e)[0] == 204
    a = events()
    assert [a.next() for _ in range(3)] == [note, state, ask]
    client.post("/event", {"kind": "ask-done"})
    assert a.next() == {"kind": "ask-done"}
    b = events()
    client.post("/event", {"kind": "note", "text": "next"})
    assert [b.next() for _ in range(3)] == [note, state, {"kind": "note", "text": "next"}]


def test_history_replayed_in_order(client, studio, events):
    """request, agent, note, turn and ended events are replayed in their order, before state and ask; other kinds
    are not kept. Guards a reloaded page showing the conversation."""
    sent = [{"kind": "agent", "text": "hello", "images": []}, {"kind": "note", "text": "step 1"},
            {"kind": "turn", "reason": "done"}]
    for e in sent:
        client.post("/event", e)
    client.post("/event", {"kind": "catalogue"})
    client.post("/api/request", {"action": "message", "kind": "image", "text": "hi"})
    client.post("/event", {"kind": "state", "busy": True, "current": None, "queued": []})
    studio.poll()
    make_project(studio.root, "cat")
    studio.poll()
    ev = events()
    got = [ev.next() for _ in range(5)]
    assert got[:3] == sent
    assert got[3]["kind"] == "request" and got[3]["request"]["text"] == "hi"
    assert got[4]["kind"] == "state"
    client.post("/event", {"kind": "note", "text": "live"})
    assert ev.next() == {"kind": "note", "text": "live"}


def test_ended_clears_ask_and_busy(client, events):
    """ended is kept, clears the open ask and sets the kept state's busy to false. Guards a page reloaded after the
    session ended."""
    client.post("/event", {"kind": "state", "busy": True, "current": "r1", "queued": ["r2"]})
    client.post("/event", {"kind": "ask", "tool": "Bash", "text": "x"})
    client.post("/event", {"kind": "ended"})
    ev = events()
    assert ev.next() == {"kind": "ended"}
    assert ev.next() == {"kind": "state", "busy": False, "current": "r1", "queued": ["r2"]}
    client.post("/event", {"kind": "note", "text": "live"})
    assert ev.next() == {"kind": "note", "text": "live"}


def test_replay_ends_with_marker(client, events):
    """The replay on connect ends with `replayed`, before any live event, also when nothing was kept. Guards the
    page, which redraws once at that marker."""
    a = events()
    client.post("/event", {"kind": "note", "text": "live"})
    assert a.next() == {"kind": "note", "text": "live"} and a.replayed
    b = events()
    assert b.next() == {"kind": "note", "text": "live"} and not b.replayed
    client.post("/event", {"kind": "note", "text": "later"})
    assert b.next() == {"kind": "note", "text": "later"} and b.replayed


def test_history_bounded(studio):
    """At most the last 1000 session events are kept. Guards memory over a long session."""
    for i in range(1005):
        studio.broadcast({"kind": "note", "text": str(i)})
    assert len(studio.history) == 1000
    assert studio.history[0]["text"] == "5" and studio.history[-1]["text"] == "1004"

