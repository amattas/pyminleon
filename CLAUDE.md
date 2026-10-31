# pyminleon - Python Library for Minleon NDB-Pro Control

## Project Overview

**Purpose**: Standalone asyncio Python library that controls Minleon NDB-Pro LED controllers' built-in effects over the
HTTP endpoints the controller's web UI uses. Extracted from aioddp so aioddp stays a pure DDP (UDP pixel) library.

**Features**: `NDBController` (`state`, `presets`, `set_effect`, `set_intensity`, `recall_preset`, `config`,
`status`), `identify(host)`, `SUPPORTED_MODELS`. Zero runtime dependencies.

### What This Is NOT
- Not a DDP sender (aioddp is) and not a Home Assistant integration (hass-ddp is; it imports pyminleon)
- Not a writer of controller settings: no saved config, no preset saves

## Architecture

```
src/pyminleon/
├── __init__.py     # Public exports; consumers import only from `pyminleon`
├── ndb.py          # NDBController, NDBState, NDBPreset, identify, SUPPORTED_MODELS
├── _http.py        # Private minimal asyncio HTTP/1.0 client (chunked decoding, size caps, host validation)
└── exceptions.py   # MinleonError > ConfigError, ControllerError
```

## Safety invariants (tested; do not weaken)

- Never request `?s=N` on `/pshows.html` (saves a preset slot); never send `saveon`
- Only `POST /api/control`, `GET /pshows.html?r=N`, and read-only pages
- Unparsable HTML/JSON is a `ControllerError`, never a guess
- No redirects followed; bodies capped at 64 KiB; one deadline per call

## Development

Python env is the conda env `pyminleon` (never base, never venv).

```bash
conda run -n pyminleon python -m pytest -q
conda run -n pyminleon ruff check .
conda run -n pyminleon ruff format --check .
conda run -n pyminleon mypy
conda run -n pyminleon bandit -q -r src
```

Coverage gate: 90% total branch coverage (`fail_under` in pyproject.toml; every pytest run enforces it).

## Testing Approach

- pytest + pytest-asyncio (`asyncio_mode = "auto"`). TDD; parametrize variations of one behavior
- `http_controller` fixture: real asyncio HTTP server on loopback serving pages captured from a real NDB-Pro
  (`tests/fixtures/ndbpro/`), with slow, chunked, unframed, and redirect modes; no mocking of the client
- `no_leaked_tasks` autouse fixture enforces no orphaned asyncio tasks

## Technical Decisions

- `src/pyminleon` layout, hatchling, `requires-python >=3.12`, `dependencies = []`, extra: `dev`
- ruff (lint + format) line length 120, rules `E, F, I, B, UP, SIM, S`; mypy strict; bandit
- Standard `logging`; the Checks workflow runs on push to main and on approved pull requests

## License

Apache-2.0
