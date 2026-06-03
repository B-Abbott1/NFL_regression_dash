"""NFL team logo URLs and DataTable helpers."""

from __future__ import annotations

import pandas as pd

# nflverse / ESPN slug mismatches
_TEAM_LOGO_SLUG: dict[str, str] = {
    "LA": "lar",
    "LAR": "lar",
    "JAC": "jax",
    "JAX": "jax",
    "WSH": "wsh",
    "WAS": "wsh",
    "OAK": "lv",
    "LV": "lv",
    "SD": "lac",
    "LAC": "lac",
    "STL": "lar",
}

TEAM_LOGO_COLUMN = {
    "name": "",
    "id": "team_logo",
    "presentation": "markdown",
    "type": "text",
}

TEAM_LOGO_PREV_COLUMN = {
    "name": "",
    "id": "team_logo_prev",
    "presentation": "markdown",
    "type": "text",
}

TEAM_LOGO_SIZE_PX = 24

TEAM_LOGO_CELL_STYLES = [
    {
        "if": {"column_id": col_id},
        "width": "36px",
        "maxWidth": "36px",
        "minWidth": "36px",
        "textAlign": "center",
        "padding": "4px 2px",
    }
    for col_id in ("team_logo", "team_logo_prev")
]


def normalize_team_abbr(team: str | None) -> str:
    if team is None or (isinstance(team, float) and pd.isna(team)):
        return ""
    return str(team).strip().upper()


def team_logo_url(team: str | None) -> str:
    abbr = normalize_team_abbr(team)
    if not abbr:
        return ""
    slug = _TEAM_LOGO_SLUG.get(abbr, abbr.lower())
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{slug}.png"


def team_logo_markdown(team: str | None) -> str:
    abbr = normalize_team_abbr(team)
    if not abbr:
        return ""
    url = team_logo_url(abbr)
    size = TEAM_LOGO_SIZE_PX
    return (
        f'<img src="{url}" alt="{abbr}" width="{size}" height="{size}" '
        f'style="width:{size}px;height:{size}px;max-width:{size}px;'
        f'max-height:{size}px;object-fit:contain;display:block;margin:0 auto;" />'
    )


def add_team_logo_columns(
    df: pd.DataFrame,
    team_col: str = "team",
    prev_team_col: str | None = None,
) -> pd.DataFrame:
    """Add markdown logo columns for current (and optional prior) team."""
    if df.empty:
        return df
    out = df.copy()
    if team_col in out.columns:
        out["team_logo"] = out[team_col].apply(team_logo_markdown)
    if prev_team_col and prev_team_col in out.columns:
        out["team_logo_prev"] = out[prev_team_col].apply(team_logo_markdown)
    return out


def table_records_with_logos(
    df: pd.DataFrame,
    display_cols: list[str],
    team_col: str = "team",
    prev_team_col: str | None = None,
) -> list[dict]:
    """Build DataTable row dicts with logo columns included."""
    if df.empty:
        return []
    enriched = add_team_logo_columns(df, team_col=team_col, prev_team_col=prev_team_col)
    logo_cols: list[str] = []
    if "team_logo" in enriched.columns:
        logo_cols.append("team_logo")
    if prev_team_col and "team_logo_prev" in enriched.columns:
        logo_cols.insert(0, "team_logo_prev")
    export = list(dict.fromkeys(logo_cols + display_cols))
    export = [c for c in export if c in enriched.columns]
    return enriched[export].to_dict("records")
