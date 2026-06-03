"""Regression leaderboard table component."""

import dash_bootstrap_components as dbc
from dash import dcc, html

import config
from components.ui_styles import filter_label, make_data_table, page_panel
from metrics.calculator import metric_view_options


def build_leaderboard_layout() -> html.Div:
    default_pos = config.LEADERBOARD_DEFAULT_POSITION
    filters = dbc.Row(
        [
            dbc.Col(
                [
                    filter_label("Position"),
                    dcc.Dropdown(
                        id="position-filter",
                        options=[{"label": p, "value": p} for p in config.POSITIONS],
                        value=default_pos,
                        clearable=False,
                        className="dash-dropdown",
                    ),
                ],
                md=4,
                lg=2,
                sm=6,
            ),
            dbc.Col(
                [
                    filter_label("Focus score"),
                    dcc.Dropdown(
                        id="metric-view-filter",
                        options=metric_view_options(),
                        value=config.METRIC_VIEW_PRODUCTION,
                        clearable=False,
                        className="dash-dropdown",
                    ),
                ],
                md=4,
                lg=3,
                sm=6,
            ),
            dbc.Col(
                [
                    filter_label("Regression flag"),
                    dcc.Dropdown(
                        id="flag-filter",
                        options=[
                            {"label": config.FLAG_LABELS[k], "value": k}
                            for k in config.PLAYER_FLAG_KEYS
                        ],
                        value=list(config.PLAYER_FLAG_KEYS),
                        multi=True,
                        className="dash-dropdown",
                    ),
                ],
                md=4,
                lg=2,
                sm=6,
            ),
            dbc.Col(
                [
                    filter_label("Team"),
                    dcc.Dropdown(
                        id="team-filter",
                        options=[],
                        value=None,
                        multi=True,
                        placeholder="All teams",
                        className="dash-dropdown",
                    ),
                ],
                md=4,
                lg=2,
                sm=6,
            ),
            dbc.Col(
                [
                    filter_label("Minimum volume"),
                    dcc.Slider(
                        id="volume-slider",
                        min=0,
                        max=200,
                        step=10,
                        value=0,
                        marks={0: "0", 100: "100", 200: "200"},
                    ),
                ],
                md=8,
                lg=3,
                sm=12,
            ),
        ],
        className="g-3",
    )

    return page_panel(
        title="Regression Leaderboard",
        description=(
            f"Full-season {config.ANALYSIS_SEASON} stats for one position at a time. "
            "Click a player name for detail. Focus score sorts by production, role, or efficiency z. "
            f"Baseline: {config.BASELINE_SEASONS[0]}–{config.BASELINE_SEASONS[-1]} peak-age cohort."
        ),
        section_id="leaderboard-section",
        children=[
            html.Div(filters, className="filters-row"),
            dbc.Alert(id="leaderboard-status", is_open=False, color="warning", className="mb-3"),
            make_data_table(
                "leaderboard-table",
                columns=config.leaderboard_columns_for_position(default_pos),
                filter_action="none",
            ),
        ],
    )
