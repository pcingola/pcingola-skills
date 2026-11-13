"""Extra CA certificate for TLS-intercepting proxies.

A proxy that intercepts HTTPS re-signs traffic with its
own root CA. A user behind such a proxy exports that root CA to a PEM file and
names it in the setting `EXTRA_CA_CERT` (or `NODE_EXTRA_CA_CERTS`). Callers add
the file `ca_cert` returns to their TLS context. With neither setting, `ca_cert`
returns None and callers keep the default trust (system store or certifi).
`SSL_CERT_FILE` is not read here: Python's `ssl` default context reads it.
"""

from __future__ import annotations

from pathlib import Path

from . import get

# Settings naming an extra CA file, in lookup order.
CA_CERT_KEYS = ("EXTRA_CA_CERT", "NODE_EXTRA_CA_CERTS")


def ca_cert(keys: tuple[str, ...] = CA_CERT_KEYS) -> Path | None:
    """The first setting of `keys` (`plugin_settings.get`) that names an existing file, else None."""
    for key in keys:
        v = (get(key) or "").strip()
        if v and Path(v).expanduser().is_file():
            return Path(v).expanduser()
    return None
