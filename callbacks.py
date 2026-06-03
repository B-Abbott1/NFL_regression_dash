"""Dash callbacks for the regression dashboard."""

from __future__ import annotations

import logging

import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.express as px
from dash import Input, Output, State, callback, html, no_update, ctx

import config
from components.charts import apply_chart_theme, apply_scatter_layout, build_weekly_volume_chart
from components.player_detail import (
    build_player_detail_header,
    build_player_metric_z_panel,
    build_player_scores_panel,
    headshot_url_for_player,
)
from components.team_logos import table_records_with_logos
from metrics.calculator import (
    apply_leaderboard_metric_view,
    build_player_insight,
    enrich_leaderboard_for_display,
    get_player_weekly_volume_series,
)
from metrics.comps import find_similar_seasons
from metrics.session import (
    format_updated_label,
    recompute_session,
    refresh_flags_session,
    reload_scoring_modules,
    session_metrics,
)
from metrics.calculator import build_outlook_2026_df, build_team_summary_df

logger = logging.getLogger(__name__)

_PLAYER_DETAIL_TABLES = (
    "leaderboard-table",
    "outlook-2026-table",
)


def _table_columns(df: pd.DataFrame, base: list[str]) -> list[str]:
    """Merge base display columns with any volume stats present in the frame."""
    extra = [c for c in config.VOLUME_STAT_FIELDS if c in df.columns]
    return [c for c in base + extra if c in df.columns]


def _volume_stats_panel(row: pd.Series) -> html.Div:
    """Season counting-stat block for player detail."""
    position = row.get("position", "")
    fields = config.VOLUME_FIELDS_BY_POSITION.get(position, [])
    items = []
    for col, label in fields:
        val = row.get(col)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        if isinstance(val, float) and col not in ("passing_yards", "receiving_yards", "rushing_yards"):
            text = f"{val:.0f}"
        elif isinstance(val, float):
            text = f"{val:.0f}"
        else:
            text = str(val)
        items.append(
            dbc.ListGroupItem(
                [html.Strong(label), html.Span(f"  {text}", className="metric-secondary")]
            )
        )
    if not items:
        return html.P("No volume stats available.", className="text-muted small")
    return html.Div(dbc.ListGroup(items, flush=True))


def _prepare_leaderboard_df(df_metrics: pd.DataFrame) -> pd.DataFrame:
    if df_metrics is None or df_metrics.empty or "player_id" not in df_metrics.columns:
        return pd.DataFrame()

    df = df_metrics.copy()
    if "flag" in df.columns:
        df["flag"] = df["flag"].apply(config.normalize_player_flag)
        df["flag_label"] = df["flag"].map(config.FLAG_LABELS).fillna(config.FLAG_LABELS["neutral"])
    else:
        df["flag_label"] = config.FLAG_LABELS["neutral"]
    if "composite_z_adjusted" in df.columns:
        return df.sort_values("composite_z_adjusted", ascending=False)
    if "composite_z" in df.columns:
        return df.sort_values("composite_z", ascending=False)
    return df


def _resolve_player_row(table_row: pd.Series, df_metrics: pd.DataFrame) -> pd.Series:
    """Merge leaderboard table row with full metrics (table omits most metric columns)."""
    if df_metrics is None or df_metrics.empty:
        return table_row

    if table_row.get("player_id"):
        match = df_metrics[df_metrics["player_id"] == table_row["player_id"]]
        if not match.empty:
            return match.iloc[0]

    name = table_row.get("player_name")
    team = table_row.get("team")
    if name:
        match = df_metrics[df_metrics["player_name"] == name]
        if team and "team" in match.columns:
            match = match[match["team"] == team]
        if not match.empty:
            return match.iloc[0]

    return table_row


def _build_player_detail_content(
    row: pd.Series,
    metrics_df: pd.DataFrame,
    raw: dict,
) -> tuple:
    """Header, insight, chart, volume, comps, v12 scores, metric z panels."""
    bio_df = enrich_leaderboard_for_display(
        pd.DataFrame([row]),
        raw.get("rosters") if raw else None,
        config.ANALYSIS_SEASON,
    )
    if not bio_df.empty:
        row = bio_df.iloc[0]

    headshot = headshot_url_for_player(
        str(row.get("player_id", "")),
        raw.get("players") if raw else None,
    )
    header = build_player_detail_header(row, headshot_url=headshot)
    insight = build_player_insight(row)

    position = str(row.get("position", ""))
    weeks, series = get_player_weekly_volume_series(
        raw,
        str(row.get("player_id", "")),
        position,
    )
    trend = build_weekly_volume_chart(weeks, series, position)
    volume_panel = _volume_stats_panel(row)

    comps = find_similar_seasons(metrics_df, row.get("player_id", ""))
    if comps.empty:
        comps_view = html.P("No comparable seasons yet.", className="text-muted small")
    else:
        comps_view = dbc.Table.from_dataframe(
            comps, striped=True, bordered=True, hover=True, size="sm", dark=True
        )

    return (
        header,
        insight,
        trend,
        volume_panel,
        comps_view,
        build_player_scores_panel(row),
        build_player_metric_z_panel(row),
    )


