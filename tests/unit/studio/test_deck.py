"""Unit tests of slide decks in the studio server: layout, slide checks, chosen versions, assembly and the watcher."""
from __future__ import annotations

import json
from pathlib import Path

import threading

from .conftest import PNG, data_url, make_project, png


def make_deck(root: Path, name: str = "deck", slides: dict[int, tuple[int, ...]] | None = None,
              titles: list[str] | None = None, meta: dict | None = None) -> Path:
    """A deck `<root>/slides/<name>` with project.json, deck.json listing `titles` (default one per slide of
    `slides`), slides.md, and for each slide k of `slides` the versions given in `slide-<k>/`."""
    slides = {1: (1, 2), 2: (1,), 3: (1, 2, 3)} if slides is None else slides
    p = root / "slides" / name
    p.mkdir(parents=True)
    (p / "project.json").write_text(json.dumps(
        {"name": name.title(), "brief": "a deck", "kind": "slide", "created": "2026-11-07T10:00:00+00:00",
         "autonomy": "step", "settings": {}, "assembly": "images", "chosen": {}, **(meta or {})}), encoding="utf-8")
    titles = [f"Slide title {k}" for k in sorted(slides)] if titles is None else titles
    (p / "deck.json").write_text(json.dumps([{"k": i + 1, "title": t} for i, t in enumerate(titles)]))
    (p / "slides.md").write_text("# Deck\n\n## Slide 1 — Opening\n", encoding="utf-8")
    for k, versions in slides.items():
        d = p / f"slide-{k}"
        d.mkdir()
        for n in versions:
            (d / f"v{n}.png").write_bytes(PNG)
            (d / f"v{n}.json").write_text(json.dumps({"prompt": f"slide {k} v{n}", "style": "ink"}))
    return p


def deck_req(p: Path | None, action: str = "generate", **kw) -> dict:
    req = {"action": action, "kind": "slide", "project": str(p) if p else None}
    if action == "generate":
        req |= {"brief": "a deck on onboarding", "refs": [], "brand": None, "shape": "16:9", "model": "best",
                "count": None, "style": "auto", "slide": None}
    req.update(kw)
    return req


def test_new_deck(client, studio, emitted):
    """A generate of kind slide with project null makes a deck under slides/ with assembly images and an empty
    chosen map; count may be null; the shape must be 16:9. Guards starting a deck."""
    status, body = client.post("/api/request", deck_req(None, brief="Onboarding in three steps"))
    assert status == 202
    p = studio.root / "slides" / "onboarding-in-three-steps"
    assert body["project"] == str(p)
    meta = json.loads((p / "project.json").read_text())
    assert meta["kind"] == "slide" and meta["assembly"] == "images" and meta["chosen"] == {}
    assert emitted[-1]["request"]["slide"] is None and emitted[-1]["request"]["count"] is None
    assert client.post("/api/request", deck_req(None, count=5))[0] == 202
    for bad in (deck_req(None, shape="4:3"), deck_req(None, count=0), deck_req(None, slide=1),
                deck_req(None, brief=" ")):
        assert client.post("/api/request", bad)[0] == 400, bad
    _, body = client.post("/api/new", {"kind": "slide"})
    assert json.loads((Path(body["project"]) / "project.json").read_text())["assembly"] == "images"


def test_deck_details(client, studio):
    """/api/project of a deck has slides.md, the slides in deck.json order with titles, versions newest first and
    the chosen version (project.json's when it exists, else the newest), and the assembled decks newest first,
    each with its sidecar; top-level versions are empty. Guards the deck view."""
    p = make_deck(studio.root, meta={"chosen": {"1": 1, "2": 9, "x": 1, "3": "2"}})
    (p / "slide-4").mkdir()  # beyond deck.json: not a slide
    for n in (1, 2):
        (p / f"deck-{n}.pptx").write_bytes(b"pptx")
        (p / f"deck-{n}.json").write_text(json.dumps({"assembly": "images", "versions": {"1": 1}, "created": "t"}))
    (p / "deck-3.pptx").write_bytes(b"pptx")  # no sidecar yet
    (p / "deck-4.json").write_text("{}")      # no pptx
    status, d = client.get(f"/api/project?dir={p}")
    assert status == 200 and d["versions"] == []
    deck = d["deck"]
    assert deck["slides_md"].startswith("# Deck")
    assert [(s["k"], s["title"], [v["n"] for v in s["versions"]], s["chosen"]) for s in deck["slides"]] == [
        (1, "Slide title 1", [2, 1], 1), (2, "Slide title 2", [1], 1), (3, "Slide title 3", [3, 2, 1], 3)]
    assert deck["slides"][0]["versions"][0]["image"] == str(p / "slide-1" / "v2.png")
    assert deck["slides"][0]["dir"] == str(p / "slide-1")
    assert [x["n"] for x in deck["decks"]] == [2, 1]
    assert deck["decks"][0]["path"] == str(p / "deck-2.pptx") and deck["decks"][0]["assembly"] == "images"


