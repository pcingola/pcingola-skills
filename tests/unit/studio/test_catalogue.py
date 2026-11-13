"""Unit tests of the style catalogue: finding the brand plugin, reading its catalogue and brands, /api/catalogue,
the sample allowlist of /file and the catalogue event."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio_server.catalogue import brand_from_list, find_brand_plugin, read_catalogue
from studio_server.server import LOADING

from tests.settings_env import write_config
from tests.subproc import child_env, py_value

from .conftest import PNG


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def plugin_dir(parent: Path, name: str) -> Path:
    d = parent / name
    write_json(d / ".claude-plugin" / "plugin.json", {"name": name})
    return d


def make_brand(root: Path, name: str) -> Path:
    (root / name).mkdir(parents=True)
    (root / name / "brand.yaml").write_text(f"name: {name}\n", encoding="utf-8")
    return root / name


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A marketplace `mk` with a studio and a brand plugin; the brand plugin has two styles and two brands."""
    m = tmp_path / "checkout"
    write_json(m / ".claude-plugin" / "marketplace.json", {"name": "mk"})
    plugin_dir(m / "plugins", "studio")
    brand = plugin_dir(m / "plugins", "brand")
    style = brand / "skills" / "style"
    for name in ("ink", "pop"):
        (style / "samples").mkdir(parents=True, exist_ok=True)
        (style / "samples" / f"{name}.png").write_bytes(PNG)
    write_json(style / "references" / "catalogue.json", [
        {"name": "ink", "description": "ink wash", "tags": ["ink"], "suits": ["slide"], "sample": "samples/ink.png"},
        {"name": "pop", "description": "pop art", "tags": ["pop"], "suits": [], "sample": "samples/pop.png"},
    ])
    bundled = brand / "skills" / "brand" / "brands"
    make_brand(bundled, "neutral")
    make_brand(bundled, "acme")
    (bundled / "not-a-brand").mkdir()
    return m


def studio_root(checkout: Path) -> Path:
    return checkout / "plugins" / "studio"


def brand_root(checkout: Path) -> Path:
    return checkout / "plugins" / "brand"


def entry(id_: str, read_from: Path | None = None, install: Path | None = None) -> dict:
    e = {"id": id_, "version": "1", "scope": "user", "enabled": True}
    if read_from is not None:
        e["readFromFolder"] = str(read_from)
    if install is not None:
        e["installPath"] = str(install)
    return e


# Finding the brand plugin

def test_read_from_folder_preferred(tmp_path):
    """readFromFolder wins over installPath; installPath is used when readFromFolder is absent or not a directory.
    Guards reading a plugin loaded in place."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    assert brand_from_list([entry("brand@x", read_from=a, install=b)]) == a
    assert brand_from_list([entry("brand@x", install=b)]) == b
    assert brand_from_list([entry("brand@x", read_from=tmp_path / "gone", install=b)]) == b
    assert brand_from_list([entry("brand@x", read_from=tmp_path / "gone")]) is None
    assert brand_from_list([entry("branding@x", install=a), "junk", {"id": 3}]) is None


def test_disabled_entries_ignored(tmp_path):
    """A brand or studio entry with enabled false is skipped. Guards using a plugin the user turned off."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    off = {**entry("brand@mk", install=a), "enabled": False}
    assert brand_from_list([off, entry("brand@other", install=b)]) == b
    assert brand_from_list([off]) is None
    studio_off = {**entry("studio@mk"), "enabled": False}
    assert brand_from_list([studio_off, entry("brand@other", install=b), entry("brand@mk", install=a)]) == b


