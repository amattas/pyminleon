# pyminleon

Asyncio Python library that controls the built-in effects of Minleon NDB-Pro LED controllers over the HTTP endpoints
the controller's own web UI uses. Zero runtime dependencies (stdlib only), Python 3.12+.

It does not send pixel data. For that, use a DDP sender such as [aioddp](https://github.com/amattas/aioddp). While DDP
data flows it overrides the built-in effect; about 20 s after DDP stops the controller falls back to it.

## Quick start

```python
import asyncio

from pyminleon import WARM_WHITE, NDBController, identify


async def main() -> None:
    host = "10.0.40.20"  # placeholder
    if await identify(host) is None:
        raise SystemExit("not a supported Minleon controller")

    ndb = NDBController(host)
    state = await ndb.state()  # NDBState(effect="Glow", intensity=100, effects=("Off", ..., "Worms"))
    await ndb.set_effect("Color Wave")
    await ndb.set_intensity(60)
    await ndb.set_palette([(255, 0, 0), WARM_WHITE])  # slots 3-5 emptied
    await ndb.recall_preset(3)  # slots 0-9 are "Show 1", 10-19 "Show 2"
    layout = await ndb.config()  # raw JSON from GET /api/config (DDP-spec layout document)
    print(state, layout["config"]["ports"][0], (await ndb.status())["status"]["mod"])


asyncio.run(main())
```

## API

- `NDBController(host, *, port=80, timeout=3.0)`
  - `await state() -> NDBState` selected effect, intensity, and every effect the controller offers
  - `await presets() -> tuple[NDBPreset, ...]` stored show slots
  - `await set_effect(name)`, `await set_intensity(percent)`, `await recall_preset(slot)`
  - `await palette() -> NDBPalette` custom colors 1-5 (`NO_COLOR` when empty; `.active` lists the
    non-empty ones) and the background color, as `RGB` tuples
  - `await set_color(slot, rgb)` one slot (1-5, or `BACKGROUND_SLOT` 6); `await set_palette(colors, *,
    background=None)` makes the custom colors exactly `colors` (up to 5; the rest are emptied, and none
    at all means automatic random colors). `COOL_WHITE` and `WARM_WHITE` are the values the colors page's
    white buttons send, which the controller maps to its white LED
  - `await config() -> dict[str, Any]`, `await status() -> dict[str, Any]` raw `/api/config` and `/api/status` documents
- `await identify(host, *, port=80, timeout=3.0) -> str | None` the model id (e.g. `"NDBPRO"`) if the host reports a
  model in `SUPPORTED_MODELS`; `None` if it answers but is not a supported Minleon, or does not answer in time
- Errors: `MinleonError` > `ConfigError` (bad host, port, timeout, or argument), `ControllerError` (unreachable,
  timed out, non-200, or an unreadable page or document)

## Safety

- Nothing is ever written to the controller's saved settings. The library never requests `/pshows.html?s=N` (which
  overwrites a preset slot) and never sends `saveon`. The only requests it makes are `POST /api/control`,
  `GET /pshows.html?r=N` (recall), and read-only pages (`/pfx2.html`, `/pcolors.html`, `/pshows.html`,
  `/api/config`, `/api/status`).
- `state()`, `presets()` and `palette()` parse the web UI's HTML with strict patterns written against firmware 2.0
  and raise `ControllerError` on anything else rather than guessing.
- HTTP responses are size-capped (64 KiB), redirects are never followed, and each call is bounded by `timeout`.
- Hosts are validated (hostname, IPv4, or IPv6 literal only) so a value can never steer the path, port, or scheme.

## Documentation

https://amattas.github.io/pyminleon/

## Development

```bash
conda create -n pyminleon -c conda-forge python=3.14
conda run -n pyminleon python -m pip install -e ".[dev]"
conda run -n pyminleon python -m pytest -q
conda run -n pyminleon ruff check . && conda run -n pyminleon ruff format --check . && conda run -n pyminleon mypy
conda run -n pyminleon bandit -q -r src
```

## License

Apache-2.0
