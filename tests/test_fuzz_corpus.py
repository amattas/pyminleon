"""Replay every fuzz/corpus/<target>/ input through that atheris target's ``check`` (its exception contract)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_FUZZ = Path(__file__).resolve().parent.parent / "fuzz"
_INPUTS = sorted(path for path in (_FUZZ / "corpus").glob("*/*") if path.is_file())


def _target(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _FUZZ / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", _INPUTS, ids=lambda path: f"{path.parent.name}/{path.name}")
def test_corpus_input_meets_the_target_contract(path: Path) -> None:
    _target(path.parent.name).check(path.read_bytes())
