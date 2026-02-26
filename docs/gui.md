# FIM24725 Dash UI

Dash-based control panel for the FIM24725 coherent optical receiver.
Communicates with the [FastAPI backend](rest_api.md) over HTTP.

---

## Running the UI

```bash
# 1. Start the API (mock hardware — no physical devices needed)
FUJ_MCU_MODE=mock FUJ_PSU1_LOCAL_IP="" FUJ_PSU2_LOCAL_IP="" \
  uvicorn fuj_backend.api.app:create_app --factory --port 8000

# 2. Start the UI (in a second terminal)
fuj-gui
```

Open `http://127.0.0.1:8050` in a browser.

Both processes can be pointed at real hardware by setting the API environment
variables — the GUI settings only control where the GUI itself listens and which
API URL it connects to.

---

## Configuration

Settings are loaded from environment variables (prefix `FUJ_GUI_`) or a `.env`
file in the working directory.

| Variable | Default | Description |
|---|---|---|
| `FUJ_GUI_API_BASE_URL` | `http://localhost:8000` | Base URL of the FastAPI backend |
| `FUJ_GUI_GUI_HOST` | `127.0.0.1` | Dash server bind address |
| `FUJ_GUI_GUI_PORT` | `8050` | Dash server port |
| `FUJ_GUI_DEBUG` | `false` | Enable Dash debug mode (hot-reload) |
| `FUJ_GUI_POLL_INTERVAL_MS` | `500` | Status + graph refresh interval (ms) |
| `FUJ_GUI_LOG_POLL_INTERVAL_MS` | `2000` | Log panel refresh interval (ms) |
| `FUJ_GUI_GRAPH_HISTORY_S` | `60` | Rolling graph window length (seconds) |

### Example `.env`

```bash
FUJ_GUI_API_BASE_URL=http://10.10.10.1:8000
FUJ_GUI_POLL_INTERVAL_MS=1000
FUJ_GUI_DEBUG=true
```

---

## Layout

```
┌─────────────────────────────────────────────────────────────┐
│ [● READY]   AGC ○──● MGC        [STARTUP]  [SHUTDOWN]      │  ← header
│─────────────────────────────────────────────────────────────│
│  Controls (col-4)         │   PI / MPD Graph (col-8)       │
│  ────────────────         │   ──────────────────────        │
│  VOA   [ 2.500 ] [Set]    │                                 │
│        0.0 – 4.8 V        │   5-trace time-series plot      │
│                           │   PI_XI  PI_XQ  PI_YI  PI_YQ   │
│  OA_X  [ 1.650 ] [Set]    │   MPD                           │
│        0.0 – 3.3 V        │   Rolling 60-second window      │
│                           │                                 │
│  OA_Y  [ 1.650 ] [Set]    │                                 │
│        0.0 – 3.3 V        │                                 │
│                           │                                 │
│  GA_X  [ 1.000 ] [Set]    │                                 │
│        0.0 – 3.3 V        │                                 │
│        [pre-staging]      │  ← badge visible in AGC mode    │
│                           │                                 │
│  GA_Y  [ 1.000 ] [Set]    │                                 │
│        0.0 – 3.3 V        │                                 │
│─────────────────────────────────────────────────────────────│
│  Logs (scrollable, 200px)                                   │
│  [INFO    ] fim24725.service — Step 4: Programming…         │
│  [DEBUG   ] fim24725.rails   — VCC_3V3: Write verified…     │
└─────────────────────────────────────────────────────────────┘
```

---

## Header

### State badge

Reflects the current system state, updated on every status poll.

| State | Badge color |
|---|---|
| `OFF` | Grey (secondary) |
| `STARTING` | Blue (info) |
| `READY` | Green (success) |
| `SHUTTING_DOWN` | Yellow (warning) |
| `FAULT` | Red (danger) |

### Mode toggle

A switch labelled **MGC**. Unchecked = AGC, checked = MGC.

- Only enabled when state is `READY`.
- Fires `POST /api/v1/mode` immediately on toggle.
- The status store refreshes after the call.

### STARTUP / SHUTDOWN buttons

Both are protected by a confirmation modal.

**STARTUP** is enabled only when state is `OFF`. Clicking it opens a modal where
the operator selects AGC or MGC as the initial mode before confirming. On
confirm, `POST /api/v1/startup` is called.

