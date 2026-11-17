"""Marketplace and plugin manifests, and the frontmatter of every skill."""

import functools
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from tests.subproc import child_env, py_value

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
PLUGINS_DIR = ROOT / "plugins"
PLUGIN_NAMES = ["docs", "media", "dev", "brand", "ai", "studio", "setup"]
DEPENDENCIES = {
    "docs": ["brand", "setup"], "media": ["ai", "brand", "docs", "setup"],
    "dev": ["setup"], "brand": ["setup"], "ai": ["setup"],
    "studio": ["brand", "media", "setup"],
}
SKILL_DIRS = sorted(p.parent for p in PLUGINS_DIR.glob("*/skills/*/SKILL.md"))
MAX_DESCRIPTION = 250
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _marketplace() -> dict:
    return json.loads(MARKETPLACE.read_text(encoding="utf-8"))


def _plugin_json(name: str) -> dict:
    return json.loads((PLUGINS_DIR / name / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))


def test_marketplace_json():
    """The marketplace manifest is named pcingola-skills and lists the plugins in order, each with the source
    plugins/<name>/. Guards the install IDs `<plugin>@pcingola-skills` and the directory source."""
    data = _marketplace()
    assert data["name"] == "pcingola-skills"
    plugins = data["plugins"]
    assert [p["name"] for p in plugins] == PLUGIN_NAMES
    for p in plugins:
        source = (ROOT / p["source"]).resolve()
        assert source == (PLUGINS_DIR / p["name"]).resolve()
        assert source.is_dir()


def test_no_other_plugin_directories():
    """plugins/ holds only the marketplace's plugins. Guards against a plugin directory no marketplace entry
    installs."""
    assert sorted(d.name for d in PLUGINS_DIR.iterdir() if d.is_dir()) == sorted(PLUGIN_NAMES)


@pytest.mark.parametrize("name", PLUGIN_NAMES)
def test_plugin_json(name):
    """Each plugin.json has its directory's name, no version and the expected dependencies, each another
    marketplace plugin. Guards the version label Claude Code takes from the HEAD commit and the plugins a
    skill may load skills from."""
    data = _plugin_json(name)
    assert data["name"] == name
    assert "version" not in data
    assert data.get("dependencies", []) == DEPENDENCIES.get(name, [])
    marketplace_names = {p["name"] for p in _marketplace()["plugins"]}
    for dep in data.get("dependencies", []):
        assert dep in marketplace_names
        assert dep != name


def test_skill_in_exactly_one_plugin():
    """No skill directory name occurs in two plugins. Guards the rule that every skill lives in exactly one
    plugin."""
    names = [d.name for d in PLUGINS_DIR.glob("*/skills/*") if d.is_dir()]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, f"skills in more than one plugin: {duplicates}"


def test_uv_env_copies_identical():
    """Every plugins/<p>/lib/uv_env.sh is byte-identical. Guards the copies, which each plugin must hold,
    against drifting apart."""
    copies = sorted(PLUGINS_DIR.glob("*/lib/uv_env.sh"))
    assert len(copies) > 1
    first = copies[0].read_bytes()
    for c in copies[1:]:
        assert c.read_bytes() == first, f"{c} differs from {copies[0]}"


def test_every_plugin_with_wrappers_has_uv_env():
    """Every plugin with a skill wrapper has lib/uv_env.sh. Guards the wrappers, which source it to keep the
    environments outside the plugin directory."""
    for wrapper in PLUGINS_DIR.glob("*/skills/*/scripts/*.sh"):
        plugin = wrapper.relative_to(PLUGINS_DIR).parts[0]
        assert (PLUGINS_DIR / plugin / "lib" / "uv_env.sh").is_file(), wrapper


def _uv_sources(pyproject: Path) -> dict:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data.get("tool", {}).get("uv", {}).get("sources", {})


LIB_PACKAGES = {
    tomllib.loads(p.read_text(encoding="utf-8"))["project"]["name"]: p.parent.name
    for p in sorted((ROOT / "lib").glob("*/pyproject.toml"))
}


