"""Trend line chart (actual vs. expected)."""

import plotly.graph_objects as go

CHART_COLORS = {
    "actual": "#58a6ff",
    "expected": "#8b949e",
    "grid": "#30363d",
    "text": "#e6edf3",
    "muted": "#9da7b3",
}

WEEKLY_SERIES_COLORS = ["#58a6ff", "#3fb950", "#f0883e", "#a371f7", "#f85149"]


def _base_layout(**overrides) -> dict:
    layout = {
        "template": "plotly_dark",
        "margin": {"l": 48, "r": 24, "t": 36, "b": 44},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "#161b22",
        "font": {"color": CHART_COLORS["text"], "size": 13},
        "legend": {"orientation": "h", "y": 1.12, "font": {"color": CHART_COLORS["muted"]}},
        "xaxis": {
            "gridcolor": CHART_COLORS["grid"],
            "linecolor": CHART_COLORS["grid"],
            "tickfont": {"color": CHART_COLORS["muted"]},
            "title": {"font": {"color": CHART_COLORS["text"]}},
        },
        "yaxis": {
            "gridcolor": CHART_COLORS["grid"],
            "linecolor": CHART_COLORS["grid"],
            "tickfont": {"color": CHART_COLORS["muted"]},
            "title": {"font": {"color": CHART_COLORS["text"]}},
        },
    }
    layout.update(overrides)
    return layout


def build_trend_chart(weeks: list, actual: list, expected: list | None = None) -> go.Figure:
    """Build a week-by-week actual vs. expected trend chart."""
    fig = go.Figure()
    if weeks and actual:
        fig.add_trace(
            go.Scatter(
                x=weeks,
                y=actual,
                mode="lines+markers",
                name="Actual",
                line={"color": CHART_COLORS["actual"], "width": 2},
                marker={"size": 6},
            )
        )
    if weeks and expected:
        fig.add_trace(
            go.Scatter(
                x=weeks,
                y=expected,
                mode="lines",
                name="Expected",
                line={"color": CHART_COLORS["expected"], "dash": "dash", "width": 2},
            )
        )

    fig.update_layout(**_base_layout(height=300, xaxis_title="Week", yaxis_title="Value"))
    if not weeks:
        fig.add_annotation(
            text="Select a player to view trends",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"color": CHART_COLORS["muted"], "size": 14},
        )
    return fig


def build_weekly_volume_chart(
    weeks: list,
    series: dict[str, list[float]],
    position: str,
) -> go.Figure:
    """Multi-series per-week production chart; counts use right axis when mixed with yards."""
    import config

    fig = go.Figure()
    if not weeks or not series:
        fig.update_layout(**_base_layout(height=300, xaxis_title="Week", yaxis_title=""))
        fig.add_annotation(
            text="No weekly stats for this player",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"color": CHART_COLORS["muted"], "size": 14},
        )
        return fig

    col_by_label = {
        label: col
        for col, label in config.PLAYER_WEEKLY_CHART_SERIES.get(position, [])
    }
    yard_cols = config.PLAYER_WEEKLY_YARD_STATS

    has_yards = any(col_by_label.get(label) in yard_cols for label in series)
    has_counts = any(
        col_by_label.get(label) not in yard_cols for label in series if col_by_label.get(label)
    )
    dual_axis = has_yards and has_counts

    for idx, (label, values) in enumerate(series.items()):
        col = col_by_label.get(label, "")
        use_primary = col in yard_cols or not dual_axis
        fig.add_trace(
            go.Scatter(
                x=weeks,
                y=values,
                mode="lines+markers",
                name=label,
                yaxis="y" if use_primary else "y2",
                line={"color": WEEKLY_SERIES_COLORS[idx % len(WEEKLY_SERIES_COLORS)], "width": 2},
                marker={"size": 5},
            )
        )

    layout = _base_layout(
        height=320,
        xaxis_title="Week",
        yaxis_title="Yards" if dual_axis else ("Yards" if has_yards else "Count"),
    )
    if dual_axis:
        layout["yaxis2"] = {
            "title": {"text": "Count", "font": {"color": CHART_COLORS["text"]}},
            "overlaying": "y",
            "side": "right",
            "gridcolor": CHART_COLORS["grid"],
            "linecolor": CHART_COLORS["grid"],
            "tickfont": {"color": CHART_COLORS["muted"]},
            "showgrid": False,
        }
        layout["margin"] = {"l": 48, "r": 56, "t": 36, "b": 44}
    fig.update_layout(**layout)
    return fig


def apply_chart_theme(fig, height: int = 480, title: str | None = None) -> go.Figure:
    """Apply consistent dashboard styling to a Plotly figure."""
    fig.update_layout(**_base_layout(height=height, title=title))
    return fig


def apply_scatter_layout(
    fig,
    x_title: str,
    y_title: str,
    *,
    height: int = 560,
) -> go.Figure:
    """Scatter-specific layout: axis titles only, legend on the right, no title clash."""
    axis_style = {
        "gridcolor": CHART_COLORS["grid"],
        "linecolor": CHART_COLORS["grid"],
        "tickfont": {"color": CHART_COLORS["muted"], "size": 11},
        "title": {"font": {"color": CHART_COLORS["text"], "size": 13}, "standoff": 12},
        "automargin": True,
        "zerolinecolor": CHART_COLORS["grid"],
    }
    fig.update_layout(
        template="plotly_dark",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#161b22",
        font={"color": CHART_COLORS["text"], "size": 13},
        title=None,
        margin={"l": 72, "r": 200, "t": 24, "b": 72},
        xaxis={**axis_style, "title": {"text": x_title, "font": {"color": CHART_COLORS["text"], "size": 13}, "standoff": 12}},
        yaxis={**axis_style, "title": {"text": y_title, "font": {"color": CHART_COLORS["text"], "size": 13}, "standoff": 12}},
        legend={
            "orientation": "v",
            "yanchor": "top",
            "y": 1,
            "xanchor": "left",
            "x": 1.02,
            "title": {"text": "Flag", "font": {"size": 12, "color": CHART_COLORS["text"]}},
            "font": {"size": 11, "color": CHART_COLORS["muted"]},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
        },
    )
    return fig
