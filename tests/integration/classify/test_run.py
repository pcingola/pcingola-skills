"""`classify run` through the CLI with one short call per backend to the local Ollama, on the models of
tests/config.yaml."""
from tests.prereq import require_ollama
from tests.settings_env import TEST_CONFIG, write_config
from tests.subproc import child_env, run_module
from tests.unit.classify.test_run import TEAM, lines


def run(argv: list[str], config=TEST_CONFIG):
    """`python -m classify_tool <argv>` in a child process whose settings file is `config`."""
    return run_module("classify_tool", argv, child_env(SKILLS_CONFIG=str(config)))


def test_system1_run():
    """`classify run` without --backend uses the system1 backend with tasks.system1 of config.yaml
    and writes a record with id, backend, model, UTC timestamp, top, p_top and answers whose
    probabilities cover the options. Guards default_backend, System1Backend and runner.record.
    """
    require_ollama("system1")
    p = run(["run", *TEAM, "--item", "My invoice is wrong."])
    assert p.returncode == 0, p.stderr
    [r] = lines(p.stdout)
    assert (r["id"], r["backend"]) == (1, "system1") and r["timestamp"].endswith("+00:00")
    assert r["top"] in ("billing", "technical") and 0.0 <= r["p_top"] <= 1.0
    assert set(r["answers"]["q"]["probabilities"]) == {"billing", "technical"}


def test_chat_run():
    """`classify run --backend chat` classifies with tasks.chat and records a label among the
    options with p_top null. Guards ChatBackend's structured output and chat_result.
    """
    require_ollama("chat")
    p = run(["run", "--backend", "chat", "--type", "noul", "--instructions", "Does the customer agree?",
             "--item", "Yes, I agree."])
    assert p.returncode == 0, p.stderr
    [r] = lines(p.stdout)
    assert (r["backend"], r["p_top"]) == ("chat", None) and r["top"] in ("true", "false")
    assert r["answers"]["q"] == {"type": "noul", "answer": r["top"]}


def test_missing_model_stops_before_other_items(tmp_path):
    """A System-1 model that Ollama does not hold ends the run once with the `ollama pull` message;
    no item line is written."""
    require_ollama()
    cfg = write_config(tmp_path / "config.yaml", providers={"ollama": {"kind": "ollama"}},
                       tasks={"system1": "ollama:no-such-model:1b"})
    out = tmp_path / "out.jsonl"
    p = run(["run", "--type", "noul", "--instructions", "Urgent?", *[a for i in range(5) for a in ("--item", f"t{i}")],
             "--out", str(out)], cfg)
    assert p.returncode == 1 and "ollama pull no-such-model:1b" in p.stderr, p.stderr
    assert p.stderr.count("ollama pull") == 1
    assert not out.exists() or not out.read_text().strip()