def test_plugin_lib_holds_only_uv_env():
    """Each plugins/<p>/lib/ holds only uv_env.sh. Guards the rule that shared Python code comes from the
    repo-root lib/ as git dependencies."""
    for lib in PLUGINS_DIR.glob("*/lib"):
        assert sorted(e.name for e in lib.iterdir()) == ["uv_env.sh"], lib


def test_lib_sources_follow_main():
    """Every plugin project takes the lib/ packages as git sources from one shared, non-file:// URL,
    subdirectory lib/<dir>, branch main, with no rev, tag or path. Guards installed plugins, whose cache
    copy holds no lib/, and environments that follow the shared code on main."""
    urls = set()
    for pyproject in sorted(PLUGINS_DIR.glob("**/pyproject.toml")):
        for name, source in _uv_sources(pyproject).items():
            assert "path" not in source, f"{pyproject}: path source for {name}"
            if name in LIB_PACKAGES:
                urls.add(source.get("git", "").removesuffix(".git"))
                assert source.get("subdirectory") == f"lib/{LIB_PACKAGES[name]}", f"{pyproject}: {name}"
                assert source.get("branch") == "main", f"{pyproject}: {name} branch"
                assert "rev" not in source and "tag" not in source, f"{pyproject}: {name} pins rev or tag"
    assert len(urls) == 1, f"lib sources use several git URLs: {sorted(urls)}"
    url = urls.pop()
    assert url and not url.startswith("file://"), f"lib git URL is local: {url!r}"


PLUGIN_PYPROJECTS = sorted(PLUGINS_DIR.glob("**/pyproject.toml"))


def _tool_uv(pyproject: Path) -> dict | None:
    return tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}).get("uv")


def test_plugin_projects_have_own_tool_uv():
    """Every uv project under plugins/ has its own [tool.uv] table. uv takes its settings from the nearest
    pyproject.toml with one, so without it a lock picks up the settings of the repository root project."""
    for pyproject in PLUGIN_PYPROJECTS:
        assert _tool_uv(pyproject) is not None, f"{pyproject}: no [tool.uv] table"


def test_lock_dependency_metadata_from_own_project():
    """Each plugin project's uv.lock records the dependency-metadata of its own pyproject.toml and no other.
    Guards against a lock written with the settings of another project."""
    for pyproject in PLUGIN_PYPROJECTS:
        lock = pyproject.parent / "uv.lock"
        locked = tomllib.loads(lock.read_text(encoding="utf-8")).get("manifest", {}).get("dependency-metadata", [])
        declared = (_tool_uv(pyproject) or {}).get("dependency-metadata", [])
        assert sorted(m["name"] for m in locked) == sorted(m["name"] for m in declared), lock


# Model SDKs and model libraries: the provider SDKs, local model libraries and torchaudio's model pipelines.
MODEL_SDK_IMPORT = re.compile(r"^\s*(?:from|import)\s+(google\.genai|google\s+import\s+genai|openai|kokoro_onnx|"
                              r"chatterbox|diffusers|transformers|torchaudio\.pipelines|torchaudio\s+import\s+pipelines)\b",
                              re.M)


def test_model_calls_only_through_ai_models():
    """No module of a plugin project that depends on ai-models imports google-genai, the OpenAI SDK or a model
    library (kokoro-onnx, chatterbox, diffusers, transformers, torchaudio's pipelines). Guards the rule that
    ai_models is the only code that runs a model."""
    modules = [module for pyproject in sorted(PLUGINS_DIR.glob("**/pyproject.toml"))
               if "ai-models" in _uv_sources(pyproject)
               for module in sorted(pyproject.parent.glob("*_tool/**/*.py"))]
    assert modules
    for module in modules:
        match = MODEL_SDK_IMPORT.search(module.read_text())
        assert not match, f"{module.relative_to(ROOT)}: imports {match.group(1)}"


def test_skills_found():
    """The skill glob finds SKILL.md files. Guards the parametrized skill tests against passing on an empty
    list."""
    assert SKILL_DIRS


