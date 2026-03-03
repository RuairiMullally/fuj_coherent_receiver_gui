"""Controls panel component: VOA, OA_X, OA_Y, GA_X, GA_Y input rows."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

_CONTROLS = [
    # (label, id_suffix, min, max, hint, is_ga)
    ("VOA",   "voa",   0.0, 4.8, "0.0 – 4.8 V", False),
    ("OA_X",  "oa-x",  0.5, 2.0, "0.5 – 2.0 V", False),
    ("OA_Y",  "oa-y",  0.5, 2.0, "0.5 – 2.0 V", False),
    ("GA_X",  "ga-x",  0.0, 3.3, "0.0 – 3.3 V", True),
    ("GA_Y",  "ga-y",  0.0, 3.3, "0.0 – 3.3 V", True),
]


def build_controls_panel() -> dbc.Card:
    rows = []
    for label, id_suffix, lo, hi, hint, is_ga in _CONTROLS:
        rows.append(_control_row(label, id_suffix, lo, hi, hint, is_ga))

    return dbc.Card(
        dbc.CardBody(rows),
        className="h-100",
    )


def _control_row(
    label: str,
    id_suffix: str,
    lo: float,
    hi: float,
    hint: str,
    is_ga: bool,
) -> html.Div:
    pre_stage_badge = dbc.Badge(
        "pre-staging",
        id=f"prestage-badge-{id_suffix}",
        color="secondary",
        className="ms-2",
        style={"display": "none"},
    ) if is_ga else html.Span()

    return html.Div(
        [
            dbc.InputGroup(
                [
                    dbc.InputGroupText(
                        [label, pre_stage_badge],
                        style={"minWidth": "90px"},
                    ),
                    dcc.Input(
                        id=f"input-{id_suffix}",
                        type="number",
                        min=lo,
                        max=hi,
                        step=0.001,
                        debounce=False,
                        placeholder="—",
                        disabled=True,
                        className="form-control bg-dark text-white",
                        style={"minWidth": "100px"},
                    ),
                    dbc.Button(
                        "Set",
                        id=f"btn-set-{id_suffix}",
                        color="primary",
                        disabled=True,
                        size="sm",
                    ),
                ],
                className="mb-1",
            ),
            html.Small(hint, className="text-muted ms-1"),
        ],
        className="mb-3",
    )
