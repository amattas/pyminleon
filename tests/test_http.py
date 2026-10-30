"""The private HTTP client, exercised through NDBController against misbehaving loopback servers."""

from __future__ import annotations

import asyncio

import pytest

from pyminleon import ConfigError, ControllerError, NDBController
from pyminleon._http import url as http_url
from tests.conftest import NDB_CONFIG_JSON, HTTPController


@pytest.mark.parametrize(
    ("host", "path", "url"),
    [
        ("10.0.0.5", "/api/config", "http://10.0.0.5:80/api/config"),
        ("fe80::1", "api/status", "http://[fe80::1]:80/api/status"),
        ("[::1]", "/api/config", "http://[::1]:80/api/config"),
        ("::1", "/api/config", "http://[::1]:80/api/config"),
        ("ndb-pro.local", "/api/config", "http://ndb-pro.local:80/api/config"),
    ],
)
def test_url_brackets_ipv6(host: str, path: str, url: str) -> None:
    assert http_url(host, 80, path) == url


@pytest.mark.parametrize(
    "host",
    ["[zz", "127.0.0.1:99999/x?", "a\r\nb", "a@127.0.0.1", "127.0.0.1/x#", "", "[1.2.3.4]", "fe80::1%en0"],
)
def test_constructor_rejects_malformed_host(host: str) -> None:
    with pytest.raises(ConfigError, match="host"):
        NDBController(host)


@pytest.mark.parametrize("path", ["/api/config HTTP/1.0\r\nX-Injected: 1", "/a b"])
def test_url_rejects_malformed_path(path: str) -> None:
    with pytest.raises(ConfigError, match="path"):
        http_url("127.0.0.1", 80, path)


@pytest.mark.parametrize(
    ("mode", "body", "expected"),
    [
        ("nolength", NDB_CONFIG_JSON, None),
        ("nolength", b" " * (64 * 1024 + 1), "more than"),
        ("chunked", NDB_CONFIG_JSON, None),
        ("chunked", b" " * (64 * 1024 + 1), "more than"),
        ("badchunk", NDB_CONFIG_JSON, "chunk size"),
        ("badlength", NDB_CONFIG_JSON, None),  # unparsable Content-Length is treated as absent: read to EOF
        ("badstatus", NDB_CONFIG_JSON, "answered None"),  # unparsable status is non-200
    ],
    ids=[
        "unframed",
        "unframed-oversized",
        "chunked",
        "chunked-oversized",
        "chunked-malformed",
        "non-ascii-length",
        "non-ascii-status",
    ],
)
async def test_reads_unframed_or_chunked_body(
    http_controller: HTTPController, mode: str, body: bytes, expected: str | None
) -> None:
    http_controller.routes["/api/config"] = body
    http_controller.slow["/api/config"] = mode
    controller = NDBController(http_controller.host, port=http_controller.port)
    if expected is None:
        assert "config" in await controller.config()
    else:
        with pytest.raises(ControllerError, match=expected):
            await controller.config()


async def test_refuses_redirects(http_controller: HTTPController) -> None:
    connections: list[int] = []

    async def count(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connections.append(1)
        writer.close()
        await writer.wait_closed()

    other = await asyncio.start_server(count, "127.0.0.1", 0)
    try:
        other_port = other.sockets[0].getsockname()[1]
        http_controller.redirects["/api/config"] = f"http://127.0.0.1:{other_port}/api/config"
        with pytest.raises(ControllerError, match="302"):
            await NDBController(http_controller.host, port=http_controller.port).config()
    finally:
        other.close()
        await other.wait_closed()
    assert connections == []


async def test_connection_closed_before_head_is_controller_error() -> None:
    async def hang_up(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(hang_up, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        with pytest.raises(ControllerError, match="failed"):
            await NDBController("127.0.0.1", port=port, timeout=1.0).status()
    finally:
        server.close()
        await server.wait_closed()
