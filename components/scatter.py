"""Position scatter plot component."""

import dash_bootstrap_components as dbc
from dash import dcc, html

import config
from components.ui_styles import filter_label, page_panel


def _metric_options(position: str) -> list[dict]:
    defs = config.METRIC_DEFINITIONS.get(position, {})
    return [{"label": meta["name"], "value": mid} for mid, meta in defs.items()]


def build_scatter_layout():
    default_pos = "QB"
    options = _metric_options(default_pos)

    filters = dbc.Row(
        [
            dbc.Col(
                [
                    filter_label("Position"),
                    dcc.Dropdown(
                        id="scatter-position",
                        options=[{"label": p, "value": p} for p in config.POSITIONS],
                        value=default_pos,
                        clearable=False,
                        className="dash-dropdown",
                    ),
                ],
                md=4,
                sm=6,
            ),
            dbc.Col(
                [
                    filter_label("X axis"),
                    dcc.Dropdown(
                        id="scatter-x-metric",
                        options=options,
                        value=options[0]["value"] if options else None,
                        clearable=False,
                        className="dash-dropdown",
                    ),
                ],
                md=4,
                sm=6,
            ),
            dbc.Col(
                [
                    filter_label("Y axis"),
                    dcc.Dropdown(
                        id="scatter-y-metric",
                        options=options,
                        value=options[1]["value"] if len(options) > 1 else None,
                        clearable=False,
                        className="dash-dropdown",
                    ),
                ],
                md=4,
                sm=6,
            ),
        ],
        className="g-3",
    )

    return page_panel(
        title="Metric Scatter",
        description=(
            f"Compare two process or NGS metrics for qualified {config.ANALYSIS_SEASON} players. "
            "Points are colored by regression flag."
        ),
        section_id="scatter-section",
        hidden=True,
        children=[
            html.Div(filters, className="filters-row"),
            html.Div(
                dcc.Graph(
                    id="scatter-plot",
                    config={"displayModeBar": False, "responsive": True},
                    style={"height": "560px", "width": "100%"},
                ),
                className="scatter-chart-wrap",
            ),
        ],
    )
