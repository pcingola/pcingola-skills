"""`music analyze`: per-clip reports on how clips fit their briefs.

Inputs are audio files and folders (their audio files, not recursive). Each
clip gets `<out>/<name>.json` with up to three sections, `model`
(`describe.py`), `signal` (`measure.py`) and `images` (`images.py`, files
`<name>_spec.png` and `<name>_wave.png`), plus `brief` and `checks`. `<name>`
is the file's stem, or the file name when two inputs share a stem. A run with
`--only` updates its sections of an existing report and keeps the others; a
brief the run does not give is kept from the existing report.
`summary.md` is rebuilt from every report in `<out>` after each run. Input
files are only read.

Briefs: the clip brief is the clip's entry in the `--prompts` file, else the
`prompt` of the `<file>.json` sidecar that `music generate` writes; the style
brief is `--brief`. The requested tempo is the sidecar's `bpm` option, else
the first "<N> BPM" in the clip brief, else in the style brief.
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import describe, images, measure

TOOL = "music analyze"
AUDIO_EXTS = (".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg")
ANALYSES = ("model", "signal", "images")
SUMMARY = "summary.md"
MAX_REASONS = 3
VERDICT_VERBS = {"fits": "fits", "partly": "partly fits", "does not fit": "does not fit"}

_BPM = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*BPM", re.IGNORECASE)
_EXT = "|".join(e[1:] for e in AUDIO_EXTS)
_LINE_ENTRY = re.compile(r"^\s*(\S.*?\.(?:" + _EXT + r"))\s*(?::|\t)\s*(.+?)\s*$", re.IGNORECASE)
_FILE = re.compile(r"^\s*File:\s*(\S.*?\.(?:" + _EXT + r")|\S+)(?:\s|$)", re.IGNORECASE)
_PROMPT = re.compile(r"^\s*Prompt(?: sent)?:\s*(.+?)\s*$", re.IGNORECASE)
_INSTRUMENTAL = re.compile(r"\binstrumental\b|\bno vocals\b", re.IGNORECASE)


class AnalyzeError(Exception):
    """Invalid analyze request."""


def collect(inputs: list[str]) -> tuple[list[Path], set[Path]]:
    """Audio files from files and folders, and the directories they came from."""
    files: list[Path] = []
    dirs: set[Path] = set()
    for raw in inputs:
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            found = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS)
            if not found:
                raise AnalyzeError(f"no audio files ({', '.join(AUDIO_EXTS)}) in {p}")
            files += found
            dirs.add(p)
        elif p.is_file():
            if p.suffix.lower() not in AUDIO_EXTS:
                raise AnalyzeError(f"{p.name}: not an audio file ({', '.join(AUDIO_EXTS)})")
            files.append(p)
            dirs.add(p.parent)
        else:
            raise AnalyzeError(f"{raw} not found")
    unique = list(dict.fromkeys(files))
    if not unique:
        raise AnalyzeError("no input files")
    return unique, dirs


def default_out_dir(dirs: set[Path]) -> Path:
    if len(dirs) != 1:
        raise AnalyzeError("inputs come from several directories; give --out-dir")
    return next(iter(dirs)) / "analysis"


def clip_names(files: list[Path]) -> dict[Path, str]:
    """The stem; the file name for files whose stem another input shares;
    `<folder>_<file name>` for files whose name another input shares; and a
    `_<n>` suffix if that still collides."""
    def counts(keys):
        c: dict[str, int] = {}
        for k in keys:
            c[k] = c.get(k, 0) + 1
        return c

    stems, names = counts(f.stem for f in files), counts(f.name for f in files)
    out = {}
    for f in files:
        if stems[f.stem] == 1:
            out[f] = f.stem
        elif names[f.name] == 1:
            out[f] = f.name
        else:
            out[f] = f"{f.parent.name}_{f.name}"
    final, seen = counts(out.values()), {}
    for f, name in out.items():
        if final[name] > 1:
            seen[name] = seen.get(name, 0) + 1
            out[f] = f"{name}_{seen[name]}"
    return out


def parse_prompts(text: str) -> dict[str, str]:
    """File name -> prompt from a prompts file in one of three forms: a JSON
    object; blocks with a `File: <name>` line and a `Prompt:` or
    `Prompt sent:` line; or one `<name>: <prompt>` (or tab) line per file."""
    if text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise AnalyzeError(f"prompts file: invalid JSON: {e}") from e
        return {str(k): str(v) for k, v in data.items()}
    out: dict[str, str] = {}
    if any(_FILE.match(line) for line in text.splitlines()):
        current = None
        for line in text.splitlines():
            if m := _FILE.match(line):
                current = m.group(1)
            elif (m := _PROMPT.match(line)) and current:
                out[current] = m.group(1)
        return out
    for line in text.splitlines():
        if m := _LINE_ENTRY.match(line):
            out[m.group(1)] = m.group(2)
    return out


def lookup_prompt(prompts: dict[str, str], path: Path) -> str | None:
    """The entry named exactly like the file, else one with the same stem."""
    if path.name in prompts:
        return prompts[path.name]
    for key, value in prompts.items():
        if Path(key).stem == path.stem:
            return value
    return None


def prompt_warnings(prompts: dict[str, str], files: list[Path], briefs: dict[Path, dict]) -> list[str]:
    """Prompts-file entries that match no input, and inputs with no clip brief."""
    if not prompts:
        return []
    out = [f"--prompts entry {key!r} matches no input file" for key in prompts
           if not any(f.name == key or f.stem == Path(key).stem for f in files)]
    out += [f"{f.name}: no clip brief (no --prompts entry, no generate sidecar)" for f in files
            if not briefs[f].get("clip")]
    return out


def generate_sidecar(path: Path) -> dict | None:
    """`<file>.json` written by `music generate`, when it has a prompt."""
    side = path.with_name(path.name + ".json")
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("prompt"), str) else None


def requested_bpm(clip_brief: str | None, style_brief: str | None, sidecar: dict | None) -> float | None:
    bpm = ((sidecar or {}).get("options") or {}).get("bpm")
    if isinstance(bpm, (int, float)) and bpm > 0:
        return float(bpm)
    for text in (clip_brief, style_brief):
        if text and (m := _BPM.search(text)):
            return float(m.group(1))
    return None


def resolve_brief(path: Path, prompts: dict[str, str], style: str | None) -> dict:
    clip, source = lookup_prompt(prompts, path), "prompts file"
    sidecar = generate_sidecar(path)
    if clip is None and sidecar:
        clip, source = sidecar["prompt"], f"{path.name}.json"
    return {"clip": clip, "clip_source": source if clip else None, "style": style or None,
            "requested_bpm": requested_bpm(clip, style, sidecar)}


def merge_brief(new: dict, old: dict | None) -> dict:
    """`new`, with the clip or style brief of an earlier report kept where
    this run gives none."""
    if not old:
        return new
    out = dict(new)
    if out.get("clip") is None and old.get("clip"):
        out["clip"], out["clip_source"] = old["clip"], old.get("clip_source")
    if out.get("style") is None and old.get("style"):
        out["style"] = old["style"]
    if out.get("requested_bpm") is None:
        out["requested_bpm"] = requested_bpm(out.get("clip"), out.get("style"), None)
        if (out["requested_bpm"] is None and out.get("clip") == old.get("clip")
                and out.get("style") == old.get("style")):
            out["requested_bpm"] = old.get("requested_bpm")
    return out


def checks(record: dict) -> dict:
    """Comparisons of the measurements and the model answer with the brief."""
    brief, sig, mod = record.get("brief") or {}, record.get("signal") or {}, record.get("model") or {}
    out: dict = {"flags": []}
    if sig.get("status") == "ok":
        out["tempo"] = {"requested_bpm": brief.get("requested_bpm"), "measured_bpm": sig["tempo_bpm"],
                        "relation": measure.tempo_relation(sig["tempo_bpm"], brief.get("requested_bpm"))}
        if out["tempo"]["relation"] == "differs" and sig["tempo_bpm"]:
            out["flags"].append(f"tempo {sig['tempo_bpm']:.0f} BPM differs from the requested "
                                f"{brief['requested_bpm']:g} BPM")
        tp = sig.get("true_peak_dbtp")
        if tp is not None and tp > measure.TRUE_PEAK_LIMIT_DBTP:
            out["flags"].append(f"true peak {tp:.1f} dBTP above {measure.TRUE_PEAK_LIMIT_DBTP:g} dBTP")
        if sig.get("level") == "sparse":
            out["flags"].append("sparse: long quiet passages")
        if sig.get("level") == "silent":
            out["flags"].append("silent")
    instrumental = any(t and _INSTRUMENTAL.search(t) for t in
                       (brief.get("clip"), brief.get("style"), mod.get("clip_brief"), mod.get("style_brief")))
    if mod.get("status") == "ok" and instrumental and mod.get("vocals"):
        out["flags"].append(f"vocals heard in an instrumental brief: {mod.get('vocals_description', '')}")
    return out


def _clause(text, lower: bool = True) -> str:
    """Model text inside a sentence: no final period; with `lower`, a
    capitalised first word is lower-cased (an acronym such as "EDM" is kept)."""
    t = str(text or "").strip().rstrip(".")
    return t[0].lower() + t[1:] if lower and len(t) > 1 and t[0].isupper() and t[1].islower() else t


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def judged_briefs(mod: dict) -> dict:
    """The briefs the model answer was given (they may differ from the
    current run's when only other analyses were rerun)."""
    return {"clip": mod.get("clip_brief"), "style": mod.get("style_brief")}


def verdict_text(mod: dict) -> str:
    if mod.get("status") == "skipped":
        return f"no model verdict ({mod.get('reason')})"
    if mod.get("status") == "error":
        return f"no model verdict (error: {mod.get('error')})"
    if mod.get("status") != "ok":
        return "no model verdict (model analysis not run)"
    parts = []
    brief = judged_briefs(mod)
    for key, label in (("clip", "clip brief"), ("style", "style brief")):
        v = mod.get(f"{key}_brief_verdict")
        if brief.get(key) and v and v != "no brief":
            parts.append(f"{VERDICT_VERBS.get(v, v)} the {label}")
    if not parts:
        return f"no brief given; described by {mod.get('model')}"
    return f"{'; '.join(parts)} ({mod.get('model')})"


def paragraph(record: dict) -> str:
    """One paragraph: verdict, then the evidence."""
    brief, sig, mod = record.get("brief") or {}, record.get("signal") or {}, record.get("model") or {}
    text = [_sentence(f"Verdict: {verdict_text(mod)}")]
    if sig.get("status") == "ok":
        req = brief.get("requested_bpm")
        rel = (record.get("checks") or {}).get("tempo", {}).get("relation")
        tempo = f"Tempo {sig['tempo_bpm']:.0f} BPM measured" if sig.get("tempo_bpm") else "No tempo measured"
        if req:
            tempo += f" vs {req:g} requested ({rel or 'no beat'}"
            if (rel != "match" and sig.get("requested_bpm_confidence") is not None
                    and sig.get("requested_bpm") == req):
                tempo += f"; beat confidence at {req:g} BPM {sig['requested_bpm_confidence']:.2f}"
            tempo += ")"
        cv = f", inter-beat CV {sig['ibi_cv']:.3f}" if sig.get("ibi_cv") is not None else ""
        text.append(_sentence(f"{tempo}; pulse {sig['pulse']} (beat confidence {sig['beat_confidence']:.2f}{cv}), "
                              f"percussive ratio {sig['percussive_ratio']:.2f}, "
                              f"{sig['onset_rate_per_s']:.1f} onsets/s; level {sig['level']} "
                              f"({sig['level_trend_db']:+.1f} dB)"))
    elif sig.get("status") == "error":
        text.append(_sentence(f"Signal measurements failed: {sig.get('error')}"))
    if mod.get("status") == "ok":
        vocals = _clause(mod.get("vocals_description")) if mod.get("vocals") else "no vocals"
        text.append(_sentence(f"Model: {_clause(mod['genre'], lower=False)}; mood {_clause(mod['mood'])}; energy {mod['energy']}, "
                              f"{_clause(mod['energy_change_description'])}; {vocals}"))
    if sig.get("status") == "ok":
        loud = ""
        if sig.get("integrated_lufs") is not None and sig.get("true_peak_dbtp") is not None:
            loud = f"; {sig['integrated_lufs']:.1f} LUFS, true peak {sig['true_peak_dbtp']:.1f} dBTP"
        key = f"Key {sig['key']} {sig['mode']} (r {sig['correlation']:.2f})" if sig.get("key") else "No key"
        text.append(_sentence(key + loud))
    if mod.get("status") == "ok":
        judged = judged_briefs(mod)
        reasons = [r for key in ("clip", "style") if judged.get(key)
                   for r in (mod.get(f"{key}_brief_reasons") or [])[:MAX_REASONS]]
        if reasons:
            text.append(_sentence("Reasons: " + "; ".join(r.rstrip(".") for r in reasons)))
    flags = (record.get("checks") or {}).get("flags") or []
    if flags:
        text.append(_sentence("Flags: " + "; ".join(flags)))
    img = record.get("images") or {}
    if img.get("status") == "ok":
        text.append(f"Images: [spectrogram]({img['spectrogram']}), [waveform]({img['waveform']}).")
    return " ".join(text)


def load_records(out_dir: Path) -> list[dict]:
    records = []
    for f in sorted(out_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("tool") == TOOL:
            records.append(data)
    return records


def safe_paragraph(record: dict) -> str:
    """`paragraph`, or a note naming what is missing from an incomplete report."""
    try:
        return paragraph(record)
    except (KeyError, TypeError, ValueError) as e:
        print(f"Warning: {record.get('name')}: incomplete report ({type(e).__name__}: {e})", file=sys.stderr)
        return f"Incomplete report ({type(e).__name__}: {e}); rerun analyze on this clip."


def write_summary(out_dir: Path) -> Path:
    lines = ["# Music analysis", "",
             "Verdicts come from a chat model listening to each clip; tempo, pulse, percussive ratio, level, "
             "key and loudness are measured with librosa and FFmpeg. They measure fit to the brief and "
             "technical defects, not musical quality.", ""]
    for rec in sorted(load_records(out_dir), key=lambda r: str(r.get("name"))):
        lines += [f"## {rec.get('name')}", "", safe_paragraph(rec), ""]
    path = out_dir / SUMMARY
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _error(exc: BaseException) -> dict:
    return {"status": "error", "error": str(exc) or type(exc).__name__}


def analyze_clip(path: Path, name: str, out_dir: Path, brief: dict, only: tuple[str, ...],
                 model: str | None, model_skip: str | None) -> dict:
    report = out_dir / f"{name}.json"
    record: dict = {}
    if report.exists():
        try:
            record = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            record = {}
        if not isinstance(record, dict) or record.get("file") != str(path):
            record = {}
    brief = merge_brief(brief, record.get("brief"))
    record.update({"tool": TOOL, "file": str(path), "name": name, "brief": brief,
                   "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    if "signal" in only:
        try:
            m = measure.measure(path, brief.get("requested_bpm"))
            record["signal"] = {"status": "ok", **m, "requested_bpm": brief.get("requested_bpm"),
                                "summary": measure.summary_line(m)}
        except Exception as e:  # noqa: BLE001 - recorded per clip
            record["signal"] = _error(e)
    if "images" in only:
        try:
            record["images"] = images.draw(path, out_dir / f"{name}_spec.png", out_dir / f"{name}_wave.png")
        except Exception as e:  # noqa: BLE001 - recorded per clip
            record["images"] = _error(e)
    if "model" in only:
        if model_skip:
            record["model"] = describe.skipped(model_skip)
        else:
            try:
                record["model"] = {**describe.describe(model, path, brief["clip"], brief["style"]),
                                   "clip_brief": brief["clip"], "style_brief": brief["style"]}
            except Exception as e:  # noqa: BLE001 - recorded per clip
                record["model"] = _error(e)
    record["checks"] = checks(record)
    report.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def run(inputs: list[str], style: str | None, prompts_file: str | None, only: list[str] | None,
        model: str | None, out_dir: str | None, jobs: int) -> int:
    files, dirs = collect(inputs)
    out = Path(out_dir).expanduser().resolve() if out_dir else default_out_dir(dirs)
    if out in dirs:
        raise AnalyzeError(f"--out-dir {out} holds input files; reports there could replace "
                           "the <file>.json sidecars of `music generate`")
    prompts: dict[str, str] = {}
    if prompts_file:
        try:
            prompts = parse_prompts(Path(prompts_file).expanduser().read_text(encoding="utf-8"))
        except OSError as e:
            raise AnalyzeError(f"--prompts: {e}") from e
        if not prompts:
            raise AnalyzeError(f"--prompts: no entries found in {prompts_file}")
    chosen = tuple(only) if only else ANALYSES
    out.mkdir(parents=True, exist_ok=True)

    model_id = skip = None
    if "model" in chosen:
        model_id, skip = describe.resolve_model(model)
        if skip:
            print(f"Warning: model analysis skipped: {skip}", file=sys.stderr)

    names = clip_names(files)
    briefs = {f: resolve_brief(f, prompts, style) for f in files}
    for warning in prompt_warnings(prompts, files, briefs):
        print(f"Warning: {warning}", file=sys.stderr)
    errors = 0
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = [pool.submit(analyze_clip, f, names[f], out, briefs[f], chosen, model_id, skip)
                   for f in files]
        for fut in futures:
            rec = fut.result()
            for key in chosen:
                sec = rec.get(key) or {}
                if sec.get("status") == "error":
                    errors += 1
                    print(f"Warning: {rec['name']}: {key}: {sec.get('error')}", file=sys.stderr)
            print(out / f"{rec['name']}.json")
    print(write_summary(out))
    return 1 if errors else 0
