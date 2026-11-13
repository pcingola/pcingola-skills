"""Narration made with the voiceover skill, imported as voice versions.

`script` writes each scene's narration, one sentence per line, to
`sources/narration/<scene>/script.txt`. The agent voices it with the
voiceover skill into the same directory (`narration.wav` + `timing.json`),
and `voice` imports that directory as the scene's next voice version after
checking that the voiced sentences are the storyboard's narration.

A scene with several speakers (see `speakers`) gets one part directory per
run of sentences, `sources/narration/<scene>/p<k>/`, each voiced in its
speaker's voice; `voice` checks every part, joins them into
`sources/narration/<scene>/` and imports that.

`pronounce:` in the settings maps written words to their spoken form. The
scripts hold the spoken form; `voice` accepts a sentence voiced in the spoken
form and stores its timing with the written text, the words that voiced one
written word merged into one entry.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import settings, speakers, state, storyboard, versions

FILES = ("script.txt", "narration.wav", "timing.json")


class NarrationError(Exception):
    """A narration directory is missing files or does not match the storyboard."""


def script_dir(project: Path, scene_id: str) -> Path:
    return project / "sources" / "narration" / scene_id


def script_text(scene: dict) -> str:
    return _lines(scene["narration"])


def _lines(sentences: list[str]) -> str:
    return "\n".join(spoken(str(x).strip()) for x in sentences) + "\n"


def spoken(text: str) -> str:
    """`text` with each `pronounce:` key replaced by its spoken form, the
    longest key first; keys match case-sensitively and hold no spaces."""
    table = {str(k): str(v) for k, v in (settings.get().get("pronounce") or {}).items()}
    bad = [k for k in table if len(k.split()) != 1 or not table[k].split()]
    if bad:
        raise NarrationError(f"pronounce: {', '.join(map(repr, bad))}: a key is one word, a spoken form is not empty")
    if not table:
        return text
    pattern = "|".join(re.escape(k) for k in sorted(table, key=len, reverse=True))
    return re.sub(pattern, lambda m: table[m.group(0)], text)


def _written(sentence: dict, text: str) -> dict:
    """A sentence voiced in the spoken form of `text`, with `text` as its text
    and the words that voiced each written word merged into one word (start
    of the first, end of the last)."""
    words = sentence.get("words")
    if not words:
        return {**sentence, "text": text}
    tokens = text.split()
    counts = [len(spoken(t).split()) for t in tokens]
    if len(words) != sum(counts):
        raise NarrationError(f"{len(words)} words voiced in {sentence['text']!r}, its spoken form has {sum(counts)}")
    merged, i = [], 0
    for token, n in zip(tokens, counts):
        merged.append({**words[i], "text": token, "end": words[i + n - 1]["end"]})
        i += n
    return {**sentence, "text": text, "words": merged}


def write_script(project: Path, scene: dict) -> list[tuple[Path, str | None]]:
    """Write the scene's script(s): `script.txt` for a scene with one run of
    speakers, `p<k>/script.txt` per run otherwise. Returns each script with
    its speaker (None = the default voice). Recordings in the scene's
    directory (a single recording, or a joined one) and part directories left
    from the other layout are removed, so a recording in another voice cannot
    be imported; recordings in part directories that stay are kept and
    checked on import."""
    d = script_dir(project, scene["id"])
    d.mkdir(parents=True, exist_ok=True)
    parts = speakers.runs(scene)
    old_parts = speakers.part_dirs(d)
    if len(parts) == 1:
        for p in old_parts:
            shutil.rmtree(p)
        for f in FILES:
            (d / f).unlink(missing_ok=True)
        p = d / "script.txt"
        p.write_text(script_text(scene), encoding="utf-8")
        return [(p, parts[0][0])]
    for f in FILES:
        (d / f).unlink(missing_ok=True)
    for p in old_parts:
        if int(p.name[1:]) > len(parts) or int(p.name[1:]) < 1:
            shutil.rmtree(p)
    out = []
    for k, (speaker, _, sentences) in enumerate(parts, 1):
        pd = speakers.part_dir(project, scene["id"], k)
        pd.mkdir(exist_ok=True)
        (pd / "script.txt").write_text(_lines(sentences), encoding="utf-8")
        out.append((pd / "script.txt", speaker))
    return out


def _norm(text: str) -> str:
    return " ".join(str(text).split())


def _check_sentences(label: str, want: list[str], timing: dict) -> dict:
    """`timing` with every sentence in its written form; raise NarrationError
    unless each voiced sentence is the storyboard's, written or spoken."""
    want = [_norm(x) for x in want]
    got = timing.get("sentences", [])
    if len(got) != len(want):
        raise NarrationError(f"{label}: {len(got)} sentences voiced, the storyboard has {len(want)}; "
                             "run `script` and voice it again")
    out = []
    for i, (s, w) in enumerate(zip(got, want), 1):
        g, say = _norm(s["text"]), spoken(w)
        if g not in (w, say):
            also = f" (spoken {say!r})" if say != w else ""
            raise NarrationError(f"{label} sentence {i}: voiced {g!r}, the storyboard has {w!r}{also}; "
                                 "run `script` and voice it again")
        try:
            out.append(s if g == w else _written(s, w))
        except NarrationError as e:
            raise NarrationError(f"{label} sentence {i}: {e}") from None
    return {**timing, "sentences": out}


