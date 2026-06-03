"""2026 outlook — positive and negative regression candidates from 2025 analysis."""

import dash_bootstrap_components as dbc

import config
from components.team_logos import TEAM_LOGO_COLUMN
from components.ui_styles import TABLE_STYLE_DATA_CONDITIONAL, make_data_table, page_panel

OUTLOOK_STYLE_EXTRA = [
    {
        "if": {"filter_query": "{flag} = star", "column_id": "outlook_type"},
        "color": config.FLAG_COLORS["star"],
        "fontWeight": "600",
    },
    {
        "if": {"filter_query": "{flag} = breakout", "column_id": "outlook_type"},
        "color": config.FLAG_COLORS["breakout"],
        "fontWeight": "600",
    },
    {
        "if": {"filter_query": "{flag} = positive_outlook", "column_id": "outlook_type"},
        "color": config.FLAG_COLORS["positive_outlook"],
        "fontWeight": "600",
    },
    {
        "if": {"filter_query": "{flag} = regress_negative", "column_id": "outlook_type"},
        "color": config.FLAG_COLORS["regress_negative"],
        "fontWeight": "600",
    },
]


def build_outlook_2026_layout():
    return page_panel(
        title=f"{config.OUTLOOK_SEASON} Regression Outlook",
        description=(
            f"Tagged players after the {config.ANALYSIS_SEASON} season (v12): stars, "
            "breakouts, positive outlook, and negative regression risk vs the "
            f"{config.BASELINE_SEASONS[0]}–{config.BASELINE_SEASONS[-1]} baseline. "
            f"Projected team from {config.ROSTER_SEASON_FOR_OUTLOOK} rosters. "
            "Rookies are out of scope."
        ),
        section_id="outlook-2026-section",
        hidden=True,
        children=[
            dbc.Alert(id="outlook-2026-status", is_open=False, color="warning", className="mb-3"),
            make_data_table(
                "outlook-2026-table",
                columns=[
                    TEAM_LOGO_COLUMN,
                    config.PLAYER_NAME_COLUMN,
                    {"name": "Pos", "id": "position"},
                    {"name": f"{config.OUTLOOK_SEASON} Team", "id": "projected_team"},
                    {"name": "Outlook", "id": "outlook_type"},
                    {"name": "2025 Z", "id": "composite_z", "type": "numeric", "format": {"specifier": ".2f"}},
                    {"name": "Primary Metric", "id": "primary_metric_name"},
                    {"name": "Current", "id": "primary_value", "type": "numeric", "format": {"specifier": ".3f"}},
                    {"name": "Expected", "id": "primary_expected", "type": "numeric", "format": {"specifier": ".3f"}},
                    {"name": "Flag", "id": "flag_label"},
                ],
                style_data_conditional=TABLE_STYLE_DATA_CONDITIONAL + OUTLOOK_STYLE_EXTRA,
            ),
        ],
    )
