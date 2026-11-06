"""Control of the Minleon NDB-Pro over the HTTP endpoints its own web UI uses.

It selects the controller's built-in effects, sets their intensity and color palette, and recalls stored show presets;
it never writes the controller's saved settings (no ``saveon``, no preset ``Set``, no ``?s=N``). The controller exposes
its effect state only as HTML, so ``state``, ``presets`` and ``palette`` read the UI pages with strict regexes and
raise ``ControllerError`` when the markup is not what firmware 2.0 serves. ``config`` and ``status`` return the raw
JSON documents from ``/api/config`` and ``/api/status``. Stdlib only.

DDP pixel data overrides the built-in effect while it flows; about 20 s after DDP stops the controller falls back to it.
"""

from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pyminleon import _http
from pyminleon.exceptions import ConfigError, ControllerError

_LOGGER = logging.getLogger(__name__)

_EFFECTS_PATH = "/pfx2.html"
_COLORS_PATH = "/pcolors.html"
_SHOWS_PATH = "/pshows.html"
_CONTROL_PATH = "/api/control"
_CONFIG_PATH = "/api/config"
_STATUS_PATH = "/api/status"
_PRESET_SLOTS = 20  # "Show 1" is slots 0-9, "Show 2" is 10-19

SUPPORTED_MODELS: frozenset[str] = frozenset({"NDBPRO"})
"""Model ids (the ``mod`` field of ``/api/status``) that pyminleon supports."""

RGB = tuple[int, int, int]
"""An 8-bit-per-channel color, ``(red, green, blue)``."""

PALETTE_SIZE = 5
"""Custom color slots 1 to 5 on the colors page."""
BACKGROUND_SLOT = 6
"""The colors page's background color slot, for ``set_color``."""
# The colors page's preset buttons send these exact values; the controller drives its white LED for them.
COOL_WHITE: RGB = (0xFE, 0xFF, 0xFF)
"""What the page's "Cool White" button sends (``#feffff``)."""
WARM_WHITE: RGB = (0xFF, 0xFF, 0xFF)
"""What the page's "Warm White" button sends (``#ffffff``; the page only displays it as ``#c69740``)."""
NO_COLOR: RGB = (0, 0, 0)
"""An empty slot (the page's "Delete", ``#000000``). All five custom slots empty means automatic random colors."""

# <button id='fxb16' class='psel button' onclick='fx2b("Glow",16)'>; the page's JS defines fx2b(name,id), unquoted.
_BUTTON_START = re.compile(r"<button\s+id='fxb")
_EFFECT_BUTTON = re.compile(
    r"""<button id='fxb(\d{1,4})' class='(psel|pnsel) button' onclick='fx2b\("([^"<>]+)",\1\)'>""", re.ASCII
)
# <input type='range' min='1' max='100' class='slider Cint' value='100'>
_INTENSITY_SLIDER = re.compile(r"<input\b[^>]*\bclass='slider Cint'[^>]*>")
_SLIDER_VALUE = re.compile(r"\bvalue='(\d{1,3})'", re.ASCII)
# <a href="/pshows.html?r=0">Recall</a><td>Off<td>0<td ...
_RECALL_LINK = re.compile(r'href="/pshows\.html\?r=')
_PRESET_ROW = re.compile(r'<a href="/pshows\.html\?r=(\d{1,2})">Recall</a><td>([^<]*)<td>(\d{1,3})<', re.ASCII)
# <td id='bc1' bgcolor="#be38f3">: custom colors bc1-bc5, background bc6.
_COLOR_CELL_START = re.compile(r"<td\s+id='bc")
_COLOR_CELL = re.compile(r"""<td id='bc(\d{1,2})' bgcolor="#([0-9a-fA-F]{6})">""", re.ASCII)


@dataclass(frozen=True, slots=True)
class NDBState:
    """What the controller's UI shows: the selected built-in effect, its intensity, and every effect it offers."""

    effect: str | None  # selected built-in effect; None if the page shows none selected
    intensity: int | None  # 0-100; None if the colors page has no intensity slider
    effects: tuple[str, ...]  # in page order


@dataclass(frozen=True, slots=True)
class NDBPreset:
    """One stored show slot as listed on the shows page."""

    slot: int  # 0-19
    effect: str
    intensity: int  # 0-100


@dataclass(frozen=True, slots=True)
class NDBPalette:
    """The colors page's palette: custom colors 1 to 5 (``NO_COLOR`` for an empty slot) and the background color."""

    colors: tuple[RGB, ...]  # exactly PALETTE_SIZE entries, slot 1 first
    background: RGB

    @property
    def active(self) -> tuple[RGB, ...]:
        """The non-empty custom colors in slot order; empty means the controller picks random colors."""
        return tuple(color for color in self.colors if color != NO_COLOR)


