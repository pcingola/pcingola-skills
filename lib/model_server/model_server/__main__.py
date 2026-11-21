"""`python -m model_server`: run the server on `model_server.host` and `model_server.port` of config.yaml
(`plugin_settings.config`, which exits with the problems of an invalid file). The settings that libraries read from
the process environment (Hugging Face, proxies, CA files) are exported first (`plugin_settings.export`)."""

from __future__ import annotations

import plugin_settings
import uvicorn

from .app import create_app


def main() -> None:
    cfg = plugin_settings.config()
    plugin_settings.export(cfg)
    s = cfg.model_server
    uvicorn.run(create_app(s), host=s.host, port=s.port)


if __name__ == "__main__":
    main()
