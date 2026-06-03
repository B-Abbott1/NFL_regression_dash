"""Player detail drill-down panel."""

from __future__ import annotations

import numpy as np
import pandas as pd
import dash_bootstrap_components as dbc
from dash import dcc, html

import config
from components.charts import build_weekly_volume_chart
from metrics.calculator import z_to_percentile


def headshot_url_for_player(
    player_id: str | None,
    df_players: pd.DataFrame | None,
) -> str | None:
    """Look up nflverse headshot URL by gsis player id."""
    if not player_id or df_players is None or df_players.empty:
        return None

    players = df_players.copy()
    id_col = "gsis_id" if "gsis_id" in players.columns else None
    url_col = "headshot" if "headshot" in players.columns else "headshot_url"
    if not id_col or url_col not in players.columns:
        return None

    match = players.loc[players[id_col] == player_id, url_col]
    if match.empty:
        return None
    url = match.iloc[0]
    if url is None or (isinstance(url, float) and pd.isna(url)) or not str(url).strip():
        return None
    return str(url).strip()


def build_player_detail_header(
    row: pd.Series,
    *,
    headshot_url: str | None = None,
) -> html.Div:
    """Header block with name/meta left and headshot top-right."""
    flag_key = row.get("flag", "neutral")
    flag_text = config.FLAG_LABELS.get(flag_key, config.FLAG_LABELS["neutral"])
    flag_color = config.FLAG_COLORS.get(flag_key, config.FLAG_COLORS["neutral"])
    name = row.get("player_name", "Unknown")

    main = html.Div(
        [
            html.H4(name, className="player-detail-name mb-1"),
            html.P(
                f"{row.get('position', '')} · {row.get('team', '')} · "
                f"{config.ANALYSIS_SEASON} season totals",
                className="player-detail-meta mb-2",
            ),
            html.Span(flag_text, className="flag-badge", style={"color": flag_color}),
        ],
        className="player-detail-header-main",
    )

    children: list = [main]
    if headshot_url:
        children.append(
            html.Img(
                src=headshot_url,
                alt=f"{name} headshot",
                className="player-detail-headshot",
            )
        )

    return html.Div(children, className="player-detail-header")


def _z_list_item(label: str, z: float | None) -> dbc.ListGroupItem | None:
    if z is None or (isinstance(z, float) and pd.isna(z)):
        return None
    zf = float(z)
    return dbc.ListGroupItem(
        [
            html.Strong(label),
            html.Span(
                f"  {zf:+.2f}  ({z_to_percentile(zf):.0f}th pct)",
                className="metric-secondary",
            ),
        ]
    )


def build_player_scores_panel(row: pd.Series) -> html.Div:
    """v12 axis z-scores (role / efficiency / production)."""
    items = [
        _z_list_item("Role Z", row.get("role_z")),
        _z_list_item("Production Z", row.get("production_z")),
    ]
    eff_adj = row.get("efficiency_age_z_adjustment", np.nan)
    eff_raw = row.get("efficiency_z_raw", row.get("efficiency_z"))
    eff_item = _z_list_item("Efficiency Z (age-adjusted)", row.get("efficiency_z"))
    if eff_item is not None:
        items.append(eff_item)
    if pd.notna(eff_adj) and float(eff_adj) != 0.0:
        raw_s = f"{float(eff_raw):+.2f}" if pd.notna(eff_raw) else "—"
        items.append(
            dbc.ListGroupItem(
                [
                    html.Strong("Efficiency (raw z)"),
                    html.Span(f"  {raw_s}", className="metric-secondary"),
                    html.Br(),
                    html.Span(
                        f"Age adjustment: {float(eff_adj):+.2f} z",
                        className="metric-secondary",
                    ),
                ]
            )
        )
    items = [item for item in items if item is not None]
    if not items:
        return html.P("Score z-values unavailable.", className="text-muted small")
    return html.Div(dbc.ListGroup(items, flush=True))