def _frontmatter(skill_dir: Path) -> str:
    m = FRONTMATTER.match(skill_dir.joinpath("SKILL.md").read_text(encoding="utf-8"))
    assert m, f"{skill_dir.name}: SKILL.md has no --- frontmatter --- block"
    return m.group(1)


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_frontmatter(skill_dir):
    """Each SKILL.md frontmatter parses with yaml.safe_load, its name equals the directory, and its
    description is quoted on one line, at most 250 characters, with `TRIGGER when:`. Guards the Agent
    Skills rules and Claude Code's truncation of descriptions."""
    raw = _frontmatter(skill_dir)
    meta = yaml.safe_load(raw)
    assert isinstance(meta, dict)
    assert meta.get("name") == skill_dir.name

    lines = [line for line in raw.splitlines() if line.startswith("description:")]
    assert len(lines) == 1, "exactly one description: line"
    value = lines[0][len("description:"):].strip()
    assert value[:1] in ("'", '"') and value[-1:] == value[:1], "description must be quoted on one line"

    description = meta.get("description")
    assert isinstance(description, str)
    assert "\n" not in description
    assert len(description) <= MAX_DESCRIPTION, f"{len(description)} chars"
    assert "TRIGGER when:" in description


# --- cross-skill references -------------------------------------------------
#
# A skill that needs another skill loads it with the Skill tool and states the task.
# It never names the other skill's wrapper, script path or references file, and its
# allowed-tools pre-approve only its own wrapper: the loaded skill's own SKILL.md and
# allowed-tools supply the command.

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".pptx", ".potx", ".docx", ".xlsx",
    ".ttf", ".otf", ".woff", ".woff2", ".onnx", ".wav", ".mp3", ".mp4", ".zip", ".gz",
}
# Vendored third-party trees inside a skill directory, relative to the skill directory.
VENDORED = [Path("assets") / "reveal.js"]
SIBLING_PATH = re.compile(r"\$\{?CLAUDE_SKILL_DIR\}?\"?/\.\.(?:/|\b)")
RELATIVE_DIR = re.compile(r"(?<![\w.])\.\./([a-z0-9-]+)/")
ALL_SKILLS = {d.name for d in SKILL_DIRS}
# File names many skills could carry; never attributed to one skill by the bare-name rule.
GENERIC_NAMES = {"README.md", "SKILL.md"}
PROSE_NAME = re.compile(
    r"(?<![<\w/:.-])(" + "|".join(PLUGIN_NAMES) + r"):([a-z0-9][a-z0-9-]*)\b"
)
# Skills with a CLI wrapper: plugins/<p>/skills/<s>/scripts/<s>.sh.
WRAPPER_SKILLS = sorted(
    (d.name for d in SKILL_DIRS if (d / "scripts" / f"{d.name}.sh").is_file()),
    key=lambda n: (-len(n), n),
)
WRAPPER_NAME = re.compile(r"(?<![\w.-])(" + "|".join(map(re.escape, WRAPPER_SKILLS)) + r")\.sh\b")
SKILL_DIR_TOKEN = re.compile(r"<([a-z][a-z0-9-]*):([a-z0-9][a-z0-9-]*|<[^>]+>)>/")
SKILL_PATH = re.compile(r"plugins/([a-z0-9-]+)/skills/([a-z0-9-]+)/")
MD_NAME = re.compile(r"(?<![\w.-])([A-Za-z0-9_-]+\.md)\b")
REFERENCES_FILE = re.compile(r"(?<![\w.-])references/([A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\.md)\b")


def _skills_of(plugin: str) -> set[str]:
    skills = PLUGINS_DIR / plugin / "skills"
    return {d.name for d in skills.iterdir() if d.is_dir()} if skills.is_dir() else set()


def _plugin_of(skill_dir: Path) -> str:
    return skill_dir.relative_to(PLUGINS_DIR).parts[0]


def _read_text(f: Path) -> str | None:
    if not f.is_file() or f.suffix.lower() in BINARY_SUFFIXES:
        return None
    try:
        return f.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