class NDBController:
    """Selects and reads the built-in effects of a Minleon NDB-Pro over plain HTTP.

    Every call is one or two short HTTP/1.0 requests bounded by ``timeout`` each. ``ControllerError`` means the
    controller could not be reached, timed out, answered with a status other than 200, or answered with a page or
    document pyminleon cannot read.
    """

    def __init__(self, host: str, *, port: int = 80, timeout: float = 3.0) -> None:
        _http.url_host(host)
        self._host = host
        self._port = _http.validate_port(port)
        self._timeout = _http.validate_timeout(timeout)

    async def state(self) -> NDBState:
        """The selected effect and effect list from ``/pfx2.html``, and the intensity from ``/pcolors.html``."""
        effects, selected = _parse_effects(await self._page(_EFFECTS_PATH), self._url(_EFFECTS_PATH))
        intensity = _parse_intensity(await self._page(_COLORS_PATH), self._url(_COLORS_PATH))
        return NDBState(effect=selected, intensity=intensity, effects=effects)

    async def presets(self) -> tuple[NDBPreset, ...]:
        """The stored show slots from ``/pshows.html``, in page order."""
        return _parse_presets(await self._page(_SHOWS_PATH), self._url(_SHOWS_PATH))

    async def palette(self) -> NDBPalette:
        """The custom colors and background color from ``/pcolors.html``."""
        return _parse_palette(await self._page(_COLORS_PATH), self._url(_COLORS_PATH))

    async def config(self) -> dict[str, Any]:
        """The raw JSON object from ``GET /api/config`` (the DDP-spec configuration document)."""
        return await self._json_object(_CONFIG_PATH)

    async def status(self) -> dict[str, Any]:
        """The raw JSON object from ``GET /api/status`` (the DDP-spec status document)."""
        return await self._json_object(_STATUS_PATH)

    async def set_effect(self, name: str) -> None:
        """Select the built-in effect ``name`` (as listed in ``NDBState.effects``); "Off" blanks the lights."""
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"effect name must be a non-empty string, got {name!r}")
        await self._control({"fx": name})

    async def set_intensity(self, percent: int) -> None:
        """Set the built-in effect intensity, 0 to 100 percent."""
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise ConfigError(f"intensity must be an integer 0 to 100, got {percent!r}")
        await self._control({"int": str(percent)})

    async def recall_preset(self, slot: int) -> None:
        """Recall stored show slot ``slot`` (0-9 are "Show 1", 10-19 "Show 2"). Never saves."""
        if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot < _PRESET_SLOTS:
            raise ConfigError(f"preset slot must be an integer 0 to {_PRESET_SLOTS - 1}, got {slot!r}")
        await self._request("GET", f"{_SHOWS_PATH}?r={slot}")

    async def set_color(self, slot: int, color: RGB) -> None:
        """Set custom color ``slot`` 1 to 5, or the background (``BACKGROUND_SLOT``, 6). ``NO_COLOR`` empties it."""
        if isinstance(slot, bool) or not isinstance(slot, int) or not 1 <= slot <= BACKGROUND_SLOT:
            raise ConfigError(f"color slot must be an integer 1 to {BACKGROUND_SLOT}, got {slot!r}")
        await self._control({"color": {"i": slot, "c": _hex(_validate_rgb(color))}})

    async def set_palette(self, colors: Sequence[RGB], *, background: RGB | None = None) -> None:
        """Make the custom colors exactly ``colors`` (up to 5); the remaining slots are emptied.

        One request per slot, 1 to 5 in order, then the background if ``background`` is given. An empty ``colors``
        leaves the controller choosing random colors. Every color is validated before anything is sent.
        """
        if isinstance(colors, str) or not isinstance(colors, Sequence) or len(colors) > PALETTE_SIZE:
            raise ConfigError(f"palette must be a sequence of at most {PALETTE_SIZE} colors, got {colors!r}")
        slots = [_validate_rgb(color) for color in colors] + [NO_COLOR] * (PALETTE_SIZE - len(colors))
        if background is not None:
            slots.append(_validate_rgb(background))
        for slot, color in enumerate(slots, start=1):
            await self.set_color(slot, color)

    def _url(self, path: str) -> str:
        return _http.url(self._host, self._port, path)

    async def _control(self, fields: dict[str, object]) -> None:
        # Compact separators: byte-for-byte what the controller's own UI sends.
        body = json.dumps(fields, separators=(",", ":")).encode()
        await self._request("POST", _CONTROL_PATH, body)

    async def _json_object(self, path: str) -> dict[str, Any]:
        return _decode_object(await self._page(path), self._url(path))

    async def _page(self, path: str) -> str:
        url = self._url(path)
        body = (await self._request("GET", path)).body or b""  # a 200 always carries a body, possibly empty
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            raise ControllerError(f"{url} is not UTF-8 text") from None

    async def _request(self, method: str, path: str, body: bytes | None = None) -> _http.Response:
        url = self._url(path)
        try:
            response = await _http.request(
                self._host, self._port, path, timeout=self._timeout, method=method, body=body
            )
        except TimeoutError as exc:
            raise ControllerError(f"{method} {url} timed out after {self._timeout:g} s") from exc
        except _http.TRANSPORT_ERRORS as exc:
            raise ControllerError(f"{method} {url} failed: {exc}") from exc
        if response.status != 200:
            raise ControllerError(f"{method} {url} answered {response.status}")
        _LOGGER.debug("%s %s answered 200", method, url)
        return response


