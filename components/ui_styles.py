"""Shared UI styling for tables, panels, and filters."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dash_table, html

import config
from components.team_logos import TEAM_LOGO_CELL_STYLES, TEAM_LOGO_SIZE_PX

# Must match make_data_table page_size (active_cell row is page-local when paginated).
TABLE_PAGE_SIZE = 25

# Readable on dark surfaces — flag column uses accent text, not full-row tint
TABLE_STYLE_HEADER = {
    "backgroundColor": "#21262d",
    "color": "#f0f3f6",
    "fontWeight": "600",
    "fontSize": "0.8rem",
    "textTransform": "uppercase",
    "letterSpacing": "0.04em",
    "border": "1px solid #373e47",
    "padding": "10px 12px",
}

TABLE_STYLE_CELL = {
    "backgroundColor": "#161b22",
    "color": "#e6edf3",
    "fontSize": "0.9rem",
    "border": "1px solid #30363d",
    "padding": "10px 12px",
    "textAlign": "left",
    "minWidth": "80px",
}

PLAYER_NAME_TABLE_STYLES = [
    {
        "if": {"column_id": "player_name"},
        "cursor": "pointer",
        "color": "#58a6ff",
        "fontWeight": "500",
    },
    {
        "if": {"column_id": "player_name", "state": "active"},
        "textDecoration": "underline",
    },
]

TABLE_STYLE_DATA_CONDITIONAL = [
    {
        "if": {"state": "selected"},
        "backgroundColor": "#1f3a5f",
        "border": "1px solid #388bfd",
    },
    *PLAYER_NAME_TABLE_STYLES,
    {
        "if": {"column_id": "flag_label"},
        "fontWeight": "600",
    },
    {
        "if": {"filter_query": "{flag} = regress_negative", "column_id": "flag_label"},
        "color": config.FLAG_COLORS["regress_negative"],
    },
    {
        "if": {"filter_query": "{flag} = star", "column_id": "flag_label"},
        "color": config.FLAG_COLORS["star"],
    },
    {
        "if": {"filter_query": "{flag} = breakout", "column_id": "flag_label"},
        "color": config.FLAG_COLORS["breakout"],
    },
    {
        "if": {"filter_query": "{flag} = positive_outlook", "column_id": "flag_label"},
        "color": config.FLAG_COLORS["positive_outlook"],
    },
    {
        "if": {"filter_query": "{flag} = neutral", "column_id": "flag_label"},
        "color": config.FLAG_COLORS["neutral"],
    },
]

TABLE_STYLE_FILTER = {
    "backgroundColor": "#21262d",
    "color": "#e6edf3",
}

TABLE_STYLE_PAGE = {
    "backgroundColor": "#161b22",
    "color": "#e6edf3",
}


def page_panel(title: str, description: str, children: list, section_id: str, hidden: bool = False) -> html.Div:
    """Card-wrapped page section with title and description."""
    return html.Div(
        dbc.Card(
            dbc.CardBody(
                [
                    html.H4(title, className="page-title mb-2"),
                    html.P(description, className="page-description mb-4"),
                    *children,
                ],
                className="p-4",
            ),
            className="page-card border-0 shadow-sm",
        ),
        id=section_id,
        className="page-section",
        style={"display": "none"} if hidden else {"display": "block"},
    )


def filter_label(text: str) -> html.Label:
    return html.Label(text, className="filter-label mb-2")


def make_data_table(
    table_id: str,
    columns: list,
    *,
    filter_action: str = "native",
    **extra,
) -> dash_table.DataTable:
    """DataTable with consistent professional styling."""
    extra = dict(extra)
    extra_conditional = extra.pop("style_data_conditional", None)
    props = {
        "id": table_id,
        "columns": columns,
        "data": [],
        "sort_action": "native",
        "filter_action": filter_action,
        "page_action": "native",
        "page_size": TABLE_PAGE_SIZE,
        "markdown_options": {"html": True, "link_target": "_self"},
        "style_table": {"overflowX": "auto", "borderRadius": "8px"},
        "style_header": TABLE_STYLE_HEADER,
        "style_cell": TABLE_STYLE_CELL,
        "style_data_conditional": TABLE_STYLE_DATA_CONDITIONAL + TEAM_LOGO_CELL_STYLES,
        "style_filter": TABLE_STYLE_FILTER,
        "css": [
            {"selector": ".dash-spreadsheet-menu", "rule": "background-color: #21262d;"},
            {"selector": ".dash-spreadsheet-menu-item", "rule": "color: #e6edf3;"},
            {"selector": "td.dash-cell input", "rule": "background-color: #0d1117; color: #e6edf3;"},
            {
                "selector": ".dash-cell.column-team_logo img, .dash-cell.column-team_logo_prev img, .dash-cell[data-dash-column=\"team_logo\"] img, .dash-cell[data-dash-column=\"team_logo_prev\"] img",
                "rule": (
                    f"height: {TEAM_LOGO_SIZE_PX}px !important; "
                    f"width: {TEAM_LOGO_SIZE_PX}px !important; "
                    f"max-height: {TEAM_LOGO_SIZE_PX}px !important; "
                    f"max-width: {TEAM_LOGO_SIZE_PX}px !important; "
                    "object-fit: contain; display: block; margin: 0 auto;"
                ),
            },
        ],
    }
    if extra_conditional:
        props["style_data_conditional"] = props["style_data_conditional"] + extra_conditional
    props.update(extra)
    return dash_table.DataTable(**props)