@functools.cache
def _repo_files() -> tuple[Path, ...]:
    """Files under plugins/ that git tracks or would track (ignored files such as a stray
    .venv or __pycache__ are left out)."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "plugins"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return tuple(sorted(ROOT / f for f in out.split("\0") if f))


@functools.cache
def _files_under(directory: Path) -> tuple[Path, ...]:
    return tuple(f for f in _repo_files() if f.is_relative_to(directory))


def _text_files(plugin: str):
    for f in _files_under(PLUGINS_DIR / plugin):
        text = _read_text(f)
        if text is not None:
            yield f, text


def _skill_text_files(skill_dir: Path):
    """Every text file in a skill directory, vendored trees excluded."""
    vendored = [skill_dir / v for v in VENDORED]
    for f in _files_under(skill_dir):
        if any(f.is_relative_to(v) for v in vendored):
            continue
        text = _read_text(f)
        if text is not None:
            yield f, text


def _doc_files(plugin: str):
    """SKILL.md files and Markdown files under a skill's references/."""
    for f, text in _text_files(plugin):
        rel = f.relative_to(PLUGINS_DIR / plugin).parts
        if rel[0] == "skills" and f.suffix == ".md" and (f.name == "SKILL.md" or "references" in rel):
            yield f, text


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _skill_of(f: Path) -> str | None:
    """The skill directory name a file under plugins/ belongs to, or None (plugin lib/)."""
    parts = f.relative_to(PLUGINS_DIR).parts
    return parts[2] if len(parts) > 2 and parts[1] == "skills" else None


@pytest.mark.parametrize("plugin", PLUGIN_NAMES)
def test_no_sibling_paths(plugin):
    """No file under plugins/<p>/ holds `${CLAUDE_SKILL_DIR}/..` in any quoting or a relative `../<s>/` into
    another skill. Guards the rule that a skill reads no other skill's files, which have no fixed location
    in a cache copy."""
    bad = []
    for f, text in _text_files(plugin):
        own = _skill_of(f)
        hits = list(SIBLING_PATH.finditer(text)) + [
            m for m in RELATIVE_DIR.finditer(text) if m.group(1) in ALL_SKILLS and m.group(1) != own
        ]
        for m in sorted(hits, key=lambda m: m.start()):
            snippet = text[m.start():m.end() + 30].splitlines()[0]
            bad.append(f"{f.relative_to(ROOT)}:{_line_of(text, m.start())}: {snippet}")
    assert not bad, "paths out of the skill directory:\n" + "\n".join(bad)


@functools.cache
def _reference_owners() -> dict[str, set[str]]:
    """File name -> names of the skills whose references/ holds a file with that name."""
    owners: dict[str, set[str]] = {}
    for d in SKILL_DIRS:
        for f in _files_under(d / "references"):
            if f.name in GENERIC_NAMES:
                continue
            owners.setdefault(f.name, set()).add(d.name)
    return owners


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_no_reference_to_other_skill_code(skill_dir):
    """No text file in a skill directory names another skill's wrapper, a path under `<p:s>/` or
    plugins/<p>/skills/<s>/, another skill's references/ file, or a bare .md of exactly one other skill's
    references/ next to that skill's name. Guards the rule that skills load each other with the Skill tool
    and refer to formats by name."""
    own = skill_dir.name
    plugin = _plugin_of(skill_dir)
    own_names = {f.name for f in _files_under(skill_dir)}
    owners = _reference_owners()
    bad = []
    for f, text in _skill_text_files(skill_dir):
        where = f.relative_to(ROOT)
        for m in WRAPPER_NAME.finditer(text):
            if m.group(1) != own:
                bad.append(f"{where}:{_line_of(text, m.start())}: {m.group(0)}")
        for m in SKILL_DIR_TOKEN.finditer(text):
            if (m.group(1), m.group(2)) != (plugin, own):
                bad.append(f"{where}:{_line_of(text, m.start())}: {m.group(0)}")
        for m in SKILL_PATH.finditer(text):
            p, s = m.groups()
            if s != own and (PLUGINS_DIR / p / "skills" / s / "SKILL.md").is_file():
                bad.append(f"{where}:{_line_of(text, m.start())}: {m.group(0)}")
        for m in REFERENCES_FILE.finditer(text):
            name = m.group(1)
            if not (skill_dir / "references" / name).is_file() and any(
                (d / "references" / name).is_file() for d in SKILL_DIRS if d != skill_dir
            ):
                bad.append(f"{where}:{_line_of(text, m.start())}: {m.group(0)} (another skill's file)")
        for m in MD_NAME.finditer(text):
            name = m.group(1)
            others = owners.get(name, set()) - {own}
            if name in own_names or len(others) != 1:
                continue
            (other,) = others
            if re.search(rf"(?<![\w-]){re.escape(other)}(?![\w-])", text):
                bad.append(f"{where}:{_line_of(text, m.start())}: {name} (a references/ file of {other})")
    assert not bad, f"{own} names other skills' code:\n" + "\n".join(bad)