def _filter_leaderboard(
    df: pd.DataFrame,
    position: str | None,
    flags: list[str] | None,
    teams: list[str] | None,
    min_volume: int,
) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    if position:
        out = out[out["position"] == position]
    if flags:
        out = out[out["flag"].isin(flags)]
    if teams and "team" in out.columns:
        out = out[out["team"].isin(teams)]
    if min_volume and min_volume > 0:
        volume = out.apply(
            lambda r: max(
                r.get("dropbacks") or 0,
                r.get("targets") or 0,
                r.get("carries") or 0,
            ),
            axis=1,
        )
        out = out[volume >= min_volume]
    return out


_NAV_SECTIONS = {
    "nav-leaderboard": "leaderboard-section",
    "nav-scatter": "scatter-section",
    "nav-outlook-2026": "outlook-2026-section",
    "nav-team": "team-view-section",
}
_NAV_IDS = list(_NAV_SECTIONS.keys())
_SECTION_IDS = list(_NAV_SECTIONS.values())


def register_callbacks(app, raw_data: dict) -> None:
    """Register all Dash callbacks."""

    @callback(
        Output("metrics-store", "data"),
        Output("refresh-metrics-btn", "children"),
        Output("refresh-flags-btn", "children"),
        Input("refresh-metrics-btn", "n_clicks"),
        Input("refresh-flags-btn", "n_clicks"),
        State("metrics-store", "data"),
        prevent_initial_call=True,
        running=[
            (Output("refresh-metrics-btn", "disabled"), True, False),
            (Output("refresh-flags-btn", "disabled"), True, False),
        ],
    )
    def refresh_metrics_or_flags(_metrics_clicks, _flags_clicks, current_session):
        triggered = ctx.triggered_id
        try:
            if triggered == "refresh-flags-btn":
                session = refresh_flags_session(current_session, raw_data)
                logger.info("Flags refreshed (tag high z=%s)", session.get("tag_axis_high_z"))
                return session, no_update, "Refresh flags"

            if not raw_data:
                return no_update, "Refresh metrics", no_update
            session = recompute_session(raw_data)
            logger.info("Metrics refreshed (%s players)", session.get("metrics_rows", 0))
            return session, "Refresh metrics", no_update
        except Exception:
            logger.exception("Refresh failed (%s)", triggered)
            if triggered == "refresh-flags-btn":
                return no_update, no_update, "Refresh failed"
            return no_update, "Refresh failed", no_update

    @callback(
        Output("metrics-updated-label", "children"),
        Input("metrics-store", "data"),
    )
    def update_metrics_timestamp(session):
        return format_updated_label(session)

    @callback(
        [Output(section_id, "style") for section_id in _SECTION_IDS]
        + [Output(nav_id, "active") for nav_id in _NAV_IDS],
        [Input(nav_id, "n_clicks") for nav_id in _NAV_IDS],
        prevent_initial_call=False,
    )
    def toggle_views(*_clicks):
        try:
            triggered = ctx.triggered_id or "nav-leaderboard"
            if triggered not in _NAV_SECTIONS:
                triggered = "nav-leaderboard"
            active_section = _NAV_SECTIONS[triggered]
            styles = [
                {"display": "block"} if sec == active_section else {"display": "none"}
                for sec in _SECTION_IDS
            ]
            actives = [nav == triggered for nav in _NAV_IDS]
            return styles + actives
        except Exception:
            logger.exception("View toggle failed")
            styles = [{"display": "block"}] + [{"display": "none"}] * (len(_SECTION_IDS) - 1)
            actives = [True] + [False] * (len(_NAV_IDS) - 1)
            return styles + actives

    @callback(
        Output("outlook-2026-table", "data"),
        Output("outlook-2026-status", "children"),
        Output("outlook-2026-status", "is_open"),
        Input("metrics-store", "data"),
        Input("nav-outlook-2026", "n_clicks"),
    )
    def update_outlook_2026_table(session, *_):
        try:
            metrics = session_metrics(session)
            rosters = raw_data.get("rosters", pd.DataFrame()) if raw_data else pd.DataFrame()
            df_outlook_2026 = (
                build_outlook_2026_df(metrics, rosters) if not metrics.empty else pd.DataFrame()
            )
            if df_outlook_2026.empty:
                return (
                    [],
                    f"No {config.OUTLOOK_SEASON} regression candidates "
                    f"(no {config.ANALYSIS_SEASON} players with outlook flags).",
                    True,
                )
            display_cols = _table_columns(
                df_outlook_2026,
                [
                    "player_name",
                    "position",
                    "projected_team",
                    "outlook_type",
                    "composite_z",
                    "primary_metric_name",
                    "primary_value",
                    "primary_expected",
                    "flag",
                    "flag_label",
                ],
            )
            return (
                table_records_with_logos(
                    df_outlook_2026,
                    display_cols,
                    team_col="projected_team",
                ),
                "",
                False,
            )
        except Exception:
            logger.exception("2026 outlook table failed")
            return [], "Unable to load 2026 outlook.", True

    @callback(
        Output("team-regression-chart", "figure"),
        Input("metrics-store", "data"),
        Input("nav-team", "n_clicks"),
    )
    def update_team_chart(session, *_):
        try:
            metrics = session_metrics(session)
            df_team_summary = build_team_summary_df(metrics) if not metrics.empty else pd.DataFrame()
            if df_team_summary.empty:
                fig = px.bar(template="plotly_dark", title="No team data available")
                return apply_chart_theme(fig, height=520)

            df = df_team_summary.copy()
            df["color"] = np.where(df["net_regression_score"] >= 0, "positive", "negative")
            fig = px.bar(
                df,
                x="team",
                y="net_regression_score",
                color="color",
                color_discrete_map={
                    "positive": config.FLAG_COLORS["regress_negative"],
                    "negative": config.FLAG_COLORS["positive_outlook"],
                },
                hover_data={"player_count": True, "net_regression_score": ":.2f"},
                template="plotly_dark",
            )
            apply_chart_theme(
                fig,
                height=520,
                title="Net Team Regression Score (sum of player composite z)",
            )
            fig.update_layout(showlegend=False, xaxis_title="Team", yaxis_title="Net composite z")
            fig.update_xaxes(tickangle=-45)
            return fig
        except Exception:
            logger.exception("Team chart failed")
            fig = px.bar(template="plotly_dark", title="Team chart unavailable")
            fig.update_layout(height=520)
            return fig

    @callback(
        Output("team-filter", "options"),
        Input("position-filter", "value"),
        Input("metrics-store", "data"),
    )
    def populate_team_filter(position, session):
        try:
            position = config.normalize_position_filter(position)
            df = _prepare_leaderboard_df(session_metrics(session))
            if df.empty or "team" not in df.columns:
                return []
            df = df[df["position"] == position]
            teams = sorted(df["team"].dropna().unique())
            return [{"label": t, "value": t} for t in teams]
        except Exception:
            logger.exception("Failed to populate team filter")
            return []

    @callback(
        Output("leaderboard-table", "columns"),
        Output("leaderboard-table", "data"),
        Output("leaderboard-status", "children"),
        Output("leaderboard-status", "is_open"),
        Input("position-filter", "value"),
        Input("metric-view-filter", "value"),
        Input("flag-filter", "value"),
        Input("team-filter", "value"),
        Input("volume-slider", "value"),
        Input("metrics-store", "data"),
    )
    def update_leaderboard(position, metric_view, flags, teams, min_volume, session):
        try:
            position = config.normalize_position_filter(position)
            columns = config.leaderboard_columns_for_position(position, metric_view)
            col_ids = [c["id"] for c in columns]

            df = session_metrics(session)
            if df.empty:
                return (
                    columns,
                    [],
                    "No metrics loaded. First run downloads data to /data (may take several minutes).",
                    True,
                )
            filtered = _filter_leaderboard(df, position, None, teams, min_volume or 0)
            if flags:
                filtered = filtered[filtered["flag"].apply(config.normalize_player_flag).isin(flags)]
            filtered = apply_leaderboard_metric_view(filtered, metric_view)
            filtered = enrich_leaderboard_for_display(
                filtered,
                raw_data.get("rosters") if raw_data else None,
                config.ANALYSIS_SEASON,
            )
            export_cols = list(
                dict.fromkeys(
                    ["team_logo"]
                    + col_ids
                    + [
                        c
                        for c in config.LEADERBOARD_ROW_HIDDEN_FIELDS
                        if c in filtered.columns
                    ]
                )
            )
            records = (
                table_records_with_logos(filtered, export_cols, team_col="team")
                if export_cols
                else []
            )
            return columns, records, "", False
        except Exception:
            logger.exception("Leaderboard update failed")
            return (
                config.leaderboard_columns_for_position(
                    config.LEADERBOARD_DEFAULT_POSITION,
                    config.METRIC_VIEW_COMPOSITE,
                ),
                [],
                "Unable to load leaderboard data.",
                True,
            )

    @callback(
        Output("player-detail-panel", "is_open"),
        Output("player-detail-header", "children"),
        Output("player-insight-text", "children"),
        Output("player-trend-chart", "figure"),
        Output("player-volume-panel", "children"),
        Output("player-comps-table", "children"),
        Output("player-scores-panel", "children"),
        Output("player-metrics-panel", "children"),
        [Input(f"{table_id}", "active_cell") for table_id in _PLAYER_DETAIL_TABLES],
        [State(f"{table_id}", "data") for table_id in _PLAYER_DETAIL_TABLES],
        State("metrics-store", "data"),
        prevent_initial_call=True,
    )
    def open_player_detail(*args):
        try:
            session = args[-1]
            table_args = args[:-1]
            df_metrics = session_metrics(session)
            triggered = ctx.triggered_id
            if triggered not in _PLAYER_DETAIL_TABLES:
                return (no_update,) * 8

            n_tables = len(_PLAYER_DETAIL_TABLES)
            active_cells = table_args[:n_tables]
            table_datas = table_args[n_tables:]
            table_index = _PLAYER_DETAIL_TABLES.index(triggered)
            active_cell = active_cells[table_index]
            table_data = table_datas[table_index]

            if not active_cell or active_cell.get("column_id") != "player_name":
                return (no_update,) * 8
            if not table_data:
                return (False,) + (no_update,) * 7

            row_idx = active_cell.get("row")
            if row_idx is None or row_idx < 0 or row_idx >= len(table_data):
                return (no_update,) * 8

            table_row = pd.Series(table_data[row_idx])
            row = _resolve_player_row(table_row, df_metrics)
            if table_row.get("focus_metric"):
                row = row.copy()
                row["focus_metric"] = table_row.get("focus_metric")

            content = _build_player_detail_content(row, df_metrics, raw_data)
            return (True, *content)
        except Exception:
            logger.exception("Player detail failed")
            return (
                True,
                html.P("Error loading player detail."),
                "",
                build_weekly_volume_chart([], {}, "QB"),
                html.P("Volume stats unavailable."),
                html.P("Comps unavailable."),
                html.P("Scores unavailable."),
                html.P("Metrics unavailable."),
            )

    @callback(
        Output("scatter-x-metric", "options"),
        Output("scatter-x-metric", "value"),
        Output("scatter-y-metric", "options"),
        Output("scatter-y-metric", "value"),
        Input("scatter-position", "value"),
    )
    def update_scatter_metric_options(position):
        try:
            defs = config.METRIC_DEFINITIONS.get(position or "QB", {})
            options = [{"label": m["name"], "value": mid} for mid, m in defs.items()]
            if not options:
                return [], None, [], None
            return options, options[0]["value"], options, options[min(1, len(options) - 1)]["value"]
        except Exception:
            logger.exception("Scatter metric options failed")
            return [], None, [], None

    @callback(
        Output("scatter-plot", "figure"),
        Input("scatter-position", "value"),
        Input("scatter-x-metric", "value"),
        Input("scatter-y-metric", "value"),
        Input("metrics-store", "data"),
    )
    def update_scatter_plot(position, x_metric, y_metric, session):
        try:
            df = _prepare_leaderboard_df(session_metrics(session))
            if df.empty or not x_metric or not y_metric:
                fig = px.scatter(template="plotly_dark")
                return apply_scatter_layout(fig, "X", "Y", height=560)

            subset = df[df["position"] == position].copy()
            x_col = f"{x_metric}_value" if f"{x_metric}_value" in subset.columns else "composite_z"
            y_col = f"{y_metric}_value" if f"{y_metric}_value" in subset.columns else "composite_z"
            defs = config.METRIC_DEFINITIONS.get(position, {})
            x_title = defs.get(x_metric, {}).get("name", x_metric)
            y_title = defs.get(y_metric, {}).get("name", y_metric)

            fig = px.scatter(
                subset,
                x=x_col,
                y=y_col,
                color="flag",
                color_discrete_map=config.FLAG_COLORS,
                hover_name="player_name",
                hover_data={"team": True, "composite_z": ":.2f"},
                template="plotly_dark",
            )
            apply_scatter_layout(fig, x_title, y_title, height=560)
            for trace in fig.data:
                trace.name = config.FLAG_LEGEND_LABELS.get(trace.name, trace.name)
            return fig
        except Exception:
            logger.exception("Scatter plot failed")
            fig = px.scatter(template="plotly_dark")
            return apply_scatter_layout(fig, "X", "Y", height=560)
