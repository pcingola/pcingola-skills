"""Weight files of the local speech and alignment models, downloaded from URLs of the config.

A provider of kind `kokoro`, `chatterbox` or `torchaudio` keeps the files of its model `<model>` in
`<dir>/<model lowercased>/`: `dir` of the provider entry, else `voiceover/` in the data directory of the plugin
that loaded the settings (`plugin_settings.data_dir`; media:voiceover's weights directory, so its earlier downloads
are reused). `ensure_file` streams a URL to `<dest>.part`, checks the byte count against Content-Length
and renames, so no file is left half-written under its final name. Downloads use the TLS context of `tls`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .errors import AIModelsError, ConfigError

# The folder of the plugin data directory that holds the weights when the provider has no `dir`.
DATA_FOLDER = "voiceover"


class DownloadError(AIModelsError):
    """A weight file could not be downloaded."""


def root(spec: dict[str, Any]) -> Path:
    """The provider's weights directory: its `dir`, else `DATA_FOLDER` in the plugin data directory; `ConfigError`
    when the process has neither (no plugin loaded its settings and CLAUDE_PLUGIN_DATA is unset)."""
    import plugin_settings

    if spec.get("dir"):
        return Path(str(spec["dir"])).expanduser()
    d = plugin_settings.data_dir()
    if d is None:
        raise ConfigError(f"a provider of kind {spec.get('kind')} has no `dir`, and this process has no plugin data "
                          "directory; set `dir` in its entry")
    return d / DATA_FOLDER


def model_dir(spec: dict[str, Any], model: str) -> Path:
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
