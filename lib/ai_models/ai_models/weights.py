"""Weight files of the local speech and alignment models, downloaded from URLs of the config.

A provider of kind `kokoro`, `chatterbox` or `torchaudio` keeps the files of its model `<model>` in
`<dir>/<model lowercased>/`: `dir` of the provider entry, else the weights directory the caller passes
(`with_dir`; media:voiceover passes `voiceover/` of its plugin data directory). `ensure_file` streams a URL to `<dest>.part`, checks the byte count against Content-Length
and renames, so no file is left half-written under its final name. Downloads use the TLS context of `tls`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TypeVar

from plugin_settings import ChatterboxProvider, KokoroProvider, TorchaudioProvider

from .errors import AIModelsError, ConfigError

# A provider with a weights directory (`dir`).
WeightsProvider = TypeVar("WeightsProvider", KokoroProvider, ChatterboxProvider, TorchaudioProvider)


class DownloadError(AIModelsError):
    """A weight file could not be downloaded."""


def with_dir(spec: WeightsProvider, default: str | Path | None) -> WeightsProvider:
    """`spec` with `dir` set to `default` when it has none (a copy; `spec` itself is unchanged)."""
    if spec.dir is not None or default is None:
        return spec
    return spec.model_copy(update={"dir": Path(default).expanduser()})


def root(spec: WeightsProvider) -> Path:
    """The provider's weights directory, its `dir`; `ConfigError` when it has none (the caller passed no default)."""
    if spec.dir is None:
        raise ConfigError(f"a provider of kind {spec.kind} has no `dir` for its weights, and the caller gave "
                          "none; set `dir` in its entry")
    return spec.dir


def model_dir(spec: WeightsProvider, model: str) -> Path:
    """The directory of the files of `model` of a provider: `<root>/<model lowercased>`."""
    return root(spec) / model.lower()


def basename(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def ensure_file(url: str, dest: Path) -> Path:
    """`dest`, downloaded from `url` when missing. Every failure, network and disk errors included, is a
    `DownloadError` naming `url`, and leaves no file under `dest`."""
    import httpx

    from .tls import ssl_verify

    dest = Path(dest)
    if dest.is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    print(f"ai_models: downloading {url} -> {dest}", file=sys.stderr, flush=True)
    try:
        with httpx.stream("GET", url, follow_redirects=True, verify=ssl_verify(),
                          timeout=httpx.Timeout(60.0, read=300.0)) as r:
            r.raise_for_status()
            length = r.headers.get("Content-Length")
            want = int(length) if length is not None else None
            got = 0
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=1 << 20):
                    f.write(chunk)
                    got += len(chunk)
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