def _metric_z_items(row: pd.Series, metric_ids: list[str], position: str) -> list:
    items = []
    defs = config.METRIC_DEFINITIONS.get(position, {})
    for mid in metric_ids:
        meta = defs.get(mid)
        if not meta:
            continue
        z = row.get(f"{mid}_z", np.nan)
        val = row.get(f"{mid}_value", np.nan)
        if pd.isna(z) and pd.isna(val):
            continue
        val_s = f"{val:.3f}" if pd.notna(val) else "—"
        z_s = f"{float(z):+.2f}" if pd.notna(z) else "—"
        pct_s = f"{z_to_percentile(float(z)):.0f}th" if pd.notna(z) else "—"
        items.append(
            dbc.ListGroupItem(
                [
                    html.Strong(meta["name"]),
                    html.Span(
                        f"  {val_s}  ·  z {z_s}  ({pct_s} pct)",
                        className="metric-secondary",
                    ),
                ]
            )
        )
    return items


def build_player_metric_z_panel(row: pd.Series) -> html.Div:
    """Per-metric z-scores grouped by v12 score axis."""
    position = str(row.get("position", ""))
    if not position:
        return html.P("No metrics available.", className="text-muted small")

    blocks: list = []
    for group_key, title in (
        ("role", "Role metrics"),
        ("efficiency", "Efficiency metrics"),
        ("production", "Production metrics"),
    ):
        mids = config.score_metric_ids(position, group_key)
        items = _metric_z_items(row, mids, position)
        if items:
            blocks.append(html.H6(title, className="detail-subsection-title mb-2 mt-3"))
            blocks.append(dbc.ListGroup(items, flush=True))

    td_mids = config.td_luck_metric_ids(position)
    td_items = _metric_z_items(row, td_mids, position)
    if td_items:
        blocks.append(html.H6("TD rate (tag modifier)", className="detail-subsection-title mb-2 mt-3"))
        blocks.append(dbc.ListGroup(td_items, flush=True))

    age_val = row.get("age_curve_value", np.nan)
    age_adj = row.get("efficiency_age_z_adjustment", np.nan)
    if pd.notna(age_val) or (pd.notna(age_adj) and float(age_adj) != 0.0):
        age_lines = []
        if pd.notna(age_val):
            age_lines.append(
                dbc.ListGroupItem(
                    [
                        html.Strong("Years outside productive window"),
                        html.Span(f"  {float(age_val):+.1f}", className="metric-secondary"),
                    ]
                )
            )
        if pd.notna(age_adj) and float(age_adj) != 0.0:
            age_lines.append(
                dbc.ListGroupItem(
                    [
                        html.Strong("Efficiency z age adjustment"),
                        html.Span(f"  {float(age_adj):+.2f}", className="metric-secondary"),
                    ]
                )
            )
        blocks.append(html.H6("Age & efficiency", className="detail-subsection-title mb-2 mt-3"))
        blocks.append(dbc.ListGroup(age_lines, flush=True))

    if not blocks:
        return html.P("No metric z-scores available.", className="text-muted small")
    return html.Div(blocks)


def build_player_detail_panel() -> dbc.Offcanvas:
    return dbc.Offcanvas(
        [
            html.Div(id="player-detail-header", className="mb-3"),
            html.Div(id="player-insight-text", className="player-insight mb-4"),
            html.H6("Weekly production", className="detail-section-title mt-2 mb-2"),
            dcc.Graph(id="player-trend-chart", figure=build_weekly_volume_chart([], {}, "QB")),
            html.H6("Season totals", className="detail-section-title mt-4 mb-2"),
            html.Div(id="player-volume-panel", className="mb-3"),
            html.H6("Similar seasons", className="detail-section-title mt-4 mb-2"),
            html.Div(id="player-comps-table", className="mb-3"),
            html.H6("v12 scores", className="detail-section-title mt-4 mb-2"),
            html.Div(id="player-scores-panel", className="mb-3"),
            html.H6("Metric z-scores", className="detail-section-title mt-4 mb-2"),
            html.Div(id="player-metrics-panel"),
        ],
        id="player-detail-panel",
        title="Player Detail",
        is_open=False,
        placement="end",
        scrollable=True,
        backdrop=True,
        style={"width": "540px"},
    )
