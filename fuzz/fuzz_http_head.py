"""atheris target: ``_parse_head`` on arbitrary bytes. Its contract is to never raise.

``check`` holds the contract so ``tests/test_fuzz_corpus.py`` replays ``fuzz/corpus/fuzz_http_head`` without atheris.
"""

from __future__ import annotations

import sys

from pyminleon._http import _parse_head


def check(data: bytes) -> None:
    _, headers = _parse_head(data)
    assert all(name == name.strip().lower() for name in headers), headers
    assert all(value == value.strip() for value in headers.values()), headers


def main() -> None:
    import atheris

    atheris.instrument_all()
    atheris.Setup(sys.argv, check)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
