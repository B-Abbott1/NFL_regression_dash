"""Team-level net regression risk bar chart."""

import dash_bootstrap_components as dbc
from dash import dcc

from components.ui_styles import page_panel


def build_team_view_layout():
    return page_panel(
        title="Team Regression Risk",
        description=(
            "Sum of qualified player composite z-scores by team. "
            "Higher values indicate more roster-wide positive regression risk (overperformance)."
        ),
        section_id="team-view-section",
        hidden=True,
        children=[
            dbc.Alert(id="team-view-status", is_open=False, color="warning", className="mb-3"),
            dcc.Graph(id="team-regression-chart", config={"displayModeBar": False}),
        ],
    )
