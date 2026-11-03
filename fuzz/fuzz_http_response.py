"""atheris target: ``_read_response`` (head, Content-Length, read-to-EOF, and chunked bodies) on arbitrary bytes.

The bytes are what the controller sent, fed through an in-memory ``asyncio.StreamReader`` with the client's
``MAX_HEAD`` limit. Contract: a ``Response`` whose body is at most ``MAX_BODY`` bytes (and present only for a 200),
or one of ``CONTRACT``; anything else is a finding. ``check`` holds the contract so
``tests/test_fuzz_corpus.py`` replays ``fuzz/corpus/fuzz_http_response`` without atheris.
"""

from __future__ import annotations

import asyncio
import sys

from pyminleon._http import MAX_BODY, MAX_HEAD, _read_response
from pyminleon.exceptions import ControllerError

CONTRACT = (ControllerError, asyncio.IncompleteReadError, asyncio.LimitOverrunError)


async def _read(data: bytes) -> None:
    reader = asyncio.StreamReader(limit=MAX_HEAD)
    reader.feed_data(data)
    reader.feed_eof()
    try:
        response = await _read_response(reader, "GET", "http://fuzz/")
    except CONTRACT:
        return
    assert (response.body is not None) == (response.status == 200), response
    assert response.body is None or len(response.body) <= MAX_BODY, len(response.body or b"")


def check(data: bytes) -> None:
    asyncio.run(_read(data))


def main() -> None:
    import atheris

    atheris.instrument_all()
    atheris.Setup(sys.argv, check)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