@pytest.mark.parametrize("plugin", PLUGIN_NAMES)
def test_plugin_skill_references(plugin):
    """Every prose `plugin:skill` in a SKILL.md or references/ file names an existing skill of that plugin,
    single letters excepted as metavariables. Guards against instructions to load a renamed or missing
    skill."""
    bad = []
    for f, text in _doc_files(plugin):
        where = f.relative_to(ROOT)
        for m in PROSE_NAME.finditer(text):
            p, s = m.groups()
            if len(s) > 1 and s not in _skills_of(p):
                bad.append(f"{where}:{_line_of(text, m.start())}: {m.group(0)} names no skill of plugin {p}")
    assert not bad, "\n".join(bad)


def _allowed_tools(skill_dir: Path) -> str:
    meta = yaml.safe_load(_frontmatter(skill_dir))
    value = meta.get("allowed-tools") or ""
    return value if isinstance(value, str) else " ".join(value)


def _bash_rules(tools: str) -> list[str]:
    return re.findall(r"Bash\([^)]*\)", tools)


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_allowed_tools_no_unanchored_bash_rules(skill_dir):
    """No allowed-tools entry starts with `Bash(*`. Guards against a rule that pre-approves any command ending
    in the wrapper path."""
    entries = _bash_rules(_allowed_tools(skill_dir))
    assert not [e for e in entries if e.startswith("Bash(*")], entries


def _has_tool(tools: str, name: str) -> bool:
    return re.search(rf"(^|[\s,]){name}($|[\s,])", tools) is not None


# Bash entries other than a skill's own wrapper rules, as {skill name: {entry: reason}}.
# Bare `Bash` is listed as "Bash".
BASH_RULE_ALLOWLIST: dict[str, dict[str, str]] = {
    "plan": {"Bash": "inspects the repository being planned (git, ls, grep, test runs)"},
    "pptx-author": {"Bash": "runs jq to merge and query per-slide JSON payloads, and magick to measure, crop and compare renders"},
}


def _own_wrapper_rule(rule: str, skill: str) -> bool:
    return rule in (f"Bash(scripts/{skill}.sh:*)", f"Bash(${{CLAUDE_SKILL_DIR}}/scripts/{skill}.sh:*)")


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_allowed_tools_no_other_skill_wrappers(skill_dir):
    """Every Bash entry in allowed-tools is the skill's own wrapper rule or in BASH_RULE_ALLOWLIST, bare Bash
    only when allowlisted, and no `Bash(` entry is unclosed. Guards the rule that a caller never
    pre-approves another skill's wrapper."""
    skill = skill_dir.name
    tools = _allowed_tools(skill_dir)
    rest = re.sub(r"Bash\([^)]*\)", " ", tools)
    assert "Bash(" not in rest, f"unclosed Bash( entry in {tools!r}"
    allow = BASH_RULE_ALLOWLIST.get(skill, {})
    bad = [r for r in _bash_rules(tools) if not _own_wrapper_rule(r, skill) and r not in allow]
    if _has_tool(rest, "Bash") and "Bash" not in allow:
        bad.append("Bash")
    assert not bad, f"{skill_dir.relative_to(ROOT)}/SKILL.md allowed-tools entries not allowed:\n" + "\n".join(bad)