def test_studio_marketplace_preferred(tmp_path):
    """The brand plugin of the listed studio plugin's marketplace wins; without a studio entry, the first brand
    entry. Guards a second marketplace's brand plugin shadowing ours."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    brands = [entry("brand@other", install=a), entry("brand@mk", install=b)]
    assert brand_from_list([*brands, entry("studio@mk", install=b)]) == b
    assert brand_from_list([entry("studio@other", install=a), *reversed(brands)]) == a
    assert brand_from_list([entry("studio@nope", install=a), *brands]) == a
    assert brand_from_list(brands) == a


def test_find_from_plugin_list(checkout, tmp_path):
    """find_brand_plugin takes the brand folder from the plugin list, in the listed studio plugin's marketplace.
    Guards the discovery at start."""
    other, ours = tmp_path / "other", tmp_path / "ours"
    other.mkdir(), ours.mkdir()
    entries = [entry("brand@other", install=other), entry("brand@mk", read_from=ours), entry("studio@mk")]
    assert find_brand_plugin(studio_root(checkout), lambda: entries) == ours


def test_find_falls_back_to_sibling(checkout, tmp_path):
    """When the command fails or lists no brand plugin, the sibling brand directory of the checkout is used; with
    no sibling, None. Guards a session with the plugins loaded from the checkout."""
    assert find_brand_plugin(studio_root(checkout), lambda: None) == brand_root(checkout)
    assert find_brand_plugin(studio_root(checkout), lambda: []) == brand_root(checkout)
    lonely = plugin_dir(tmp_path / "alone", "studio")
    assert find_brand_plugin(lonely, lambda: None) is None


def test_plugin_list_without_claude(tmp_path):
    """plugin_list returns None when no claude binary is on PATH. Guards the fallback to the sibling checkout."""
    got = py_value("from studio_server.catalogue import plugin_list", "plugin_list()",
                   child_env(PATH=str(tmp_path)))
    assert got is None


# Reading the catalogue and the brands

def test_read_catalogue(checkout):
    """Styles keep their fields with each sample made absolute under skills/style/; the samples are returned for the
    allowlist; the brands are the bundled folders with a brand.yaml. Guards /api/catalogue's content."""
    root = brand_root(checkout)
    cat, samples = read_catalogue(root)
    style_dir = (root / "skills" / "style").resolve()
    assert cat == {"styles": [
        {"name": "ink", "description": "ink wash", "tags": ["ink"], "suits": ["slide"],
         "sample": str(style_dir / "samples" / "ink.png")},
        {"name": "pop", "description": "pop art", "tags": ["pop"], "suits": [],
         "sample": str(style_dir / "samples" / "pop.png")},
    ], "brands": ["acme", "neutral"]}
    assert samples == {style_dir / "samples" / "ink.png", style_dir / "samples" / "pop.png"}


def test_read_catalogue_skips_bad_styles(checkout):
    """A style without a string name or sample is left out. Guards the allowlist against odd entries."""
    root = brand_root(checkout)
    write_json(root / "skills" / "style" / "references" / "catalogue.json",
               [{"name": "ok", "sample": "s.png"}, {"name": "x"}, {"sample": "y.png"}, "z"])
    cat, samples = read_catalogue(root)
    assert [s["name"] for s in cat["styles"]] == ["ok"] and len(samples) == 1


def test_read_catalogue_null_sample(checkout):
    """A style with `"sample": null` (no sample image yet) is kept with a null sample and adds nothing to the
    allowlist. Guards that a style without a sample still shows in Studio."""
    root = brand_root(checkout)
    write_json(root / "skills" / "style" / "references" / "catalogue.json",
               [{"name": "ok", "sample": "s.png"}, {"name": "new", "description": "d", "sample": None}])
    cat, samples = read_catalogue(root)
    assert [s["name"] for s in cat["styles"]] == ["ok", "new"]
    assert cat["styles"][1] == {"name": "new", "description": "d", "sample": None}
    assert samples == {(root / "skills" / "style" / "s.png").resolve()}


def test_read_catalogue_errors(checkout):
    """No brand plugin: empty lists and an error. No catalogue file, bad JSON or a non-list: no styles and an
    error, the brands still listed. Guards the page's error notice and the brand list not hanging on the file."""
    cat, samples = read_catalogue(None)
    assert cat["styles"] == [] and cat["brands"] == [] and "brand plugin" in cat["error"] and not samples
    path = brand_root(checkout) / "skills" / "style" / "references" / "catalogue.json"
    for content in ("[not json", '{"styles": []}', None):
        if content is None:
            path.unlink()
        else:
            path.write_text(content, encoding="utf-8")
        cat, samples = read_catalogue(brand_root(checkout))
        assert cat["styles"] == [] and str(path) in cat["error"] and not samples
        assert cat["brands"] == ["acme", "neutral"]