async def identify(host: str, *, port: int = 80, timeout: float = 3.0) -> str | None:
    """The supported model id (e.g. ``"NDBPRO"``) at ``host``, or ``None``.

    ``None`` means the host did not answer in time, did not answer ``GET /api/status`` with a JSON status, or reports
    a model not in ``SUPPORTED_MODELS``. ``ConfigError`` for a bad host, port, or timeout.
    """
    controller = NDBController(host, port=port, timeout=timeout)
    try:
        document = await controller.status()
    except ControllerError:
        return None
    nested = document.get("status")
    model = (nested if isinstance(nested, dict) else document).get("mod")
    return model if isinstance(model, str) and model in SUPPORTED_MODELS else None


def _validate_rgb(color: object) -> RGB:
    if (
        not isinstance(color, tuple | list)
        or len(color) != 3
        or not all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in color)
    ):
        raise ConfigError(f"color must be three integers 0 to 255, got {color!r}")
    return (color[0], color[1], color[2])


def _hex(color: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


def _decode_object(page: str, url: str) -> dict[str, Any]:
    try:
        document = json.loads(page)
    except (ValueError, RecursionError):  # json recurses per nesting level; deep input exhausts the recursion limit
        raise ControllerError(f"{url} is not valid JSON") from None
    if not isinstance(document, dict):
        raise ControllerError(f"{url} is not a JSON object")
    return document


def _parse_effects(page: str, url: str) -> tuple[tuple[str, ...], str | None]:
    buttons = _EFFECT_BUTTON.findall(page)
    if not buttons:
        raise ControllerError(f"{url} has no effect buttons")
    if len(buttons) != len(_BUTTON_START.findall(page)):
        raise ControllerError(f"{url} has effect button markup pyminleon does not recognize")
    effects: list[str] = []
    selected: list[str] = []
    for _, css, raw_name in buttons:
        name = html.unescape(raw_name)
        if name in effects:
            raise ControllerError(f"{url} lists effect {name!r} more than once")
        effects.append(name)
        if css == "psel":
            selected.append(name)
    if len(selected) > 1:
        raise ControllerError(f"{url} shows {len(selected)} effects selected: {selected!r}")
    return tuple(effects), selected[0] if selected else None


def _parse_intensity(page: str, url: str) -> int | None:
    sliders = _INTENSITY_SLIDER.findall(page)
    if not sliders:
        return None
    if len(sliders) > 1:
        raise ControllerError(f"{url} has {len(sliders)} intensity sliders")
    value = _SLIDER_VALUE.search(sliders[0])
    intensity = int(value.group(1)) if value else None
    if intensity is None or intensity > 100:
        raise ControllerError(f"{url} intensity slider has no value 0 to 100: {sliders[0]!r}")
    return intensity


def _parse_presets(page: str, url: str) -> tuple[NDBPreset, ...]:
    rows = _PRESET_ROW.findall(page)
    if not rows:
        raise ControllerError(f"{url} has no preset rows")
    if len(rows) != len(_RECALL_LINK.findall(page)):
        raise ControllerError(f"{url} has preset rows pyminleon does not recognize")
    presets: list[NDBPreset] = []
    seen: set[int] = set()
    for raw_slot, raw_effect, raw_intensity in rows:
        slot, effect, intensity = int(raw_slot), html.unescape(raw_effect).strip(), int(raw_intensity)
        if slot >= _PRESET_SLOTS or slot in seen:
            raise ControllerError(f"{url} lists preset slot {slot}, outside 0 to {_PRESET_SLOTS - 1} or repeated")
        if not effect or intensity > 100:
            raise ControllerError(f"{url} slot {slot}: effect {effect!r} at intensity {intensity} is not usable")
        seen.add(slot)
        presets.append(NDBPreset(slot, effect, intensity))
    return tuple(presets)


def _parse_palette(page: str, url: str) -> NDBPalette:
    cells = _COLOR_CELL.findall(page)
    if len(cells) != len(_COLOR_CELL_START.findall(page)):
        raise ControllerError(f"{url} has color cell markup pyminleon does not recognize")
    colors: dict[int, RGB] = {}
    for raw_slot, raw_hex in cells:
        slot = int(raw_slot)
        if not 1 <= slot <= BACKGROUND_SLOT or slot in colors:
            raise ControllerError(f"{url} lists color cell bc{slot}, outside bc1 to bc{BACKGROUND_SLOT} or repeated")
        colors[slot] = (int(raw_hex[0:2], 16), int(raw_hex[2:4], 16), int(raw_hex[4:6], 16))
    missing = [f"bc{slot}" for slot in range(1, BACKGROUND_SLOT + 1) if slot not in colors]
    if missing:
        raise ControllerError(f"{url} has no color cell {', '.join(missing)}")
    return NDBPalette(
        colors=tuple(colors[slot] for slot in range(1, PALETTE_SIZE + 1)), background=colors[BACKGROUND_SLOT]
    )
