"""`network:`: proxies and TLS trust, exported to the process environment (`env_export.ENV_EXPORTS`)."""

from __future__ import annotations

from .base import Strict
from .fields import ExistingFile, ProxyUrl


class Network(Strict):
    """`extra_ca_cert`: a CA trusted on top of certifi's roots by the model layer, and NODE_EXTRA_CA_CERTS;
    `ca_bundle`: SSL_CERT_FILE, which replaces the default trust store. Both must exist."""

    http_proxy: ProxyUrl | None = None
    https_proxy: ProxyUrl | None = None
    all_proxy: ProxyUrl | None = None
    no_proxy: list[str] = []
    extra_ca_cert: ExistingFile | None = None
    ca_bundle: ExistingFile | None = None
