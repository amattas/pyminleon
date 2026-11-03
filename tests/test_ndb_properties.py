"""Property tests: the page and JSON parsers return a valid result or raise ``ControllerError``, never anything else."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyminleon import ControllerError, NDBPreset
from pyminleon.ndb import (
    _decode_object,
    _parse_effects,
    _parse_intensity,
    _parse_presets,
)
from tests.conftest import NDB_CONFIG_JSON, NDB_PAGES, NDB_STATUS_JSON

_REAL = [page.decode() for page in (*NDB_PAGES.values(), NDB_CONFIG_JSON, NDB_STATUS_JSON)]
# Tags, text runs, and JSON tokens of real NDB-Pro answers, spliced into real answers so the parsers' accept and
# reject paths are both reached.
_FRAGMENTS = sorted({fragment for page in _REAL for fragment in re.findall(r"<[^>]*>|[{}\[\],:]|\"[^\"]*\"|\w+", page)})
_SPLICE = st.one_of(st.sampled_from(_FRAGMENTS), st.text(max_size=10))


@st.composite
def _pages(draw: st.DrawFn) -> str:
    page = draw(st.sampled_from(_REAL))
    for _ in range(draw(st.integers(0, 4))):
        start = draw(st.integers(0, len(page)))
        end = draw(st.integers(start, min(len(page), start + 40)))
        page = page[:start] + draw(_SPLICE) + page[end:]
    return page


def _effects_ok(result: tuple[tuple[str, ...], str | None]) -> bool:
    effects, selected = result
    return bool(effects) and len(set(effects)) == len(effects) and (selected is None or selected in effects)


def _presets_ok(result: tuple[NDBPreset, ...]) -> bool:
    slots = [preset.slot for preset in result]
    return (
        bool(result)
        and len(set(slots)) == len(slots)
        and all(0 <= p.slot < 20 and p.effect and 0 <= p.intensity <= 100 for p in result)
    )


@pytest.mark.parametrize(
    ("parse", "valid"),
    [
        (_decode_object, lambda result: isinstance(result, dict)),
        (_parse_effects, _effects_ok),
        (_parse_intensity, lambda result: result is None or 0 <= result <= 100),
        (_parse_presets, _presets_ok),
    ],
    ids=["json-object", "effects", "intensity", "presets"],
)
@given(page=st.one_of(_pages(), st.lists(_SPLICE, max_size=40).map("".join)))
def test_parser_returns_a_valid_result_or_raises_controller_error(
    parse: Callable[[str, str], Any], valid: Callable[[Any], bool], page: str
) -> None:
    try:
        result = parse(page, "http://ndb/")
    except ControllerError:
        return
    assert valid(result), result
