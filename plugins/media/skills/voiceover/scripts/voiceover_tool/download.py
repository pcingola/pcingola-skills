"""Weight downloads: stream to `<dest>.part`, check the byte count, rename.

Weights come from GitHub releases, Meta's download server and the ModelScope
mirror of Resemble AI's Chatterbox-Turbo repository. Our own downloader is also
used for the MMS_FA aligner (instead of torch.hub's) so every download checks
its size and none is left half-written under its final name.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from . import config

_KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"


@dataclass(frozen=True)
class Weight:
    url: str
    rel_path: str  # relative to config.model_dir()
    size: int  # expected size in bytes


KOKORO_MODEL = Weight(f"{_KOKORO_BASE}/kokoro-v1.0.onnx", "kokoro-v1.0/kokoro-v1.0.onnx", 325_532_387)
KOKORO_VOICES = Weight(f"{_KOKORO_BASE}/voices-v1.0.bin", "kokoro-v1.0/voices-v1.0.bin", 28_214_398)
MMS_FA = Weight(
    "https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt",
    "mms_fa/model.pt",
    1_262_047_414,
)
ALL_WEIGHTS = (KOKORO_MODEL, KOKORO_VOICES, MMS_FA)

_CHATTERBOX_BASE = "https://www.modelscope.cn/models/ResembleAI/chatterbox-turbo/resolve/master"
CHATTERBOX_DIR = "chatterbox-turbo"
# file name -> size in bytes; s3gen.safetensors (the non-Turbo decoder) is not needed
_CHATTERBOX_FILES = {
    "t3_turbo_v1.safetensors": 1_915_480_052,
    "s3gen_meanflow.safetensors": 1_064_875_036,
    "ve.safetensors": 5_695_784,
    "conds.pt": 169_454,
    "vocab.json": 999_186,
    "merges.txt": 456_318,
    "tokenizer_config.json": 3_878,
    "added_tokens.json": 418,
    "special_tokens_map.json": 470,
}
CHATTERBOX_WEIGHTS = tuple(
    Weight(f"{_CHATTERBOX_BASE}/{name}", f"{CHATTERBOX_DIR}/{name}", size)
    for name, size in _CHATTERBOX_FILES.items()
)


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
    return [weight_path(w) for w in ALL_WEIGHTS if not weight_path(w).is_file()]


def ensure_all() -> list[Path]:
    """Download every weight that is missing; return all weight paths."""
    return [ensure_weight(w) for w in ALL_WEIGHTS]
