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
    """True when `node` is None or a number constant of TEST_TIMEOUT or more; a name passed through is fine."""
    if node is None:
        return True
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and node.value >= TEST_TIMEOUT


def _timeout(call: ast.Call) -> ast.expr | None:
    """The `timeout` keyword of `call`, None when absent."""
    return next((k.value for k in call.keywords if k.arg == "timeout"), None)


def _helpers(trees: dict[Path, ast.Module]) -> set[str]:
    """Names of the functions under tests/ that take a `timeout` parameter."""
    return {f.name for tree in trees.values() for f in ast.walk(tree)
            if isinstance(f, ast.FunctionDef) and any(a.arg == "timeout" for a in [*f.args.args, *f.args.kwonlyargs])}


def _violations(path: Path, tree: ast.Module, helpers: set[str]) -> list[str]:
    """Each subprocess call, process wait, helper call or helper default in `tree` with no timeout or one of
    TEST_TIMEOUT seconds or more, as file:line."""
    where = path.relative_to(TESTS.parent)
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
        is_subprocess = (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "subprocess"
                         and name in SUBPROCESS_CALLS)
        is_wait = isinstance(f, ast.Attribute) and name in PROCESS_WAITS
        if (is_subprocess or is_wait) and _too_long(_timeout(node)):
            out.append(f"{where}:{node.lineno} {name}")
        elif name in helpers and _timeout(node) is not None and _too_long(_timeout(node)):
            out.append(f"{where}:{node.lineno} {name}")
    return out


def test_every_subprocess_has_a_short_timeout():
    """Every subprocess a test outside tests/models/ starts has a timeout below the 30 s test timeout, so a hung
    child fails the test with its own message. Checked: `subprocess.run`, `check_output`, `check_call` and `call`,
    and `.communicate` and `.wait` of a started process, need a `timeout` keyword below 30; a test helper with a
    `timeout` parameter needs a default below 30, and a call to it may not pass 30 or more."""
    trees = {p: ast.parse(p.read_text(encoding="utf-8"), str(p)) for p in _files()}
    helpers = _helpers(trees)
    bad = [v for p, tree in trees.items() for v in _violations(p, tree, helpers)]
    assert not bad, "subprocess without a timeout below 30 s:\n" + "\n".join(bad)