**SHUTDOWN** is enabled when state is not `OFF` or `SHUTTING_DOWN`. On confirm,
`POST /api/v1/shutdown` is called.

### Error toast

A dismissable toast (top-right, 5-second auto-dismiss) shown whenever an API
call returns an error. Displays the error message from the backend.

---

## Controls panel

One row per controllable output:

| Rail | Input ID | Range |
|---|---|---|
| VOA | `input-voa` | 0.0 – 4.8 V |
| OA_X | `input-oa-x` | 0.0 – 3.3 V |
| OA_Y | `input-oa-y` | 0.0 – 3.3 V |
| GA_X | `input-ga-x` | 0.0 – 3.3 V |
| GA_Y | `input-ga-y` | 0.0 – 3.3 V |

Each row has:
- A number input whose **placeholder** shows the current live PSU measurement
  (updated on every status poll).
- A **Set** button (`btn-set-<rail>`) that fires the corresponding
  `POST /api/v1/controls/<rail>` endpoint.
- All inputs and Set buttons are **disabled** when state is not `READY`.

**GA pre-staging**: When state is `READY` and mode is `AGC`, GA_X and GA_Y rows
show a grey *pre-staging* badge. The PSU accepts the written value and applies it
the moment the mode switches to MGC — no need to re-enter GA values after the
mode switch.

---

## PI / MPD graph

A Plotly time-series chart with five traces:

| Trace | Color |
|---|---|
| PI_XI | `#00b4d8` (cyan) |
| PI_XQ | `#90e0ef` (light cyan) |
| PI_YI | `#f77f00` (orange) |
| PI_YQ | `#fcbf49` (yellow-orange) |
| MPD | `#a8dadc` (teal) |

- Y-axis: 0 – 2.2 V (FIM24725 PI outputs are 0–2 V; MPD is similarly scaled).
- X-axis: rolling window controlled by `FUJ_GUI_GRAPH_HISTORY_S` (default 60 s).
- `uirevision="constant"` preserves the user's zoom/pan between updates.
- Data is appended on every status poll and trimmed to the rolling window.

---

## Log panel

Polls `GET /api/v1/logs?n=100` every `log_poll_interval_ms` (default 2 s).

Lines are colour-coded by log level:

| Level | Color |
|---|---|
| DEBUG | Muted grey |
| INFO | White |
| WARNING | Yellow |
| ERROR | Red |
| CRITICAL | Red bold |

The panel auto-scrolls to the bottom on each update. The full ISO timestamp is
available as a tooltip on each line.

---

## Polling and data flow

```
dcc.Interval (500ms)
    └─→ GET /api/v1/status
            └─→ status-store (dcc.Store)
                    ├─→ header update  (badge, toggle, buttons)
                    ├─→ controls update (placeholders, disabled state)
                    └─→ graph-store append → pi-mpd-graph render

dcc.Interval (2000ms)
    └─→ GET /api/v1/logs
            └─→ log-panel children
```

All control actions (Set, mode toggle, startup, shutdown) also refresh
`status-store` after the API call completes, so the header and placeholders
update immediately without waiting for the next interval.

---

## File structure

```
src/fuj_gui/
├── app.py                    Dash factory, layout assembly, main() entry point
├── config.py                 GUISettings (pydantic-settings, FUJ_GUI_ prefix)
├── api_client.py             Synchronous httpx wrapper; module-level singleton
├── callbacks/
│   ├── __init__.py           register_all(app, settings)
│   ├── status.py             Status poll, header, controls, mode, startup/shutdown, SET
│   ├── graph.py              graph-store accumulation + figure render
│   └── logs.py               Log poll + clientside auto-scroll
└── components/
    ├── __init__.py           Public component exports
    ├── header.py             State badge, mode toggle, buttons, modals, toast
    ├── controls.py           VOA/OA/GA input rows
    ├── graph.py              dcc.Graph panel + empty_figure() helper
    └── logs.py               Log panel + format_log_line() helper
```

---

## References

- [REST API Documentation](rest_api.md)
- [ADR-004: REST API Layer](adr/ADR-004-rest-api.md)
- [Dash documentation](https://dash.plotly.com/)
- [dash-bootstrap-components DARKLY theme](https://dash-bootstrap-components.opensource.faculty.ai/docs/themes/)