def test_list_brands_with_brand_path(checkout, tmp_path):
    """BRAND_PATH directories add brands after the bundled ones; the first folder of a name wins; empty entries,
    missing directories and repeats are skipped; `~` is expanded. Guards matching the brand CLI's list."""
    home = tmp_path / "home"
    extra, more = tmp_path / "extra", home / "more"
    make_brand(extra, "zeta")
    make_brand(extra, "neutral")
    make_brand(more, "beta")
    setting = f"{extra}::{tmp_path / 'missing'}:{extra}:~/more"
    # `~` expands against HOME, so list_brands runs in a child process with HOME in tmp_path.
    got = py_value("from pathlib import Path\nfrom studio_server.catalogue import list_brands",
                   f"list_brands(Path({str(brand_root(checkout))!r}), {setting!r})", child_env(HOME=str(home)))
    assert got == ["acme", "neutral", "zeta", "beta"]


def test_brand_path_from_settings(checkout, tmp_path):
    """BRAND_PATH comes from the process environment, overridden by config.yaml, as the brand CLI reads it.
    Guards the catalogue listing the brands the brand CLI finds."""
    from_process, from_file = tmp_path / "process", tmp_path / "file"
    make_brand(from_process, "proc")
    make_brand(from_file, "filed")
    imports = "from pathlib import Path\nfrom studio_server.catalogue import read_catalogue"
    expr = f"read_catalogue(Path({str(brand_root(checkout))!r}))[0]['brands']"
    env = child_env(CLAUDE_CONFIG_DIR=str(tmp_path / "config"), BRAND_PATH=str(from_process))
    assert py_value(imports, expr, env) == ["acme", "neutral", "proc"]
    cfg = write_config(tmp_path / "config.yaml", {"BRAND_PATH": str(from_file)})
    assert py_value(imports, expr, {**env, "SKILLS_CONFIG": str(cfg)}) == ["acme", "neutral", "filed"]


# The server

def test_catalogue_loading_then_loaded(studio, client, events, checkout):
    """/api/catalogue answers loading until the catalogue is read, then the catalogue, with a catalogue event to
    every page. Guards the page's catalogue refresh."""
    assert client.get("/api/catalogue") == (200, LOADING)
    studio.find_brand = lambda: brand_root(checkout)
    ev = events()
    studio.start_catalogue().join(10)
    assert ev.next() == {"kind": "catalogue"}
    status, cat = client.get("/api/catalogue")
    assert status == 200 and [s["name"] for s in cat["styles"]] == ["ink", "pop"] and "loading" not in cat
    assert cat["brands"] == ["acme", "neutral"]


def test_catalogue_error_answer(studio, client, events):
    """With no brand plugin found, /api/catalogue has empty lists and an error, and the event is still sent.
    Guards the page leaving its loading state."""
    studio.find_brand = lambda: None
    ev = events()
    studio.load_catalogue()
    assert ev.next() == {"kind": "catalogue"}
    status, cat = client.get("/api/catalogue")
    assert status == 200 and cat["styles"] == [] and cat["brands"] == [] and cat["error"]


def test_catalogue_lookup_failure(studio, client):
    """An exception in the lookup is answered as an error, not a page loading forever. Guards the loader thread."""
    def boom():
        raise RuntimeError("broken")
    studio.find_brand = boom
    studio.load_catalogue()
    assert "broken" in client.get("/api/catalogue")[1]["error"]


def test_sample_allowlist(studio, client, checkout):
    """/file serves the catalogue's samples, and no other file of the brand plugin, only once the catalogue is
    read. Guards the sample allowlist."""
    root = brand_root(checkout)
    sample = (root / "skills" / "style" / "samples" / "ink.png").resolve()
    other = sample.parent / "other.png"
    other.write_bytes(PNG)
    assert client.call("GET", f"/file?path={sample}")[0] == 403
    studio.find_brand = lambda: root
    studio.load_catalogue()
    status, headers, body = client.call("GET", f"/file?path={sample}")
    assert status == 200 and body == PNG and headers["content-security-policy"] == "sandbox"
    for refused in (other, root / "skills" / "style" / "references" / "catalogue.json"):
        assert client.call("GET", f"/file?path={refused}")[0] == 403, refused


def test_no_catalogue_post(client, emitted, events):
    """POST /catalogue is gone (404) and a connecting page makes the server print nothing. Guards against the
    agent-made catalogue coming back."""
    assert client.post("/catalogue", {"styles": [], "brands": []})[0] == 404
    events()
    assert emitted == []
