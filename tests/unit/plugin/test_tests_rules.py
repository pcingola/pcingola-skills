"""Rules that every test file follows, checked on the source with `ast`."""

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]
TEST_TIMEOUT = 30  # pytest-timeout of tests/unit and tests/integration (root pyproject.toml)
SUBPROCESS_CALLS = {"run", "check_output", "check_call", "call"}
PROCESS_WAITS = {"communicate", "wait"}


def _files() -> list[Path]:
    """Every .py under tests/ except the full-size suite tests/models/, which sets larger timeouts."""
    return sorted(p for p in TESTS.rglob("*.py") if "models" not in p.relative_to(TESTS).parts[:1])


def _too_long(node: ast.expr | None) -> bool:
    """True when `node` is None or a number constant of TEST_TIMEOUT or more. Any other expression (a name, an
    attribute, arithmetic) is not evaluated and passes."""
    if node is None:
        return True
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and node.value >= TEST_TIMEOUT


def _timeout(call: ast.Call, position: int | None = None) -> ast.expr | None:
    """The `timeout` keyword of `call`, else its positional argument at `position` (a helper's `timeout`
    parameter), None when absent."""
    keyword = next((k.value for k in call.keywords if k.arg == "timeout"), None)
    if keyword is None and position is not None and position < len(call.args):
        return call.args[position]
    return keyword


def _helpers(trees: dict[Path, ast.Module]) -> dict[str, int | None]:
    """The functions under tests/ that take a `timeout` parameter: name -> the position of `timeout` among the
    arguments of a call (None for a keyword-only parameter; a leading `self` or `cls` is not counted)."""
    out = {}
    for tree in trees.values():
        for f in ast.walk(tree):
            if not isinstance(f, ast.FunctionDef):
                continue
            names = [a.arg for a in f.args.args]
            if names[:1] in (["self"], ["cls"]):
                names = names[1:]
            if "timeout" in names:
                out[f.name] = names.index("timeout")
            elif any(a.arg == "timeout" for a in f.args.kwonlyargs):
                out[f.name] = None
    return out


def _subprocess_names(tree: ast.Module) -> set[str]:
    """The local names of the SUBPROCESS_CALLS that `tree` imports with `from subprocess import ...`."""
    return {a.asname or a.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            and node.module == "subprocess" for a in node.names if a.name in SUBPROCESS_CALLS}


