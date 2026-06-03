"""Data fetching and Parquet cache logic."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)

WEEKLY_OFFICIAL_MAX_SEASON = 2024

PBP_REQUIRED_COLS = ("season", "week", "posteam", "pass_attempt")
# Present in config.PBP_COLUMNS; stale caches built without these break QB INT stats.
PBP_CACHE_STAT_COLS = ("interception",)
WEEKLY_REQUIRED_COLS = ("player_id", "season", "week", "position")


def get_cache_path(source: str, year: int) -> Path:
    """Return the Parquet cache path for a data source and season."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return config.DATA_DIR / f"{source}_{year}.parquet"


def get_static_cache_path(source: str) -> Path:
    """Return the Parquet cache path for a non-seasonal data source."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return config.DATA_DIR / f"{source}.parquet"


def is_cache_valid(path: Path) -> bool:
    """Return True if cache file exists and is younger than CACHE_MAX_AGE_DAYS."""
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(tz=timezone.utc) - mtime
    return age < timedelta(days=config.CACHE_MAX_AGE_DAYS)


def _dataframe_usable(
    df: pd.DataFrame,
    required_cols: tuple[str, ...] | None = None,
    min_rows: int = 1,
) -> bool:
    """Return True if DataFrame has rows, columns, and required fields."""
    if df is None or df.empty or len(df.columns) == 0:
        return False
    if len(df) < min_rows:
        return False
    if required_cols:
        return all(col in df.columns for col in required_cols)
    return True


def _read_cache(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _read_cache_if_valid(
    path: Path,
    required_cols: tuple[str, ...] | None = None,
    min_rows: int = 1,
    extra_cols: tuple[str, ...] | None = None,
) -> pd.DataFrame | None:
    """Read cache file or delete and return None if corrupt/empty."""
    if not path.exists() or not is_cache_valid(path):
        return None
    df = _read_cache(path)
    need = tuple(required_cols or ()) + tuple(extra_cols or ())
    if _dataframe_usable(df, need if need else None, min_rows):
        return df
    logger.warning("Removing invalid cache file %s", path.name)
    path.unlink(missing_ok=True)
    return None


def _derived_weekly_missing_interceptions(df: pd.DataFrame) -> bool:
    """True when PBP-derived weekly has pass volume but no recorded interceptions."""
    if df.empty or "interceptions" not in df.columns:
        return True
    qb = df[df.get("position") == "QB"]
    if qb.empty:
        return False
    ints = qb["interceptions"].fillna(0).sum()
    att = qb["attempts"].fillna(0).sum() if "attempts" in qb.columns else 0
    return ints == 0 and att > 0


def pbp_pass_interception_mask(pass_df: pd.DataFrame) -> pd.Series:
    """Boolean series: pass play resulted in an interception."""
    if "interception" in pass_df.columns:
        return pass_df["interception"].fillna(0).astype(bool)
    if "interception_player_id" in pass_df.columns:
        return pass_df["interception_player_id"].notna()
    return pd.Series(False, index=pass_df.index)


def _write_cache(
    df: pd.DataFrame,
    path: Path,
    required_cols: tuple[str, ...] | None = None,
    min_rows: int = 1,
) -> None:
    if not _dataframe_usable(df, required_cols, min_rows):
        raise ValueError(f"Refusing to cache empty or incomplete data at {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _filter_regular_season(df: pd.DataFrame) -> pd.DataFrame:
    """Keep regular-season rows with week >= 1."""
    out = df.copy()
    if "season_type" in out.columns:
        out = out[out["season_type"] == "REG"]
    if "week" in out.columns:
        out = out[out["week"] >= 1]
    return out


def load_pbp_data(years: list[int] | None = None, force_refresh: bool = False) -> pd.DataFrame:
    """Load play-by-play data with Parquet caching."""
    years = years or config.SEASONS
    frames: list[pd.DataFrame] = []

    for year in years:
        path = get_cache_path("pbp", year)
        if not force_refresh:
            cached = _read_cache_if_valid(
                path, PBP_REQUIRED_COLS, extra_cols=PBP_CACHE_STAT_COLS
            )
            if cached is not None:
                logger.info("Loading cached PBP %s", year)
                frames.append(cached)
                continue

        logger.info("Fetching PBP %s from nfl_data_py", year)
        import nfl_data_py as nfl

        available_cols = nfl.see_pbp_cols()
        cols = [c for c in config.PBP_COLUMNS if c in available_cols]
        for required in PBP_REQUIRED_COLS:
            if required in available_cols and required not in cols:
                cols.append(required)
        # nfl_data_py requires game_id in columns list or returns empty data
        if "game_id" in available_cols and "game_id" not in cols:
            cols = ["game_id", *cols]
        if cols:
            df_year = nfl.import_pbp_data(years=[year], columns=cols, downcast=True)
        else:
            logger.warning("No PBP columns matched config; loading full dataset for %s", year)
            df_year = nfl.import_pbp_data(years=[year], downcast=True)
        df_year = _filter_regular_season(df_year)
        _write_cache(df_year, path, PBP_REQUIRED_COLS)
        frames.append(df_year)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _pbp_for_season(df_pbp: pd.DataFrame, year: int) -> pd.DataFrame:
    """Filter PBP to a season, injecting season column when loading a single-year slice."""
    pbp = _filter_regular_season(df_pbp)
    if not _dataframe_usable(pbp, min_rows=1):
        raise ValueError(
            f"PBP for {year} is empty. Delete data/pbp_{year}.parquet and restart the app."
        )
    if "season" not in pbp.columns:
        pbp = pbp.copy()
        pbp["season"] = year
        return pbp
    return pbp[pbp["season"] == year].copy()


def derive_weekly_from_pbp(
    df_pbp: pd.DataFrame,
    year: int,
    df_rosters: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Aggregate weekly player stats from play-by-play for seasons without official weekly files."""
    pbp = _pbp_for_season(df_pbp, year)

    team_pass = (
        pbp.groupby(["season", "week", "posteam"], as_index=False)["pass_attempt"]
        .sum()
        .rename(columns={"posteam": "recent_team", "pass_attempt": "team_pass_attempts"})
    )

    recv = pbp[pbp["receiver_player_id"].notna()].copy()
    recv_stats = (
        recv.groupby(
            ["season", "week", "receiver_player_id", "receiver_player_name", "posteam"],
            as_index=False,
        )
        .agg(
            targets=("pass_attempt", "sum"),
            receptions=("complete_pass", "sum"),
            receiving_yards=("yards_gained", "sum"),
            receiving_tds=("pass_touchdown", "sum"),
        )
        .rename(
            columns={
                "receiver_player_id": "player_id",
                "receiver_player_name": "player_name",
                "posteam": "recent_team",
            }
        )
    )
    rush_col = "rush_attempt" if "rush_attempt" in pbp.columns else "rush"
    rush = pbp[(pbp["rusher_player_id"].notna()) & (pbp[rush_col] == 1)].copy()
    rush_stats = (
        rush.groupby(
            ["season", "week", "rusher_player_id", "rusher_player_name", "posteam"],
            as_index=False,
        )
        .agg(
            carries=(rush_col, "sum"),
            rushing_yards=("yards_gained", "sum"),
            rushing_tds=("rush_touchdown", "sum"),
        )
        .rename(
            columns={
                "rusher_player_id": "player_id",
                "rusher_player_name": "player_name",
                "posteam": "recent_team",
            }
        )
    )
    rush_stats["position"] = "RB"

    pass_df = pbp[pbp["passer_player_id"].notna()].copy()
    pass_agg: dict = {
        "attempts": ("pass_attempt", "sum"),
        "completions": ("complete_pass", "sum"),
        "passing_yards": ("yards_gained", "sum"),
        "passing_tds": ("pass_touchdown", "sum"),
    }
    if (
        "interception" in pass_df.columns
        or "interception_player_id" in pass_df.columns
    ):
        pass_df = pass_df.copy()
        pass_df["_is_int"] = pbp_pass_interception_mask(pass_df).astype(int)
        pass_agg["interceptions"] = ("_is_int", "sum")
    pass_stats = (
        pass_df.groupby(
            ["season", "week", "passer_player_id", "passer_player_name", "posteam"],
            as_index=False,
        )
        .agg(**pass_agg)
        .rename(
            columns={
                "passer_player_id": "player_id",
                "passer_player_name": "player_name",
                "posteam": "recent_team",
            }
        )
    )
    df_weekly = pd.concat([recv_stats, rush_stats, pass_stats], ignore_index=True)

    if df_rosters is not None and not df_rosters.empty:
        roster = df_rosters.copy()
        if "season" in roster.columns:
            roster = roster[roster["season"] == year]
        id_col = "gsis_id" if "gsis_id" in roster.columns else "player_id"
        if id_col in roster.columns and "position" in roster.columns:
            pos_map = roster.drop_duplicates(id_col).set_index(id_col)["position"]
            df_weekly["position"] = df_weekly["player_id"].map(pos_map)
    df_weekly["position"] = df_weekly.get("position", pd.Series(dtype=object))
    df_weekly.loc[df_weekly["position"].isna() & df_weekly["attempts"].notna(), "position"] = "QB"
    df_weekly.loc[df_weekly["position"].isna() & df_weekly["carries"].notna(), "position"] = "RB"
    df_weekly.loc[df_weekly["position"].isna() & df_weekly["targets"].notna(), "position"] = "WR"
    df_weekly = df_weekly[df_weekly["position"].isin(config.POSITIONS)]
    df_weekly = df_weekly.merge(team_pass, on=["season", "week", "recent_team"], how="left")
    df_weekly["team_pass_attempts"] = df_weekly["team_pass_attempts"].replace(0, np.nan)
    df_weekly["target_share"] = np.where(
        df_weekly["position"].isin(["WR", "TE", "RB"]),
        df_weekly["targets"] / df_weekly["team_pass_attempts"],
        np.nan,
    )
    for col in ("completions", "attempts", "passing_yards", "passing_tds", "interceptions",
                "carries", "rushing_yards", "rushing_tds", "receptions", "targets",
                "receiving_yards", "receiving_tds", "air_yards_share", "wopr", "racr"):
        if col not in df_weekly.columns:
            df_weekly[col] = np.nan

    return df_weekly


