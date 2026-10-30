# Safety

pyminleon talks to a controller through its own web UI endpoints, so it is
deliberately narrow about what it sends.

- **Nothing is ever written to the controller's saved settings.** The library never
  requests `/pshows.html?s=N` (which overwrites a preset slot) and never sends
  `saveon`. The only requests it makes are `POST /api/control`,
  `GET /pshows.html?r=N` (recall), and read-only pages (`/pfx2.html`,
  `/pcolors.html`, `/pshows.html`, `/api/config`, `/api/status`).
- **Strict parsing.** `state()` and `presets()` parse the web UI's HTML with strict
  patterns written against firmware 2.0 and raise `ControllerError` on anything
  else rather than guessing.
- **Bounded I/O.** HTTP responses are size-capped (64 KiB), redirects are never
  followed, and each call is bounded by `timeout`.
- **Validated hosts.** Hosts are validated (hostname, IPv4, or IPv6 literal only)
  so a value can never steer the path, port, or scheme.
