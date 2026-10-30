"""Shared fixtures: a loopback HTTP server that plays a Minleon NDB-Pro, and the leaked-task check."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

# Captured verbatim from a Minleon NDB-Pro (firmware 2.0) at /api/config and /api/status, and its web UI pages.
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ndbpro"
NDB_CONFIG_JSON = (FIXTURES_DIR / "api_config.json").read_bytes()
NDB_STATUS_JSON = (FIXTURES_DIR / "api_status.json").read_bytes()
# The control endpoint's reply body is not recorded.
NDB_PAGES: dict[str, bytes] = {
    f"/{name}": (FIXTURES_DIR / name).read_bytes() for name in ("pfx2.html", "pcolors.html", "pshows.html")
}


class HTTPController:
    """Loopback HTTP server answering any method for each path in ``routes`` (query string ignored for routing).

    ``None`` or a missing path is a 404. ``requests`` records each request target; ``calls`` records
    ``(method, target, body)``, with the body read by ``Content-Length``.

    Paths in ``redirects`` answer 302 to the given location. ``slow`` maps a path to a misbehaving mode:
    ``"body"`` sends headers, then one body byte every 0.1 s; ``"head"`` sends the whole response one byte every
    0.1 s; both stop when the client hangs up. ``"chunked"`` sends the route's body chunked (``"badchunk"``
    with a malformed size), and
    ``"nolength"`` sends the route's body without a Content-Length header, ``"badstatus"`` answers
    ``HTTP/1.0 2² OK`` and ``"badlength"`` sends ``Content-Length: ²`` (non-ASCII digits).
    """

    host: str = "127.0.0.1"

    def __init__(self) -> None:
        self.port: int = 0
        self.routes: dict[str, bytes | None] = {
            "/api/config": NDB_CONFIG_JSON,
            "/api/status": NDB_STATUS_JSON,
            "/api/control": b"",
            **NDB_PAGES,
        }
        self.requests: list[str] = []
        self.calls: list[tuple[str, str, bytes]] = []
        self.redirects: dict[str, str] = {}
        self.slow: dict[str, str] = {}

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            method, target = (part.decode() for part in head.split(b" ", 2)[:2])
            length = 0
            for line in head.split(b"\r\n")[1:]:
                name, _, value = line.partition(b":")
                if name.strip().lower() == b"content-length":
                    length = int(value)
            body_in = await reader.readexactly(length) if length else b""
            self.requests.append(target)
            self.calls.append((method, target, body_in))
            path = target.partition("?")[0]
            if path in self.redirects:
                writer.write(
                    f"HTTP/1.1 302 Found\r\nLocation: {self.redirects[path]}\r\nContent-Length: 0\r\n"
                    "Connection: close\r\n\r\n".encode()
                )
                await writer.drain()
                return
            body = self.routes.get(path)
            status = "200 OK" if body is not None else "404 Not Found"
            body = body if body is not None else b"not found"
            response = (
                f"HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n".encode()
                + body
            )
            mode = self.slow.get(path)
            if mode == "head":
                await self._drip(reader, writer, response)
            elif mode == "body":
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n")
                await self._drip(reader, writer, b" " * 200)
            elif mode == "nolength":
                writer.write(b"HTTP/1.0 200 OK\r\n\r\n" + body)
                await writer.drain()
            elif mode == "badstatus":
                writer.write("HTTP/1.0 2\u00b2 OK\r\n\r\n".encode("latin-1") + body)
                await writer.drain()
            elif mode == "badlength":
                writer.write("HTTP/1.0 200 OK\r\nContent-Length: \u00b2\r\n\r\n".encode("latin-1") + body)
                await writer.drain()
            elif mode in ("chunked", "badchunk"):
                # What the NDB-Pro firmware sends: HTTP/1.1, chunked, lower-case hex sizes, even to HTTP/1.0 requests.
                chunks = b"".join(
                    b"%x\r\n%s\r\n" % (len(body[i : i + 1000]), body[i : i + 1000]) for i in range(0, len(body), 1000)
                )
                if mode == "badchunk":
                    chunks = b"zz\r\n" + chunks
                writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + chunks + b"0\r\n\r\n")
                await writer.drain()
            else:
                writer.write(response)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    @staticmethod
    async def _drip(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, data: bytes) -> None:
        try:
            for i in range(len(data)):
                writer.write(data[i : i + 1])
                await writer.drain()
                try:
                    if not await asyncio.wait_for(reader.read(1), 0.1):
                        return  # client hung up
                except TimeoutError:
                    continue
        except ConnectionError:
            return


@pytest.fixture
async def http_controller() -> AsyncIterator[HTTPController]:
    controller = HTTPController()
    server = await asyncio.start_server(controller.handle, HTTPController.host, 0)
    controller.port = server.sockets[0].getsockname()[1]
    try:
        yield controller
    finally:
        server.close()
        await server.wait_closed()


@pytest.fixture
async def _task_snapshot() -> AsyncIterator[None]:
    current = asyncio.current_task()
    before = asyncio.all_tasks() - {current}
    yield
    after = asyncio.all_tasks() - {asyncio.current_task(), current}
    leaked = after - before
    assert not leaked, f"test leaked asyncio tasks: {leaked}"


@pytest.fixture(autouse=True)
def no_leaked_tasks(request: pytest.FixtureRequest) -> Iterator[None]:
    """For async tests, assert no asyncio task outlives the test and its fixtures."""
    if inspect.iscoroutinefunction(request.function):
        request.getfixturevalue("_task_snapshot")
    yield
