"""Unit tests of the editor server's comment storage, its checks of a comment body, the prompt, the messages from
the mod, the `index.html` watch and the origin check of POST requests."""
from __future__ import annotations

import http.client
import json
import os
import queue
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from html_animation_server.comment import CommentInput
from html_animation_server.comment_store import CommentStore
from html_animation_server.editor import Editor
from html_animation_server.handler import serve
from html_animation_server.http_error import HttpError
from html_animation_server.kinds import CommentState
from html_animation_server.mark import Mark
from html_animation_server.prompt import comment_prompt

BODY = {"t": 2.5, "chapter": "intro", "mark": {"point": {"x": 640, "y": 360}}, "ids": ["title", "intro-bg"],
        "message": "Make the title larger."}


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    anim = tmp_path / "anim"
    anim.mkdir()
    (anim / "index.html").write_text("<html></html>", encoding="utf-8")
    (anim / "animation.json").write_text(json.dumps({"title": "T", "width": 1920, "height": 1080}), encoding="utf-8")
    return anim


def test_mark_point_and_rect() -> None:
    """A point and a rectangle mark parse, convert back to JSON and give the CLI's `--mark` argument."""
    point = Mark.from_json({"point": {"x": 10, "y": 20.25}})
    assert point.cli_arg() == "point:10,20.2"
    assert point.to_json() == {"point": {"x": 10.0, "y": 20.25}}
    rect = Mark.from_json({"rect": {"x": 1, "y": 2, "w": 300, "h": 40.5}})
    assert rect.cli_arg() == "rect:1,2,300,40.5"
    assert Mark.from_json(rect.to_json()) == rect


@pytest.mark.parametrize("mark", [
    None, {}, {"point": {"x": 1}}, {"point": {"x": "1", "y": 2}}, {"point": {"x": True, "y": 2}},
    {"rect": {"x": 1, "y": 2, "w": 0, "h": 3}}, {"point": {"x": 1, "y": 2}, "rect": {"x": 1, "y": 2, "w": 1, "h": 1}},
    {"point": {"x": float("nan"), "y": 2}},
])
def test_bad_mark_is_400(mark: object) -> None:
    """A mark that is neither a point nor a rectangle of finite numbers is refused with 400."""
    with pytest.raises(HttpError) as raised:
        Mark.from_json(mark)
    assert raised.value.status == 400


@pytest.mark.parametrize("change", [
    {"t": -1}, {"t": "2"}, {"chapter": 3}, {"ids": "title"}, {"ids": [1]}, {"ids": [""]}, {"message": "  "},
    {"message": None},
])
def test_bad_body_is_400(change: dict) -> None:
    """A comment body with a wrong t, chapter, ids or message is refused with 400."""
    with pytest.raises(HttpError) as raised:
        CommentInput.from_json({**BODY, **change})
    assert raised.value.status == 400


