"""NFL NGS Regression Dashboard — Dash application entry point."""

from __future__ import annotations

import logging

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import dcc, html

import config
from callbacks import register_callbacks
from components.header import build_header
from components.leaderboard import build_leaderboard_layout
from components.outlook_2026 import build_outlook_2026_layout
from components.player_detail import build_player_detail_panel
from components.scatter import build_scatter_layout
from components.team_view import build_team_view_layout
from metrics.calculator import (
    build_df_metrics,
    build_outlook_2026_df,
    build_team_summary_df,
)
from metrics.loader import load_all_data, load_metrics_computed, refresh_metrics_cache
from metrics.calculator import reapply_player_tags
from metrics.session import pack_session, recompute_session, reload_scoring_modules

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

RAW_DATA: dict = {}
df_metrics: pd.DataFrame | None = None
df_outlook_2026: pd.DataFrame | None = None
df_team_summary: pd.DataFrame | None = None
load_error: str | None = None


def load_app_data() -> tuple[pd.DataFrame, dict, pd.DataFrame, pd.DataFrame, str | None]:
    """Load raw sources and all derived tables for the app session."""
    raw: dict = {}
    metrics = load_metrics_computed()

    if metrics is not None and not metrics.empty:
        logger.info("Loaded metrics from cache (%s rows)", len(metrics))
        try:
            raw = load_all_data(force_refresh=False)
        except Exception:
            logger.exception("Failed to load raw data alongside metrics cache")
            raw = {}
    else:
        try:
            raw = load_all_data(force_refresh=False)
            metrics = build_df_metrics(raw, config.ANALYSIS_SEASON)
            if not metrics.empty:
                refresh_metrics_cache(metrics)
        except ImportError:
            msg = "nfl_data_py is not installed. Run: .\\install.ps1"
            logger.warning(msg)
            empty = build_df_metrics({})
            return empty, {}, pd.DataFrame(), pd.DataFrame(), msg
        except Exception as exc:
            msg = f"Data load failed: {exc}"
            logger.exception(msg)
            empty = build_df_metrics({})
            return empty, {}, pd.DataFrame(), pd.DataFrame(), msg

    rosters = raw.get("rosters", pd.DataFrame()) if raw else pd.DataFrame()
    outlook = build_outlook_2026_df(metrics, rosters) if not metrics.empty else pd.DataFrame()
    team = build_team_summary_df(metrics)

    return metrics, raw, outlook, team, None


df_metrics, RAW_DATA, df_outlook_2026, df_team_summary, load_error = load_app_data()
reload_scoring_modules()
if df_metrics is not None and not df_metrics.empty:
    df_metrics = reapply_player_tags(df_metrics)
    rosters = RAW_DATA.get("rosters", pd.DataFrame()) if RAW_DATA else pd.DataFrame()
    df_outlook_2026 = build_outlook_2026_df(df_metrics, rosters)
    df_team_summary = build_team_summary_df(df_metrics)
_initial_session = pack_session(df_metrics, df_outlook_2026, df_team_summary)

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title="NFL NGS Regression Dashboard",
)
server = app.server

app.layout = dbc.Container(
    [
        dcc.Store(id="metrics-store", data=_initial_session),
        build_header(),
        dbc.Alert(
            load_error,
            color="warning",
            is_open=bool(load_error),
            dismissable=True,
            className="mb-3",
        )
        if load_error
        else html.Div(),
        html.Div(
            [
                html.Span("Analysis season: ", className="meta-label"),
                html.Strong(str(config.ANALYSIS_SEASON)),
                html.Span(" · Outlook: ", className="meta-label"),
                html.Strong(str(config.OUTLOOK_SEASON)),
                html.Span(f" (rosters {config.ROSTER_SEASON_FOR_OUTLOOK}) · Baseline: ", className="meta-label"),
                html.Strong(f"{config.BASELINE_SEASONS[0]}–{config.BASELINE_SEASONS[-1]}"),
                html.Span(" · Flag threshold |z| ≥ ", className="meta-label"),
                html.Strong(str(config.REGRESSION_Z_THRESHOLD)),
                html.Span(id="metrics-updated-label", className="meta-label text-muted"),
            ],
            className="app-meta-strip",
            id="app-subtitle",
        ),
        build_leaderboard_layout(),
        build_scatter_layout(),
        build_outlook_2026_layout(),
        build_team_view_layout(),
        build_player_detail_panel(),
    ],
    fluid=True,
    className="pb-5 dashboard-container",
)

register_callbacks(app, RAW_DATA)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)
