"""`References`: the reference recordings that speech requests carry (`reference_audio`), as files of the server.

A cloning speech model (Chatterbox) reads its reference from a file and keeps the conditioning of the last file it
read, keyed by path. Each recording is written once to `<sha256 of its bytes>.<format>` in a temporary directory of
the server, so the requests of one voice name one file and the model conditions on it once. The directory keeps the
`KEEP` most recently used recordings and is removed when the server stops.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import shutil
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from ai_models.chatterbox import REFERENCE_FIELD as FIELD
from ai_models.chatterbox import REFERENCE_FORMATS as FORMATS

from .server_error import ServerError

KEEP = 16


class References:
    """The reference recordings of one server, in a temporary directory until `close`."""

    def __init__(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="model-server-references-"))
        self._used: OrderedDict[Path, None] = OrderedDict()
        self._lock = threading.Lock()

    def path(self, field: Any) -> Path:
        """The file of the recording `field` (`{"data": <base64>, "format": <FORMATS>}`), written when it is new;
        `ServerError` 400 naming `reference_audio` when the field is not of that shape."""
        if not isinstance(field, dict) or set(field) != {"data", "format"} or not isinstance(field["data"], str):
            raise ServerError(400, f"`{FIELD}` is {{\"data\": <base64 audio>, \"format\": "
                              f"{' | '.join(FORMATS)}}}", param=FIELD)
        fmt = field["format"]
        if fmt not in FORMATS:
            raise ServerError(400, f"`{FIELD}.format` {fmt!r} is not one of {', '.join(FORMATS)}", param=FIELD)
        try:
            data = base64.b64decode(field["data"], validate=True)
        except (binascii.Error, ValueError):
            raise ServerError(400, f"`{FIELD}.data` is not base64", param=FIELD) from None
        if not data:
            raise ServerError(400, f"`{FIELD}.data` is empty", param=FIELD)
        p = self.dir / f"{hashlib.sha256(data).hexdigest()}.{fmt}"
        with self._lock:
            if not p.is_file():
                tmp = p.with_suffix(".part")
                tmp.write_bytes(data)
                tmp.replace(p)
            self._used[p] = None
            self._used.move_to_end(p)
            while len(self._used) > KEEP:
                old, _ = self._used.popitem(last=False)
                old.unlink(missing_ok=True)
        return p

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
