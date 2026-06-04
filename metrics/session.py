"""Serialize dashboard metrics for dcc.Store and recompute from raw data."""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone

import pandas as pd

import config
from metrics.calculator import (
    build_df_metrics,
    build_outlook_2026_df,
    build_team_summary_df,
    reapply_player_tags,
)
from metrics.loader import refresh_metrics_cache


def reload_scoring_modules() -> None:
    """Pick up edits to config.py and calculator logic without restarting the app."""
    importlib.reload(config)
    import metrics.calculator as calculator

    importlib.reload(calculator)


def reload_scoring_config() -> None:
    """Backward-compatible alias."""
    reload_scoring_modules()


def pack_dataframe(df: pd.DataFrame | None) -> list[dict]:
    """JSON-safe records for dcc.Store."""
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso"))


def unpack_dataframe(records: list | dict | None) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def pack_session(
    metrics: pd.DataFrame,
    outlook: pd.DataFrame,
    team: pd.DataFrame,
) -> dict:
    """Bundle derived tables for the client-side metrics store."""
    return {
        "metrics": pack_dataframe(metrics),
        "outlook": pack_dataframe(outlook),
        "team": pack_dataframe(team),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "scoring_version": config.METRICS_SCORING_VERSION,
        "tag_scoring": "percentile_v14",
        "metrics_rows": len(metrics) if metrics is not None and not metrics.empty else 0,
        "outlook_rows": len(outlook) if outlook is not None and not outlook.empty else 0,
    }


def session_metrics(session: dict | None, *, reapply_tags: bool = True) -> pd.DataFrame:
    if not session:
        return pd.DataFrame()
    df = unpack_dataframe(session.get("metrics"))
    if reapply_tags and not df.empty and "role_z" in df.columns:
        reload_scoring_modules()
        df = reapply_player_tags(df)
    return df


def refresh_flags_session(session: dict | None, raw: dict) -> dict:
    """Re-tag players from stored z-scores using current config (fast; no metric recompute)."""
    reload_scoring_modules()
    metrics = unpack_dataframe(session.get("metrics") if session else None)
    if metrics.empty:
        return session or {}
    metrics = reapply_player_tags(metrics)
    rosters = raw.get("rosters", pd.DataFrame()) if raw else pd.DataFrame()
    outlook = build_outlook_2026_df(metrics, rosters)
    team = build_team_summary_df(metrics)
    return pack_session(metrics, outlook, team)


def session_outlook(session: dict | None) -> pd.DataFrame:
    if not session:
        return pd.DataFrame()
    return unpack_dataframe(session.get("outlook"))


def session_team(session: dict | None) -> pd.DataFrame:
    if not session:
        return pd.DataFrame()
    return unpack_dataframe(session.get("team"))


def recompute_session(raw: dict) -> dict:
    """Rebuild metrics from raw Parquet sources and refresh the on-disk cache."""
    reload_scoring_modules()
    metrics = build_df_metrics(raw, config.ANALYSIS_SEASON)
    if not metrics.empty:
        refresh_metrics_cache(metrics)
    rosters = raw.get("rosters", pd.DataFrame()) if raw else pd.DataFrame()
    outlook = build_outlook_2026_df(metrics, rosters) if not metrics.empty else pd.DataFrame()
    team = build_team_summary_df(metrics)
    return pack_session(metrics, outlook, team)


def format_updated_label(session: dict | None) -> str:
    if not session or not session.get("updated_at"):
        return ""
    try:
        ts = datetime.fromisoformat(session["updated_at"].replace("Z", "+00:00"))
        local = ts.astimezone()
        stamp = local.strftime("%H:%M:%S")
    except (TypeError, ValueError):
        stamp = str(session.get("updated_at", ""))[:19]
    rows = session.get("metrics_rows", 0)
    ver = session.get("scoring_version", "?")
    return f" · Updated {stamp} ({rows} players, scoring v{ver})"