def _violations(path: Path, tree: ast.Module, helpers: dict[str, int | None]) -> list[str]:
    """Each subprocess call, process wait, helper call or helper default in `tree` with no timeout or one of
    TEST_TIMEOUT seconds or more, as file:line."""
    where = path.relative_to(TESTS.parent)
    imported = _subprocess_names(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in helpers:
            args = node.args
            pos = args.args[len(args.args) - len(args.defaults):]
            defaults = {a.arg: d for a, d in [*zip(pos, args.defaults), *zip(args.kwonlyargs, args.kw_defaults)]}
            if "timeout" in defaults and _too_long(defaults["timeout"]):
                out.append(f"{where}:{node.lineno} {node.name}(timeout=...) default")
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
        is_subprocess = ((isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "subprocess"
                          and name in SUBPROCESS_CALLS) or (isinstance(f, ast.Name) and name in imported))
        is_wait = isinstance(f, ast.Attribute) and name in PROCESS_WAITS
        if (is_subprocess or is_wait) and _too_long(_timeout(node)):
            out.append(f"{where}:{node.lineno} {name}")
        elif name in helpers and (t := _timeout(node, helpers[name])) is not None and _too_long(t):
            out.append(f"{where}:{node.lineno} {name}")
    return out


def test_every_subprocess_has_a_short_timeout():
    """Every subprocess a test outside tests/models/ starts has a timeout below the 30 s test timeout, so a hung
    child fails the test with its own message. Checked: `subprocess.run`, `check_output`, `check_call` and `call`,
    also imported with `from subprocess import`, and `.communicate` and `.wait` of a started process, need a
    `timeout` keyword below 30; a test helper with a `timeout` parameter needs a default below 30, and a call to it
    may not pass 30 or more, as a keyword or by position. Only number literals are checked: a timeout given as a
    name or another expression passes unevaluated. Reads of a running process (`proc.stdout.readline()`) are not
    checked and are bounded by the test timeout only."""
    trees = {p: ast.parse(p.read_text(encoding="utf-8"), str(p)) for p in _files()}
    helpers = _helpers(trees)
    bad = [v for p, tree in trees.items() for v in _violations(p, tree, helpers)]
    assert not bad, "subprocess without a timeout below 30 s:\n" + "\n".join(bad)


ROOT = TESTS.parent
PLUGINS = ROOT / "plugins"
# The files that start a skill's wrapper or CLI as a process, with the reason. docs/architecture.md, Tests.
CLI_PROCESS_ALLOWLIST = {
    "tests/integration/pptx/test_wrapper.py":
        "subject is pptx.sh: the wrapper, uv_env.sh and the skill's locked environment",
    "tests/integration/second_opinion/test_review.py": "not converted yet",
    "tests/integration/short_video/test_wrapper.py":
        "subject is short-video.sh: the wrapper, uv_env.sh and the skill's locked environment",
    "tests/integration/voiceover/test_fish_voice.py":
        "a voice saved by one command and reused by the next is the subject",
    "tests/unit/brand/test_brand.py": "not converted yet",
    "tests/unit/image_gen/test_generate.py":
        "test_wrapper_local_extra: subject is the wrapper's `--extra local` choice (runs the wrapper's lines in bash)",
    "tests/unit/music/test_cli.py":
        "test_wrapper_local_extra: subject is the wrapper's `--extra local` choice (runs the wrapper's lines in bash)",
    "tests/unit/second_opinion/conftest.py": "not converted yet",
    "tests/unit/second_opinion/test_review.py": "not converted yet",
    "tests/unit/second_opinion/test_routes.py": "not converted yet",
    "tests/unit/short_video/test_routes.py": "not converted yet",
}
DOCSTRING_DIRS = ("tests/integration/pptx", "tests/integration/pptx_author")
SUBPROCESS_STARTS = {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"}
OS_STARTS = {"system", "popen", "execv", "execve", "execvp", "execvpe", "execl", "execlp", "spawnv", "spawnl",
             "posix_spawn", "posix_spawnp"}
ASYNCIO_STARTS = {"create_subprocess_exec", "create_subprocess_shell"}
MODULE_CODE = "<module>"


def _cli_names() -> tuple[set[str], set[str]]:
    """The wrapper file names (`pptx.sh`) and `<skill>_tool` package names of every skill under plugins/."""
    wrappers = {p.name for p in PLUGINS.glob("*/skills/*/scripts/*.sh")}
    packages = {p.name for p in PLUGINS.glob("*/skills/*/scripts/*_tool") if p.is_dir()}
    return wrappers, packages


def _module_name(path: Path) -> str:
    """The dotted module name of `path` from the repository root; a package's __init__.py is the package."""
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


class _Module:
    """What the CLI process rule needs from one file: per function (`MODULE_CODE` for the code outside functions)
    whether it names a skill CLI, whether it starts a process itself, and the functions of tests/ it calls."""

    def __init__(self, path: Path, cli: tuple[set[str], set[str]]):
        self.path, self.name = path, _module_name(path)
        self.tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        self.wrappers, self.packages = cli
        package = self.name if path.name == "__init__.py" else self.name.rpartition(".")[0]
        self.aliases: dict[str, str] = {}  # local name -> "subprocess", "os", "asyncio" or a tests module
        self.imported: dict[str, tuple[str, str]] = {}  # local name -> (module, name)
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.aliases[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    up = package.split(".")[: len(package.split(".")) - node.level + 1]
                    base = ".".join([*up, *([node.module] if node.module else [])])
                for a in node.names:
                    self.imported[a.asname or a.name] = (base, a.name)
        self.functions = {f.name for f in ast.walk(self.tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def is_cli_string(self, node: ast.AST) -> bool:
        """True for a string constant that is a wrapper file name or path, or a `<skill>_tool` module name."""
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            return False
        s = node.value
        return (any(s == w or s.endswith("/" + w) for w in self.wrappers)
                or any(s == p or s.startswith(p + ".") for p in self.packages))

    def units(self) -> dict[str, list[ast.AST]]:
        """Function name -> the nodes of its body (nested functions included); MODULE_CODE -> the nodes outside
        every function."""
        out: dict[str, list[ast.AST]] = {}
        outside: list[ast.AST] = []

        def visit(node: ast.AST):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.setdefault(child.name, []).extend(ast.walk(child))
                else:
                    outside.append(child)
                    visit(child)

        visit(self.tree)
        out[MODULE_CODE] = outside
        return out

    def callee(self, call: ast.Call) -> tuple[str, str] | str | None:
        """"start" for a call that starts a process, (module, function) for a call of a function of tests/,
        None otherwise."""
        f = call.func
        if isinstance(f, ast.Name):
            if f.id in self.imported:
                module, name = self.imported[f.id]
                if module == "subprocess" and name in SUBPROCESS_STARTS:
                    return "start"
                return (module, name) if module.startswith("tests") else None
            return (self.name, f.id) if f.id in self.functions else None
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            owner = self.aliases.get(f.value.id)
            starts = {"subprocess": SUBPROCESS_STARTS, "os": OS_STARTS, "asyncio": ASYNCIO_STARTS}
            if owner in starts:
                return "start" if f.attr in starts[owner] else None
            if f.value.id in self.imported:  # from tests.x import module
                module, name = self.imported[f.value.id]
                return (f"{module}.{name}", f.attr)
            if owner and owner.startswith("tests"):
                return (owner, f.attr)
            if f.value.id in ("self", "cls") and f.attr in self.functions:
                return (self.name, f.attr)
        return None

    def cli_values(self) -> set[str]:
        """The module-level names whose assigned value names a skill CLI, directly or through another such name."""
        names: set[str] = set()
        assigns = [n for n in self.tree.body if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None]
        while True:
            more = {t.id for n in assigns for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
                    if isinstance(t, ast.Name) and t.id not in names
                    and any(self.is_cli_string(x) or (isinstance(x, ast.Name) and x.id in names)
                            for x in ast.walk(n.value))}
            if not more:
                return names
            names |= more


def _cli_process_files() -> dict[str, list[int]]:
    """The files under tests/ that start a skill's wrapper or CLI as a process: path -> lines of the calls."""
    cli = _cli_names()
    modules = {m.name: m for m in (_Module(p, cli) for p in sorted(TESTS.rglob("*.py")))}
    cli_values = {name: m.cli_values() for name, m in modules.items()}
    facts = {}  # (module, function) -> (names a CLI, starts a process itself, callees with their lines)
    for name, m in modules.items():
        for fn, nodes in m.units().items():
            names_cli = any(m.is_cli_string(n) or (isinstance(n, ast.Name) and (
                n.id in cli_values[name] or (n.id in m.imported and m.imported[n.id][1] in cli_values.get(
                    m.imported[n.id][0], ())))) for n in nodes)
            calls = [(m.callee(n), n.lineno) for n in nodes if isinstance(n, ast.Call)]
            facts[(name, fn)] = (names_cli, [line for c, line in calls if c == "start"],
                                 [(c, line) for c, line in calls if isinstance(c, tuple)])
    starts = {k for k, (_, own, _) in facts.items() if own}
    launches: set[tuple[str, str]] = set()
    while True:
        new_starts = {k for k, (_, _, callees) in facts.items() if k not in starts
                      and any(c in starts for c, _ in callees)}
        new_launches = {k for k, (named, _, callees) in facts.items() if k not in launches
                        and ((named and k in starts) or any(c in launches for c, _ in callees))}
        if not new_starts and not new_launches:
            break
        starts |= new_starts
        launches |= new_launches
    out: dict[str, list[int]] = {}
    for module, fn in sorted(launches):
        named, own, callees = facts[(module, fn)]
        lines = list(own) if named else []
        lines += [line for c, line in callees if c in launches or (named and c in starts)]
        rel = str(modules[module].path.relative_to(ROOT))
        out.setdefault(rel, []).extend(lines)
    return {k: sorted(set(v)) for k, v in out.items()}


def test_cli_process_only_in_allowlisted_files():
    """A test calls the code under test in process; only the files in CLI_PROCESS_ALLOWLIST start a skill's wrapper
    (`plugins/*/skills/*/scripts/*.sh`) or CLI (`python -m <skill>_tool`, or its `main` in a child) as a process,
    each with its reason (docs/architecture.md, Tests). Every .py file under tests/ is read; nothing outside
    tests/ is. A function launches a CLI when it names a wrapper file or a `<skill>_tool` module (a string
    constant, or a module-level name assigned from one, also imported) and starts a process (a `subprocess`,
    `os` or `asyncio` process call, or a call of a function of tests/ that starts one), or when it calls a
    function of tests/ that launches a CLI. A file is flagged when a function of it, or its code outside
    functions, launches a CLI. Not seen: a pytest fixture used by name (only the conftest.py that defines it is
    flagged) and a process started by a function passed as a value. Also fails on an allowlist entry that is no
    longer flagged, so the list shows what remains."""
    found = _cli_process_files()
    extra = {f: lines for f, lines in found.items() if f not in CLI_PROCESS_ALLOWLIST}
    stale = sorted(set(CLI_PROCESS_ALLOWLIST) - set(found))
    assert not extra, "starts a skill CLI as a process, not in CLI_PROCESS_ALLOWLIST:\n" + "\n".join(
        f"{f}:{','.join(map(str, lines))}" for f, lines in sorted(extra.items()))
    assert not stale, "in CLI_PROCESS_ALLOWLIST but starts no skill CLI any more:\n" + "\n".join(stale)


def test_pptx_tests_have_docstrings():
    """Every `test_*` function and method under tests/integration/pptx/ and tests/integration/pptx_author/ has a
    docstring, which states what the test checks and what it guards (docs/architecture.md, Tests). Fails with
    file:line of each test without one. Only the presence of a docstring is checked, not its content."""
    bad = []
    for d in DOCSTRING_DIRS:
        for path in sorted((ROOT / d).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            bad += [f"{path.relative_to(ROOT)}:{f.lineno} {f.name}" for f in ast.walk(tree)
                    if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name.startswith("test_")
                    and not ast.get_docstring(f)]
    assert not bad, "test without a docstring:\n" + "\n".join(bad)
