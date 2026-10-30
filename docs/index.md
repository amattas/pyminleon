# pyminleon

pyminleon is an asyncio Python library that controls the built-in effects of
Minleon NDB-Pro LED controllers over the HTTP endpoints the controller's own web
UI uses. Zero runtime dependencies (stdlib only), Python 3.12+.

It does not send pixel data. For that, use a DDP sender such as
[aioddp](https://amattas.github.io/aioddp/). While DDP data flows it overrides the
built-in effect; about 20 s after DDP stops the controller falls back to it.

<div class="pd-cards">
  <a class="pd-card" href="guide/safety/">
    <span class="pd-card-kicker">Guide</span>
    <span class="pd-card-title">Safety</span>
    <span class="pd-card-desc">What the library will and will not send to a controller.</span>
  </a>
  <a class="pd-card" href="api/reference/">
    <span class="pd-card-kicker">Reference</span>
    <span class="pd-card-title">API reference</span>
    <span class="pd-card-desc">NDBController, identify and the error types — generated from docstrings.</span>
  </a>
</div>

## Installation

```bash
pip install pyminleon
```

## Quick start

```python
import asyncio

from pyminleon import NDBController, identify


async def main() -> None:
    host = "10.0.40.20"  # placeholder
    if await identify(host) is None:
        raise SystemExit("not a supported Minleon controller")

    ndb = NDBController(host)
    state = await ndb.state()  # NDBState(effect="Glow", intensity=100, effects=("Off", ..., "Worms"))
    await ndb.set_effect("Color Wave")
    await ndb.set_intensity(60)
    await ndb.recall_preset(3)  # slots 0-9 are "Show 1", 10-19 "Show 2"
    layout = await ndb.config()  # raw JSON from GET /api/config (DDP-spec layout document)
    print(state, layout["config"]["ports"][0], (await ndb.status())["status"]["mod"])


asyncio.run(main())
```

## API overview

- `NDBController(host, *, port=80, timeout=3.0)`
    - `await state() -> NDBState` selected effect, intensity, and every effect the controller offers
    - `await presets() -> tuple[NDBPreset, ...]` stored show slots
    - `await set_effect(name)`, `await set_intensity(percent)`, `await recall_preset(slot)`
    - `await config() -> dict[str, Any]`, `await status() -> dict[str, Any]` raw `/api/config` and `/api/status` documents
- `await identify(host, *, port=80, timeout=3.0) -> str | None` the model id (e.g. `"NDBPRO"`) if the host reports a
  model in `SUPPORTED_MODELS`; `None` if it answers but is not a supported Minleon, or does not answer in time
- Errors: `MinleonError` > `ConfigError` (bad host, port, timeout, or argument), `ControllerError` (unreachable,
  timed out, non-200, or an unreadable page or document)

The [API reference](api/reference.md) documents every public name.
