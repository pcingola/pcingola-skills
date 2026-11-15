"""Download of the pinned libraries into the plugin data directory, checked against their SHA-256."""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from .common import HAError, data_dir
from .lib_pin import LibPin


class Vendor:
    """The pinned library files under `<root>/<package>@<version>/` (default `<data dir>/vendor`)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or data_dir() / "vendor"

    def path(self, pin: LibPin) -> Path:
        """The local file of `pin`, downloaded on first use; HAError when its hash differs from the pin."""
        dest = self.root / pin.vendor_dir / pin.file
        if dest.is_file() and self._sha(dest.read_bytes()) == pin.sha256:
            return dest
        try:
            with urllib.request.urlopen(pin.url, timeout=60) as r:
                data = r.read()
        except OSError as e:
            raise HAError(f"cannot download {pin.url}: {e}") from None
        sha = self._sha(data)
        if sha != pin.sha256:
            raise HAError(f"{pin.url}: SHA-256 {sha} differs from the pinned {pin.sha256}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)
        return dest

    @staticmethod
    def _sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
