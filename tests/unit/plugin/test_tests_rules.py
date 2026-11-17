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