def test_deck_without_deck_json(client, studio):
    """Without deck.json the slides are the slide-<k> directories from 1 without a gap, untitled; a listed slide
    without a directory has no versions and no chosen version. Guards a deck while the agent writes it."""
    p = make_deck(studio.root, slides={1: (1,), 2: (1,), 4: (1,)})
    (p / "deck.json").unlink()
    (p / "slides.md").unlink()
    _, d = client.get(f"/api/project?dir={p}")
    assert [(s["k"], s["title"]) for s in d["deck"]["slides"]] == [(1, ""), (2, "")]
    assert d["deck"]["slides_md"] is None
    (p / "deck.json").write_text(json.dumps([{"k": 1, "title": "A"}, {"k": 2}, {"k": 3, "title": "C"}]))
    _, d = client.get(f"/api/project?dir={p}")
    assert [(s["k"], s["title"], s["chosen"]) for s in d["deck"]["slides"]] == [(1, "A", 1), (2, "", 1), (3, "C", None)]


def test_deck_list(client, studio):
    """/api/projects?kind=slide counts a deck's slides and the versions of all its slides. Guards the left column."""
    make_deck(studio.root)
    _, projects = client.get("/api/projects?kind=slide")
    assert projects[0]["slides"] == 3 and projects[0]["versions"] == 6


def test_slide_actions(client, studio):
    """change, variations and other-styles of a deck need `slide`, a slide of the deck, and a version in that
    slide's directory; marked copies and masks are those of the slide's marks/. Guards per-slide actions."""
    p = make_deck(studio.root)
    marks = p / "slide-3" / "marks"
    marks.mkdir()
    (marks / "v3-marked-1.png").write_bytes(PNG)
    (marks / "v3-mask-1.png").write_bytes(PNG)
    change = deck_req(p, "change", slide=3, version=3, note="",
                      marks=[{"n": 1, "kind": "point", "comment": "here", "x": 0.5, "y": 0.5}],
                      marked=str(marks / "v3-marked-1.png"), mask=str(marks / "v3-mask-1.png"))
    assert client.post("/api/request", change)[0] == 202
    assert client.post("/api/request", deck_req(p, "variations", slide=1, version=2, count=3))[0] == 202
    assert client.post("/api/request", deck_req(p, "other-styles", slide=2, version=1, styles=[]))[0] == 202
    bad = [
        {**change, "slide": None}, {**change, "slide": 4}, {**change, "slide": 0}, {**change, "slide": "3"},
        {**change, "slide": 1}, {**change, "version": 4},
        deck_req(p, "variations", slide=2, version=2, count=3), deck_req(p, "variations", version=1, count=3),
        deck_req(p, "other-styles", slide=5, version=1, styles=[]),
    ]
    for b in bad:
        assert client.post("/api/request", b)[0] == 400, b


def test_slide_generate(client, studio, emitted):
    """A deck's generate with slide k regenerates a slide of the deck (brief may be empty) or adds the slide one past
    the last (brief required), always with style "auto" (the deck's style); with slide null it rewrites the deck.
    Guards per-slide generation keeping the deck's style."""
    p = make_deck(studio.root)
    assert client.post("/api/request", deck_req(p, slide=2, brief="", count=1))[0] == 202
    assert client.post("/api/request", deck_req(p, slide=4, brief="a closing slide", count=1))[0] == 202
    assert client.post("/api/request", deck_req(p, brief="", count=None))[0] == 202
    assert emitted[-1]["request"]["slide"] is None
    for b in (deck_req(p, slide=4, brief=" ", count=1), deck_req(p, slide=5, count=1), deck_req(p, slide=2),
              deck_req(p, slide=2, count=1, shape="1:1"), deck_req(p, slide=2, count=1, style="invent"),
              deck_req(p, slide=2, count=1, style="ink")):
        assert client.post("/api/request", b)[0] == 400, b