def check(scene: dict, timing: dict) -> dict:
    """`timing` in the written form; raise NarrationError unless the voiced
    sentences are the scene's narration."""
    return _check_sentences(f"scene {scene['id']}", scene["narration"], timing)


def _write_timing(path: Path, timing: dict) -> None:
    path.write_text(json.dumps(timing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_timing(d: Path) -> dict:
    return json.loads((d / "timing.json").read_text(encoding="utf-8"))


def _missing(scene: dict, d: Path) -> None:
    missing = [f for f in FILES if not (d / f).is_file()]
    if missing:
        raise NarrationError(f"scene {scene['id']}: {d} has no {', '.join(missing)}")


def is_multipart(scene: dict) -> bool:
    return len(speakers.runs(scene)) > 1


def join_parts(project: Path, data: dict, scene: dict, src: Path) -> Path:
    """Check each part directory `src/p<k>` of a scene with several runs
    (files, sentences, voice) and write the joined `narration.wav`,
    `timing.json` and `script.txt` into the scene's `script_dir`. Returns
    that directory."""
    parts = []
    for k, (speaker, _, sentences) in enumerate(speakers.runs(scene), 1):
        d = src / f"p{k}"
        _missing(scene, d)
        timing = _check_sentences(f"scene {scene['id']} part {k}", sentences, _read_timing(d))
        try:
            speakers.check_voice(timing, storyboard.speaker_voice(data, speaker), speaker)
        except NarrationError as e:
            raise NarrationError(f"scene {scene['id']} part {k}: {e}") from None
        samples, sr = speakers.read_wav(d / "narration.wav")
        parts.append((speaker, samples, sr, timing))
    audio, timing = speakers.join(parts, settings.get()["voice"]["speaker_gap"])
    out = script_dir(project, scene["id"])
    out.mkdir(parents=True, exist_ok=True)
    speakers.write_wav(out / "narration.wav", audio, timing["sample_rate"])
    _write_timing(out / "timing.json", timing)
    (out / "script.txt").write_text(script_text(scene), encoding="utf-8")
    return out


def _speakers_meta(data: dict, scene: dict, timing: dict) -> list[dict]:
    """Each sentence's speaker and that speaker's resolved voice; a null voice
    name is the voice recorded in `timing` (its parts' `speakers`, else its `voice`)."""
    recorded = {v["speaker"]: v.get("voice") for v in timing.get("speakers") or []}
    out = []
    for name in scene["speakers"]:
        voice = storyboard.speaker_voice(data, name)
        if voice["name"] is None:
            voice["name"] = recorded.get(name, timing.get("voice"))
        out.append({"speaker": name, "voice": voice})
    return out


def import_voice(project: Path, data: dict, scene: dict, src: Path) -> Path:
    """Copy a voiced narration directory into the scene's next voice version.
    A scene with several runs of speakers is joined from its part directories
    first; a scene with a Speaker column has each recording's voice checked.
    The stored `timing.json` holds the written form of every sentence."""
    if is_multipart(scene):
        src = join_parts(project, data, scene, src)
    _missing(scene, src)
    timing = check(scene, _read_timing(src))
    if "speakers" in scene and not is_multipart(scene):
        speaker = speakers.runs(scene)[0][0]
        try:
            speakers.check_voice(timing, storyboard.speaker_voice(data, speaker), speaker)
        except NarrationError as e:
            raise NarrationError(f"scene {scene['id']}: {e}") from None
    out = versions.next_version(state.voice_root(project, scene["id"]))
    for f in ("script.txt", "narration.wav"):
        shutil.copyfile(src / f, out / f)
    _write_timing(out / "timing.json", timing)
    voice = {k: timing[k] for k in ("backend", "voice", "speed", "model", "style") if timing.get(k) is not None}
    meta = {
        "scene": scene["id"],
        "version": out.name,
        "voice": voice,
        "duration": timing["duration"],
        "source": str(src.relative_to(project)) if src.is_relative_to(project) else str(src),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if "speakers" in scene:
        meta["speakers"] = _speakers_meta(data, scene, timing)
    state.write_meta(out, meta)
    return out