def _reachable(plugin: str) -> set[str]:
    """The caller's own plugin plus its plugin.json dependencies."""
    return {plugin, *_plugin_json(plugin).get("dependencies", [])}


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_loading_listed(skill_dir):
    """A skill whose SKILL.md body or references name another skill as `plugin:skill` lists Skill in
    allowed-tools and has that skill's plugin as its own or a dependency. Guards loads that would fail in
    an install without the other plugin."""
    plugin = _plugin_of(skill_dir)
    reachable = _reachable(plugin)
    own = (plugin, skill_dir.name)
    skill_md = skill_dir / "SKILL.md"
    files = [skill_md, *(f for f in _files_under(skill_dir / "references") if f.suffix == ".md")]
    named, unreachable = [], []
    for f in files:
        text = f.read_text(encoding="utf-8")
        start = FRONTMATTER.match(text).end() if f == skill_md else 0
        for m in PROSE_NAME.finditer(text, start):
            if len(m.group(2)) == 1 or m.groups() == own or m.group(2) not in _skills_of(m.group(1)):
                continue
            hit = f"{f.relative_to(ROOT)}:{_line_of(text, m.start())}: {m.group(0)}"
            named.append(hit)
            if m.group(1) not in reachable:
                unreachable.append(hit)
    assert not unreachable, (
        f"skills named outside {plugin} and its dependencies {sorted(reachable - {plugin})}:\n"
        + "\n".join(unreachable)
    )
    if named:
        assert _has_tool(_allowed_tools(skill_dir), "Skill"), (
            f"{skill_md.relative_to(ROOT)} allowed-tools lacks `Skill`; the skill names:\n" + "\n".join(named)
        )


def _shell_data_dir(plugin_root: Path, env: dict[str, str]) -> Path:
    """The plugin data directory plugin_env resolves, run as a wrapper runs it."""
    script = (
        f'set -eu -o pipefail; source "{plugin_root}/lib/uv_env.sh"; '
        f'plugin_env "{plugin_root}/lib"; echo "$PLUGIN_ENV_DIR"'
    )
    out = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return Path(out.stdout.strip().split("/env/")[0])


def _copy_plugin(plugin: str, dest: Path) -> Path:
    """The manifest and lib/ of a plugin copied to `dest`."""
    (dest / ".claude-plugin").mkdir(parents=True)
    (dest / ".claude-plugin" / "plugin.json").write_bytes(
        (PLUGINS_DIR / plugin / ".claude-plugin" / "plugin.json").read_bytes()
    )
    (dest / "lib").mkdir()
    (dest / "lib" / "uv_env.sh").write_bytes((PLUGINS_DIR / plugin / "lib" / "uv_env.sh").read_bytes())
    return dest


def _layouts(tmp_path: Path, plugin: str):
    """(plugin root, CLAUDE_CONFIG_DIR or None, expected data directory)."""
    home = tmp_path / "home"
    marketplace = _marketplace()["name"]
    yield PLUGINS_DIR / plugin, None, home / ".claude" / "plugins" / "data" / f"{plugin}-{marketplace}"
    cache = _copy_plugin(plugin, home / ".claude" / "plugins" / "cache" / "mk" / plugin / "0123abcd")
    yield cache, None, home / ".claude" / "plugins" / "data" / f"{plugin}-mk"
    cfg = _copy_plugin(plugin, home / "cfg" / "plugins" / "cache" / "mk2" / plugin / "v1")
    yield cfg, "~/cfg", home / "cfg" / "plugins" / "data" / f"{plugin}-mk2"


@pytest.mark.parametrize(
    "plugin", sorted(p for p in PLUGIN_NAMES if (PLUGINS_DIR / p / "lib" / "uv_env.sh").is_file())
)
def test_uv_env_data_dir(plugin, tmp_path):
    """uv_env.sh's plugin_env and plugin_settings resolve the same data directory in place, in a cache copy
    and under a CLAUDE_CONFIG_DIR with `~`. Guards wrappers and settings agreeing on where environments and
    data live."""
    (tmp_path / "home").mkdir()
    for root, config_dir, expected in _layouts(tmp_path, plugin):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PLUGIN_DATA", "CLAUDE_CONFIG_DIR")}
        env["HOME"] = str(tmp_path / "home")
        if config_dir:
            env["CLAUDE_CONFIG_DIR"] = config_dir
        assert _shell_data_dir(root, env) == expected, root
        got = py_value("from plugin_settings import Plugin", f"Plugin.of({str(root / 'lib')!r}).data_dir()",
                       child_env(env))
        assert got == str(expected), root