def test_slide_field_only_for_decks(client, studio):
    """`slide` is refused on other kinds' requests and in their /api/marked; assemble is a deck action only.
    Guards the kinds that are not decks."""
    p = make_project(studio.root)
    assert client.post("/api/request", {"action": "variations", "kind": "image", "project": str(p), "version": 1,
                                        "count": 3, "slide": 1})[0] == 400
    assert client.post("/api/request", {"action": "assemble", "kind": "image", "project": str(p),
                                        "assembly": "images"})[0] == 400
    assert client.post("/api/marked", {"project": str(p), "version": 1, "slide": 1, "png": data_url()})[0] == 400


def test_assemble(client, studio, emitted):
    """assemble takes `assembly` images or native and the server adds the chosen version of every slide; a deck
    with a slide without an image, or without slides, is 400. Guards the PowerPoint request."""
    p = make_deck(studio.root, meta={"chosen": {"1": 1}})
    assert client.post("/api/request", deck_req(p, "assemble", assembly="images"))[0] == 202
    assert emitted[-1]["request"]["versions"] == {"1": 1, "2": 1, "3": 3}
    assert client.post("/api/request", deck_req(p, "assemble", assembly="native", versions={"1": 2}))[0] == 202
    assert emitted[-1]["request"]["versions"] == {"1": 1, "2": 1, "3": 3}
    assert client.post("/api/request", deck_req(p, "assemble", assembly="pdf"))[0] == 400
    (p / "deck.json").write_text(json.dumps([{"title": t} for t in "ABCD"]))
    status, body = client.post("/api/request", deck_req(p, "assemble", assembly="images"))
    assert status == 400 and "slide 4" in body["error"]
    empty = make_deck(studio.root, "empty", slides={}, titles=[])
    assert client.post("/api/request", deck_req(empty, "assemble", assembly="images"))[0] == 400


def test_chosen(client, studio):
    """/api/chosen sets chosen[k] in project.json to an existing version of slide k and keeps the other keys;
    a missing slide or version, or a project that is not a deck, is 400. Guards "Use this version"."""
    p = make_deck(studio.root, meta={"chosen": {"3": 2}})
    assert client.post("/api/chosen", {"project": str(p), "slide": 1, "version": 1}) == (
        200, {"chosen": {"3": 2, "1": 1}})
    meta = json.loads((p / "project.json").read_text())
    assert meta["chosen"] == {"3": 2, "1": 1} and meta["name"] == "Deck"
    _, d = client.get(f"/api/project?dir={p}")
    assert [s["chosen"] for s in d["deck"]["slides"]] == [1, 1, 2]
    image = make_project(studio.root)
    for body in ({"project": str(p), "slide": 1, "version": 3}, {"project": str(p), "slide": 4, "version": 1},
                 {"project": str(p), "slide": 1}, {"project": str(image), "slide": 1, "version": 1}):
        assert client.post("/api/chosen", body)[0] == 400, body


def test_assembly(client, studio):
    """/api/assembly sets assembly images or native in a deck's project.json. Guards the assembly choice."""
    p = make_deck(studio.root)
    assert client.post("/api/assembly", {"project": str(p), "assembly": "native"}) == (200, {"assembly": "native"})
    assert json.loads((p / "project.json").read_text())["assembly"] == "native"
    assert client.post("/api/assembly", {"project": str(p), "assembly": "pdf"})[0] == 400


def test_marked_slide(client, studio):
    """/api/marked of a deck writes into the slide's marks/, checked against the slide's version and its image size;
    without slide, or with a slide of no directory, it is 400. Guards marking a slide."""
    p = make_deck(studio.root)
    (p / "slide-2" / "v1.png").write_bytes(png(16, 9))
    status, body = client.post("/api/marked", {"project": str(p), "slide": 2, "version": 1, "png": data_url(),
                                               "mask": data_url(png(16, 9, alpha=True))})
    assert status == 200
    assert body == {"path": str(p / "slide-2" / "marks" / "v1-marked-1.png"),
                    "mask": str(p / "slide-2" / "marks" / "v1-mask-1.png")}
    for b in ({"project": str(p), "version": 1, "png": data_url()},
              {"project": str(p), "slide": 2, "version": 2, "png": data_url()},
              {"project": str(p), "slide": 4, "version": 1, "png": data_url()},
              {"project": str(p), "slide": 2, "version": 1, "png": data_url(), "mask": data_url(png(9, 16, True))}):
        assert client.post("/api/marked", b)[0] == 400, b