def test_store_append_and_done(folder: Path) -> None:
    """comments.json holds the appended comments with the fields of the interfaces, and `done` sets the state and the answer."""
    store = CommentStore(folder / "comments.json")
    assert store.load() == []
    first = store.append("c1", CommentInput.from_json(BODY), folder / "marks" / "c1.png")
    store.append("c2", CommentInput.from_json({**BODY, "mark": {"rect": {"x": 0, "y": 0, "w": 5, "h": 5}}}),
                 folder / "marks" / "c2.png")
    stored = json.loads((folder / "comments.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in stored] == ["c1", "c2"]
    assert set(stored[0]) == {"id", "t", "chapter", "mark", "ids", "message", "png", "state", "answer", "created"}
    assert stored[0]["state"] == "open" and stored[0]["answer"] is None
    assert stored[0]["png"] == str(folder / "marks" / "c1.png")
    assert first.message == "Make the title larger."

    done = store.mark_done("c1", "The title is 20% larger.")
    assert done is not None and done.state is CommentState.DONE
    again = store.load()
    assert again[0].state is CommentState.DONE and again[0].answer == "The title is 20% larger."
    assert again[1].state is CommentState.OPEN
    assert store.mark_done("missing", None) is None


def test_store_keeps_unknown_keys(folder: Path) -> None:
    """Rewriting comments.json keeps keys the server does not know."""
    store = CommentStore(folder / "comments.json")
    store.append("c1", CommentInput.from_json(BODY), folder / "marks" / "c1.png")
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data[0]["agent_note"] = "kept"
    store.path.write_text(json.dumps(data), encoding="utf-8")
    store.mark_done("c1", None)
    assert json.loads(store.path.read_text(encoding="utf-8"))[0]["agent_note"] == "kept"


def test_prompt_holds_the_comment(folder: Path) -> None:
    """The request prompt names the skill, the folder, the comment, t, chapter, mark, ids, PNG, message and the post tool, and tells the agent to snapshot before its first edit (the server takes none)."""
    comment = CommentStore(folder / "comments.json").append("c9", CommentInput.from_json(BODY), folder / "m.png")
    text = comment_prompt(comment, folder)
    for part in ("media:html-animation", str(folder), "c9", "t = 2.500 s", "`intro`", "x=640, y=360", "`title`",
                 "`intro-bg`", str(folder / "m.png"), "Make the title larger.", "`post` tool",
                 "Run `snapshot` on the folder immediately before your first edit"):
        assert part in text


def test_agent_messages(folder: Path) -> None:
    """post, note and done from the mod reach the page as events; done stores the last post as the answer; bad ones are refused."""
    lines: list[dict] = []
    editor = Editor(folder, emit=lines.append)
    CommentStore(folder / "comments.json").append("c1", CommentInput.from_json(BODY), folder / "m.png")
    editor.current = "c1"
    client = editor.connect()
    editor.agent_message({"type": "note", "text": "Editing chapter intro."})
    editor.agent_message({"type": "post", "text": "Done: larger title.", "images": [str(folder / "index.html"), "/x.png"]})
    editor.agent_message({"type": "done", "id": "c1"})
    events = [client.get_nowait() for _ in range(3)]
    assert [e["kind"] for e in events] == ["note", "post", "comment"]
    assert events[1]["images"] == [{"path": str(folder / "index.html"), "url": "/anim/index.html"},
                                   {"path": "/x.png", "url": None}]
    assert events[2]["comment"]["state"] == "done" and events[2]["comment"]["answer"] == "Done: larger title."
    assert [m["kind"] for m in editor.state()["messages"]] == ["note", "post"]
    with pytest.raises(HttpError):
        editor.agent_message({"type": "shout"})
    with pytest.raises(HttpError):
        editor.agent_message({"type": "done", "id": "missing"})
    assert lines == []


def test_stdin_lines(folder: Path) -> None:
    """JSON lines on stdin are handled as mod messages; bad lines are skipped."""
    editor = Editor(folder, emit=lambda line: None)
    read, write = os.pipe()
    with os.fdopen(write, "w") as w:
        w.write('{"type": "note", "text": "one"}\nnot json\n\n{"type": "post", "text": "two"}\n')
    with os.fdopen(read) as r:
        editor.read_stdin(r)
    assert [m["text"] for m in editor.messages] == ["one", "two"]


def test_stop_line(folder: Path) -> None:
    """A stop from the page writes the `stop` line, with the id when one is given; a stopped comment stays open and is shown as stopped."""
    lines: list[dict] = []
    editor = Editor(folder, emit=lines.append)
    CommentStore(folder / "comments.json").append("c1", CommentInput.from_json(BODY), folder / "m.png")
    client = editor.connect()
    editor.stop(None)
    editor.stop("c1")
    assert lines == [{"type": "stop"}, {"type": "stop", "id": "c1"}]
    event = client.get_nowait()
    assert event["kind"] == "comment" and event["comment"]["stopped"] is True
    assert event["comment"]["state"] == "open"
    assert [c["stopped"] for c in editor.state()["comments"]] == [True]


def test_index_change_event(folder: Path) -> None:
    """A changed index.html mtime is sent to the page as `change`, an unchanged one sends nothing."""
    editor = Editor(folder, emit=lambda line: None)
    client = editor.connect()
    editor.poll_index()
    with pytest.raises(queue.Empty):
        client.get_nowait()
    stat = (folder / "index.html").stat()
    os.utime(folder / "index.html", (stat.st_atime, stat.st_mtime + 5))
    editor.poll_index()
    assert client.get_nowait()["kind"] == "change"


@pytest.fixture
def address(folder: Path) -> Iterator[tuple[str, int]]:
    editor = Editor(folder, emit=lambda line: None)
    httpd = serve(editor)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[0], httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def post(address: tuple[str, int], path: str, body: object, origin: str | None, extra: dict | None = None) -> int:
    connection = http.client.HTTPConnection(*address, timeout=10)
    headers = {"content-type": "application/json", **(extra or {})}
    if origin is not None:
        headers["origin"] = origin
    try:
        connection.request("POST", path, json.dumps(body), headers)
        return connection.getresponse().status
    finally:
        connection.close()


def test_origin_check(address: tuple[str, int]) -> None:
    """POSTs with no Origin or the server's own are taken; the sandboxed animation's `null` and other sites get 403."""
    own = f"http://{address[0]}:{address[1]}"
    note = {"type": "note", "text": "hi"}
    assert post(address, "/api/agent", note, None) == 200
    assert post(address, "/api/agent", note, own) == 200
    assert post(address, "/api/agent", note, "null") == 403
    assert post(address, "/api/comment", BODY, "null") == 403
    assert post(address, "/api/stop", {}, "https://example.com") == 403
    assert post(address, "/api/comment", {**BODY, "message": ""}, own) == 400


def get(address: tuple[str, int], path: str, headers: dict) -> int:
    connection = http.client.HTTPConnection(*address, timeout=10)
    try:
        connection.request("GET", path, headers=headers)
        return connection.getresponse().status
    finally:
        connection.close()


def test_host_check(address: tuple[str, int]) -> None:
    """A request whose Host is not 127.0.0.1 or localhost on the server's port (DNS rebinding) gets 403, as in the
    Studio server; localhost on the right port is taken."""
    port = address[1]
    evil = {"host": f"evil.example:{port}"}
    assert get(address, "/api/state", evil) == 403
    assert get(address, "/anim/index.html", evil) == 403
    assert post(address, "/api/comment", BODY, None, evil) == 403
    assert post(address, "/api/agent", {"type": "note", "text": "hi"}, None, evil) == 403
    assert get(address, "/api/state", {"host": f"127.0.0.1:{port + 1}"}) == 403
    assert get(address, "/api/state", {"host": f"localhost:{port}"}) == 200


def test_fetch_site_check(address: tuple[str, int]) -> None:
    """`sec-fetch-site` other than same-origin or none gets 403, except a GET of the animation's files, which the
    sandboxed iframe (an opaque origin) loads as cross-site."""
    assert get(address, "/api/state", {"sec-fetch-site": "cross-site"}) == 403
    assert get(address, "/api/state", {"sec-fetch-site": "same-site"}) == 403
    assert get(address, "/api/state", {"sec-fetch-site": "same-origin"}) == 200
    assert get(address, "/anim/index.html", {"sec-fetch-site": "cross-site"}) == 200
    assert post(address, "/api/agent", {"type": "note", "text": "hi"}, None, {"sec-fetch-site": "cross-site"}) == 403
