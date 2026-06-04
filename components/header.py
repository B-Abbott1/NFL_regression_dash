"""App header and navigation."""

import dash_bootstrap_components as dbc
from dash import dcc, html

import config

NAV_ITEMS = [
    ("leaderboard", "Leaderboard"),
    ("scatter", "Scatter"),
    ("outlook-2026", "2026 Outlook"),
    ("team", "Teams"),
]


def build_header() -> dbc.Navbar:
    links = [
        dbc.NavItem(
            dbc.NavLink(
                label,
                href="#",
                id=f"nav-{nav_id}",
                active=(nav_id == "leaderboard"),
            )
        )
        for nav_id, label in NAV_ITEMS
    ]

    return dbc.Navbar(
        dbc.Container(
            [
                html.Div(
                    [
                        dbc.NavbarBrand(
                            [
                                "NFL Regression Analytics",
                                html.Span(
                                    "Next Gen Stats · Player regression signals",
                                    className="navbar-brand-sub",
                                ),
                            ],
                            className="py-0",
                        ),
                    ]
                ),
                dbc.Nav(
                    links
                    + [
                        dbc.NavItem(
                            dcc.Loading(
                                id="refresh-metrics-loading",
                                type="circle",
                                color="#58a6ff",
                                parent_style={"display": "inline-block"},
                                children=[
                                    dbc.Button(
                                        "Refresh metrics",
                                        id="refresh-metrics-btn",
                                        color="primary",
                                        outline=True,
                                        size="sm",
                                        className="ms-2 refresh-metrics-btn",
                                        title="Recompute scores from cached raw data (use after editing calculator.py)",
                                    ),
                                    dbc.Button(
                                        "Refresh flags",
                                        id="refresh-flags-btn",
                                        color="secondary",
                                        outline=True,
                                        size="sm",
                                        className="ms-2 refresh-flags-btn",
                                        title="Re-apply tags from config TAG_*_PCT rules (fast; use after editing New_scoring thresholds)",
                                    ),
                                ],
                            )
                        ),
                    ],
                    className="ms-auto align-items-center",
                    navbar=True,
                ),
            ],
            fluid=True,
        ),
        dark=True,
        className="app-navbar mb-0",
    )