def test_slide_link_out_of_deck(client, studio, tmp_path):
    """A slide-<k> link out of the deck, dangling or not, is shown with `error` and no versions while the other
    slides show; every write and request on it, and assembling the deck, is refused. Guards writes into marks/ of a
    slide and the deck view."""
    p = make_deck(studio.root, slides={1: (1,)})
    outside = tmp_path / "out"
    outside.mkdir()
    (outside / "v1.png").write_bytes(PNG)
    (outside / "v1.json").write_text("{}")
    (p / "deck.json").write_text(json.dumps([{"title": "A"}, {"title": "B"}, {"title": "C"}]))
    (p / "slide-2").symlink_to(outside)
    (p / "slide-3").symlink_to(tmp_path / "missing")
    status, d = client.get(f"/api/project?dir={p}")
    assert status == 200
    s1, s2, s3 = d["deck"]["slides"]
    assert "error" not in s1 and s1["chosen"] == 1
    for s in (s2, s3):
        assert s["error"] and s["versions"] == [] and s["chosen"] is None
    for k in (2, 3):
        assert client.post("/api/marked", {"project": str(p), "slide": k, "version": 1, "png": data_url()})[0] == 400
        assert client.post("/api/chosen", {"project": str(p), "slide": k, "version": 1})[0] == 400
        assert client.post("/api/request", deck_req(p, "variations", slide=k, version=1, count=3))[0] == 400
        assert client.post("/api/request", deck_req(p, slide=k, count=1))[0] == 400
    assert client.post("/api/request", deck_req(p, "assemble", assembly="images"))[0] == 400
    assert sorted(f.name for f in outside.iterdir()) == ["v1.json", "v1.png"]
    assert not (tmp_path / "missing").exists()


def test_empty_deck_json(client, studio):
    """deck.json holding an empty list is a deck of no slides, whatever slide-<k> directories remain. Guards the
    slide count after a rewrite."""
    p = make_deck(studio.root, titles=[])
    _, d = client.get(f"/api/project?dir={p}")
    assert d["deck"]["slides"] == []
    assert client.post("/api/request", deck_req(p, "variations", slide=1, version=1, count=3))[0] == 400
    assert client.post("/api/request", deck_req(p, slide=1, brief="a title slide", count=1))[0] == 202


def test_slide_on_message_and_assemble(client, studio):
    """A deck message may name an existing slide; a missing or bad slide, a slide on a message without a project,
    and any slide on assemble are refused. Guards `slide` on every deck action."""
    p = make_deck(studio.root)
    msg = {"action": "message", "kind": "slide", "project": str(p), "text": "shorter title"}
    assert client.post("/api/request", msg)[0] == 202
    assert client.post("/api/request", {**msg, "slide": 2})[0] == 202
    for b in ({**msg, "slide": 4}, {**msg, "slide": "2"}, {**msg, "slide": 0}, {**msg, "project": None, "slide": 1},
              deck_req(p, "assemble", assembly="images", slide=1)):
        assert client.post("/api/request", b)[0] == 400, b
    assert client.post("/api/request", deck_req(p, "assemble", assembly="images", slide=None))[0] == 202


def test_chosen_concurrent(client, studio):
    """Many /api/chosen calls at once for different slides all land in project.json. Guards the lock around its
    read, change and write."""
    slides = {k: (1, 2) for k in range(1, 13)}
    p = make_deck(studio.root, slides=slides)
    statuses = []
    threads = [threading.Thread(target=lambda k=k: statuses.append(
        client.post("/api/chosen", {"project": str(p), "slide": k, "version": 1})[0])) for k in slides]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert statuses == [200] * len(slides)
    assert json.loads((p / "project.json").read_text())["chosen"] == {str(k): 1 for k in slides}


def test_deck_watcher(studio):
    """Files in slide-<k>/ and slide-<k>/marks/ of a deck give `changed` with project_kind slide; deeper files and
    other subdirectories do not. Guards the page refresh of a deck."""
    p = make_deck(studio.root)
    studio.poll()
    changed = [{"kind": "changed", "project_kind": "slide", "project": str(p)}]
    (p / "slide-1" / "v3.png").write_bytes(PNG)
    assert studio.poll() == changed
    (p / "slide-1" / "marks").mkdir()
    (p / "slide-1" / "marks" / "v1-marked-1.png").write_bytes(PNG)
    assert studio.poll() == changed
    (p / "slide-4").mkdir()
    (p / "slide-4" / "v1.png").write_bytes(PNG)
    assert studio.poll() == changed
    (p / "work" / "renders").mkdir(parents=True)
    (p / "work" / "renders" / "a.png").write_bytes(PNG)
    (p / "slide-1" / "marks" / "deep").mkdir()
    (p / "slide-1" / "marks" / "deep" / "x.png").write_bytes(PNG)
    assert studio.poll() == []
    (p / "deck-1.pptx").write_bytes(b"pptx")
    assert studio.poll() == changed
