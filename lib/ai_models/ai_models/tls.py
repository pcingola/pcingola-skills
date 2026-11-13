"""TLS context for remote providers: certifi roots plus an extra CA (setting EXTRA_CA_CERT)."""

from __future__ import annotations

import functools
import ssl
from pathlib import Path

from plugin_settings.ca import CA_CERT_KEYS
from plugin_settings.ca import ca_cert as _ca_cert


def ca_cert(keys: tuple[str, ...] = CA_CERT_KEYS) -> Path | None:
    """The extra CA to trust: the first setting of `keys` (EXTRA_CA_CERT, then
    NODE_EXTRA_CA_CERTS) naming an existing file, else None."""
    return _ca_cert(keys)


def ssl_context(ca: Path | None) -> ssl.SSLContext:
    """An httpx-compatible `verify` SSLContext: certifi's roots plus `ca`.

    The process default is not used: a machine behind a TLS-intercepting
    proxy can point SSL_CERT_FILE at the proxy CA alone, which replaces the
    public root bundle and breaks the public chain of the model endpoints. certifi restores
    the public roots; the extra CA is added on top so intercepted endpoints
    still verify.
    """
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - certifi missing: fall back to system store
        ctx = ssl.create_default_context()

    if ca is not None:
        try:
            ctx.load_verify_locations(cafile=str(ca))
        except ssl.SSLError:
            pass  # malformed extra cert: keep certifi trust only
    return ctx


@functools.cache
def _cached_context(ca: Path | None) -> ssl.SSLContext:
    return ssl_context(ca)


def ssl_verify() -> ssl.SSLContext:
    """`ssl_context(ca_cert())`, one context object per extra CA file, so
    clients keyed by their TLS context (`clients`) are shared."""
    return _cached_context(ca_cert())