def load_weekly_data(years: list[int] | None = None, force_refresh: bool = False) -> pd.DataFrame:
    """Load weekly player stats; derive 2025+ from PBP when official files are unavailable."""
    years = years or config.SEASONS
    frames: list[pd.DataFrame] = []

    for year in years:
        path = get_cache_path("weekly", year)
        if not force_refresh:
            cached = _read_cache_if_valid(path, WEEKLY_REQUIRED_COLS)
            if cached is not None and year > WEEKLY_OFFICIAL_MAX_SEASON:
                if _derived_weekly_missing_interceptions(cached):
                    logger.warning(
                        "Removing stale weekly cache (missing INTs) %s", path.name
                    )
                    path.unlink(missing_ok=True)
                    cached = None
            if cached is not None:
                logger.info("Loading cached weekly %s", year)
                frames.append(cached)
                continue

        if year <= WEEKLY_OFFICIAL_MAX_SEASON:
            logger.info("Fetching weekly %s from nfl_data_py", year)
            import nfl_data_py as nfl

            df_year = nfl.import_weekly_data(years=[year], downcast=True)
            if config.WEEKLY_COLUMNS:
                keep = [c for c in config.WEEKLY_COLUMNS if c in df_year.columns]
                df_year = df_year[keep]
            df_year = df_year[df_year["week"] >= 1]
        else:
            logger.info("Deriving weekly %s from PBP", year)
            df_pbp = load_pbp_data(years=[year], force_refresh=force_refresh)
            df_rosters = load_rosters(years=[year], force_refresh=force_refresh)
            df_year = derive_weekly_from_pbp(df_pbp, year, df_rosters)

        _write_cache(df_year, path, WEEKLY_REQUIRED_COLS)
        frames.append(df_year)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_ngs_data(
    stat_type: str,
    years: list[int] | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Load NGS data for a stat type with per-season Parquet caching."""
    years = years or config.SEASONS
    source = f"ngs_{stat_type}"
    frames: list[pd.DataFrame] = []

    for year in years:
        path = get_cache_path(source, year)
        if not force_refresh:
            cached = _read_cache_if_valid(path, ("season",), min_rows=1)
            if cached is not None:
                logger.info("Loading cached %s %s", source, year)
                frames.append(cached)
                continue

        logger.info("Fetching %s %s from nfl_data_py", source, year)
        import nfl_data_py as nfl

        df_all = nfl.import_ngs_data(stat_type=stat_type, years=[year])
        df_year = df_all[df_all["season"] == year].copy()
        if "week" in df_year.columns:
            df_year = df_year[df_year["week"] >= 1]
        _write_cache(df_year, path, ("season",))
        frames.append(df_year)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_rosters(years: list[int] | None = None, force_refresh: bool = False) -> pd.DataFrame:
    """Load seasonal rosters with Parquet caching."""
    years = years or [config.ANALYSIS_SEASON, config.ROSTER_SEASON_FOR_OUTLOOK]
    years = list(dict.fromkeys(years))
    frames: list[pd.DataFrame] = []

    for year in years:
        path = get_cache_path("rosters", year)
        if not force_refresh:
            cached = _read_cache_if_valid(path, min_rows=10)
            if cached is not None:
                logger.info("Loading cached rosters %s", year)
                frames.append(cached)
                continue

        logger.info("Fetching rosters %s from nfl_data_py", year)
        import nfl_data_py as nfl

        df_year = nfl.import_seasonal_rosters(years=[year])
        _write_cache(df_year, path, min_rows=10)
        frames.append(df_year)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_players(force_refresh: bool = False) -> pd.DataFrame:
    """Load nflverse player master data (includes headshot URLs)."""
    path = get_static_cache_path("players")
    required = ("gsis_id", "headshot")
    if not force_refresh:
        cached = _read_cache_if_valid(path, required, min_rows=100)
        if cached is not None:
            logger.info("Loading cached players master")
            return cached

    logger.info("Fetching players master from nfl_data_py")
    import nfl_data_py as nfl

    df = nfl.import_players()
    _write_cache(df, path, required, min_rows=100)
    return df


def load_all_data(force_refresh: bool = False) -> dict[str, pd.DataFrame]:
    """Load all raw data sources into a dict of DataFrames."""
    return {
        "pbp": load_pbp_data(force_refresh=force_refresh),
        "weekly": load_weekly_data(force_refresh=force_refresh),
        "ngs_passing": load_ngs_data("passing", force_refresh=force_refresh),
        "ngs_receiving": load_ngs_data("receiving", force_refresh=force_refresh),
        "ngs_rushing": load_ngs_data("rushing", force_refresh=force_refresh),
        "rosters": load_rosters(years=config.SEASONS, force_refresh=force_refresh),
        "players": load_players(force_refresh=force_refresh),
    }


def load_metrics_computed() -> pd.DataFrame | None:
    """Load pre-computed metrics from cache if valid."""
    path = config.DATA_DIR / "metrics_computed.parquet"
    if not path.exists() or not is_cache_valid(path):
        return None
    df = pd.read_parquet(path)
    if df.empty:
        return None
    # Ignore stale scaffold cache (placeholder NaN metrics)
    if "primary_value" not in df.columns or not df["primary_value"].notna().any():
        return None
    # Rebuild if cache predates volume stats on leaderboard
    if "passing_yards" not in df.columns:
        return None
    if "scoring_version" not in df.columns:
        return None
    if df["scoring_version"].iloc[0] != config.METRICS_SCORING_VERSION:
        return None
    # Rebuild if QB interceptions were cached as all zeros (stale PBP without INT column)
    qb = df[
        (df.get("position") == "QB")
        & (df.get("season") == config.ANALYSIS_SEASON)
    ]
    if not qb.empty and "interceptions" in qb.columns:
        att = qb.get("pass_attempts", qb.get("attempts", pd.Series(dtype=float))).fillna(0)
        if qb["interceptions"].fillna(0).max() == 0 and att.max() > 0:
            return None
    return df


def refresh_metrics_cache(df_metrics: pd.DataFrame) -> Path:
    """Write computed metrics to Parquet cache."""
    path = config.DATA_DIR / "metrics_computed.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df_metrics.to_parquet(path, index=False)
    return path
