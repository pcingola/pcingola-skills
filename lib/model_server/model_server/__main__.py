"""`python -m model_server`: run the server on `model_server.host` and `model_server.port` of config.yaml
(`plugin_settings.config`, which exits with the problems of an invalid file). The settings that libraries read from
the process environment (Hugging Face, proxies, CA files) are exported first (`plugin_settings.export`).

Host `::` listens on IPv6 and IPv4 through one dual-stack socket. uvicorn alone cannot do this: asyncio sets
`IPV6_V6ONLY` on the IPv6 sockets it creates."""

from __future__ import annotations

import socket

import plugin_settings
import uvicorn

from .app import create_app


def dual_stack_socket(port: int) -> socket.socket:
    """A socket bound to `[::]:<port>` with `IPV6_V6ONLY` off, so it also accepts IPv4 connections."""
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::", port))
    return sock


def main() -> None:
    cfg = plugin_settings.config()
    plugin_settings.export(cfg)
    s = cfg.model_server
    app = create_app(s)
    if s.host == "::":
        uvicorn.Server(uvicorn.Config(app, host=s.host, port=s.port)).run(sockets=[dual_stack_socket(s.port)])
    else:
        uvicorn.run(app, host=s.host, port=s.port)


if __name__ == "__main__":
    main()
