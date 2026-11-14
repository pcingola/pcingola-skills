"""Weight downloads: stream to `<dest>.part`, check the byte count, rename.

The weight URLs and file names are settings (`config.py`). Our own downloader
is also used for the aligner (instead of torch.hub's) so every download checks
its size against Content-Length and none is left half-written under its final name.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass(frozen=True)
class Weight:
    url: str
    rel_path: str  # relative to config.model_dir()
    size: int | None = None  # expected size in bytes; None checks Content-Length only


def _basename(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def kokoro_weights() -> tuple[Weight, Weight]:
    """The Kokoro model and voices files of the settings, in `<model file stem>/`."""
    model_url = config.require("VOICEOVER_KOKORO_MODEL_URL")
    voices_url = config.require("VOICEOVER_KOKORO_VOICES_URL")
    model_name = _basename(model_url)
    d = model_name.rsplit(".", 1)[0]
    return Weight(model_url, f"{d}/{model_name}"), Weight(voices_url, f"{d}/{_basename(voices_url)}")


def aligner_weight() -> Weight:
    """The forced aligner's weights, in `<pipeline name lowercased>/`, the file name torch.hub looks for."""
    url = config.require("VOICEOVER_ALIGNER_URL")
    return Weight(url, f"{config.aligner().lower()}/{_basename(url)}")


def chatterbox_weights() -> tuple[Weight, ...]:
    """The files of `VOICEOVER_CHATTERBOX_FILES` under the repository URL `VOICEOVER_CHATTERBOX_URL`."""
    base = config.require("VOICEOVER_CHATTERBOX_URL").rstrip("/")
    names = [n.strip() for n in config.require("VOICEOVER_CHATTERBOX_FILES").split(",") if n.strip()]
    return tuple(Weight(f"{base}/{n}", f"{config.chatterbox_model()}/{n}") for n in names)


def all_weights() -> tuple[Weight, ...]:
    return (*kokoro_weights(), aligner_weight())


class DownloadError(RuntimeError):
    pass


def ensure_file(url: str, dest: Path, expected_size: int | None = None) -> Path:
    """Download `url` to `dest` unless `dest` already exists.

    Streams to `dest.part`, checks the byte count against Content-Length (and
    `expected_size` when given), then renames to `dest`. A failed or short
    download leaves no file under the final name. Every failure, network and
    disk errors included, is a `DownloadError` naming `url`.
    """
    import httpx

    dest = Path(dest)
    if dest.is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    print(f"Downloading {url} -> {dest}", file=sys.stderr)
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=httpx.Timeout(60.0, read=300.0)) as r:
            r.raise_for_status()
            length = r.headers.get("Content-Length")
            declared = int(length) if length is not None else None
            if declared is not None and expected_size is not None and declared != expected_size:
                raise DownloadError(f"{url}: server reports {declared} bytes, expected {expected_size}")
            total = declared or expected_size
            got = 0
            last_pct = -10
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=1 << 20):
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        pct = got * 100 // total
                        if pct >= last_pct + 10:
                            print(f"  {pct}% of {total / 1e6:.0f} MB", file=sys.stderr)
                            last_pct = pct
        want = declared if declared is not None else expected_size
        if want is not None and got != want:
            raise DownloadError(f"{url}: got {got} bytes, expected {want}")
    except (httpx.HTTPError, OSError) as e:
        part.unlink(missing_ok=True)
        raise DownloadError(f"cannot download {url}: {e}") from e
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)
    return dest


def weight_path(w: Weight) -> Path:
    return config.model_dir() / w.rel_path


def ensure_weight(w: Weight) -> Path:
    return ensure_file(w.url, weight_path(w), w.size)


def missing_weights() -> list[Path]:
    return [weight_path(w) for w in all_weights() if not weight_path(w).is_file()]


def ensure_all() -> list[Path]:
    """Download every weight that is missing; return all weight paths."""
    return [ensure_weight(w) for w in all_weights()]
