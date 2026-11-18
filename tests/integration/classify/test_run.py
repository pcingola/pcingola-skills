"""`classify run` with one short call per backend to the local Ollama, on the models of tests/config.yaml: through
the CLI in process where its printed output is the subject, else through `runner.score`."""
from pathlib import Path

from classify_tool import cli, questions, runner
from classify_tool.items import items_from_texts
from tests.inproc import CliResult, run_main
from tests.prereq import require_ollama
from tests.settings_env import TEST_CONFIG, use_settings, write_config
from tests.unit.classify.test_run import TEAM, lines


def classify(*argv: str, settings: Path = TEST_CONFIG) -> CliResult:
    """`classify <argv>` in process (`cli.main`) with the settings file `settings`."""
    return run_main(cli.main, *argv, settings=settings)


def test_system1_run():
    """`classify run` without --backend uses the system1 backend with tasks.system1 of config.yaml
    and prints a record with id, backend, model, UTC timestamp, top, p_top and answers whose
    probabilities cover the options. Guards default_backend, System1Backend, runner.record and the
    JSONL lines that `run` prints without --out.
    """
    require_ollama("system1")
    p = classify("run", *TEAM, "--item", "My invoice is wrong.")
    assert p.returncode == 0, p.stderr
    [r] = lines(p.stdout)
    assert (r["id"], r["backend"]) == (1, "system1") and r["timestamp"].endswith("+00:00")
    assert r["top"] in ("billing", "technical") and 0.0 <= r["p_top"] <= 1.0
    assert set(r["answers"]["q"]["probabilities"]) == {"billing", "technical"}


def test_chat_run():
    """`runner.score` with the chat backend classifies with tasks.chat and records a label among the
    options with p_top null. Guards ChatBackend's structured output and chat_result.
    """
    require_ollama("chat")
    qs = questions.from_flags("noul", "Does the customer agree?")
    with use_settings(TEST_CONFIG):
        scored = runner.score(items_from_texts(["Yes, I agree."]), qs, backend_name="chat")
    [r] = scored.records.values()
    assert (r["backend"], r["p_top"]) == ("chat", None) and r["top"] in ("true", "false")
    assert r["answers"]["q"] == {"type": "noul", "answer": r["top"]}


def test_missing_model_stops_before_other_items(tmp_path):
    """A System-1 model that Ollama does not hold ends the run once with the `ollama pull` message;
    no item line is written."""
    require_ollama()
    cfg = write_config(tmp_path / "config.yaml", providers={"ollama": {"kind": "ollama"}},
                       tasks={"system1": "ollama:no-such-model:1b"})
    out = tmp_path / "out.jsonl"
    p = classify("run", "--type", "noul", "--instructions", "Urgent?", *[a for i in range(5) for a in ("--item", f"t{i}")],
                 "--out", str(out), settings=cfg)
    assert p.returncode == 1 and "ollama pull no-such-model:1b" in p.stderr, p.stderr
    assert p.stderr.count("ollama pull") == 1
    assert not out.exists() or not out.read_text().strip()
