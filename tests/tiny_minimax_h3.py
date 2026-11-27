"""A tiny MiniMax-H3 modular pipeline with random weights, for the video tests: the Hub repository `REPO` copied to a
folder whose `modular_model_index.json` points each component at that folder. The published index points them at
`./tmp/tiny-random/minimax-h3`, the folder the repository was saved from, so a load from the Hub fails."""

from __future__ import annotations

import json
from pathlib import Path

REPO = "tiny-random/minimax-h3"
INDEX = "modular_model_index.json"


def build(path: Path, folder: Path) -> Path:
    """Download `REPO` without `transformer_ref` (the ref2va workflow, unused) to `path`, point every component of
    its index at `folder` (where `path` is moved to), and return `path`."""
    from huggingface_hub import snapshot_download

    snapshot_download(REPO, local_dir=path, ignore_patterns=["transformer_ref/*"])
    index = json.loads((path / INDEX).read_text())
    for spec in index.values():
        if isinstance(spec, list) and len(spec) == 3 and isinstance(spec[2], dict):
            spec[2]["pretrained_model_name_or_path"] = str(folder)
    (path / INDEX).write_text(json.dumps(index, indent=2))
    return path
